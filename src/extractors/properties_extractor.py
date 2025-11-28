from __future__ import annotations

"""PropertiesExtractor for extracting Property entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Property
from ..repositories import Repository
from .base_extractor import BaseExtractor


class PropertiesExtractor(BaseExtractor[Property]):
    """
    Extractor for Property entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for Property entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    Properties are simpler than other entities as they don't have related notes
    or complex relationships. Focus is on proper address field handling and
    GPS coordinates.
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
        """Initialize PropertiesExtractor with required dependencies.

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
            entity_type=Property,
            entity_name="property",
            config_manager=config_manager,
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[Property] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of properties from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_properties(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[List[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        properties_data = response.get("data", {}).get("properties", {})
        edges = properties_data.get("edges", [])
        page_info = properties_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Property:
        """Map a single property node to domain model.

        Args:
            node: Property data from API

        Returns:
            Mapped Property instance
        """
        return self._entity_mapper.map_property(node)

    def _save_entities(self, entities: List[Property]) -> None:
        """Save properties to repository.

        Args:
            entities: List of properties to save
        """
        self._repository.save_properties(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract properties data from GraphQL response."""
        return response.get("data", {}).get("properties", {})

    def _extract_related_entities(self, node: dict[str, Any], primary_entity: Property) -> dict[str, List[Note]]:
        """Extract related entities from property node.

        Properties don't have related notes or other complex relationships,
        so this always returns an empty dictionary.

        Args:
            node: Property data from API
            primary_entity: The property that was mapped

        Returns:
            Empty dictionary as properties have no related entities
        """
        return {}

    def _save_related_entities(self, related_entities: dict[str, List[Note]]) -> None:
        """Save related entities for properties.

        Properties don't have related entities, so this is a no-op.

        Args:
            related_entities: Dictionary with related entities (always empty)
        """
        pass

    def _get_entities_from_last_batch(self) -> List[Property]:
        """Get properties from the last extraction batch.

        Returns:
            List of properties from last batch
        """
        return self._last_batch_entities

