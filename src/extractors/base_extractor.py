from __future__ import annotations
"""Abstract base class for entity extractors with common extraction logic."""

import time
from abc import ABC, abstractmethod
from typing import Any, Generic, List, Optional, Type, TypeVar

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    RepositoryError,
)
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import (
    Attachment,
    Client,
    Expense,
    Invoice,
    Job,
    Note,
    ProductService,
    Property,
    Quote,
    Request,
    TaxRate,
    TimeSheetEntry,
    User,
    Visit,
)
from ..repositories import Repository
from .attachment_downloader import AttachmentDownloader

# Type variable for entity types
T = TypeVar(
    "T",
    Attachment,
    Client,
    Expense,
    Invoice,
    Job,
    Note,
    ProductService,
    Property,
    Quote,
    Request,
    TaxRate,
    TimeSheetEntry,
    User,
    Visit,
)

# Type alias for related entities dictionary
# Maps entity type names to lists of related entities (e.g., {"notes": [Note, Note, ...]})
# Using Note union for extensibility as more related entity types are added
RelatedEntities = dict[str, List[Note]]


class BaseExtractor(ABC, Generic[T]):
    """
    Abstract base class for entity extractors with common extraction logic.

    Implements common patterns for:
    - Cursor-based pagination
    - Error handling and recovery
    - Progress tracking and logging
    - Batch processing
    - Extraction state management
    - Entity existence checking and skip logic

    Subclasses must implement entity-specific methods for API calls and mapping.
    """

    # Entity type to table name mapping for entity existence checking
    _ENTITY_TABLE_MAP = {
        Attachment: "attachments",
        Client: "clients",
        Expense: "expenses",
        Invoice: "invoices",
        Job: "jobs",
        Note: "notes",
        ProductService: "products_services",
        Property: "properties",
        Quote: "quotes",
        Request: "requests",
        TaxRate: "tax_rates",
        TimeSheetEntry: "timesheet_entries",
        User: "users",
        Visit: "visits",
    }

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        entity_type: Type[T],
        entity_name: str,
        config_manager: Optional[ConfigManagerImpl] = None,
        skip_existing_entities: bool = False,
    ) -> None:
        """Initialize BaseExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            entity_type: Type of entity being extracted (for type safety)
            entity_name: Human-readable name of entity for logging
            config_manager: Optional ConfigManager for delays and pagination settings
            skip_existing_entities: Whether to skip entities that already exist in database
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._entity_type = entity_type
        self._entity_name = entity_name
        self._config_manager = config_manager or ConfigManagerImpl()
        self._skip_existing_entities = skip_existing_entities

        # Get table name for entity existence checking
        self._table_name = self._ENTITY_TABLE_MAP.get(entity_type)
        if not self._table_name:
            raise ConfigurationError(
                f"No table mapping found for entity type: {entity_type}"
            )

        # Extraction state tracking
        self._last_extraction_summary = {
            "total_entities": 0,
            "entities_skipped": 0,
            "total_pages": 0,
            "extraction_duration": 0.0,
            "average_page_size": 0.0,
            "entities_per_second": 0.0,
            "last_cursor": None,
            "extraction_status": "pending",
            "error_count": 0,
        }

        # Attachment downloader and metrics tracking
        # Used by extractors that handle nested attachments (clients, invoices, quotes, jobs, requests)
        self._attachment_downloader = AttachmentDownloader(logger=logger)
        self._attachments_processed = 0
        self._files_downloaded = 0
        self._bytes_downloaded = 0
        self._download_failures = 0
        self._attachment_mapping_failures = 0

    def _should_skip_entity(self, entity_id: str) -> bool:
        """Check if an entity should be skipped based on existence in database.

        Uses Repository.entity_exists() for fast primary key lookups when
        skip_existing_entities is enabled.

        Args:
            entity_id: ID of the entity to check

        Returns:
            True if entity should be skipped, False otherwise
        """
        if not self._skip_existing_entities or not self._table_name:
            return False

        try:
            return self._repository.entity_exists(self._table_name, entity_id)
        except RepositoryError as e:
            self._logger.debug(f"Failed to check entity existence for {entity_id}: {e}")
            # Err on the side of processing if check fails
            return False

    def _filter_new_entities(self, entities: List[T]) -> tuple[List[T], int]:
        """Filter out existing entities if skip logic is enabled.

        Args:
            entities: List of entities to filter

        Returns:
            Tuple of (filtered_entities, skipped_count)
        """
        if not self._skip_existing_entities:
            return entities, 0

        new_entities = []
        skipped_count = 0

        for entity in entities:
            if hasattr(entity, "id") and self._should_skip_entity(entity.id):
                skipped_count += 1
            else:
                new_entities.append(entity)

        return new_entities, skipped_count

    @abstractmethod
    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of entities from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        ...

    @abstractmethod
    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        ...

    @abstractmethod
    def _map_entity(self, node: dict[str, Any]) -> T:
        """Map a single entity node to domain model.

        Args:
            node: Entity data from API

        Returns:
            Mapped domain model instance
        """
        ...

    @abstractmethod
    def _save_entities(self, entities: List[T]) -> None:
        """Save entities to repository.

        Args:
            entities: List of entities to save
        """
        ...

    def _extract_related_entities(
        self, node: dict[str, Any], primary_entity: T
    ) -> RelatedEntities:
        """Extract related entities (like notes) from a node.

        Override in subclasses that have related entities.

        Args:
            node: Entity data from API
            primary_entity: The primary entity that was mapped

        Returns:
            Dictionary mapping entity type names to lists of related entities
        """
        return {}

    def _save_related_entities(self, related_entities: RelatedEntities) -> None:
        """Save related entities to repository.

        Override in subclasses that have related entities.

        Args:
            related_entities: Dictionary mapping entity type names to lists of related entities
        """
        pass

    def get_resume_cursor(self, entity_type_name: str) -> Optional[str]:
        """Get the last saved cursor position for resuming extraction.

        Args:
            entity_type_name: Name of the entity type (e.g., 'clients', 'quotes')

        Returns:
            Last saved cursor position, or None if no saved state exists
        """
        try:
            migration_state = self._repository.get_migration_state(entity_type_name)
            if migration_state:
                self._logger.debug(
                    f"Found saved cursor for {entity_type_name}: {migration_state.last_cursor}"
                )
                return migration_state.last_cursor
            return None
        except RepositoryError as e:
            self._logger.debug(
                f"Failed to get resume cursor for {entity_type_name}: {e}"
            )
            return None

    def _save_cursor_progress(
        self, entity_type_name: str, cursor: Optional[str]
    ) -> None:
        """Save cursor position for resumption.

        Args:
            entity_type_name: Name of the entity type (e.g., 'clients', 'quotes')
            cursor: Current cursor position to save
        """
        try:
            self._repository.save_migration_state(entity_type_name, cursor)
            self._logger.debug(
                f"Saved cursor progress for {entity_type_name}: {cursor}"
            )
        except RepositoryError as e:
            self._logger.debug(
                f"Failed to save cursor progress for {entity_type_name}: {e}"
            )

    def _cleanup_cursor_state(self, entity_type_name: str) -> None:
        """Clean up cursor state after successful completion.

        Args:
            entity_type_name: Name of the entity type (e.g., 'clients', 'quotes')
        """
        try:
            self._repository.save_migration_state(entity_type_name, None)
            self._logger.debug(f"Cleaned up cursor state for {entity_type_name}")
        except RepositoryError as e:
            self._logger.debug(
                f"Failed to cleanup cursor state for {entity_type_name}: {e}"
            )

    def extract(
        self,
        cursor: Optional[str] = None,
        page_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Extract entities from Jobber GraphQL API with cursor-based pagination.

        Performs complete extraction workflow including:
        - GraphQL API calls with cursor pagination
        - Data transformation via EntityMapper
        - Entity existence checking and skip logic (if enabled)
        - Cursor persistence for resumption support
        - Batch persistence via Repository
        - Progress logging and error handling

        Args:
            cursor: Optional pagination cursor for continuing extraction
            page_limit: Optional limit on number of pages to process (for testing)

        Returns:
            Dictionary containing extraction results with keys:
            - 'entities_processed': int - Total number of entities extracted
            - 'entities_skipped': int - Total number of entities skipped
            - 'pages_processed': int - Number of API pages processed
            - 'has_next_page': bool - Whether more pages are available
            - 'end_cursor': Optional[str] - Final cursor for continuation
            - 'extraction_time': float - Total extraction time in seconds

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
            RepositoryError: If database operations fail
        """
        start_time = time.time()
        entities_processed = 0
        entities_skipped = 0
        pages_processed = 0
        current_cursor = cursor
        error_count = 0
        page_info = {}
        entity_type_name = (
            self._entity_name + "s"
        )  # Convert to plural for state tracking

        # Check for resume cursor if no cursor provided and skip mode is enabled
        if cursor is None and self._skip_existing_entities:
            resume_cursor = self.get_resume_cursor(entity_type_name)
            if resume_cursor:
                current_cursor = resume_cursor
                self._logger.info(
                    f"🔄 Resuming {self._entity_name} extraction from saved cursor: {resume_cursor}"
                )

        skip_status = " (skip mode enabled)" if self._skip_existing_entities else ""
        self._logger.info(
            f"Starting {self._entity_name} extraction from cursor: {current_cursor}{skip_status}"
        )

        try:
            while True:
                # Check page limit for testing
                if page_limit is not None and pages_processed >= page_limit:
                    self._logger.debug(f"Reached page limit: {page_limit}")
                    break

                # Fetch page from API
                self._logger.debug(
                    f"Fetching {self._entity_name} page {pages_processed + 1}"
                )
                response = self._fetch_page(current_cursor)

                # Extract edges and page info
                edges, page_info = self._extract_edges_and_page_info(response)

                if not edges:
                    self._logger.debug(f"No more {self._entity_name} data to process")
                    break

                # Map nodes to domain models
                entities = []
                all_related_entities = {}

                for edge in edges:
                    node = edge.get("node", {})
                    try:
                        entity = self._map_entity(node)
                        entities.append(entity)

                        # Extract related entities if any
                        related = self._extract_related_entities(node, entity)
                        for entity_type, related_list in related.items():
                            if entity_type not in all_related_entities:
                                all_related_entities[entity_type] = []
                            all_related_entities[entity_type].extend(related_list)

                    except MappingError as e:
                        error_msg = (
                            f"Failed to map {self._entity_name} "
                            f"{node.get('id', 'unknown')}: {e}"
                        )
                        self._logger.error(error_msg)
                        error_count += 1

                # Filter entities and apply skip logic
                if entities:
                    entities_to_save, page_skipped = self._filter_new_entities(entities)
                    entities_skipped += page_skipped

                    # Batch save entities to database
                    if entities_to_save:
                        self._save_entities(entities_to_save)
                        entities_processed += len(entities_to_save)

                    # Log with processed vs skipped counts
                    if self._skip_existing_entities and page_skipped > 0:
                        self._logger.info(
                            f"Processed {len(entities_to_save)} {self._entity_name}s, "
                            f"skipped {page_skipped} (total: {entities_processed} processed, "
                            f"{entities_skipped} skipped)"
                        )
                    else:
                        self._logger.info(
                            f"Processed {len(entities_to_save)} {self._entity_name}s "
                            f"(total: {entities_processed})"
                        )

                # Save related entities if any
                if all_related_entities:
                    self._save_related_entities(all_related_entities)
                    for entity_type, related_list in all_related_entities.items():
                        self._logger.info(
                            f"Saved {len(related_list)} {entity_type} "
                            f"for {self._entity_name}s"
                        )

                pages_processed += 1

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                end_cursor = page_info.get("endCursor")

                # Save cursor progress after successful page processing
                if self._skip_existing_entities and end_cursor:
                    self._save_cursor_progress(entity_type_name, end_cursor)

                if not has_next_page:
                    self._logger.debug(f"Reached last page of {self._entity_name}s")
                    break

                # Update cursor for next iteration
                current_cursor = end_cursor

                # Add configurable delay between pages to prevent API overload
                page_delay = self._config_manager.get_delay_config("page_delay")
                time.sleep(page_delay)
                self._logger.debug(
                    f"Added {page_delay}s delay before page {pages_processed + 1}"
                )

            extraction_time = time.time() - start_time

            # Clean up cursor state after successful completion
            if self._skip_existing_entities:
                self._cleanup_cursor_state(entity_type_name)
                self._logger.debug(
                    f"✅ Completed {self._entity_name} extraction - cursor state cleaned up"
                )

            # Update extraction summary
            self._update_extraction_summary(
                entities_processed,
                entities_skipped,
                pages_processed,
                extraction_time,
                current_cursor,
                "completed",
                error_count,
            )

            result = {
                "entities_processed": entities_processed,
                "entities_skipped": entities_skipped,
                "pages_processed": pages_processed,
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": current_cursor,
                "extraction_time": extraction_time,
            }

            summary_msg = f"Completed {self._entity_name} extraction: {entities_processed} entities"
            if self._skip_existing_entities and entities_skipped > 0:
                summary_msg += f", {entities_skipped} skipped"
            summary_msg += f" in {extraction_time:.2f}s"
            self._logger.info(summary_msg)

            return result

        except (JobberApiError, ConfigurationError, RepositoryError) as e:
            # Update summary with error status
            extraction_time = time.time() - start_time
            self._update_extraction_summary(
                entities_processed,
                entities_skipped,
                pages_processed,
                extraction_time,
                current_cursor,
                "failed",
                error_count,
            )
            self._logger.error(f"{self._entity_name} extraction failed: {e}")
            raise

    def extract_all(self) -> List[T]:
        """Extract all entities with automatic pagination until completion.

        Continuously calls extract() with cursor pagination until all available
        entities are processed. Provides complete dataset extraction with
        comprehensive progress logging and error recovery.

        Returns:
            List of all extracted entity objects

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
            RepositoryError: If database operations fail
        """
        all_entities = []
        cursor = None
        total_pages = 0

        self._logger.info(f"Starting complete {self._entity_name} extraction")

        while True:
            result = self.extract(cursor=cursor)

            # Get entities from this batch
            entities = self._get_entities_from_last_batch()
            all_entities.extend(entities)

            total_pages += result["pages_processed"]

            if not result["has_next_page"]:
                break

            cursor = result["end_cursor"]
            self._logger.info(
                f"Continuing extraction from cursor: {cursor} "
                f"(total pages: {total_pages})"
            )

        self._logger.info(
            f"Completed full extraction: {len(all_entities)} {self._entity_name}s "
            f"from {total_pages} pages"
        )

        return all_entities

    @abstractmethod
    def _get_entities_from_last_batch(self) -> List[T]:
        """Get entities from the last extraction batch.

        Used by extract_all to accumulate entities.

        Returns:
            List of entities from last batch
        """
        ...

    @abstractmethod
    def get_entity_count(self) -> int:
        """Get total count of entities available for extraction.

        Returns:
            Total number of entities available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        ...

    def validate_dependencies(self) -> bool:
        """Validate that all required dependencies are properly configured.

        Returns:
            True if all dependencies are valid and ready for extraction

        Raises:
            ConfigurationError: If any required dependency is missing or invalid
        """
        if not self._jobber_client:
            raise ConfigurationError("JobberClient dependency is missing")
        if not self._entity_mapper:
            raise ConfigurationError("EntityMapper dependency is missing")
        if not self._repository:
            raise ConfigurationError("Repository dependency is missing")
        if not self._logger:
            raise ConfigurationError("Logger dependency is missing")

        self._logger.debug(f"All dependencies validated for {self._entity_name}")
        return True

    def get_extraction_summary(self) -> dict[str, Any]:
        """Get summary statistics of the last extraction operation.

        Returns:
            Dictionary containing extraction summary including skip counts
        """
        return self._last_extraction_summary.copy()

    def get_download_metrics(self) -> dict[str, int]:
        """Get attachment download metrics.

        Returns instance variable values for extractors that download attachments.
        Extractors that don't handle attachments will return zeros (default values).

        Returns:
            Dictionary with download statistics:
            - attachments_processed: Total number of attachment records processed
            - files_downloaded: Number of files successfully downloaded
            - bytes_downloaded: Total bytes downloaded
            - download_failures: Number of failed downloads
            - attachment_mapping_failures: Number of attachment mapping errors
        """
        return {
            "attachments_processed": self._attachments_processed,
            "files_downloaded": self._files_downloaded,
            "bytes_downloaded": self._bytes_downloaded,
            "download_failures": self._download_failures,
            "attachment_mapping_failures": self._attachment_mapping_failures,
        }

    def _update_extraction_summary(
        self,
        entities_processed: int,
        entities_skipped: int,
        pages_processed: int,
        extraction_time: float,
        last_cursor: Optional[str],
        status: str,
        error_count: int,
    ) -> None:
        """Update internal extraction summary statistics.

        Args:
            entities_processed: Total entities processed
            entities_skipped: Total entities skipped
            pages_processed: Total pages processed
            extraction_time: Total extraction time in seconds
            last_cursor: Final pagination cursor
            status: Extraction status ('completed', 'partial', 'failed')
            error_count: Number of errors encountered
        """
        avg_page_size = (
            entities_processed / pages_processed if pages_processed > 0 else 0
        )
        entities_per_second = (
            entities_processed / extraction_time if extraction_time > 0 else 0
        )

        self._last_extraction_summary = {
            "total_entities": entities_processed,
            "entities_skipped": entities_skipped,
            "total_pages": pages_processed,
            "extraction_duration": extraction_time,
            "average_page_size": avg_page_size,
            "entities_per_second": entities_per_second,
            "last_cursor": last_cursor,
            "extraction_status": status,
            "error_count": error_count,
        }

    def _extract_notes_and_attachments(
        self, node: dict[str, Any], primary_entity: T
    ) -> dict[str, Any]:
        """Extract nested notes and attachments from entity query response.

        Common implementation for extracting notes and attachments that are
        fetched inline with parent entities (clients, invoices, quotes, jobs, requests).
        Uses optimized pagination (configurable via pagination.nested_notes) to reduce API costs.

        Args:
            node: Entity data from API response
            primary_entity: The parent entity that was mapped

        Returns:
            Dictionary with 'notes' and 'attachments' lists (if present)
        """
        related = {}

        # Extract notes if present
        notes_data = node.get("notes", {})
        entity_notes = notes_data.get("edges", [])
        notes_page_info = notes_data.get("pageInfo", {})

        if entity_notes:
            notes = []
            for note_edge in entity_notes:
                note_node = note_edge.get("node", {})
                # Skip empty nodes or nodes missing ID (can happen with union fragments)
                if not note_node or not note_node.get("id"):
                    self._logger.debug(
                        f"Skipping note with missing data for {self._entity_name} {primary_entity.id}"
                    )
                    continue

                try:
                    # Add parent entity relationship to note data
                    # Uses entity_name to create dynamic relationship field (e.g., "client", "invoice")
                    note_data = {
                        **note_node,
                        self._entity_name: {"id": primary_entity.id},
                    }
                    note = self._entity_mapper.map_note(note_data)
                    notes.append(note)
                except MappingError as e:
                    self._logger.debug(
                        f"Failed to map note for {self._entity_name} {primary_entity.id}: {e}"
                    )
            if notes:
                related["notes"] = notes

                # Warn if there are more notes that weren't fetched
                if notes_page_info.get("hasNextPage", False):
                    self._logger.warning(
                        f"{self._entity_name.capitalize()} {primary_entity.id} has additional notes beyond the "
                        f"{len(notes)} fetched. Increase pagination.nested_notes in "
                        f"settings.yaml to fetch more notes inline."
                    )

        # Extract attachments if present
        attachments_data = node.get("noteAttachments", {})
        entity_attachments = attachments_data.get("edges", [])
        attachments_page_info = attachments_data.get("pageInfo", {})

        if entity_attachments:
            attachments = []
            for attachment_edge in entity_attachments:
                attachment_node = attachment_edge.get("node", {})
                if attachment_node:
                    try:
                        attachment = self._entity_mapper.map_attachment(attachment_node)
                        attachments.append(attachment)
                    except MappingError as e:
                        self._attachment_mapping_failures += 1
                        self._logger.warning(
                            f"Failed to map attachment for {self._entity_name} {primary_entity.id}: {e}"
                        )
            if attachments:
                related["attachments"] = attachments

                # Warn if there are more attachments that weren't fetched
                if attachments_page_info.get("hasNextPage", False):
                    self._logger.warning(
                        f"{self._entity_name.capitalize()} {primary_entity.id} has additional attachments beyond the "
                        f"{len(attachments)} fetched. Increase pagination.nested_notes in "
                        f"settings.yaml to fetch more attachments inline."
                    )

        return related

    def _save_notes_and_attachments(self, related_entities: dict[str, Any]) -> None:
        """Save notes and attachments to repository.

        Common implementation for saving notes and downloading/saving attachments.
        Downloads attachment files and updates metadata with local file paths before saving,
        unless auto_download is disabled in configuration.

        Args:
            related_entities: Dictionary with 'notes' and 'attachments' lists
        """
        # Save notes if present
        notes = related_entities.get("notes", [])
        if notes:
            self._repository.save_notes(notes)

        # Download and save attachments if present
        attachments = related_entities.get("attachments", [])
        if attachments:
            # Track total attachments processed
            self._attachments_processed += len(attachments)

            # Check if automatic downloading is enabled
            attachment_config = self._config_manager.get_attachment_config()
            auto_download = attachment_config.get("auto_download", True)

            if not auto_download:
                # Metadata-only mode: save attachments without downloading files
                self._logger.debug(
                    f"Skipping download of {len(attachments)} attachment(s) (auto_download=false)"
                )
                self._repository.save_attachments(attachments)
                return

            # Download files and update attachment metadata
            attachments_with_files = []
            for attachment in attachments:
                download_result = self._attachment_downloader.download_attachment(attachment)

                if download_result["success"]:
                    # Update attachment with downloaded file path
                    updated_attachment = Attachment(
                        id=attachment.id,
                        note_id=attachment.note_id,
                        file_name=attachment.file_name,
                        content_type=attachment.content_type,
                        original_url=attachment.original_url,
                        local_file_path=download_result["local_file_path"],
                        file_size=attachment.file_size,
                        created_at=attachment.created_at,
                    )
                    attachments_with_files.append(updated_attachment)

                    # Track download metrics
                    self._files_downloaded += 1
                    self._bytes_downloaded += download_result["bytes_downloaded"]
                else:
                    # Download failed, save metadata only with original local_file_path
                    self._logger.warning(
                        f"Failed to download attachment {attachment.id}: "
                        f"{download_result['error_message']}"
                    )
                    attachments_with_files.append(attachment)
                    self._download_failures += 1

            # Save all attachments with updated file paths
            self._repository.save_attachments(attachments_with_files)
