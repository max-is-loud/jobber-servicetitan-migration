from __future__ import annotations

"""QuotesExtractor for extracting Quote entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Quote
from ..repositories import Repository
from .base_extractor import BaseExtractor


class QuotesExtractor(BaseExtractor[Quote]):
    """
    Extractor for Quote entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for Quote entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.
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
        """Initialize QuotesExtractor with required dependencies.

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
            entity_type=Quote,
            entity_name="quote",
            config_manager=config_manager,
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[Quote] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of quotes from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_quotes(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        quotes_data = response.get("data", {}).get("quotes", {})
        edges = quotes_data.get("edges", [])
        page_info = quotes_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Quote:
        """Map a single quote node to domain model.

        Args:
            node: Quote data from API

        Returns:
            Mapped Quote instance
        """
        return self._entity_mapper.map_quote(node)

    def _save_entities(self, entities: List[Quote]) -> None:
        """Save quotes to repository.

        Args:
            entities: List of quotes to save
        """
        self._repository.save_quotes(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_related_entities(self, node: dict[str, Any], primary_entity: Quote) -> dict[str, Any]:
        """Extract notes and attachments related to the quote.

        Delegates to base implementation for common extraction logic.

        Args:
            node: Quote data from API
            primary_entity: The quote that was mapped

        Returns:
            Dictionary with notes and attachments lists
        """
        return self._extract_notes_and_attachments(node, primary_entity)

    def _save_related_entities(self, related_entities: dict[str, Any]) -> None:
        """Save notes and attachments related to quotes.

        Delegates to base implementation for common save logic.

        Args:
            related_entities: Dictionary with notes and attachments lists
        """
        self._save_notes_and_attachments(related_entities)

    def _get_entities_from_last_batch(self) -> List[Quote]:
        """Get quotes from the last extraction batch.

        Returns:
            List of quotes from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of quotes available for extraction.

        Performs a lightweight API call to determine the total number of quotes
        available for extraction without actually extracting data.

        Returns:
            Total number of quotes available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total quote count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_quotes(cursor=None)
        quotes_data = response.get("data", {}).get("quotes", {})
        page_info = quotes_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = quotes_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total quote count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = quotes_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info("Cannot determine exact quote count without full pagination")
        return -1  # Indicate unknown count
