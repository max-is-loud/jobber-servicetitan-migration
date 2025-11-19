"""UsersMapExtractor for lightweight user entity discovery."""

import json
from typing import Any, List, Optional

from ...clients import JobberClient
from ...interfaces import Logger
from ...models import EntityInventory
from ...repositories import Repository
from .base_map_extractor import BaseMapExtractor


class UsersMapExtractor(BaseMapExtractor):
    """Map mode extractor for User entities - lightweight discovery pass."""

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        map_snapshot_id: str,
    ) -> None:
        """Initialize UsersMapExtractor.

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
            entity_type_name="users",
        )

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of users using map mode query."""
        return self._jobber_client.fetch_users_map(cursor)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from users API response."""
        users_data = response.get("data", {}).get("users", {})
        edges = users_data.get("edges", [])
        page_info = users_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> EntityInventory:
        """Map a user node to EntityInventory."""
        return EntityInventory(
            entity_type="users",
            entity_id=node["id"],
            discovered_at=self._get_current_timestamp(),
            map_snapshot_id=self._map_snapshot_id,
            updated_at=node.get("lastLoginAt"),  # Users use lastLoginAt instead of updatedAt
            estimated_relations_json=json.dumps({}),  # No relations tracked
        )
