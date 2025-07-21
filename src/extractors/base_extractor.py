"""Abstract base class for entity extractors with common extraction logic."""

import time
from abc import ABC, abstractmethod
from typing import Any, Generic, List, Optional, Type, TypeVar, Union

from ..clients import JobberClient
from ..exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    RepositoryError,
)
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Attachment, Client, Invoice, Job, Note, Property, Quote, Request
from ..repositories import Repository

# Type variable for entity types
T = TypeVar("T", Client, Invoice, Quote, Note, Attachment, Job, Property, Request)


class BaseExtractor(ABC, Generic[T]):
    """
    Abstract base class for entity extractors with common extraction logic.

    Implements common patterns for:
    - Cursor-based pagination
    - Error handling and recovery
    - Progress tracking and logging
    - Batch processing
    - Extraction state management

    Subclasses must implement entity-specific methods for API calls and mapping.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        entity_type: Type[T],
        entity_name: str,
    ) -> None:
        """Initialize BaseExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            entity_type: Type of entity being extracted (for type safety)
            entity_name: Human-readable name of entity for logging
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._entity_type = entity_type
        self._entity_name = entity_name

        # Extraction state tracking
        self._last_extraction_summary = {
            "total_entities": 0,
            "total_pages": 0,
            "extraction_duration": 0.0,
            "average_page_size": 0.0,
            "entities_per_second": 0.0,
            "last_cursor": None,
            "extraction_status": "pending",
            "error_count": 0,
        }

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
    ) -> dict[str, List[Any]]:
        """Extract related entities (like notes) from a node.

        Override in subclasses that have related entities.

        Args:
            node: Entity data from API
            primary_entity: The primary entity that was mapped

        Returns:
            Dictionary mapping entity type names to lists of related entities
        """
        return {}

    def _save_related_entities(self, related_entities: dict[str, List[Any]]) -> None:
        """Save related entities to repository.

        Override in subclasses that have related entities.

        Args:
            related_entities: Dictionary mapping entity type names to lists
        """
        pass

    def extract(
        self,
        cursor: Optional[str] = None,
        page_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Extract entities from Jobber GraphQL API with cursor-based pagination.

        Performs complete extraction workflow including:
        - GraphQL API calls with cursor pagination
        - Data transformation via EntityMapper
        - Batch persistence via Repository
        - Progress logging and error handling

        Args:
            cursor: Optional pagination cursor for continuing extraction
            page_limit: Optional limit on number of pages to process (for testing)

        Returns:
            Dictionary containing extraction results with keys:
            - 'entities_processed': int - Total number of entities extracted
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
        pages_processed = 0
        current_cursor = cursor
        error_count = 0
        page_info = {}

        self._logger.info(
            f"Starting {self._entity_name} extraction from cursor: {cursor}"
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

                # Batch save entities to database
                if entities:
                    self._save_entities(entities)
                    entities_processed += len(entities)
                    self._logger.info(
                        f"Processed {len(entities)} {self._entity_name}s "
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

                if not has_next_page:
                    self._logger.debug(f"Reached last page of {self._entity_name}s")
                    break

                # Update cursor for next iteration
                current_cursor = end_cursor

                # Add delay between pages to prevent API overload
                time.sleep(1.0)
                self._logger.debug(f"Added 1s delay before page {pages_processed + 1}")

            extraction_time = time.time() - start_time

            # Update extraction summary
            self._update_extraction_summary(
                entities_processed,
                pages_processed,
                extraction_time,
                current_cursor,
                "completed",
                error_count,
            )

            result = {
                "entities_processed": entities_processed,
                "pages_processed": pages_processed,
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": current_cursor,
                "extraction_time": extraction_time,
            }

            self._logger.info(
                f"Completed {self._entity_name} extraction: "
                f"{entities_processed} entities in {extraction_time:.2f}s"
            )

            return result

        except (JobberApiError, ConfigurationError, RepositoryError) as e:
            # Update summary with error status
            extraction_time = time.time() - start_time
            self._update_extraction_summary(
                entities_processed,
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
            Dictionary containing extraction summary
        """
        return self._last_extraction_summary.copy()

    def _update_extraction_summary(
        self,
        entities_processed: int,
        pages_processed: int,
        extraction_time: float,
        last_cursor: Optional[str],
        status: str,
        error_count: int,
    ) -> None:
        """Update internal extraction summary statistics.

        Args:
            entities_processed: Total entities processed
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
            "total_pages": pages_processed,
            "extraction_duration": extraction_time,
            "average_page_size": avg_page_size,
            "entities_per_second": entities_per_second,
            "last_cursor": last_cursor,
            "extraction_status": status,
            "error_count": error_count,
        }
