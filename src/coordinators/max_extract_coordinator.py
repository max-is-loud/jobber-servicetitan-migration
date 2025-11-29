"""MaxExtractCoordinator for orchestration of multi-entity extraction with Rich UI."""

from datetime import datetime
from typing import Any, List, Optional

from ..cli.services.shared import SharedServices
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
from ..extractors.note_reference_collector import NoteReferenceCollector
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models.migration_summary import MigrationSummary
from ..repositories import Repository
from ..ui.migration_ui import MigrationUI


class MaxExtractCoordinator:
    """
    Orchestrates multi-entity extraction for all Jobber entities with unified Rich UI.

    Coordinates multi-entity extraction following dependency order to ensure
    foreign key relationships are maintained. Supports selective extraction
    and resumable operations via checkpoint-based progress tracking.

    Features:
    - Processes entities in dependency order (ENTITY_ORDER)
    - Each extractor manages its own pagination and checkpointing
    - Supports resume from last checkpoint per entity
    - Provides real-time progress feedback via MigrationUI
    - Aggregated summary statistics with Rich terminal output
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
        migration_ui: Optional[MigrationUI] = None,
        db_path: Optional[str] = None,
    ) -> None:
        """Initialize coordinator with required dependencies.

        Args:
            jobber_client: GraphQL client for Jobber API
            repository: Database repository for persistence
            logger: Logger for structured output
            entity_mapper: Entity mapper for GraphQL transformations
            migration_ui: Optional MigrationUI for Rich UI output (creates default if not provided)
            db_path: Optional database path for display purposes
        """
        self._jobber_client = jobber_client
        self._repository = repository
        self._logger = logger
        self._entity_mapper = entity_mapper
        self._db_path = db_path

        # Create or use provided MigrationUI
        if migration_ui is None:
            console = SharedServices.get_console()
            self._migration_ui = MigrationUI(console)
        else:
            self._migration_ui = migration_ui

        # Create note reference collector for deferred note loading
        self._note_collector = NoteReferenceCollector(
            repository=repository,
            logger=logger,
            enable_persistence=True,  # Persist note references to database
        )

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
                note_reference_collector=self._note_collector,
            ),
            "clients": ClientsExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
                note_reference_collector=self._note_collector,
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
                note_reference_collector=self._note_collector,
            ),
            "quotes": QuotesExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
                note_reference_collector=self._note_collector,
            ),
            "jobs": JobsExtractor(
                jobber_client=self._jobber_client,
                entity_mapper=self._entity_mapper,
                repository=self._repository,
                logger=self._logger,
                note_reference_collector=self._note_collector,
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
                note_reference_collector=self._note_collector,
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

    def _build_summary(
        self,
        results: dict[str, int],
        errors: list[dict],
        total_entities: int
    ) -> MigrationSummary:
        """Build MigrationSummary from extraction results.

        Args:
            results: Dictionary mapping entity type to count
            errors: List of error dictionaries
            total_entities: Total entities extracted

        Returns:
            MigrationSummary instance with all metrics
        """
        # Get current timestamp for end_time
        end_time = datetime.now().isoformat()

        # Build error list from error dicts
        error_messages = [f"{e['entity_type']}: {e['error']}" for e in errors]

        # Create MigrationSummary with minimal required fields
        # Note: This is simplified - actual migrations would track more metrics
        return MigrationSummary(
            clients_processed=results.get("clients", 0),
            invoices_processed=results.get("invoices", 0),
            quotes_processed=results.get("quotes", 0),
            notes_processed=results.get("notes", 0),
            note_references_collected=0,  # Tracked separately by note collector
            start_time=end_time,  # We don't track start time in current implementation
            end_time=end_time,
            duration_seconds=0.0,  # We don't track duration in current implementation
            errors=error_messages,
            # Additional entity counts
            attachments_processed=0,  # Attachments extracted inline, not tracked here
            files_downloaded=0,  # Not relevant for metadata extraction
            total_bytes_downloaded=0,  # Not relevant for metadata extraction
        )

    def extract_all(
        self,
        entities: Optional[List[str]] = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        """Extract specified entities or all entities in dependency order.

        Processes entities following ENTITY_ORDER to maintain foreign key relationships.
        Each entity extraction is independently checkpointed for resume support.
        Uses MigrationUI for Rich-based progress display and summary reporting.

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

        # Show run header with database path
        self._migration_ui.show_run_header(
            db_path=self._db_path,
            config=None  # No config manager currently integrated
        )

        # Create logger adapter to redirect logs to UI and file
        ui_logger = self._migration_ui.create_logger_adapter()

        # Log session start
        from datetime import datetime
        ui_logger.info("=" * 80)
        ui_logger.info(f"Migration session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        ui_logger.info(f"Database: {self._db_path}")
        ui_logger.info(f"Entities to extract: {', '.join(ordered_entities)}")
        ui_logger.info(f"Resume mode: {resume}")
        ui_logger.info("=" * 80)

        # Start entity progress display
        self._migration_ui.start_entity_progress(ordered_entities)

        results = {}
        errors = []
        total_entities = 0

        ui_logger.info(
            f"Starting max extraction: {len(ordered_entities)} entity types "
            f"(resume={resume})"
        )

        try:
            for entity_type in ordered_entities:
                try:
                    ui_logger.info(f"📦 Extracting: {entity_type}")

                    # Get extractor
                    extractor = self._extractors[entity_type]
                    entity_name = extractor._entity_name

                    # Replace extractor's logger with UI logger
                    original_logger = extractor._logger
                    extractor._logger = ui_logger

                    # Set progress callback BEFORE extraction
                    # (total_count will be set by extractor during first API call)
                    def progress_callback(completed: int, ext: Any = extractor, ent_type: str = entity_type) -> None:
                        total_count = getattr(ext, '_total_count', None)
                        self._migration_ui.update_entity_progress(ent_type, completed, total_count)

                    extractor._progress_callback = progress_callback

                    # Extract all entities
                    extractor.extract_all(resume=resume)

                    # Restore original logger
                    extractor._logger = original_logger

                    # Get final count from migration_state
                    state = self._repository.get_migration_state(entity_name)
                    count = state.total_fetched if state else 0
                    results[entity_type] = count
                    total_entities += count

                    # Get total count from extractor for final progress update
                    total_count = getattr(extractor, '_total_count', None)

                    # Update progress (complete - removes progress bar)
                    self._migration_ui.update_entity_progress(entity_type, count, total_count, finished=True)

                    ui_logger.info(f"✓ Completed {entity_type}: {count} entities")

                except KeyboardInterrupt:
                    # Re-raise to handle in outer try/except
                    raise

                except Exception as e:
                    error_msg = f"Failed to extract {entity_type}: {e}"
                    ui_logger.error(error_msg)
                    errors.append({"entity_type": entity_type, "error": str(e)})
                    results[entity_type] = 0

            # Log summary
            ui_logger.info(
                f"\n📊 Extraction Summary:\n"
                f"   Total entities extracted: {total_entities}\n"
                f"   Entity types processed: {len(results)}\n"
                f"   Errors: {len(errors)}"
            )

            # Build and show migration summary with Rich UI
            migration_summary = self._build_summary(results, errors, total_entities)
            self._migration_ui.show_run_summary(migration_summary, metrics=None)

        except KeyboardInterrupt:
            self._migration_ui.show_keyboard_interrupt()
            raise

        except Exception as e:
            self._migration_ui.show_error(e)
            raise

        finally:
            # Always finalize UI
            self._migration_ui.finalize()

        return {
            "total_entities": total_entities,
            "results": results,
            "errors": errors,
        }
