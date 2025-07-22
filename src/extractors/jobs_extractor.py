"""JobsExtractor for extracting Job entities from Jobber GraphQL API."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..exceptions import MappingError
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
    ) -> None:
        """Initialize JobsExtractor with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
        """
        super().__init__(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            entity_type=Job,
            entity_name="job",
        )
        # Track entities from last batch for extract_all
        self._last_batch_entities: List[Job] = []

    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """Fetch a page of jobs from the Jobber API.

        Args:
            cursor: Optional pagination cursor

        Returns:
            API response dictionary
        """
        return self._jobber_client.fetch_jobs(cursor)

    def _extract_edges_and_page_info(
        self, response: dict[str, Any]
    ) -> tuple[List[dict[str, Any]], dict[str, Any]]:
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

    def _save_entities(self, entities: List[Job]) -> None:
        """Save jobs to repository.

        Args:
            entities: List of jobs to save
        """
        self._repository.save_jobs(entities)
        # Track for extract_all
        self._last_batch_entities = entities

    def _extract_related_entities(
        self, node: dict[str, Any], primary_entity: Job
    ) -> dict[str, List[Any]]:
        """Extract notes related to the job.

        Args:
            node: Job data from API
            primary_entity: The job that was mapped

        Returns:
            Dictionary with notes list
        """
        related = {}

        # Extract notes if present
        job_notes = node.get("notes", {}).get("edges", [])
        if job_notes:
            notes = []
            for note_edge in job_notes:
                note_node = note_edge.get("node", {})
                if note_node:
                    # Add job relationship to note data
                    note_node["job"] = {"id": primary_entity.id}
                    try:
                        note = self._entity_mapper.map_note(note_node)
                        notes.append(note)
                    except MappingError as e:
                        self._logger.debug(
                            f"Failed to map note for job {primary_entity.id}: {e}"
                        )
            if notes:
                related["notes"] = notes

        return related

    def _save_related_entities(self, related_entities: dict[str, List[Any]]) -> None:
        """Save notes related to jobs.

        Args:
            related_entities: Dictionary with notes list
        """
        notes = related_entities.get("notes", [])
        if notes:
            self._repository.save_notes(notes)

    def _get_entities_from_last_batch(self) -> List[Job]:
        """Get jobs from the last extraction batch.

        Returns:
            List of jobs from last batch
        """
        return self._last_batch_entities

    def get_entity_count(self) -> int:
        """Get total count of jobs available for extraction.

        Performs a lightweight API call to determine the total number of jobs
        available for extraction without actually extracting data.

        Returns:
            Total number of jobs available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        self._logger.debug("Fetching total job count from API")

        # Use minimal query to get just the count
        response = self._jobber_client.fetch_jobs(cursor=None)
        jobs_data = response.get("data", {}).get("jobs", {})
        page_info = jobs_data.get("pageInfo", {})

        # If API provides totalCount, use it
        total_count = jobs_data.get("totalCount")
        if total_count is not None:
            self._logger.debug(f"API reported total job count: {total_count}")
            return int(total_count)

        # Otherwise estimate from first page
        edges = jobs_data.get("edges", [])
        if not edges:
            return 0

        # Rough estimate based on first page size and hasNextPage
        page_size = len(edges)
        if not page_info.get("hasNextPage", False):
            return page_size

        # Can't determine exact count without pagination
        self._logger.info("Cannot determine exact job count without full pagination")
        return -1  # Indicate unknown count
