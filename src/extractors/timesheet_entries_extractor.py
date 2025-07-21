"""TimesheetEntriesExtractor for extracting TimeSheetEntry entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
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
    ) -> None:
        """Initialize TimesheetEntriesExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
        """
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=TimeSheetEntry,
            entity_name="timesheet entry",
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[TimeSheetEntry] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of timesheet entries from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_timesheet_entries(cursor)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        timesheet_data = response.get("data", {}).get("timesheetEntries", {})
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

    def _get_entities_from_last_batch(self) -> List[TimeSheetEntry]:
        """Get timesheet entries from the last extraction batch.

        Returns:
            List of timesheet entries from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of timesheet entries available for extraction.

        Performs a lightweight API call to determine the total number of timesheet entries
        available for extraction without actually extracting data.

        Returns:
            Total number of timesheet entries available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total timesheet entry count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_timesheet_entries(cursor=None)
        timesheet_data = response.get("data", {}).get("timesheetEntries", {})
        page_info = timesheet_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = timesheet_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(
                f"API reported total timesheet entry count: {total_count}"
            )
            return int(total_count)

        # Otherwise estimate from first page
        edges = timesheet_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info(
            "Cannot determine exact timesheet entry count without full pagination"
        )
        return -1  # Indicate unknown count
