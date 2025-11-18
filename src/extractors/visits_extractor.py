"""VisitsExtractor for extracting Visit entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..exceptions import MappingError
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Visit
from ..repositories import Repository
from .base_extractor import BaseExtractor


class VisitsExtractor(BaseExtractor[Visit]):
    """
    Extractor for Visit entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for Visit entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    Visits represent scheduled service appointments and may have associated notes
    for tracking appointment details, special instructions, or completion notes.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        skip_existing_entities: bool = False,
    ) -> None:
        """Initialize VisitsExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            skip_existing_entities: Whether to skip entities that already exist in database
        """
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=Visit,
            entity_name="visit",
            skip_existing_entities=skip_existing_entities,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[Visit] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of visits from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_visits(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        visits_data = response.get("data", {}).get("visits", {})
        edges = visits_data.get("edges", [])
        page_info = visits_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Visit:
        """Map a single visit node to domain model.

        Args:
            node: Visit data from API

        Returns:
            Mapped Visit instance
        """
        return self._entity_mapper.map_visit(node)

    def _save_entities(self, entities: List[Visit]) -> None:
        """Save visits to repository.

        Args:
            entities: List of visits to save
        """
        self._repository.save_visits(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_related_entities(self, node: dict[str, Any], primary_entity: Visit) -> dict[str, List[Note]]:
        """Extract notes related to the visit.

        Args:
            node: Visit data from API
            primary_entity: The visit that was mapped

        Returns:
            Dictionary with notes list
        """
        related = {}

        # Extract notes if present
        visit_notes = node.get("notes", {}).get("edges", [])
        if visit_notes:
            notes = []
            for note_edge in visit_notes:
                note_node = note_edge.get("node", {})
                if note_node:
                    # Add visit relationship to note data
                    note_node["visit"] = {"id": primary_entity.id}
                    try:
                        note = self._entity_mapper.map_note(note_node)
                        notes.append(note)
                    except MappingError as e:
                        self._logger.debug(f"Failed to map note for visit {primary_entity.id}: {e}")
            if notes:
                related["notes"] = notes

        return related

    def _save_related_entities(self, related_entities: dict[str, List[Note]]) -> None:
        """Save notes related to visits.

        Args:
            related_entities: Dictionary with notes list
        """
        notes = related_entities.get("notes", [])
        if notes:
            self._repository.save_notes(notes)

    def _get_entities_from_last_batch(self) -> List[Visit]:
        """Get visits from the last extraction batch.

        Returns:
            List of visits from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of visits available for extraction.

        Performs a lightweight API call to determine the total number of visits
        available for extraction without actually extracting data.

        Returns:
            Total number of visits available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total visit count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_visits(cursor=None)
        visits_data = response.get("data", {}).get("visits", {})
        page_info = visits_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = visits_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total visit count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = visits_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info("Cannot determine exact visit count without full pagination")
        return -1  # Indicate unknown count
