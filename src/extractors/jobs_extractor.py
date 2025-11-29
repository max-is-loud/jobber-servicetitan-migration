from __future__ import annotations

"""JobsExtractor for extracting Job entities from Jobber GraphQL API."""

from typing import Any

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Job
from ..repositories import Repository
from .base_extractor import BaseExtractor


class JobsExtractor(BaseExtractor[Job]):  # type: ignore[reportInvalidTypeArguments]
    """
    Extractor for Job entities implementing BaseExtractor.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for Job entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        config_manager: ConfigManagerImpl | None = None,
        skip_existing_entities: bool = False,
        **kwargs,
    ) -> None:
        """Initialize JobsExtractor with required dependencies.

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
            logger=logger,
            entity_type=Job,
            entity_name="job",
            config_manager=config_manager,
            skip_existing_entities=skip_existing_entities,
            **kwargs,
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: list[Job] = []

    def _fetch_page(self, cursor: str | None = None) -> dict[str, Any]:
        """Fetch a page of jobs from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_jobs(cursor)

    def _extract_edges_and_page_info(self, response: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Extract edges and page info from API response.

        Args:
            response: API response dictionary

        Returns:
            Tuple of (edges list, page_info dict)
        """
        jobs_data = response.get("data", {}).get("jobs", {})
        edges = jobs_data.get("edges", [])
        page_info = jobs_data.get("pageInfo", {})
        return edges, page_info

    def _map_entity(self, node: dict[str, Any]) -> Job:
        """Map a single job node to domain model.

        Args:
            node: Job data from API

        Returns:
            Mapped Job instance
        """
        return self._entity_mapper.map_job(node)

    def _save_entities(self, entities: list[Job]) -> None:
        """Save jobs to repository.

        Args:
            entities: List of jobs to save
        """
        self._repository.save_jobs(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract jobs data from GraphQL response."""
        return response.get("data", {}).get("jobs", {})

    def _extract_related_entities(self, node: dict[str, Any], primary_entity: Job) -> dict[str, Any]:
        """Extract notes and attachments related to the job.

        Extracts nested note and attachment data from the job query response.
        Both are fetched inline with the job query using optimized pagination
        (configurable via pagination.nested_notes) to reduce API costs.

        Args:
            node: Job data from API
            primary_entity: The job that was mapped

        Returns:
            Dictionary with notes and attachments lists
        """
        return self._extract_notes_and_attachments(node, primary_entity)

    def _save_related_entities(self, related_entities: dict[str, Any]) -> None:
        """Save notes and attachments related to jobss.

        Downloads attachment files and updates metadata with local file paths
        before saving to repository.

        Args:
            related_entities: Dictionary with notes and attachments lists
        """
        self._save_notes_and_attachments(related_entities)

    def _get_entities_from_last_batch(self) -> list[Job]:
        """Get jobs from the last extraction batch.

        Returns:
            List of jobs from last batch
        """
        return self._last_batch_entities

