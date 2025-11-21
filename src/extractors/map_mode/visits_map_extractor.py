"""VisitsMapExtractor for lightweight visit entity discovery."""

import json
from typing import Any, Callable, List, Optional

from ...clients import JobberClient
from ...interfaces import Logger
from ...performance import AdaptivePerformanceOptimizer
from ...models import EntityInventory
from ...repositories import Repository
from .base_map_extractor import BaseMapExtractor


class VisitsMapExtractor(BaseMapExtractor):
    """Map mode extractor for Visit entities - lightweight discovery pass."""

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        map_snapshot_id: str,
        adaptive_optimizer: Optional[AdaptivePerformanceOptimizer] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Initialize VisitsMapExtractor.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            repository: Repository for database operations
            logger: Logger for structured output
            map_snapshot_id: ID of the map snapshot this extraction belongs to
        """
        super().__init__(
            jobber_client=jobber_client,
            repository=repository,
            logger=logger,
            map_snapshot_id=map_snapshot_id,
            entity_type_name="visits",
            adaptive_optimizer=adaptive_optimizer,
            progress_callback=progress_callback,
        )

    def _fetch_page(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch a page of visits using map mode query."""
        return self._jobber_client.fetch_visits_map(cursor, page_size)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from visits API response."""
        visits_data = response.get("data", {}).get("visits", {})
        edges = visits_data.get("edges", [])
        page_info = visits_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> EntityInventory:
        """Map a visit node to EntityInventory."""
        # Extract relation counts from node
        relations = {}

        # Extract notes count if available
        if "notes" in node and isinstance(node["notes"], dict):
            relations["notes"] = node["notes"].get("totalCount", 0)

        # Extract note attachments count if available (stored as "attachments" key)
        if "noteAttachments" in node and isinstance(node["noteAttachments"], dict):
            relations["attachments"] = node["noteAttachments"].get("totalCount", 0)

        return EntityInventory(
            entity_type="visits",
            entity_id=node["id"],
            discovered_at=self._get_current_timestamp(),
            map_snapshot_id=self._map_snapshot_id,
            updated_at=node.get("createdAt"),  # Visits use createdAt instead of updatedAt
            estimated_relations_json=json.dumps(relations),
        )
