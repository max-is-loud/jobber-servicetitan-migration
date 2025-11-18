"""NotesExtractor for extracting Note entities from Jobber GraphQL API."""

import time
from typing import Any, List, Optional

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Note
from ..repositories import Repository
from .base_extractor import BaseExtractor


class NotesExtractor(BaseExtractor[Note]):
    """
    Extractor for Note entities implementing BaseExtractor.

    Provides modular OO extraction for Note entities with polymorphic
    relationships to various parent entities (clients, jobs, quotes, etc.).
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        config_manager: Optional[ConfigManagerImpl] = None,
        skip_existing_entities: bool = False,
    ) -> None:
        """Initialize NotesExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            config_manager: Optional ConfigManager for delays and pagination settings
            skip_existing_entities: Whether to skip entities that already exist in database
        """
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=Note,
            entity_name="note",
            config_manager=config_manager,
            skip_existing_entities=skip_existing_entities,
        )
        self._last_batch_entities: List[Note] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of notes from the Jobber API.

        Note: This method is not used in production. Notes are fetched using the
        deferred loading pattern via extract_deferred_notes() instead.
        """
        raise NotImplementedError(
            "Bulk note fetching is not supported by Jobber's API. "
            "Use extract_deferred_notes() for note extraction."
        )

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response."""
        notes_data = response.get("data", {}).get("notes", {})
        edges = notes_data.get("edges", [])
        page_info = notes_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Note:
        """Map a single note node to domain model."""
        return self._entity_mapper.map_note(node)

    def _save_entities(self, entities: List[Note]) -> None:
        """Save notes to repository."""
        self._repository.save_notes(entities)
        self._last_batch_entities = entities

    def _get_entities_from_last_batch(self) -> List[Note]:
        """Get notes from the last extraction batch."""
        return self._last_batch_entities

    def extract_deferred_notes(self, note_references: List[dict[str, str]]) -> dict[str, int]:
        """
        Process notes from collected note references (deferred processing).

        This method processes notes that were collected as ID references during
        parent entity processing, avoiding the nested query complexity that
        causes GraphQL throttling. Enhanced with skip functionality to avoid
        unnecessary API calls for already-processed notes.

        Args:
            note_references: List of dicts with note_id, entity_type, entity_id

        Returns:
            Dictionary with processed and skipped counts:
            - 'processed': Number of notes successfully processed
            - 'skipped': Number of notes skipped (already exist)

        Raises:
            JobberApiError: If API communication fails
            RepositoryError: If database operations fail
        """
        if not note_references:
            self._logger.info("No note references to process")
            return {"processed": 0, "skipped": 0}

        processed_count = 0
        skipped_count = 0
        errors = []
        start_time = time.time()

        skip_status = " (skip mode enabled)" if self._skip_existing_entities else ""
        self._logger.info(f"Starting deferred processing of {len(note_references)} note references{skip_status}")

        self._logger.info("Entering note processing loop...")
        for i, ref in enumerate(note_references):
            if i == 0:
                self._logger.info(f"Processing first note reference: {ref}")
            if i % 1000 == 0 and i > 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                self._logger.info(f"Reached note reference {i}/{len(note_references)}, rate: {rate:.1f} refs/sec")
            note_id = ref.get("note_id")
            entity_type = ref.get("entity_type")
            entity_id = ref.get("entity_id")

            if not all([note_id, entity_type, entity_id]):
                self._logger.debug(f"Skipping invalid note reference: {ref}")
                continue

            try:
                # Check if note already exists in database (skip logic)
                if self._skip_existing_entities and note_id:
                    check_start = time.time()
                    should_skip = self._should_skip_entity(note_id)
                    check_elapsed = time.time() - check_start

                    if should_skip:
                        skipped_count += 1
                        if check_elapsed > 0.1:  # Log slow checks (>100ms)
                            self._logger.debug(f"Slow skip check for note {note_id}: {check_elapsed:.3f}s")
                        else:
                            self._logger.debug(f"Skipping existing note {note_id}")

                        # Log progress periodically for skipped notes
                        if (processed_count + skipped_count) % 10 == 0:
                            self._logger.info(
                                f"Progress: {processed_count} processed, {skipped_count} skipped "
                                f"(total: {processed_count + skipped_count})"
                            )
                        continue

                # Fetch individual note by ID (note_id is guaranteed to be non-None here)  # noqa: E501
                note_response = self._jobber_client.fetch_note_by_id(note_id)  # type: ignore
                note_data = note_response.get("data", {}).get("node", {})

                if not note_data:
                    self._logger.debug(f"Note {note_id} not found or empty")
                    continue

                # Ensure parent relationship is set based on collected reference
                # This overrides whatever parent relationship comes from the API
                note_data[entity_type] = {"id": entity_id}

                # Map and save the note
                note = self._entity_mapper.map_note(note_data)
                self._repository.save_notes([note])
                processed_count += 1

                # Log progress periodically with processed vs skipped counts
                if (processed_count + skipped_count) % 10 == 0:
                    if self._skip_existing_entities and skipped_count > 0:
                        self._logger.info(
                            f"Progress: {processed_count} processed, {skipped_count} skipped "
                            f"(total: {processed_count + skipped_count})"
                        )
                    else:
                        self._logger.info(f"Progress: {processed_count} notes processed")

            except Exception as e:
                error_msg = f"Failed to process note {note_id}: {e}"
                self._logger.debug(error_msg)
                errors.append(error_msg)

        # Log final summary with processed vs skipped counts
        if errors:
            self._logger.info(f"Deferred note processing completed with {len(errors)} errors")
            for error in errors[:5]:  # Log first 5 errors
                self._logger.debug(error)
            if len(errors) > 5:
                self._logger.debug(f"... and {len(errors) - 5} more errors")

        elapsed_total = time.time() - start_time
        overall_rate = len(note_references) / elapsed_total if elapsed_total > 0 else 0

        if self._skip_existing_entities and skipped_count > 0:
            self._logger.info(
                f"✅ Deferred note processing completed: {processed_count} notes processed, "
                f"{skipped_count} skipped (total references: {len(note_references)}) "
                f"in {elapsed_total:.1f}s (rate: {overall_rate:.1f} refs/sec)"
            )
        else:
            self._logger.info(
                f"✅ Deferred note processing completed: {processed_count} notes processed "
                f"(total references: {len(note_references)}) "
                f"in {elapsed_total:.1f}s (rate: {overall_rate:.1f} refs/sec)"
            )

        return {"processed": processed_count, "skipped": skipped_count}

    def get_entity_count(self) -> int:
        """Get total count of notes available for extraction.

        Note: This method is not used in production. Note counts are determined
        by the number of note references collected during parent entity extraction.
        Jobber's API does not provide a bulk notes query, so count is unavailable.
        """
        self._logger.debug("Note count not available via bulk query - using deferred loading pattern")
        return 0  # Notes are counted via NoteReferenceCollector instead
