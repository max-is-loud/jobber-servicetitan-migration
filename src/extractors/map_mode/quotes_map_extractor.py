"""QuotesMapExtractor for lightweight quote entity discovery."""

import json
from typing import Any, Callable, List, Optional

from ...clients import JobberClient
from ...interfaces import Logger
from ...performance import AdaptivePerformanceOptimizer
from ...models import EntityInventory
from ...repositories import Repository
from .base_map_extractor import BaseMapExtractor


class QuotesMapExtractor(BaseMapExtractor):
    """Map mode extractor for Quote entities - lightweight discovery pass."""

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        map_snapshot_id: str,
        adaptive_optimizer: Optional[AdaptivePerformanceOptimizer] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Initialize QuotesMapExtractor.

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
            entity_type_name="quotes",
            adaptive_optimizer=adaptive_optimizer,
            progress_callback=progress_callback,
        )

    def _fetch_page(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch a page of quotes using map mode query."""
        return self._jobber_client.fetch_quotes_map(cursor, page_size)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from quotes API response."""
        quotes_data = response.get("data", {}).get("quotes", {})
        edges = quotes_data.get("edges", [])
        page_info = quotes_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> EntityInventory:
        """Map a quote node to EntityInventory with relation counts."""
        # Extract relation counts
        line_items_count = node.get("lineItems", {}).get("totalCount", 0)
        notes_count = node.get("notes", {}).get("totalCount", 0)
        attachments_count = node.get("noteAttachments", {}).get("totalCount", 0)

        return EntityInventory(
            entity_type="quotes",
            entity_id=node["id"],
            discovered_at=self._get_current_timestamp(),
            map_snapshot_id=self._map_snapshot_id,
            updated_at=node.get("updatedAt"),
            estimated_relations_json=json.dumps(
                {
                    "line_items": line_items_count,
                    "notes": notes_count,
                    "attachments": attachments_count,
                }
            ),
        )
