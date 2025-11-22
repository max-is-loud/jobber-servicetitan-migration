"""TaxRatesExtractor for extracting TaxRate entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import TaxRate
from ..repositories import Repository
from .base_extractor import BaseExtractor


class TaxRatesExtractor(BaseExtractor[TaxRate]):
    """
    Extractor for TaxRate entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for TaxRate entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    TaxRates represent regional tax configuration including rates, regions,
    compound calculations, and government tax numbers. They are simpler
    configuration entities without complex relationships or notes.
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
        """Initialize TaxRatesExtractor with required dependencies.

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
            entity_type=TaxRate,
            entity_name="tax rate",
            config_manager=config_manager,
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[TaxRate] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of tax rates from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_tax_rates(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        tax_rates_data = response.get("data", {}).get("taxRates", {})
        edges = tax_rates_data.get("edges", [])
        page_info = tax_rates_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> TaxRate:
        """Map a single tax rate node to domain model.

        Args:
            node: TaxRate data from API

        Returns:
            Mapped TaxRate instance
        """
        return self._entity_mapper.map_tax_rate(node)

    def _save_entities(self, entities: List[TaxRate]) -> None:
        """Save tax rates to repository.

        Args:
            entities: List of tax rates to save
        """
        self._repository.save_tax_rates(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _get_entities_from_last_batch(self) -> List[TaxRate]:
        """Get tax rates from the last extraction batch.

        Returns:
            List of tax rates from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of tax rates available for extraction.

        Performs a lightweight API call to determine the total number of tax rates
        available for extraction without actually extracting data.

        Returns:
            Total number of tax rates available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total tax rate count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_tax_rates(cursor=None)
        tax_rates_data = response.get("data", {}).get("taxRates", {})
        page_info = tax_rates_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = tax_rates_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total tax rate count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = tax_rates_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info("Cannot determine exact tax rate count without full pagination")
        return -1  # Indicate unknown count
