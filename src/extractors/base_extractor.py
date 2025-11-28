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
        **kwargs,
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
            **kwargs: Additional optional parameters:
                - queue_attachments: If True, queue attachments instead of downloading (default: False)
                - map_snapshot_id: Required if queue_attachments is True, for attachment queue foreign key
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._entity_type = entity_type
        self._entity_name = entity_name
        self._entity_name_plural = self._pluralize(entity_name)
        self._config_manager = config_manager or ConfigManagerImpl()
        self._skip_existing_entities = skip_existing_entities

        # Get table name for entity existence checking
        self._table_name = self._ENTITY_TABLE_MAP.get(entity_type)
        if not self._table_name:
            raise ConfigurationError(f"No table mapping found for entity type: {entity_type}")

        # Extraction state tracking
        self._last_extraction_summary = {
            "total_entities": 0,
            "total_available": None,
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
        self._attachment_downloader = AttachmentDownloader(repository=repository, logger=logger)
        self._attachments_processed = 0
        self._files_downloaded = 0
        self._bytes_downloaded = 0
        self._download_failures = 0
        self._attachment_mapping_failures = 0

        # Extract mode attachment queuing (Phase 3)
        self._queue_attachments = kwargs.get("queue_attachments", False)
        self._map_snapshot_id = kwargs.get("map_snapshot_id")
        self._attachments_queued = 0  # Track attachments added to queue

        # Data quality issue tracking - detailed failure information
        # Preserves specific IDs and errors for debugging and reporting
        self._data_quality_issues: list[dict[str, Any]] = []

        # Note reference collector for deferred note loading (Phase 2)
        # Optional - only provided for extractors that collect note IDs
        self._note_reference_collector = kwargs.get("note_reference_collector")

    @staticmethod
    def _pluralize(word: str) -> str:
        """Simple pluralization for entity names.

        Args:
            word: Singular word to pluralize

        Returns:
            Pluralized form of the word
        """
        # Handle special cases
        if word.endswith('y'):
            return word[:-1] + 'ies'  # property -> properties
        elif word.endswith(('s', 'x', 'z', 'ch', 'sh')):
            return word + 'es'
        else:
            return word + 's'

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
    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        ...

    @abstractmethod
    def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract entity data container from GraphQL response.

        This method extracts the top-level entity data object that contains
        totalCount, edges, and pageInfo.

        Args:
            response: Raw GraphQL API response

        Returns:
            Entity data dictionary (e.g., response['data']['visits'])

        Example:
            response = {"data": {"visits": {"totalCount": 150, "edges": [...]}}}
            return response.get("data", {}).get("visits", {})
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

    def _fetch_single(self, entity_id: str) -> Optional[dict[str, Any]]:
        """Fetch a single entity by ID using GraphQL node interface.

        This method uses the GraphQL node(id:) interface to fetch a single entity.
        Subclasses can override this if they need custom single-entity fetching logic.

        Args:
            entity_id: The ID of the entity to fetch

        Returns:
            Entity node data dictionary, or None if not found

        Raises:
            JobberApiError: If API communication fails
        """
        # Use the node(id:) interface for direct entity fetching
        # This is much more efficient than pagination-based search
        try:
            # Get nested notes limit from config
            nested_notes_limit = 10
            if self._config_manager:
                try:
                    nested_notes_limit = self._config_manager.get_pagination_config("nested_notes")
                except:
                    pass  # Use default if not configured

            # Fetch entity using node interface
            response = self._jobber_client.fetch_entity_by_id(
                entity_id=entity_id,
                nested_notes_limit=nested_notes_limit
            )

            # Extract the node from the response
            node = response.get("data", {}).get("node")
            return node

        except Exception as e:
            self._logger.debug(f"Failed to fetch single entity {entity_id}: {e}")
            return None

    def extract_single(self, entity_id: str) -> dict[str, Any]:
        """Extract a single entity by ID for queue-based extraction.

        Used in extract mode to fetch and process individual entities from the
        extract queue. Performs complete extraction for one entity including
        related entities (notes, attachments, etc.).

        Args:
            entity_id: The ID of the entity to extract

        Returns:
            Dictionary containing extraction results:
            - 'success': bool - Whether extraction succeeded
            - 'entity_id': str - The entity ID that was extracted
            - 'entity_found': bool - Whether the entity was found in API
            - 'error': Optional[str] - Error message if extraction failed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If entity mapping fails
            RepositoryError: If database operations fail
        """
        self._logger.debug(f"Extracting single {self._entity_name}: {entity_id}")

        try:
            # Fetch single entity
            node = self._fetch_single(entity_id)

            if not node:
                self._logger.warning(f"{self._entity_name} not found: {entity_id}")
                return {
                    "success": False,
                    "entity_id": entity_id,
                    "entity_found": False,
                    "error": f"Entity not found: {entity_id}",
                }

            # Map entity to domain model
            entity = self._map_entity(node)

            # Extract related entities
            related_entities = self._extract_related_entities(node, entity)

            # Save entity and related entities
            self._save_entities([entity])
            if related_entities:
                self._save_related_entities(related_entities)

            self._logger.success(f"Successfully extracted {self._entity_name}: {entity_id}")

            return {
                "success": True,
                "entity_id": entity_id,
                "entity_found": True,
                "error": None,
            }

        except MappingError as e:
            error_msg = f"Mapping error for {self._entity_name} {entity_id}: {e}"
            self._logger.error(error_msg)
            return {
                "success": False,
                "entity_id": entity_id,
                "entity_found": True,
                "error": error_msg,
            }
        except RepositoryError as e:
            error_msg = f"Repository error for {self._entity_name} {entity_id}: {e}"
            self._logger.error(error_msg)
            return {
                "success": False,
                "entity_id": entity_id,
                "entity_found": True,
                "error": error_msg,
            }
        except Exception as e:
            error_msg = f"Unexpected error extracting {self._entity_name} {entity_id}: {e}"
            self._logger.error(error_msg)
            return {
                "success": False,
                "entity_id": entity_id,
                "entity_found": False,
                "error": error_msg,
            }

    def _extract_related_entities(self, node: dict[str, Any], primary_entity: T) -> RelatedEntities:
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
                self._logger.debug(f"Found saved cursor for {entity_type_name}: {migration_state.last_cursor}")
                return migration_state.last_cursor
            return None
        except RepositoryError as e:
            self._logger.debug(f"Failed to get resume cursor for {entity_type_name}: {e}")
            return None

    def _save_cursor_progress(self, entity_type_name: str, cursor: Optional[str]) -> None:
        """Save cursor position for resumption.

        Args:
            entity_type_name: Name of the entity type (e.g., 'clients', 'quotes')
            cursor: Current cursor position to save
        """
        try:
            self._repository.save_migration_state(entity_type_name, cursor)
            self._logger.debug(f"Saved cursor progress for {entity_type_name}: {cursor}")
        except RepositoryError as e:
            self._logger.debug(f"Failed to save cursor progress for {entity_type_name}: {e}")

    def _cleanup_cursor_state(self, entity_type_name: str) -> None:
        """Clean up cursor state after successful completion.

        Args:
            entity_type_name: Name of the entity type (e.g., 'clients', 'quotes')
        """
        try:
            self._repository.save_migration_state(entity_type_name, None)
            self._logger.debug(f"Cleaned up cursor state for {entity_type_name}")
        except RepositoryError as e:
            self._logger.debug(f"Failed to cleanup cursor state for {entity_type_name}: {e}")

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
        entity_type_name = self._entity_name + "s"  # Convert to plural for state tracking

        # Check for resume cursor if no cursor provided and skip mode is enabled
        if cursor is None and self._skip_existing_entities:
            resume_cursor = self.get_resume_cursor(entity_type_name)
            if resume_cursor:
                current_cursor = resume_cursor
                self._logger.info(f"🔄 Resuming {self._entity_name} extraction from saved cursor: {resume_cursor}")

        skip_status = " (skip mode enabled)" if self._skip_existing_entities else ""
        self._logger.info(f"Starting {self._entity_name} extraction from cursor: {current_cursor}{skip_status}")

        try:
            while True:
                # Check page limit for testing
                if page_limit is not None and pages_processed >= page_limit:
                    self._logger.debug(f"Reached page limit: {page_limit}")
                    break

                # Fetch page from API
                self._logger.debug(f"Fetching {self._entity_name} page {pages_processed + 1}")
                response = self._fetch_page(current_cursor)

                # Extract edges and page info
                edges, page_info = self._extract_edges_and_page_info(response)

                # Extract totalCount on first page
                if not hasattr(self, '_total_count'):
                    try:
                        entity_data = self._extract_entity_data(response)
                        total_count = entity_data.get("totalCount")
                        if total_count is not None:
                            self._total_count = int(total_count)
                            self._logger.debug(
                                f"Total {self._entity_name_plural} available: {self._total_count:,}"
                            )
                        else:
                            self._total_count = None
                            self._logger.debug("totalCount not available from API")
                    except Exception as e:
                        self._logger.debug(f"Failed to extract totalCount: {e}")
                        self._total_count = None

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
                        error_msg = f"Failed to map {self._entity_name} " f"{node.get('id', 'unknown')}: {e}"
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

                    # Log with processed vs skipped counts and percentage if available
                    if hasattr(self, '_total_count') and self._total_count:
                        percentage = (entities_processed / self._total_count) * 100
                        if self._skip_existing_entities and page_skipped > 0:
                            self._logger.info(
                                f"Processed {len(entities_to_save)} {self._entity_name_plural}, "
                                f"skipped {page_skipped} ({entities_processed:,}/{self._total_count:,} - {percentage:.1f}%)"
                            )
                        else:
                            self._logger.info(
                                f"Processed {len(entities_to_save)} {self._entity_name_plural} "
                                f"({entities_processed:,}/{self._total_count:,} - {percentage:.1f}%)"
                            )
                    else:
                        if self._skip_existing_entities and page_skipped > 0:
                            self._logger.info(
                                f"Processed {len(entities_to_save)} {self._entity_name_plural}, "
                                f"skipped {page_skipped} (total: {entities_processed:,} processed, "
                                f"{entities_skipped:,} skipped)"
                            )
                        else:
                            self._logger.info(
                                f"Processed {len(entities_to_save)} {self._entity_name_plural} (total: {entities_processed:,})"
                            )

                # Save related entities if any
                if all_related_entities:
                    self._save_related_entities(all_related_entities)
                    for entity_type, related_list in all_related_entities.items():
                        self._logger.info(f"Saved {len(related_list)} {entity_type} " f"for {self._entity_name_plural}")

                pages_processed += 1

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                end_cursor = page_info.get("endCursor")

                # Save cursor progress after successful page processing
                if self._skip_existing_entities and end_cursor:
                    self._save_cursor_progress(entity_type_name, end_cursor)

                if not has_next_page:
                    self._logger.debug(f"Reached last page of {self._entity_name_plural}")
                    break

                # Update cursor for next iteration
                current_cursor = end_cursor

                # Add configurable delay between pages to prevent API overload
                page_delay = self._config_manager.get_delay_config("page_delay")
                time.sleep(page_delay)
                self._logger.debug(f"Added {page_delay}s delay before page {pages_processed + 1}")

            extraction_time = time.time() - start_time

            # Clean up cursor state after successful completion
            if self._skip_existing_entities:
                self._cleanup_cursor_state(entity_type_name)
                self._logger.debug(f"✅ Completed {self._entity_name} extraction - cursor state cleaned up")

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

            summary_msg = f"Completed {self._entity_name} extraction: {entities_processed:,} entities"

            # Add percentage if total count is available
            if hasattr(self, '_total_count') and self._total_count:
                percentage = (entities_processed / self._total_count) * 100
                summary_msg += f" ({percentage:.1f}% of {self._total_count:,})"

            if self._skip_existing_entities and entities_skipped > 0:
                summary_msg += f", {entities_skipped:,} skipped"
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

    def extract_all(self, resume: bool = False) -> List[T]:
        """Extract all entities with automatic pagination and resumable checkpoints.

        Continuously calls extract() with cursor pagination until all available
        entities are processed. Supports Phase 7's resumable extraction pattern
        where migrations can be interrupted and resumed without re-processing data.

        When resume=True, checks migration_state for existing progress and continues
        from the last checkpoint. After each page, saves progress checkpoint to enable
        resume on interruption. Marks extraction as completed when done.

        Args:
            resume: If True, resume from last checkpoint if available (default: False)

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
        total_fetched = 0

        # Check for existing progress if resume is enabled
        if resume:
            state = self._repository.get_migration_state(self._entity_name)
            if state and state.sync_status != "completed":
                cursor = state.last_cursor
                total_fetched = state.total_fetched
                self._logger.info(
                    f"Resuming {self._entity_name} extraction from cursor: {cursor}, "
                    f"already fetched: {total_fetched}"
                )

        # Mark extraction as in progress
        self._repository.save_migration_state(
            entity_type=self._entity_name,
            last_cursor=cursor,
            total_fetched=total_fetched,
            sync_status="in_progress",
        )

        # Get total count before extraction if available
        total_count = self.get_entity_count()
        if total_count is not None:
            self._logger.info(
                f"Starting {self._entity_name} extraction (resume={resume}): "
                f"{total_count:,} entities available"
            )
        else:
            self._logger.info(
                f"Starting {self._entity_name} extraction (resume={resume}): "
                f"total count unknown"
            )

        while True:
            result = self.extract(cursor=cursor)

            # Get entities from this batch
            entities = self._get_entities_from_last_batch()
            all_entities.extend(entities)

            total_pages += result["pages_processed"]
            total_fetched += len(entities)
            cursor = result["end_cursor"]

            # Checkpoint progress after each page (enables resume)
            self._repository.save_migration_state(
                entity_type=self._entity_name,
                last_cursor=cursor,
                total_fetched=total_fetched,
                sync_status="in_progress",
            )

            if not result["has_next_page"]:
                break

            self._logger.info(f"Continuing extraction from cursor: {cursor} " f"(total pages: {total_pages})")

        # Mark extraction as completed
        self._repository.save_migration_state(
            entity_type=self._entity_name,
            last_cursor=None,  # Clear cursor on completion
            total_fetched=total_fetched,
            sync_status="completed",
        )

        completion_msg = f"Completed full extraction: {len(all_entities):,} {self._entity_name_plural} from {total_pages} pages"

        # Add percentage if total count is available
        if hasattr(self, '_total_count') and self._total_count:
            percentage = (len(all_entities) / self._total_count) * 100
            completion_msg += f" ({percentage:.1f}% of {self._total_count:,})"

        self._logger.info(completion_msg)

        return all_entities

    @abstractmethod
    def _get_entities_from_last_batch(self) -> List[T]:
        """Get entities from the last extraction batch.

        Used by extract_all to accumulate entities.

        Returns:
            List of entities from last batch
        """
        ...

    def get_entity_count(self) -> Optional[int]:
        """Get total count of entities available for extraction.

        Returns totalCount from API if available, otherwise None.
        Should be called after first page is fetched.

        Returns:
            Total count if available, None if unknown

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        if hasattr(self, '_total_count'):
            return self._total_count

        # Fallback: Try to get from API
        try:
            response = self._fetch_page(cursor=None)
            entity_data = self._extract_entity_data(response)
            total_count = entity_data.get("totalCount")
            if total_count is not None:
                self._total_count = int(total_count)
                return self._total_count
        except Exception as e:
            self._logger.debug(f"Failed to get entity count: {e}")

        return None

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

    def get_data_quality_issues(self) -> dict[str, Any]:
        """Get detailed data quality issue information.

        Returns:
            Dictionary containing:
            - total_entities_with_issues: Count of entities that had data quality problems
            - total_notes_skipped: Aggregate count of skipped notes
            - total_attachments_orphaned: Aggregate count of orphaned attachments
            - issues: List of specific entity IDs with their issue counts and types
        """
        total_notes_skipped = sum(issue.get("notes_skipped", 0) for issue in self._data_quality_issues)
        total_attachments_orphaned = sum(issue.get("attachments_orphaned", 0) for issue in self._data_quality_issues)

        return {
            "total_entities_with_issues": len(self._data_quality_issues),
            "total_notes_skipped": total_notes_skipped,
            "total_attachments_orphaned": total_attachments_orphaned,
            "issues": self._data_quality_issues.copy(),
        }

    def _get_entity_display_identifier(self, entity: T) -> str:
        """Extract human-readable identifier for entity (for Jobber UI cross-reference).

        Args:
            entity: The entity object (Invoice, Job, Quote, Client, etc.)

        Returns:
            Human-readable identifier string (e.g., "INV-1234", "Job #5678", "John Smith")
        """
        try:
            # Invoice: number field (e.g., "INV-1234")
            if hasattr(entity, "number"):
                return f"Invoice #{entity.number}"

            # Job: job_number field (e.g., "J-5678")
            if hasattr(entity, "job_number"):
                return f"Job #{entity.job_number}"

            # Quote: quote_number field (e.g., "Q-9012")
            if hasattr(entity, "quote_number"):
                return f"Quote #{entity.quote_number}"

            # Client: first_name + last_name
            if hasattr(entity, "first_name") and hasattr(entity, "last_name"):
                name = f"{entity.first_name} {entity.last_name}".strip()
                return f"Client: {name}" if name else "Client: (unnamed)"

            # Request: request_number (if it exists)
            if hasattr(entity, "request_number"):
                return f"Request #{entity.request_number}"

            # Visit: visit_number (if it exists)
            if hasattr(entity, "visit_number"):
                return f"Visit #{entity.visit_number}"

            # Fallback: use entity type name
            return f"{self._entity_name.title()}"

        except Exception:
            # If anything fails, return entity type as fallback
            return f"{self._entity_name.title()}"

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
        avg_page_size = entities_processed / pages_processed if pages_processed > 0 else 0
        entities_per_second = entities_processed / extraction_time if extraction_time > 0 else 0

        self._last_extraction_summary = {
            "total_entities": entities_processed,
            "total_available": self._total_count if hasattr(self, '_total_count') else None,
            "entities_skipped": entities_skipped,
            "total_pages": pages_processed,
            "extraction_duration": extraction_time,
            "average_page_size": avg_page_size,
            "entities_per_second": entities_per_second,
            "last_cursor": last_cursor,
            "extraction_status": status,
            "error_count": error_count,
        }

    def _fetch_all_remaining_notes(self, entity_id: str, cursor: str | None) -> list[Any]:
        """
        Fetch all remaining pages of notes for an entity using cursor pagination.

        Args:
            entity_id: The entity's ID
            cursor: Starting cursor from pageInfo.endCursor

        Returns:
            List of mapped note entities
        """
        if not cursor or not self._jobber_client:
            return []

        all_notes = []
        current_cursor = cursor
        page_num = 2  # Starting from page 2 (first page already fetched)

        while current_cursor:
            try:
                response = self._jobber_client.fetch_additional_notes(
                    entity_id=entity_id,
                    entity_type=self._entity_name,
                    cursor=current_cursor,
                    page_size=100  # Fetch in larger batches for efficiency
                )

                edges = response.get("edges", [])
                page_info = response.get("pageInfo", {})

                # Map notes from this page
                for note_edge in edges:
                    note_node = note_edge.get("node", {})
                    if not note_node or not note_node.get("id"):
                        continue

                    try:
                        note_data = {
                            **note_node,
                            self._entity_name: {"id": entity_id},
                        }
                        note = self._entity_mapper.map_note(note_data)
                        all_notes.append(note)
                    except MappingError as e:
                        # Try lenient mapping to preserve orphaned notes
                        try:
                            orphaned_note = self._entity_mapper.map_note(note_node, lenient=True)
                            all_notes.append(orphaned_note)
                            self._logger.debug(f"Saved orphaned note with lenient mapping (pagination) for {self._entity_name} {entity_id}: {e}")
                        except Exception as lenient_error:
                            # Even lenient mapping failed
                            self._logger.debug(f"Failed to map note even with lenient mode (pagination) for {self._entity_name} {entity_id}: {lenient_error}")

                # Check if there are more pages
                if page_info.get("hasNextPage", False):
                    current_cursor = page_info.get("endCursor")
                    page_num += 1
                    self._logger.debug(
                        f"Fetching notes page {page_num} for {self._entity_name} {entity_id} "
                        f"({len(all_notes)} notes fetched so far)"
                    )
                else:
                    current_cursor = None

            except Exception as e:
                self._logger.warning(
                    f"Error fetching additional notes for {self._entity_name} {entity_id}: {e}. "
                    f"Returning {len(all_notes)} notes fetched so far."
                )
                break

        return all_notes

    def _fetch_all_remaining_attachments(self, entity_id: str, cursor: str | None) -> list[Any]:
        """
        Fetch all remaining pages of attachments for an entity using cursor pagination.

        Args:
            entity_id: The entity's ID
            cursor: Starting cursor from pageInfo.endCursor

        Returns:
            List of mapped attachment entities
        """
        if not cursor or not self._jobber_client:
            return []

        all_attachments = []
        current_cursor = cursor
        page_num = 2  # Starting from page 2 (first page already fetched)

        while current_cursor:
            try:
                response = self._jobber_client.fetch_additional_attachments(
                    entity_id=entity_id,
                    entity_type=self._entity_name,
                    cursor=current_cursor,
                    page_size=100  # Fetch in larger batches for efficiency
                )

                edges = response.get("edges", [])
                page_info = response.get("pageInfo", {})

                # Map attachments from this page
                for attachment_edge in edges:
                    attachment_node = attachment_edge.get("node", {})
                    if not attachment_node:
                        continue

                    try:
                        attachment = self._entity_mapper.map_attachment(attachment_node)
                        all_attachments.append(attachment)
                    except MappingError as e:
                        self._attachment_mapping_failures += 1
                        error_msg = str(e).lower()
                        # Try lenient mapping to preserve orphaned attachments
                        if "note id is required" in error_msg or "note id" in error_msg:
                            try:
                                orphaned_attachment = self._entity_mapper.map_attachment(
                                    attachment_node,
                                    lenient=True,
                                    parent_entity_id=entity_id
                                )
                                all_attachments.append(orphaned_attachment)
                            except Exception as lenient_error:
                                self._logger.warning(
                                    f"Failed to map orphaned attachment even with lenient mode (pagination) for {self._entity_name} {entity_id}: {lenient_error}"
                                )
                        else:
                            self._logger.warning(
                                f"Failed to map attachment for {self._entity_name} {entity_id}: {e}"
                            )

                # Check if there are more pages
                if page_info.get("hasNextPage", False):
                    current_cursor = page_info.get("endCursor")
                    page_num += 1
                    self._logger.debug(
                        f"Fetching attachments page {page_num} for {self._entity_name} {entity_id} "
                        f"({len(all_attachments)} attachments fetched so far)"
                    )
                else:
                    current_cursor = None

            except Exception as e:
                self._logger.warning(
                    f"Error fetching additional attachments for {self._entity_name} {entity_id}: {e}. "
                    f"Returning {len(all_attachments)} attachments fetched so far."
                )
                break

        return all_attachments

    def _collect_note_ids(self, node: dict[str, Any], primary_entity: T) -> None:
        """Collect note IDs from entity response for deferred processing.

        Implements the deferred loading pattern (Option C) documented in
        docs/notes_extraction_strategy.md. Collects note IDs instead of extracting
        full note content. Note IDs are stored in the note_reference_collector
        for later bulk fetching via NotesExtractor.

        Strategy Reference: docs/notes_extraction_strategy.md - Phase 1: Collect Note IDs

        Args:
            node: Entity data from API response
            primary_entity: The parent entity that was mapped
        """
        if not self._note_reference_collector:
            # No collector configured - skip note ID collection
            return

        # Extract note IDs from nested notes field
        notes_data = node.get("notes", {})
        note_edges = notes_data.get("edges", [])
        total_count = notes_data.get("totalCount", 0)
        page_info = notes_data.get("pageInfo", {})

        if note_edges:
            # Collect note IDs from first page
            self._note_reference_collector.collect_note_ids_from_edges(
                note_edges=note_edges,
                entity_type=self._entity_name,
                entity_id=primary_entity.id,
            )

            # Handle pagination if more notes exist
            if page_info.get("hasNextPage", False):
                cursor = page_info.get("endCursor")
                fetched_count = len(note_edges)

                self._logger.debug(
                    f"Entity {primary_entity.id} has {total_count} notes, "
                    f"fetched {fetched_count} IDs, fetching remaining via pagination..."
                )

                # Fetch additional note ID pages
                remaining_note_ids = self._fetch_remaining_note_ids(
                    entity_id=primary_entity.id,
                    cursor=cursor,
                    total_count=total_count,
                    fetched_count=fetched_count,
                )

                # Collect remaining IDs
                for note_id in remaining_note_ids:
                    self._note_reference_collector.collect_note_id(
                        note_id=note_id,
                        entity_type=self._entity_name,
                        entity_id=primary_entity.id,
                    )

    def _fetch_remaining_note_ids(
        self, entity_id: str, cursor: str, total_count: int, fetched_count: int
    ) -> list[str]:
        """Fetch remaining note IDs beyond the first page.

        Args:
            entity_id: Parent entity ID
            cursor: Pagination cursor from first page
            total_count: Total number of notes for this entity
            fetched_count: Number of note IDs already fetched

        Returns:
            List of additional note IDs
        """
        note_ids = []
        current_cursor = cursor
        page_num = 2

        while current_cursor and fetched_count < total_count:
            try:
                # Fetch next page of note IDs only
                response = self._jobber_client.fetch_additional_note_ids(
                    entity_id=entity_id,
                    entity_type=self._entity_name,
                    cursor=current_cursor,
                    page_size=100,
                )

                edges = response.get("edges", [])
                page_info = response.get("pageInfo", {})

                # Extract note IDs from edges
                for edge in edges:
                    node = edge.get("node", {})
                    note_id = node.get("id")
                    if note_id:
                        note_ids.append(note_id)
                        fetched_count += 1

                # Check for next page
                if page_info.get("hasNextPage", False) and fetched_count < total_count:
                    current_cursor = page_info.get("endCursor")
                    page_num += 1
                    self._logger.debug(
                        f"Fetching note IDs page {page_num} for {self._entity_name} {entity_id} "
                        f"({fetched_count}/{total_count} IDs collected)"
                    )
                else:
                    break

            except Exception as e:
                self._logger.warning(
                    f"Error fetching additional note IDs for {self._entity_name} {entity_id}: {e}. "
                    f"Collected {len(note_ids)} additional IDs so far."
                )
                break

        return note_ids

    def _extract_notes_and_attachments(self, node: dict[str, Any], primary_entity: T) -> dict[str, Any]:
        """Extract note IDs and attachments from entity query response.

        REFACTORED for deferred loading pattern (docs/notes_extraction_strategy.md):
        - Collects note IDs for later bulk fetching (via _collect_note_ids) - Phase 1
        - Extracts attachment metadata inline (attachments not available via top-level query)

        Strategy Reference: docs/notes_extraction_strategy.md - Option C: Deferred Loading

        Args:
            node: Entity data from API response
            primary_entity: The parent entity that was mapped

        Returns:
            Dictionary with 'attachments' list (notes are now collected separately)
        """
        related = {}

        # DEFERRED LOADING: Collect note IDs instead of extracting full content
        self._collect_note_ids(node, primary_entity)

        # Extract attachments if present
        attachments_data = node.get("noteAttachments", {})
        entity_attachments = attachments_data.get("edges", [])
        attachments_page_info = attachments_data.get("pageInfo", {})

        if entity_attachments:
            attachments = []
            orphaned_attachments_saved = 0  # Track orphaned attachments saved with lenient mapping
            for attachment_edge in entity_attachments:
                attachment_node = attachment_edge.get("node", {})
                if attachment_node:
                    try:
                        attachment = self._entity_mapper.map_attachment(attachment_node)
                        attachments.append(attachment)
                    except MappingError as e:
                        self._attachment_mapping_failures += 1
                        error_msg = str(e).lower()
                        # Try lenient mapping to preserve orphaned attachments
                        if "note id is required" in error_msg or "note id" in error_msg:
                            try:
                                # Use lenient mode with parent entity ID for file organization
                                orphaned_attachment = self._entity_mapper.map_attachment(
                                    attachment_node,
                                    lenient=True,
                                    parent_entity_id=primary_entity.id
                                )
                                attachments.append(orphaned_attachment)
                                orphaned_attachments_saved += 1
                            except Exception as lenient_error:
                                # Even lenient mapping failed
                                self._logger.warning(
                                    f"Failed to map orphaned attachment even with lenient mode for {self._entity_name} {primary_entity.id}: {lenient_error}"
                                )
                        else:
                            # Unexpected attachment mapping error - worth logging
                            self._logger.warning(
                                f"Failed to map attachment for {self._entity_name} {primary_entity.id}: {e}"
                            )

            # Auto-paginate to fetch all remaining attachments
            if attachments_page_info.get("hasNextPage", False):
                total_count = attachments_data.get("totalCount", "unknown")
                remaining = total_count - len(attachments) if isinstance(total_count, int) else "unknown"
                self._logger.debug(
                    f"Fetching remaining attachments for {self._entity_name} {primary_entity.id} "
                    f"(total: {total_count}, initial batch: {len(attachments)}, remaining: {remaining})"
                )
                attachments.extend(self._fetch_all_remaining_attachments(primary_entity.id, attachments_page_info.get("endCursor")))

            # Log consolidated message if we found and saved orphaned attachments
            # Note: Orphaned notes are no longer tracked here due to deferred loading pattern
            # (see docs/notes_extraction_strategy.md - Option C: Deferred Loading)
            if orphaned_attachments_saved > 0:
                # Extract human-readable identifier for cross-reference with Jobber UI
                display_id = self._get_entity_display_identifier(primary_entity)

                self._logger.info(
                    f"Saved {orphaned_attachments_saved} orphaned attachment(s) for {display_id} "
                    f"(review in ./attachments/ORPHANED/)"
                )
                # Track detailed information for reporting
                self._data_quality_issues.append({
                    "entity_type": self._entity_name,
                    "entity_id": primary_entity.id,
                    "display_id": display_id,
                    "attachments_saved_orphaned": orphaned_attachments_saved,
                    "issue_type": "orphaned_data_preserved",
                    "review_path": f"./attachments/ORPHANED/{primary_entity.id}/"
                })

            if attachments:
                related["attachments"] = attachments

        return related

    def _save_notes_and_attachments(self, related_entities: dict[str, Any]) -> None:
        """Save attachments to repository.

        REFACTORED for deferred loading pattern:
        - Notes are NO LONGER saved here (collected as IDs, saved later via NotesExtractor)
        - Only attachments are processed

        In queue mode (queue_attachments=True), attachments are added to attachment_queue
        for later batch processing. Otherwise, downloads attachment files and updates metadata
        with local file paths before saving (unless auto_download is disabled).

        Args:
            related_entities: Dictionary with 'attachments' list (notes handled separately)
        """
        # Notes are now handled via deferred loading - skip inline saving
        # This maintains backward compatibility but notes list should be empty

        # Handle attachments (queue or download)
        attachments = related_entities.get("attachments", [])
        if attachments:
            # Extract mode: queue attachments for later batch processing
            if self._queue_attachments:
                self._queue_attachments_for_download(attachments)
                return
            # Track total attachments processed
            self._attachments_processed += len(attachments)

            # Check if automatic downloading is enabled
            attachment_config = self._config_manager.get_attachment_config()
            auto_download = attachment_config.get("auto_download", False)

            if not auto_download:
                # Metadata-only mode: save attachments without downloading files
                self._logger.debug(f"Skipping download of {len(attachments)} attachment(s) (auto_download=false)")
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
                        f"Failed to download attachment {attachment.id}: " f"{download_result['error_message']}"
                    )
                    attachments_with_files.append(attachment)
                    self._download_failures += 1

            # Save all attachments with updated file paths
            self._repository.save_attachments(attachments_with_files)

    def _queue_attachments_for_download(self, attachments: List[Attachment]) -> None:
        """Queue attachments for batch download processing.

        Used in extract mode to decouple attachment downloads from entity extraction.
        Adds attachments to attachment_queue table for later processing, enabling:
        - Retry of failed downloads without re-fetching parent entity
        - Batch download processing with separate progress tracking
        - Status tracking per attachment (pending/in_progress/done/failed)

        Args:
            attachments: List of Attachment domain models to queue

        Raises:
            ConfigurationError: If map_snapshot_id is not set (required for queuing)
        """
        if not self._map_snapshot_id:
            raise ConfigurationError("map_snapshot_id is required when queue_attachments=True")

        # Prepare attachment queue items
        attachment_queue_items = []
        for attachment in attachments:
            # Determine parent entity ID from note_id pattern
            # Note IDs follow pattern: {parent_type}_{parent_id}_note_{note_number}
            # Example: "client_12345_note_1" -> parent_type="clients", parent_id="12345"
            note_id_parts = attachment.note_id.split("_")
            if len(note_id_parts) >= 2:
                parent_type = f"{note_id_parts[0]}s"  # Convert singular to plural
                parent_id = note_id_parts[1]
            else:
                # Fallback: use entity_name if note_id pattern doesn't match
                parent_type = self._entity_name
                parent_id = attachment.note_id.split("_")[0] if "_" in attachment.note_id else attachment.note_id

            attachment_queue_items.append(
                {
                    "attachment_id": attachment.id,
                    "parent_type": parent_type,
                    "parent_id": parent_id,
                }
            )

        # Save attachments metadata first
        self._repository.save_attachments(attachments)

        # Add to attachment queue
        if attachment_queue_items:
            self._repository.create_attachment_queue(
                snapshot_id=self._map_snapshot_id,
                attachments=attachment_queue_items,
            )
            self._attachments_queued += len(attachment_queue_items)
            self._logger.debug(f"Queued {len(attachment_queue_items)} attachment(s) for download")
