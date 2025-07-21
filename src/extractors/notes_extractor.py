"""NotesExtractor for extracting Note entities from Jobber GraphQL API."""

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
    ) -> None:
        """Initialize NotesExtractor with required dependencies."""
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=Note,
            entity_name="note",
            config_manager=config_manager,
        )
        self._last_batch_entities: List[Note] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of notes from the Jobber API."""
        # TODO: Implement fetch_notes in JobberClient when adding Notes support
        return self._jobber_client.fetch_notes(cursor)  # type: ignore

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
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

    def extract_deferred_notes(self, note_references: List[dict[str, str]]) -> int:
        """
        Process notes from collected note references (deferred processing).

        This method processes notes that were collected as ID references during
        parent entity processing, avoiding the nested query complexity that
        causes GraphQL throttling.

        Args:
            note_references: List of dicts with note_id, entity_type, entity_id

        Returns:
            Number of notes successfully processed

        Raises:
            JobberApiError: If API communication fails
            RepositoryError: If database operations fail
        """
        if not note_references:
            self._logger.info("No note references to process")
            return 0

        processed_count = 0
        errors = []

        self._logger.info(
            f"Starting deferred processing of {len(note_references)} note references"
        )

        for ref in note_references:
            note_id = ref.get("note_id")
            entity_type = ref.get("entity_type")
            entity_id = ref.get("entity_id")

            if not all([note_id, entity_type, entity_id]):
                self._logger.debug(f"Skipping invalid note reference: {ref}")
                continue

            try:
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

                if processed_count % 100 == 0:
                    self._logger.info(f"Processed {processed_count} notes")

            except Exception as e:
                error_msg = f"Failed to process note {note_id}: {e}"
                self._logger.debug(error_msg)
                errors.append(error_msg)

        # Log summary
        if errors:
            self._logger.info(
                f"Deferred note processing completed with {len(errors)} errors"
            )
            for error in errors[:5]:  # Log first 5 errors
                self._logger.debug(error)
            if len(errors) > 5:
                self._logger.debug(f"... and {len(errors) - 5} more errors")

        self._logger.info(
            f"Deferred note processing completed: {processed_count} notes processed"
        )
        return processed_count

    def get_entity_count(self) -> int:
        """Get total count of notes available for extraction."""
        self._logger.debug("Fetching total note count from API")

        # TODO: Implement fetch_notes in JobberClient when adding Notes support
        response = self._jobber_client.fetch_notes(cursor=None)  # type: ignore
        notes_data = response.get("data", {}).get("notes", {})

        # If API provides totalCount, use it
        total_count = notes_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total note count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = notes_data.get("edges", [])
        if not edges:
            return 0

        page_info = notes_data.get("pageInfo", {})
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        self._logger.info("Cannot determine exact note count without full pagination")
        return -1
