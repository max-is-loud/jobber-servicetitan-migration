from __future__ import annotations

"""UsersExtractor for extracting User entities from Jobber GraphQL API."""

from typing import Any

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..exceptions import MappingError
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Note, User
from ..repositories import Repository
from .base_extractor import BaseExtractor


class UsersExtractor(BaseExtractor[User]):
    """
    Extractor for User entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for User entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.

    Users represent team members and may have associated notes for tracking
    performance, permissions, and administrative information.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        config_manager: ConfigManagerImpl | None = None,
        skip_existing_entities: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize UsersExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            config_manager: Optional ConfigManager for delays and pagination settings
            skip_existing_entities: Whether to skip entities that already exist in database
            **kwargs: Reserved for future use
        """
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            config_manager=config_manager,
            logger=logger,
            entity_type=User,
            entity_name="user",
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: list[User] = []

    def _fetch_page(self, cursor: str | None = None) -> dict[str, Any]:
        """Fetch a page of users from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_users(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        users_data = response.get("data", {}).get("users", {})
        edges = users_data.get("edges", [])
        page_info = users_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> User:
        """Map a single user node to domain model.

        Args:
            node: User data from API

        Returns:
            Mapped User instance
        """
        return self._entity_mapper.map_user(node)

    def _save_entities(self, entities: list[User]) -> None:
        """Save users to repository.

        Args:
            entities: List of users to save
        """
        self._repository.save_users(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract users data from GraphQL response."""
        return response.get("data", {}).get("users", {})

    def _extract_related_entities(self, node: dict[str, Any], primary_entity: User) -> dict[str, list[Note]]:
        """Extract notes related to the user.

        Args:
            node: User data from API
            primary_entity: The user that was mapped

        Returns:
            Dictionary with notes list
        """
        related = {}

        # Extract notes if present
        user_notes = node.get("notes", {}).get("edges", [])
        if user_notes:
            notes = []
            for note_edge in user_notes:
                note_node = note_edge.get("node", {})
                if note_node:
                    # Add user relationship to note data
                    note_node["user"] = {"id": primary_entity.id}
                    try:
                        note = self._entity_mapper.map_note(note_node)
                        notes.append(note)
                    except MappingError as e:
                        self._logger.debug(f"Failed to map note for user {primary_entity.id}: {e}")
            if notes:
                related["notes"] = notes

        return related

    def _save_related_entities(self, related_entities: dict[str, list[Note]]) -> None:
        """Save notes related to users.

        Args:
            related_entities: Dictionary with notes list
        """
        notes = related_entities.get("notes", [])
        if notes:
            self._repository.save_notes(notes)

    def _get_entities_from_last_batch(self) -> list[User]:
        """Get users from the last extraction batch.

        Returns:
            List of users from last batch
        """
        return self._last_batch_entities

