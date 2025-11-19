"""Base class for map mode extractors with lightweight entity discovery."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional

from ...clients import JobberClient
from ...interfaces import Logger
from ...models import EntityInventory
from ...repositories import Repository


class BaseMapExtractor(ABC):
    """
    Base class for map mode extractors implementing lightweight entity discovery.

    Map mode extractors fetch minimal entity data (id, updatedAt, relation counts)
    to enable fast discovery and density analysis before full extraction.
    Used in multi-pass migration strategy to estimate extraction effort.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        map_snapshot_id: str,
        entity_type_name: str,
    ) -> None:
        """Initialize BaseMapExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            map_snapshot_id: ID of the map snapshot this extraction belongs to
            entity_type_name: Name of entity type (e.g., "clients", "invoices")
        """
        self._jobber_client = jobber_client
        self._repository = repository
        self._logger = logger
        self._map_snapshot_id = map_snapshot_id
        self._entity_type_name = entity_type_name

        # Extraction statistics
        self._total_entities = 0
        self._total_pages = 0

    @abstractmethod
    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of entities using map mode query.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary

        Raises:
            JobberApiError: If API communication fails
        """
        pass

    @abstractmethod
    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        pass

    @abstractmethod
    def _map_entity(self, node: dict[str, Any]) -> EntityInventory:
        """Map a single entity node to EntityInventory.

        Args:
            node: Entity data from API (minimal fields)

        Returns:
            Mapped EntityInventory instance with relation counts
        """
        pass

    def _save_entities(self, entities: List[EntityInventory]) -> None:
        """Save entity inventory records to repository.

        Args:
            entities: List of EntityInventory instances to save
        """
        self._repository.save_entity_inventory(entities)

    def extract(self) -> dict[str, Any]:
        """
        Execute map mode extraction for this entity type.

        Fetches all entities using cursor-based pagination, creates EntityInventory
        records with relation counts, and saves to entity_inventory table.

        Returns:
            Dictionary with extraction summary:
            - total_entities: Number of entities discovered
            - total_pages: Number of API pages fetched
            - entity_type: Name of entity type extracted
        """
        self._logger.info(f"Starting map mode extraction for {self._entity_type_name}")

        cursor = None
        has_next_page = True

        while has_next_page:
            # Fetch page
            response = self._fetch_page(cursor)

            # Extract edges and pagination info
            edges, page_info = self._extract_edges_and_page_info(response)

            # Map entities to EntityInventory
            entities = [self._map_entity(edge["node"]) for edge in edges]

            # Save batch
            if entities:
                self._save_entities(entities)
                self._total_entities += len(entities)

            self._total_pages += 1

            # Check for next page
            has_next_page = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            self._logger.debug(
                f"Processed page {self._total_pages} "
                f"({len(entities)} entities, total: {self._total_entities})"
            )

        self._logger.success(
            f"Completed map mode extraction for {self._entity_type_name}: "
            f"{self._total_entities} entities in {self._total_pages} pages"
        )

        return {
            "total_entities": self._total_entities,
            "total_pages": self._total_pages,
            "entity_type": self._entity_type_name,
        }

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format.

        Returns:
            ISO8601 formatted timestamp string
        """
        return datetime.utcnow().isoformat() + "Z"
