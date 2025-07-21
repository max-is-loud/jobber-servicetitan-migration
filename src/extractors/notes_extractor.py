"""NotesExtractor for extracting Note entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Note
from ..repositories import Repository
from .base_extractor import BaseExtractor


class NotesExtractor(BaseExtractor[Note]):
    """
    Extractor for Note entities implementing BaseExtractor.

    Provides modular OO extraction for Note entities with polymorphic
    relationships to various parent entities (clients, jobs, quotes, etc.).
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
    ) -> None:
        """Initialize NotesExtractor with required dependencies."""
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=Note,
            entity_name="note",
        )
        self._last_batch_entities: List[Note] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of notes from the Jobber API."""
        return self._jobber_client.fetch_notes(cursor)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response."""
        notes_data = response.get("data", {}).get("notes", {})
        edges = notes_data.get("edges", [])
        page_info = notes_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Note:
        """Map a single note node to domain model."""
        return self._entity_mapper.map_note(node)

    def _save_entities(self, entities: List[Note]) -> None:
        """Save notes to repository."""
        self._repository.save_notes(entities)
        self._last_batch_entities = entities

    def _get_entities_from_last_batch(self) -> List[Note]:
        """Get notes from the last extraction batch."""
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of notes available for extraction."""
        self._logger.debug("Fetching total note count from API")

        response = self._jobber_client.fetch_notes(cursor=None)
        notes_data = response.get("data", {}).get("notes", {})

        # If API provides totalCount, use it
        total_count = notes_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total note count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = notes_data.get("edges", [])
        if not edges:
            return 0

        page_info = notes_data.get("pageInfo", {})
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        self._logger.info("Cannot determine exact note count without full pagination")
        return -1
