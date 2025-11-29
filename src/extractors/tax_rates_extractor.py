"""TaxRatesExtractor for extracting TaxRate entities from Jobber GraphQL API."""

import time
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
            **kwargs: Reserved for future use
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

        # Batch fetching optimization for extract mode
        self._batch_cache: dict[str, dict[str, Any]] = {}  # entity_id -> node data
        self._batch_cache_ids: set[str] = set()  # IDs we attempted to fetch in current batch

    def _fetch_single(self, entity_id: str) -> Optional[dict[str, Any]]:
        """
        Fetch a single tax rate by ID using batch-optimized pagination.

        Jobber's API doesn't support single-entity queries for tax rates.
        This method uses pagination to search for the specific ID, caching
        all entities encountered for subsequent lookups.

        Args:
            entity_id: The ID of the tax rate to fetch

        Returns:
            Tax rate node data dictionary, or None if not found
        """
        # Check if already in cache
        if entity_id in self._batch_cache:
            return self._batch_cache[entity_id]

        # Check if we already tried to fetch this and it wasn't found
        if entity_id in self._batch_cache_ids:
            return None

        # Cache miss - paginate and cache everything we see
        self._logger.debug(
            "Batch cache empty, paginating through ALL tax rates and caching (one-time cost)"
        )

        cursor = None
        pages_searched = 0
        max_pages = 200  # Safety limit
        found_target = False

        try:
            while pages_searched < max_pages:
                # Fetch a page of tax rates
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
                f"Cached {len(self._batch_cache)} tax rates from {pages_searched + 1} pages"
            )

            # Return the target if found
            if found_target:
                return self._batch_cache[entity_id]

            # Mark as not found
            return None

        except Exception as e:
            self._logger.debug(f"Failed to fetch and cache tax rates: {e}")
            # Return target if we found it before the error
            return self._batch_cache.get(entity_id)

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

    def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract tax rates data from GraphQL response."""
        return response.get("data", {}).get("taxRates", {})

    def _get_entities_from_last_batch(self) -> List[TaxRate]:
        """Get tax rates from the last extraction batch.

        Returns:
            List of tax rates from last batch
        """
        return self._last_batch_entities

