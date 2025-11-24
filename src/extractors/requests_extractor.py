from __future__ import annotations

"""RequestsExtractor for extracting Request entities from Jobber GraphQL API."""

import time
from typing import Any, List, Optional

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Request
from ..repositories import Repository
from .base_extractor import BaseExtractor


class RequestsExtractor(BaseExtractor[Request]):
    """
    Extractor for Request entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for Request entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    Requests are similar to Jobs with notes extraction and include conversion
    tracking fields (converted_to_quote_id, converted_to_job_id) for workflow
    tracking in the Request -> Quote -> Job -> Invoice flow.
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
        """Initialize RequestsExtractor with required dependencies.

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
            entity_type=Request,
            entity_name="request",
            config_manager=config_manager,
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[Request] = []

        # Batch fetching optimization for extract mode
        self._batch_cache: dict[str, dict[str, Any]] = {}  # entity_id -> node data
        self._batch_cache_ids: set[str] = set()  # IDs we attempted to fetch in current batch

    def _fetch_batch(self, entity_ids: set[str]) -> dict[str, dict[str, Any]]:
        """
        Fetch multiple requests in a single pagination sweep.

        This is a massive optimization for extract mode. Instead of fetching each
        request individually (which requires paginating through ALL requests for each),
        we batch multiple IDs and fetch them all in one pass.

        Performance comparison:
        - Old: 100 entities × 50 pages each = 5,000 API calls
        - New: 1 batch × 50 pages = 50 API calls (100x faster!)

        Args:
            entity_ids: Set of request IDs to fetch

        Returns:
            Dictionary mapping entity_id -> node data for found entities
        """
        self._logger.debug(
            f"Batch fetching {len(entity_ids)} requests using pagination API"
        )

        found_entities: dict[str, dict[str, Any]] = {}
        remaining_ids = set(entity_ids)
        cursor = None
        pages_searched = 0
        max_pages = 200  # Safety limit

        try:
            while remaining_ids and pages_searched < max_pages:
                # Fetch a page of requests
                response = self._fetch_page(cursor)
                edges, page_info = self._extract_edges_and_page_info(response)

                # Check each node in this page
                for edge in edges:
                    node = edge.get("node", {})
                    node_id = node.get("id")

                    # If this node is one we're looking for, save it
                    if node_id in remaining_ids:
                        found_entities[node_id] = node
                        remaining_ids.remove(node_id)

                # Stop if we found everything
                if not remaining_ids:
                    self._logger.debug(
                        f"Found all {len(entity_ids)} requests after {pages_searched + 1} pages"
                    )
                    break

                # Check if there are more pages
                if not page_info.get("hasNextPage", False):
                    break

                cursor = page_info.get("endCursor")
                pages_searched += 1

            # Log what we found vs. what's missing
            if remaining_ids:
                self._logger.debug(
                    f"Batch fetch incomplete: found {len(found_entities)}/{len(entity_ids)} "
                    f"after {pages_searched} pages, missing {len(remaining_ids)} entities"
                )

            return found_entities

        except Exception as e:
            self._logger.debug(f"Failed to batch fetch requests: {e}")
            return found_entities  # Return what we found before the error

    def _fetch_single(self, entity_id: str) -> Optional[dict[str, Any]]:
        """
        Fetch a single request by ID using batch-optimized pagination.

        OPTIMIZATION: Uses batch caching with opportunistic prefetching. When the
        requested ID is not cached, we paginate through ALL requests once, caching
        every entity we encounter. This way:
        - First call: Full pagination to find target + cache everything
        - Subsequent calls: Instant cache hits

        This transforms the worst case of O(N²) API calls into O(N) calls.

        Performance for 5000 entities:
        - Old: 5000 entities × avg 25 pages = 125,000 API calls
        - New: ~50 pages once = 50 API calls (2500x improvement!)

        Args:
            entity_id: The ID of the request to fetch

        Returns:
            Request node data dictionary, or None if not found
        """
        # Check if already in cache
        if entity_id in self._batch_cache:
            return self._batch_cache[entity_id]

        # Check if we already tried to fetch this and it wasn't found
        if entity_id in self._batch_cache_ids:
            return None

        # Cache miss - paginate and cache everything we see
        self._logger.debug(
            f"Batch cache empty, paginating through ALL requests and caching (one-time cost)"
        )

        cursor = None
        pages_searched = 0
        max_pages = 200  # Safety limit
        found_target = False

        try:
            while pages_searched < max_pages:
                # Fetch a page of requests
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
                # This prevents overwhelming the API with rapid-fire requests
                if page_info.get("hasNextPage", False) and self._config_manager:
                    page_delay = self._config_manager.get_delay_config("page_delay")
                    time.sleep(page_delay)
                    self._logger.debug(f"Batch cache: Added {page_delay}s delay before page {pages_searched + 1}")

            self._logger.debug(
                f"Cached {len(self._batch_cache)} requests from {pages_searched + 1} pages"
            )

            # Return the target if found
            if found_target:
                return self._batch_cache[entity_id]

            # Mark as not found
            return None

        except Exception as e:
            self._logger.debug(f"Failed to fetch and cache requests: {e}")
            # Return target if we found it before the error
            return self._batch_cache.get(entity_id)

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of requests from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_requests(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        requests_data = response.get("data", {}).get("requests", {})
        edges = requests_data.get("edges", [])
        page_info = requests_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Request:
        """Map a single request node to domain model.

        Args:
            node: Request data from API

        Returns:
            Mapped Request instance
        """
        return self._entity_mapper.map_request(node)

    def _save_entities(self, entities: List[Request]) -> None:
        """Save requests to repository.

        Args:
            entities: List of requests to save
        """
        self._repository.save_requests(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_related_entities(self, node: dict[str, Any], primary_entity: Request) -> dict[str, Any]:
        """Extract notes and attachments related to the request.

        Extracts nested note and attachment data from the request query response.
        Both are fetched inline with the request query using optimized pagination
        (configurable via pagination.nested_notes) to reduce API costs.

        Args:
            node: Request data from API
            primary_entity: The request that was mapped

        Returns:
            Dictionary with notes and attachments lists
        """
        return self._extract_notes_and_attachments(node, primary_entity)

    def _save_related_entities(self, related_entities: dict[str, Any]) -> None:
        """Save notes and attachments related to requestss.

        Downloads attachment files and updates metadata with local file paths
        before saving to repository.

        Args:
            related_entities: Dictionary with notes and attachments lists
        """
        self._save_notes_and_attachments(related_entities)

    def _get_entities_from_last_batch(self) -> List[Request]:
        """Get requests from the last extraction batch.

        Returns:
            List of requests from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of requests available for extraction.

        Performs a lightweight API call to determine the total number of requests
        available for extraction without actually extracting data.

        Returns:
            Total number of requests available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total request count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_requests(cursor=None)
        requests_data = response.get("data", {}).get("requests", {})
        page_info = requests_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = requests_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total request count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = requests_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info("Cannot determine exact request count without full pagination")
        return -1  # Indicate unknown count
