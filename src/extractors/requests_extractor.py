"""RequestsExtractor for extracting Request entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..exceptions import MappingError
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
    ) -> None:
        """Initialize RequestsExtractor with required dependencies.

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
            entity_type=Request,
            entity_name="request",
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[Request] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of requests from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_requests(cursor)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
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

    def _extract_related_entities(
        self, node: dict[str, Any], primary_entity: Request
    ) -> dict[str, List[Any]]:
        """Extract notes related to the request.

        Extracts nested note data from the request query response. Notes are
        fetched inline with the request query using optimized pagination
        (configurable via pagination.nested_notes) to reduce API costs by 60-70%.

        Args:
            node: Request data from API
            primary_entity: The request that was mapped

        Returns:
            Dictionary with notes list
        """
        related = {}

        # Extract notes if present
        notes_data = node.get("notes", {})
        request_notes = notes_data.get("edges", [])
        notes_page_info = notes_data.get("pageInfo", {})

        if request_notes:
            notes = []
            for note_edge in request_notes:
                note_node = note_edge.get("node", {})
                if note_node:
                    try:
                        # Add request relationship to note data without mutation
                        note_data = {**note_node, "request": {"id": primary_entity.id}}
                        note = self._entity_mapper.map_note(note_data)
                        notes.append(note)
                    except MappingError as e:
                        self._logger.debug(
                            f"Failed to map note for request {primary_entity.id}: {e}"
                        )
            if notes:
                related["notes"] = notes

                # Warn if there are more notes that weren't fetched
                if notes_page_info.get("hasNextPage", False):
                    self._logger.warning(
                        f"Request {primary_entity.id} has additional notes beyond the "
                        f"{len(notes)} fetched. Increase pagination.nested_notes in "
                        f"settings.yaml to fetch more notes inline."
                    )

        return related

    def _save_related_entities(self, related_entities: dict[str, List[Any]]) -> None:
        """Save notes related to requests.

        Args:
            related_entities: Dictionary with notes list
        """
        notes = related_entities.get("notes", [])
        if notes:
            self._repository.save_notes(notes)

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
        self._logger.info(
            "Cannot determine exact request count without full pagination"
        )
        return -1  # Indicate unknown count
