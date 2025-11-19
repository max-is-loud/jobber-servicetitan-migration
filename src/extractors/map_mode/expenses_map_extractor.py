"""ExpensesMapExtractor for lightweight expense entity discovery."""

import json
from typing import Any, List, Optional

from ...clients import JobberClient
from ...interfaces import Logger
from ...models import EntityInventory
from ...repositories import Repository
from .base_map_extractor import BaseMapExtractor


class ExpensesMapExtractor(BaseMapExtractor):
    """Map mode extractor for Expense entities - lightweight discovery pass."""

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        map_snapshot_id: str,
    ) -> None:
        """Initialize ExpensesMapExtractor.

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
            entity_type_name="expenses",
        )

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of expenses using map mode query."""
        return self._jobber_client.fetch_expenses_map(cursor)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from expenses API response."""
        expenses_data = response.get("data", {}).get("expenses", {})
        edges = expenses_data.get("edges", [])
        page_info = expenses_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> EntityInventory:
        """Map an expense node to EntityInventory."""
        return EntityInventory(
            entity_type="expenses",
            entity_id=node["id"],
            discovered_at=self._get_current_timestamp(),
            map_snapshot_id=self._map_snapshot_id,
            updated_at=node.get("updatedAt"),
            estimated_relations_json=json.dumps({}),  # No relations tracked
        )
