"""ExpensesExtractor for extracting Expense entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Expense
from ..repositories import Repository
from .base_extractor import BaseExtractor


class ExpensesExtractor(BaseExtractor[Expense]):
    """
    Extractor for Expense entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for Expense entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    Expenses represent job-related costs and financial tracking for business
    operations. They are linked to specific jobs and include monetary amounts,
    vendor information, and categorization.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        skip_existing_entities: bool = False,
        **kwargs,
    ) -> None:
        """Initialize ExpensesExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            skip_existing_entities: Whether to skip entities that already exist in database
            **kwargs: Additional optional parameters (e.g., queue_attachments, map_snapshot_id)
        """
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=Expense,
            entity_name="expense",
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[Expense] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of expenses from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_expenses(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        expenses_data = response.get("data", {}).get("expenses", {})
        edges = expenses_data.get("edges", [])
        page_info = expenses_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Expense:
        """Map a single expense node to domain model.

        Args:
            node: Expense data from API

        Returns:
            Mapped Expense instance
        """
        return self._entity_mapper.map_expense(node)

    def _save_entities(self, entities: List[Expense]) -> None:
        """Save expenses to repository.

        Args:
            entities: List of expenses to save
        """
        self._repository.save_expenses(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _get_entities_from_last_batch(self) -> List[Expense]:
        """Get expenses from the last extraction batch.

        Returns:
            List of expenses from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of expenses available for extraction.

        Performs a lightweight API call to determine the total number of expenses
        available for extraction without actually extracting data.

        Returns:
            Total number of expenses available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total expense count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_expenses(cursor=None)
        expenses_data = response.get("data", {}).get("expenses", {})
        page_info = expenses_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = expenses_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total expense count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = expenses_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info("Cannot determine exact expense count without full pagination")
        return -1  # Indicate unknown count
