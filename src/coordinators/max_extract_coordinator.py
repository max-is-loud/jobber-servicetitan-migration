"""MaxExtractCoordinator for Phase 7 orchestration of multi-entity extraction."""

from typing import Any, List, Optional

from ..clients import JobberClient
from ..extractors import (
    ClientsExtractor,
    ExpensesExtractor,
    InvoicesExtractor,
    JobsExtractor,
    NotesExtractor,
    ProductServicesExtractor,
    PropertiesExtractor,
    QuotesExtractor,
    RequestsExtractor,
    TaxRatesExtractor,
    TimesheetEntriesExtractor,
    UsersExtractor,
    VisitsExtractor,
)
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..repositories import Repository


class MaxExtractCoordinator:
    """
    Orchestrates Pass 1 (metadata) extraction for all Jobber entities.

    Coordinates multi-entity extraction following dependency order to ensure
    foreign key relationships are maintained. Supports selective extraction
    and resumable operations via checkpoint-based progress tracking.

    Phase 7 Pattern:
    - Processes entities in dependency order (ENTITY_ORDER)
    - Each extractor manages its own pagination and checkpointing
    - Supports resume from last checkpoint per entity
    - Provides aggregated summary statistics
    """

    # Entity extraction order based on foreign key dependencies
    # Users extracted first (no dependencies), then entities that reference users/clients
    ENTITY_ORDER = [
        "users",  # No dependencies - extract first
        "clients",  # References users (assigned_user_id)
        "properties",  # References clients
        "requests",  # References clients, properties
        "quotes",  # References clients, properties, visits
        "jobs",  # References clients, properties, visits
        "visits",  # References clients, properties, jobs
        "invoices",  # References clients, jobs
        "expenses",  # References jobs
        "timesheet_entries",  # References users, jobs
        "product_services",  # No dependencies (catalog items)
        "tax_rates",  # No dependencies (configuration)
        "notes",  # References clients, jobs, quotes, requests, invoices
    ]

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        entity_mapper: EntityMapper,
    ) -> None:
        """Initialize coordinator with required dependencies.

        Args:
            jobber_client: GraphQL client for Jobber API
            repository: Database repository for persistence
            logger: Logger for structured output
            entity_mapper: Entity mapper for GraphQL transformations
        """
        self._jobber_client = jobber_client
        self._repository = repository
        self._logger = logger
        self._entity_mapper = entity_mapper
        self._extractors = self._build_extractors()

    def _build_extractors(self) -> dict[str, Any]:
        """Build extractor instances for all entity types.

        Creates instances of all available extractors with shared dependencies.
        Extractors are lazy-loaded - only those requested will be used.

        Returns:
            Dictionary mapping entity type names to extractor instances
        """
        return {
            "users": UsersExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "clients": ClientsExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "properties": PropertiesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "requests": RequestsExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "quotes": QuotesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "jobs": JobsExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "visits": VisitsExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "invoices": InvoicesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "expenses": ExpensesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "timesheet_entries": TimesheetEntriesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "product_services": ProductServicesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "tax_rates": TaxRatesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
            "notes": NotesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
            ),
        }

    def extract_all(
        self,
        entities: Optional[List[str]] = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        """Extract specified entities or all entities in dependency order.

        Processes entities following ENTITY_ORDER to maintain foreign key relationships.
        Each entity extraction is independently checkpointed for resume support.

        Args:
            entities: List of entity types to extract, or None for all (default: None)
            resume: If True, resume from last checkpoint for each entity (default: False)

        Returns:
            Dictionary with extraction summary:
            - total_entities: Total number of entities extracted across all types
            - results: Dict mapping entity type to extraction count
            - errors: List of any errors encountered

        Example:
            coordinator = MaxExtractCoordinator(...)
            summary = coordinator.extract_all(entities=["clients", "invoices"], resume=True)
        """
        # Determine which entities to extract
        entities_to_extract = entities or self.ENTITY_ORDER

        # Validate entity names
        invalid_entities = [e for e in entities_to_extract if e not in self._extractors]
        if invalid_entities:
            self._logger.warning(f"Unknown entities will be skipped: {invalid_entities}")
            entities_to_extract = [e for e in entities_to_extract if e in self._extractors]

        # Maintain dependency order even if subset requested
        ordered_entities = [e for e in self.ENTITY_ORDER if e in entities_to_extract]

        results = {}
        errors = []
        total_entities = 0

        self._logger.info(
            f"Starting max extraction: {len(ordered_entities)} entity types "
            f"(resume={resume})"
        )

        for entity_type in ordered_entities:
            try:
                self._logger.info(f"📦 Extracting: {entity_type}")

                extractor = self._extractors[entity_type]
                extractor.extract_all(resume=resume)

                # Get count from migration_state using extractor's entity_name
                # (entity_type is plural key like "product_services",
                # entity_name is singular like "product service")
                entity_name = extractor._entity_name
                state = self._repository.get_migration_state(entity_name)
                count = state.total_fetched if state else 0
                results[entity_type] = count
                total_entities += count

                self._logger.info(f"✓ Completed {entity_type}: {count} entities")

            except Exception as e:
                error_msg = f"Failed to extract {entity_type}: {e}"
                self._logger.error(error_msg)
                errors.append({"entity_type": entity_type, "error": str(e)})
                results[entity_type] = 0

        # Log summary
        self._logger.info(
            f"\n📊 Extraction Summary:\n"
            f"   Total entities extracted: {total_entities}\n"
            f"   Entity types processed: {len(results)}\n"
            f"   Errors: {len(errors)}"
        )

        return {
            "total_entities": total_entities,
            "results": results,
            "errors": errors,
        }
