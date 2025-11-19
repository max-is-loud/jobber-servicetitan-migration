"""Base class for migration coordinators with Rich UI and Template Method pattern."""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Column
from rich.text import Text

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..exceptions import JobberApiError, MappingError, RepositoryError
from ..extractors import (
    ClientsExtractor,
    InvoicesExtractor,
    NoteReferenceCollector,
    NotesExtractor,
    QuotesExtractor,
)
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import MigrationSummary
from ..performance import AdaptivePerformanceOptimizer
from ..repositories import Repository
from ..reports import MigrationReportGenerator


class BaseMigrationCoordinator:
    """
    Base class for migration coordinators with Rich UI and Template Method pattern.

    Provides shared migration workflow logic with Rich-based progress and error reporting.
    All progress display and error reporting uses Rich exclusively for enhanced
    visual feedback during migration operations.

    Shared responsibilities:
    - Database schema initialization
    - Cursor-based pagination loops
    - Error handling and recovery
    - Timing calculations and progress tracking
    - Resume functionality with cursor management
    - Optional extractor integration
    - Adaptive performance optimization
    - Rich-based progress bars and error panels
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        note_reference_collector: Optional[NoteReferenceCollector] = None,
        notes_extractor: Optional[NotesExtractor] = None,
        clients_extractor: Optional[ClientsExtractor] = None,
        invoices_extractor: Optional[InvoicesExtractor] = None,
        quotes_extractor: Optional[QuotesExtractor] = None,
        config_manager: Optional[ConfigManagerImpl] = None,
        resume: bool = False,
        enable_adaptive_optimization: bool = False,
        report_output_dir: Optional[Path] = None,
    ) -> None:
        """Initialize BaseMigrationCoordinator with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            note_reference_collector: Optional collector for deferred note processing
            notes_extractor: Optional extractor for Note entities with deferred processing
            clients_extractor: Optional extractor for Client entities
            invoices_extractor: Optional extractor for Invoice entities
            quotes_extractor: Optional extractor for Quote entities
            config_manager: Optional ConfigManager for delays and pagination settings
            resume: Whether to skip entities that already exist in database
            enable_adaptive_optimization: Whether to enable adaptive performance optimization
            report_output_dir: Optional directory for migration reports (default: ./reports)
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._config_manager = config_manager or ConfigManagerImpl()
        self._resume = resume
        self._report_output_dir = report_output_dir or Path("reports")

        # Note reference collector for deferred note processing
        self._note_reference_collector = note_reference_collector

        # Optional extractors for enhanced entity coverage
        self._clients_extractor = clients_extractor
        self._invoices_extractor = invoices_extractor
        self._notes_extractor = notes_extractor
        self._quotes_extractor = quotes_extractor

        # Rich console for progress and error display
        self._console = Console()

        # Adaptive performance optimization
        self._adaptive_optimizer: Optional[AdaptivePerformanceOptimizer] = None
        if enable_adaptive_optimization:
            self._adaptive_optimizer = AdaptivePerformanceOptimizer(
                config_manager=self._config_manager,
                logger=self._logger,
                target_throttle_rate=0.05,  # Allow 5% throttling
                optimization_interval=10,  # Optimize every 10 requests
            )

    def _create_progress_display(self) -> Progress:
        """Create Rich Progress display for migration tracking with custom columns.

        Returns:
            Rich Progress object with customized columns for migration workflows
        """
        return Progress(
            SpinnerColumn(),
            TextColumn(
                "[progress.description]{task.description}",
                table_column=Column(ratio=2, min_width=20),
            ),
            BarColumn(
                bar_width=None,
                complete_style="green",
                finished_style="bright_green",
                table_column=Column(ratio=3),
            ),
            MofNCompleteColumn(table_column=Column(min_width=12, justify="right")),
            TextColumn("•", justify="center"),
            TransferSpeedColumn(table_column=Column(min_width=12, justify="right")),
            TextColumn("•", justify="center"),
            TimeElapsedColumn(table_column=Column(min_width=8, justify="right")),
            TextColumn("/"),
            TimeRemainingColumn(table_column=Column(min_width=8, justify="right")),
            console=self._console,
            expand=True,
        )

    def _add_entity_task(self, display_obj: Progress, entity_name: str, description: str) -> TaskID:
        """Add a new entity migration task to Rich progress display.

        Args:
            display_obj: Rich Progress object from _create_progress_display()
            entity_name: Name of entity type being migrated
            description: Initial task description with Rich formatting

        Returns:
            TaskID for progress updates
        """
        return display_obj.add_task(description, total=None)

    def _add_indeterminate_task(self, display_obj: Progress, entity_name: str, description: str) -> TaskID:
        """Add a new indeterminate progress task for unknown totals.

        Args:
            display_obj: Rich Progress object from _create_progress_display()
            entity_name: Name of entity type being migrated
            description: Task description with Rich formatting

        Returns:
            TaskID for progress updates
        """
        return display_obj.add_task(description, total=None, start=False)

    def _start_task(self, display_obj: Progress, task_id: TaskID, total: Optional[int] = None) -> None:
        """Start an indeterminate task with optional total.

        Args:
            display_obj: Rich Progress object
            task_id: TaskID from _add_indeterminate_task()
            total: Total number of steps if known
        """
        display_obj.start_task(task_id)
        if total is not None:
            display_obj.update(task_id, total=total)

    def _update_task_progress(
        self,
        display_obj: Progress,
        task_id: Optional[TaskID],
        description: str,
        completed: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        """Update Rich progress display for existing task.

        Args:
            display_obj: Rich Progress object from _create_progress_display()
            task_id: TaskID from _add_entity_task()
            description: Updated task description with Rich formatting
            completed: Current progress count
            total: Total expected count (if known)
        """
        # Only update if we have a valid task_id
        if task_id is not None:
            if completed is not None and total is not None:
                display_obj.update(task_id, description=description, completed=completed, total=total)
            elif completed is not None:
                display_obj.update(task_id, description=description, completed=completed)
            else:
                display_obj.update(task_id, description=description)

    def _complete_task(
        self,
        display_obj: Progress,
        task_id: Optional[TaskID],
        entity_name: str,
        final_count: int,
    ) -> None:
        """Mark Rich progress task as completed with final status.

        Args:
            display_obj: Rich Progress object from _create_progress_display()
            task_id: TaskID from _add_entity_task()
            entity_name: Name of entity type that was migrated
            final_count: Final number of entities processed
        """
        # Only update if we have a valid task_id
        if task_id is not None:
            display_obj.update(
                task_id,
                description=f"[green]✓ {entity_name.title()} complete ({final_count:,} processed)",
                completed=final_count,
                total=final_count,
            )

    def _start_display_context(self, display_obj: Progress) -> Live:
        """Start Rich Live display context for real-time updates.

        Args:
            display_obj: Rich Progress object from _create_progress_display()

        Returns:
            Rich Live context manager for real-time display updates
        """
        return Live(display_obj, console=self._console, refresh_per_second=4)

    def _display_error_panel(self, title: str, message: str, error_type: str = "error") -> None:
        """Display a styled error panel using Rich.

        Args:
            title: Error panel title
            message: Error message content
            error_type: Type of error for styling ("error", "warning", "info")
        """
        style_map = {"error": "red", "warning": "yellow", "info": "blue"}

        style = style_map.get(error_type, "red")

        panel = Panel(
            Text(message, style="white"),
            title=f"[bold {style}]{title}[/bold {style}]",
            border_style=style,
            padding=(1, 2),
        )

        self._console.print()
        self._console.print(panel)
        self._console.print()

    def _print_exception(self, exception: Exception) -> None:
        """Print exception traceback using Rich formatting.

        Args:
            exception: Exception to display
        """
        self._console.print_exception(
            show_locals=False,
            max_frames=5,
            word_wrap=True,
            extra_lines=2,
        )

    def migrate(self, include_extended_entities: bool = True) -> MigrationSummary:
        """
        Execute complete migration workflow with Rich progress display.

        Orchestrates the full migration process using Rich progress bars:
        1. Initialize database schema
        2. Create Rich progress display
        3. Migrate clients with cursor pagination (includes notes & attachments inline)
        4. Migrate invoices with cursor pagination (includes notes & attachments inline)
        5. Migrate quotes (if extractor provided and enabled, includes notes & attachments inline)
        6. Migrate notes (if extractor provided and enabled, deferred note processing)
        7. Calculate timing and return comprehensive summary

        Note: Attachments are now extracted inline with parent entities (Client, Job, Quote,
        Request, Invoice) via their noteAttachments fields, not as a separate migration step.

        Args:
            include_extended_entities: Whether to include Quote and Note extraction

        Returns:
            MigrationSummary with processing counts, timing, and any errors

        Raises:
            RepositoryError: If database initialization fails
            JobberApiError: If API communication fails critically
            MappingError: If data transformation fails critically
        """
        start_time = time.time()
        start_time_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time))

        # Initialize comprehensive summary for tracking all entity types
        summary = MigrationSummary(
            clients_processed=0,
            invoices_processed=0,
            quotes_processed=0,
            notes_processed=0,
            note_references_collected=0,
            start_time=start_time_iso,
            end_time="",
            duration_seconds=0.0,
            errors=[],
        )

        try:
            self._logger.info("Starting comprehensive migration workflow")

            # Initialize database schema
            self._logger.info("Initializing database schema")
            self._repository.init_schema()

            # Create Rich progress display
            display_obj = self._create_progress_display()

            # Start display context and execute migration workflow
            with self._start_display_context(display_obj):
                # Core entity migrations (backward compatibility)
                self._logger.info("Starting client migration")
                client_task = self._add_entity_task(display_obj, "clients", "[cyan]Migrating clients...")
                summary.clients_processed = self._migrate_clients(summary, display_obj, client_task)
                self._complete_task(display_obj, client_task, "clients", summary.clients_processed)

                self._logger.info("Starting invoice migration")
                invoice_task = self._add_entity_task(display_obj, "invoices", "[cyan]Migrating invoices...")
                summary.invoices_processed = self._migrate_invoices(summary, display_obj, invoice_task)
                self._complete_task(display_obj, invoice_task, "invoices", summary.invoices_processed)

                # Extended entity migrations (if enabled and extractors available)
                if include_extended_entities:
                    if self._quotes_extractor:
                        self._logger.info("Starting quote migration")
                        summary.quotes_processed = self._migrate_quotes(summary)
                    else:
                        self._logger.debug("Quote extraction skipped - no extractor provided")

                    # Process collected note references using deferred processing
                    if self._notes_extractor and self._note_reference_collector:
                        self._logger.info("Starting deferred note migration")
                        summary.notes_processed = self._migrate_deferred_notes(summary)
                    else:
                        self._logger.debug("Deferred note extraction skipped - no extractor or collector provided")
                else:
                    self._logger.info("Extended entity migration disabled - using legacy Client/Invoice only mode")

        except (RepositoryError, JobberApiError, MappingError) as e:
            self._logger.error(f"Critical migration error: {e}")
            self._display_error_panel(
                "Critical Migration Error", f"Migration failed due to {type(e).__name__}: {str(e)}", "error"
            )
            summary.add_error(f"Critical error: {str(e)}")
            raise
        except Exception as e:
            self._logger.error(f"Unexpected migration error: {e}")
            self._display_error_panel("Unexpected Migration Error", f"An unexpected error occurred: {str(e)}", "error")
            self._print_exception(e)
            summary.add_error(f"Unexpected error: {str(e)}")
            raise
        finally:
            # Calculate final timing
            end_time = time.time()
            summary.end_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time))
            summary.duration_seconds = end_time - start_time

            # Update note reference count if collector was used
            if self._note_reference_collector:
                summary.note_references_collected = self._note_reference_collector.get_reference_count()

            # Log comprehensive completion summary
            self._logger.info("Migration workflow completed")
            self._logger.info(summary.format_summary())

            # Log adaptive optimization performance summary
            if self._adaptive_optimizer:
                perf_summary = self._adaptive_optimizer.get_performance_summary()
                self._logger.info("🤖 Adaptive Optimization Performance Summary:")
                self._logger.info(f"   • Total requests: {perf_summary['requests_made']}")
                self._logger.info(f"   • Throttle rate: {perf_summary['throttle_rate']}")
                self._logger.info(f"   • Final throughput: {perf_summary['current_throughput']}")
                self._logger.info(
                    f"   • Final settings: {perf_summary['current_page_size']} per page, {perf_summary['current_page_delay']} delay"
                )
                self._logger.info(f"   • Confidence: {perf_summary['confidence_score']}")

            # Generate migration reports
            self._generate_migration_reports(
                start_time=datetime.fromtimestamp(start_time),
                end_time=datetime.fromtimestamp(end_time)
            )

        return summary

    def migrate_legacy(self) -> MigrationSummary:
        """
        Execute legacy migration workflow (Client and Invoice only).

        Provides backward compatibility with existing systems that expect
        only Client and Invoice migration without extended entity types.

        Returns:
            MigrationSummary with Client and Invoice counts only
        """
        return self.migrate(include_extended_entities=False)

    def _get_resume_cursor(self, entity_type: str) -> Optional[str]:
        """Get resume cursor for the specified entity type.

        Args:
            entity_type: Entity type name (e.g., 'clients', 'invoices')

        Returns:
            Last saved cursor position, or None if no saved state exists
        """
        if not self._resume:
            return None

        try:
            migration_state = self._repository.get_migration_state(entity_type)
            if migration_state:
                self._logger.info(f"🔄 Found saved cursor for {entity_type}: {migration_state.last_cursor}")
                return migration_state.last_cursor
            return None
        except Exception as e:
            self._logger.debug(f"Failed to get resume cursor for {entity_type}: {e}")
            return None

    def _save_cursor_progress(self, entity_type: str, cursor: Optional[str]) -> None:
        """Save cursor progress for resumption.

        Args:
            entity_type: Entity type name (e.g., 'clients', 'invoices')
            cursor: Current cursor position to save
        """
        if not self._resume:
            return

        try:
            self._repository.save_migration_state(entity_type, cursor)
            self._logger.debug(f"Saved cursor progress for {entity_type}: {cursor}")
        except Exception as e:
            self._logger.debug(f"Failed to save cursor progress for {entity_type}: {e}")

    def _cleanup_cursor_state(self, entity_type: str) -> None:
        """Clean up cursor state after successful completion.

        Args:
            entity_type: Entity type name (e.g., 'clients', 'invoices')
        """
        if not self._resume:
            return

        try:
            self._repository.save_migration_state(entity_type, None)
            self._logger.debug(f"Cleaned up cursor state for {entity_type}")
        except Exception as e:
            self._logger.debug(f"Failed to cleanup cursor state for {entity_type}: {e}")

    def _migrate_clients(
        self,
        summary: MigrationSummary,
        display_obj: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
    ) -> int:
        """
        Migrate all clients using the dedicated ClientsExtractor.

        Uses the injected ClientsExtractor if available, otherwise falls back to
        inline extraction logic for backward compatibility.

        Args:
            summary: Migration summary for error tracking
            display_obj: Progress display object (optional, unused with extractor)
            task_id: Task identifier for progress updates (optional, unused with extractor)

        Returns:
            Total number of clients processed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If client data transformation fails
            RepositoryError: If database operations fail
        """
        if not self._clients_extractor:
            self._logger.warning("Client migration skipped: ClientsExtractor was not provided.")
            return 0

        try:
            # Execute client extraction using dedicated extractor
            result = self._clients_extractor.extract()

            # Track any errors from extractor summary
            extractor_summary = self._clients_extractor.get_extraction_summary()
            if extractor_summary["error_count"] > 0:
                summary.add_error(
                    f"Client extraction completed with {extractor_summary['error_count']} recoverable errors"
                )

            # Collect download metrics from extractor
            metrics = self._clients_extractor.get_download_metrics()
            summary.attachments_processed += metrics["attachments_processed"]
            summary.files_downloaded += metrics["files_downloaded"]
            summary.total_bytes_downloaded += metrics["bytes_downloaded"]
            summary.download_failures += metrics["download_failures"]
            summary.attachment_mapping_failures += metrics["attachment_mapping_failures"]

            return result["entities_processed"]

        except (JobberApiError, MappingError, RepositoryError) as e:
            error_msg = f"Client migration failed: {e}"
            self._logger.error(error_msg)

            # Display Rich error panel for user-friendly error display
            if isinstance(e, JobberApiError):
                self._display_error_panel(
                    "API Communication Error",
                    f"Failed to fetch clients: {str(e)}",
                    "warning" if "throttled" in str(e).lower() else "error",
                )
            elif isinstance(e, MappingError):
                self._display_error_panel(
                    "Data Transformation Error",
                    f"Failed to process client data: {str(e)}",
                    "error",
                )
            elif isinstance(e, RepositoryError):
                self._display_error_panel("Database Error", f"Failed to save clients: {str(e)}", "error")

            summary.add_error(error_msg)
            raise

    def _migrate_invoices(
        self,
        summary: MigrationSummary,
        display_obj: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
    ) -> int:
        """
        Migrate all invoices using the dedicated InvoicesExtractor.

        Uses the injected InvoicesExtractor if available, otherwise falls back to
        inline extraction logic for backward compatibility.

        Args:
            summary: Migration summary for error tracking
            display_obj: Progress display object (optional, unused with extractor)
            task_id: Task identifier for progress updates (optional, unused with extractor)

        Returns:
            Total number of invoices processed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If invoice data transformation fails
            RepositoryError: If database operations fail
        """
        if not self._invoices_extractor:
            self._logger.warning("Invoice migration skipped: InvoicesExtractor was not provided.")
            return 0

        try:
            # Execute invoice extraction using dedicated extractor
            result = self._invoices_extractor.extract()

            # Track any errors from extractor summary
            extractor_summary = self._invoices_extractor.get_extraction_summary()
            if extractor_summary["error_count"] > 0:
                summary.add_error(
                    f"Invoice extraction completed with {extractor_summary['error_count']} recoverable errors"
                )

            # Collect download metrics from extractor
            metrics = self._invoices_extractor.get_download_metrics()
            summary.attachments_processed += metrics["attachments_processed"]
            summary.files_downloaded += metrics["files_downloaded"]
            summary.total_bytes_downloaded += metrics["bytes_downloaded"]
            summary.download_failures += metrics["download_failures"]
            summary.attachment_mapping_failures += metrics["attachment_mapping_failures"]

            return result["entities_processed"]

        except (JobberApiError, MappingError, RepositoryError) as e:
            error_msg = f"Invoice migration failed: {e}"
            self._logger.error(error_msg)

            # Display Rich error panel for user-friendly error display
            if isinstance(e, JobberApiError):
                self._display_error_panel(
                    "API Communication Error",
                    f"Failed to fetch invoices: {str(e)}",
                    "warning" if "throttled" in str(e).lower() else "error",
                )
            elif isinstance(e, MappingError):
                self._display_error_panel(
                    "Data Transformation Error",
                    f"Failed to process invoice data: {str(e)}",
                    "error",
                )
            elif isinstance(e, RepositoryError):
                self._display_error_panel("Database Error", f"Failed to save invoices: {str(e)}", "error")

            summary.add_error(error_msg)
            raise

    def _migrate_deferred_notes(self, summary: MigrationSummary) -> int:
        """
        Process collected note references using deferred processing.

        This method processes notes that were collected as ID references during
        client and invoice migrations to avoid GraphQL throttling caused by
        nested queries. Enhanced with skip functionality to avoid unnecessary
        API calls for already-processed notes.

        Args:
            summary: Migration summary for error tracking and skip counts

        Returns:
            Total number of notes processed (not including skipped)

        Raises:
            JobberApiError: If API communication fails
            RepositoryError: If database operations fail
        """
        if not self._notes_extractor or not self._note_reference_collector:
            self._logger.debug("Deferred note migration skipped - missing extractor or collector")
            return 0

        try:
            # Get collected note references
            note_references = self._note_reference_collector.get_references()

            if not note_references:
                self._logger.info("No note references collected for deferred processing")
                return 0

            # Process notes using deferred processing with skip tracking
            result = self._notes_extractor.extract_deferred_notes(note_references)

            notes_processed = result["processed"]
            notes_skipped = result["skipped"]

            # Update summary with skip counts
            summary.notes_skipped += notes_skipped

            # Clear references after successful processing
            self._note_reference_collector.clear_references()

            if self._resume and notes_skipped > 0:
                self._logger.info(
                    f"✅ Deferred note migration completed: {notes_processed} notes processed, "
                    f"{notes_skipped} skipped"
                )
            else:
                self._logger.info(f"✅ Deferred note migration completed: {notes_processed} notes processed")

            return notes_processed

        except Exception as e:
            error_msg = f"Deferred note migration failed: {e}"
            self._logger.error(error_msg)
            summary.add_error(error_msg)
            raise

    def _migrate_quotes(self, summary: MigrationSummary) -> int:
        """
        Migrate all quotes using the dedicated QuotesExtractor.

        Uses the injected QuotesExtractor to handle cursor-based pagination,
        data transformation, and persistence with comprehensive error handling.

        Args:
            summary: Migration summary for error tracking

        Returns:
            Total number of quotes processed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If quote data transformation fails
            RepositoryError: If database operations fail
        """
        if not self._quotes_extractor:
            self._logger.info("Quote migration requested but no QuotesExtractor provided")
            return 0

        try:
            # Execute quote extraction using dedicated extractor
            result = self._quotes_extractor.extract()

            # Track any errors from extractor summary
            extractor_summary = self._quotes_extractor.get_extraction_summary()
            if extractor_summary["error_count"] > 0:
                summary.add_error(
                    f"Quote extraction completed with {extractor_summary['error_count']} recoverable errors"
                )

            # Collect download metrics from extractor
            metrics = self._quotes_extractor.get_download_metrics()
            summary.attachments_processed += metrics["attachments_processed"]
            summary.files_downloaded += metrics["files_downloaded"]
            summary.total_bytes_downloaded += metrics["bytes_downloaded"]
            summary.download_failures += metrics["download_failures"]
            summary.attachment_mapping_failures += metrics["attachment_mapping_failures"]

            self._logger.info(f"Quote migration completed: {result['entities_processed']} quotes processed")
            return result["entities_processed"]

        except Exception as e:
            error_msg = f"Quote migration failed: {e}"
            self._logger.error(error_msg)
            summary.add_error(error_msg)
            raise

    def _generate_migration_reports(
        self, start_time: datetime, end_time: datetime
    ) -> None:
        """Generate and save migration summary reports.

        Creates both text and JSON format reports summarizing extraction
        metrics from all active extractors.

        Args:
            start_time: Migration start timestamp
            end_time: Migration end timestamp
        """
        try:
            # Create report generator
            report = MigrationReportGenerator(migration_name="TightBeam Migration")
            report.set_timing(start_time, end_time)

            # Collect extractor summaries
            if self._clients_extractor:
                report.add_extractor_summary(
                    "clients", self._clients_extractor.get_extraction_summary()
                )

            if self._invoices_extractor:
                report.add_extractor_summary(
                    "invoices", self._invoices_extractor.get_extraction_summary()
                )

            if self._quotes_extractor:
                report.add_extractor_summary(
                    "quotes", self._quotes_extractor.get_extraction_summary()
                )

            if self._notes_extractor:
                report.add_extractor_summary(
                    "notes", self._notes_extractor.get_extraction_summary()
                )

            # Save reports
            text_path, json_path = report.save_reports(
                self._report_output_dir, include_timestamp=True
            )

            self._logger.info(f"📊 Migration reports saved:")
            self._logger.info(f"   • Text: {text_path}")
            self._logger.info(f"   • JSON: {json_path}")

        except (OSError, IOError, PermissionError) as e:
            self._logger.warning(
                f"Failed to save migration reports to {self._report_output_dir}: {e}. "
                "Check directory permissions or disk space."
            )
        except Exception as e:
            self._logger.warning(
                f"Failed to generate migration reports due to unexpected error: {e}"
            )
