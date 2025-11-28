"""TimesheetEntriesExtractor for extracting TimeSheetEntry entities from Jobber GraphQL API."""

import time
from typing import Any, List, Optional

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import TimeSheetEntry
from ..repositories import Repository
from .base_extractor import BaseExtractor


class TimesheetEntriesExtractor(BaseExtractor[TimeSheetEntry]):
    """
    Extractor for TimeSheetEntry entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for TimeSheetEntry entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    TimeSheetEntries represent time tracking records with relationships to Users,
    Jobs, and Visits. They include duration calculations, approval workflows,
    and payment tracking for payroll and billing operations.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        config_manager: Optional[ConfigManagerImpl] = None,
        skip_existing_entities: bool = False,
        **kwargs,
    ) -> None:
        """Initialize TimesheetEntriesExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            config_manager: Optional ConfigManager for delays and pagination settings
            skip_existing_entities: Whether to skip entities that already exist in database
            **kwargs: Additional optional parameters (e.g., queue_attachments, map_snapshot_id)
        """
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=TimeSheetEntry,
            entity_name="timesheet entry",
            config_manager=config_manager,
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[TimeSheetEntry] = []

        # Batch fetching optimization for extract mode
        self._batch_cache: dict[str, dict[str, Any]] = {}  # entity_id -> node data
        self._batch_cache_ids: set[str] = set()  # IDs we attempted to fetch in current batch

    def _fetch_single(self, entity_id: str) -> Optional[dict[str, Any]]:
        """
        Fetch a single timesheet entry by ID using batch-optimized pagination.

        Jobber's API doesn't support single-entity queries for timesheet entries.
        This method uses pagination to search for the specific ID, caching
        all entities encountered for subsequent lookups.

        Args:
            entity_id: The ID of the timesheet entry to fetch

        Returns:
            Timesheet entry node data dictionary, or None if not found
        """
        # Check if already in cache
        if entity_id in self._batch_cache:
            return self._batch_cache[entity_id]

        # Check if we already tried to fetch this and it wasn't found
        if entity_id in self._batch_cache_ids:
            return None

        # Cache miss - paginate and cache everything we see
        self._logger.debug(
            f"Batch cache empty, paginating through ALL timesheet entries and caching (one-time cost)"
        )

        cursor = None
        pages_searched = 0
        max_pages = 200  # Safety limit
        found_target = False

        try:
            while pages_searched < max_pages:
                # Fetch a page of timesheet entries
                response = self._fetch_page(cursor)
                edges, page_info = self._extract_edges_and_page_info(response)

                # Cache every entity we encounter
                for edge in edges:
                    node = edge.get("node", {})
                    node_id = node.get("id")
                    if node_id:
                        self._batch_cache[node_id] = node
                        self._batch_cache_ids.add(node_id)
                        if node_id == entity_id:
                            found_target = True

                # Check if there are more pages
                if not page_info.get("hasNextPage", False):
                    break

                cursor = page_info.get("endCursor")
                pages_searched += 1

                # Add delay before next page to respect rate limits
                if page_info.get("hasNextPage", False) and self._config_manager:
                    page_delay = self._config_manager.get_delay_config("page_delay")
                    time.sleep(page_delay)
                    self._logger.debug(f"Batch cache: Added {page_delay}s delay before page {pages_searched + 1}")

            self._logger.debug(
                f"Cached {len(self._batch_cache)} timesheet entries from {pages_searched + 1} pages"
            )

            # Return the target if found
            if found_target:
                return self._batch_cache[entity_id]

            # Mark as not found
            return None

        except Exception as e:
            self._logger.debug(f"Failed to fetch and cache timesheet entries: {e}")
            # Return target if we found it before the error
            return self._batch_cache.get(entity_id)

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of timesheet entries from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_timesheet_entries(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        timesheet_data = response.get("data", {}).get("timeSheetEntries", {})
        edges = timesheet_data.get("edges", [])
        page_info = timesheet_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> TimeSheetEntry:
        """Map a single timesheet entry node to domain model.

        Args:
            node: TimeSheetEntry data from API

        Returns:
            Mapped TimeSheetEntry instance
        """
        return self._entity_mapper.map_timesheet_entry(node)

    def _save_entities(self, entities: List[TimeSheetEntry]) -> None:
        """Save timesheet entries to repository.

        Args:
            entities: List of timesheet entries to save
        """
        self._repository.save_timesheet_entries(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract timesheet entries data from GraphQL response."""
        return response.get("data", {}).get("timeSheetEntries", {})

    def _get_entities_from_last_batch(self) -> List[TimeSheetEntry]:
        """Get timesheet entries from the last extraction batch.

        Returns:
            List of timesheet entries from last batch
        """
        return self._last_batch_entities

