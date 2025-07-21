"""ProductServicesExtractor for extracting ProductService entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import ProductService
from ..repositories import Repository
from .base_extractor import BaseExtractor


class ProductServicesExtractor(BaseExtractor[ProductService]):
    """
    Extractor for ProductService entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for ProductService entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    ProductServices represent the service catalog items including pricing,
    duration, category, and online booking configuration. They are simpler
    entities without complex related notes or other relationships.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
    ) -> None:
        """Initialize ProductServicesExtractor with required dependencies.

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
            entity_type=ProductService,
            entity_name="product service",
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[ProductService] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of products/services from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_products_services(cursor)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        products_data = response.get("data", {}).get("productsOrServices", {})
        edges = products_data.get("edges", [])
        page_info = products_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> ProductService:
        """Map a single product/service node to domain model.

        Args:
            node: ProductService data from API

        Returns:
            Mapped ProductService instance
        """
        return self._entity_mapper.map_product_service(node)

    def _save_entities(self, entities: List[ProductService]) -> None:
        """Save products/services to repository.

        Args:
            entities: List of products/services to save
        """
        self._repository.save_products_services(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _get_entities_from_last_batch(self) -> List[ProductService]:
        """Get products/services from the last extraction batch.

        Returns:
            List of products/services from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of products/services available for extraction.

        Performs a lightweight API call to determine the total number of products/services
        available for extraction without actually extracting data.

        Returns:
            Total number of products/services available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total product/service count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_products_services(cursor=None)
        products_data = response.get("data", {}).get("productsOrServices", {})
        page_info = products_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = products_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(
                f"API reported total product/service count: {total_count}"
            )
            return int(total_count)

        # Otherwise estimate from first page
        edges = products_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info(
            "Cannot determine exact product/service count without full pagination"
        )
        return -1  # Indicate unknown count
