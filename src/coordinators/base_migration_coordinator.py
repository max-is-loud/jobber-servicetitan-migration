"""Abstract base class for migration coordinators with Template Method pattern."""

import time
from abc import ABC, abstractmethod
from typing import Optional, Any

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..exceptions import JobberApiError, MappingError, RepositoryError
from ..extractors import (
    AttachmentDownloader,
    NoteReferenceCollector,
    NotesExtractor,
    QuotesExtractor,
)
from ..interfaces import Logger
from ..interfaces.migration_progress import MigrationProgressDisplay
from ..mappers import EntityMapper
from ..models import MigrationSummary
from ..performance import AdaptivePerformanceOptimizer
from ..repositories import Repository


class BaseMigrationCoordinator(ABC):
    """
    Abstract base class for migration coordinators with Template Method pattern.

    Extracts shared migration workflow logic from MigrationCoordinator and
    RichMigrationCoordinator to eliminate duplication. Implements the Template
    Method pattern following BaseExtractor design.

    Shared responsibilities:
    - Database schema initialization
    - Cursor-based pagination loops
    - Error handling and recovery
    - Timing calculations and progress tracking
    - Resume functionality with cursor management
    - Optional extractor integration
    - Adaptive performance optimization

    Subclasses implement display-specific progress feedback methods.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        note_reference_collector: Optional[NoteReferenceCollector] = None,
        notes_extractor: Optional[NotesExtractor] = None,
        quotes_extractor: Optional[QuotesExtractor] = None,
        attachment_downloader: Optional[AttachmentDownloader] = None,
        config_manager: Optional[ConfigManagerImpl] = None,
        resume: bool = False,
        enable_adaptive_optimization: bool = False,
    ) -> None:
        """Initialize BaseMigrationCoordinator with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            note_reference_collector: Optional collector for deferred note processing
            notes_extractor: Optional extractor for Note entities with deferred processing
            quotes_extractor: Optional extractor for Quote entities
            attachment_downloader: Optional downloader for Attachment files
            config_manager: Optional ConfigManager for delays and pagination settings
            resume: Whether to skip entities that already exist in database
            enable_adaptive_optimization: Whether to enable adaptive performance optimization
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._config_manager = config_manager or ConfigManagerImpl()
        self._resume = resume

        # Note reference collector for deferred note processing
        self._note_reference_collector = note_reference_collector

        # Optional extractors for enhanced entity coverage
        self._notes_extractor = notes_extractor
        self._quotes_extractor = quotes_extractor
        self._attachment_downloader = attachment_downloader

        # Adaptive performance optimization
        self._adaptive_optimizer: Optional[AdaptivePerformanceOptimizer] = None
        if enable_adaptive_optimization:
            self._adaptive_optimizer = AdaptivePerformanceOptimizer(
                config_manager=self._config_manager,
                logger=self._logger,
                target_throttle_rate=0.05,  # Allow 5% throttling
                optimization_interval=10,  # Optimize every 10 requests
            )

    @abstractmethod
    def _create_progress_display(self) -> Any:
        """Create and initialize progress display system.

        Template Method: Subclasses implement display-specific initialization.

        Returns:
            Display object (Progress for Rich UI, None for console logging)
        """
        ...

    @abstractmethod
    def _add_entity_task(
        self, display_obj: Any, entity_name: str, description: str
    ) -> Optional[Any]:
        """Add a new entity migration task to the progress display.

        Template Method: Subclasses implement display-specific task creation.

        Args:
            display_obj: Display object from _create_progress_display()
            entity_name: Name of entity type being migrated
            description: Initial task description

        Returns:
            Task identifier for updates (TaskID for Rich, None for console)
        """
        ...

    @abstractmethod
    def _update_task_progress(
        self,
        display_obj: Any,
        task_id: Optional[Any],
        description: str,
        completed: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        """Update progress for an existing task.

        Template Method: Subclasses implement display-specific progress updates.

        Args:
            display_obj: Display object from _create_progress_display()
            task_id: Task identifier from _add_entity_task()
            description: Updated task description
            completed: Current progress count
            total: Total expected count (if known)
        """
        ...

    @abstractmethod
    def _complete_task(
        self,
        display_obj: Any,
        task_id: Optional[Any],
        entity_name: str,
        final_count: int,
    ) -> None:
        """Mark a task as completed with final status.

        Template Method: Subclasses implement display-specific completion.

        Args:
            display_obj: Display object from _create_progress_display()
            task_id: Task identifier from _add_entity_task()
            entity_name: Name of entity type that was migrated
            final_count: Final number of entities processed
        """
        ...

    @abstractmethod
    def _start_display_context(self, display_obj: Any):
        """Start the display context manager (for Rich Live or console).

        Template Method: Subclasses implement display lifecycle management.

        Args:
            display_obj: Display object from _create_progress_display()

        Returns:
            Context manager for display lifecycle
        """
        ...

    def migrate(self, include_extended_entities: bool = True) -> MigrationSummary:
        """
        Execute complete migration workflow with Template Method pattern.

        Orchestrates the full migration process using Template Method:
        1. Initialize database schema
        2. Create progress display (subclass-specific)
        3. Migrate clients with cursor pagination
        4. Migrate invoices with cursor pagination
        5. Migrate quotes (if extractor provided and enabled)
        6. Migrate notes (if extractor provided and enabled)
        7. Migrate attachments with file downloads (if downloader provided and enabled)
        8. Calculate timing and return comprehensive summary

        Args:
            include_extended_entities: Whether to include Quote, Note, Attachment extraction

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
            attachments_processed=0,
            files_downloaded=0,
            total_bytes_downloaded=0,
            download_failures=0,
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

            # Create progress display (Template Method - subclass specific)
            display_obj = self._create_progress_display()

            # Start display context and execute migration workflow
            with self._start_display_context(display_obj):
                # Core entity migrations (backward compatibility)
                self._logger.info("Starting client migration")
                client_task = self._add_entity_task(
                    display_obj, "clients", "[cyan]Migrating clients..."
                )
                summary.clients_processed = self._migrate_clients(
                    summary, display_obj, client_task
                )
                self._complete_task(
                    display_obj, client_task, "clients", summary.clients_processed
                )

                self._logger.info("Starting invoice migration")
                invoice_task = self._add_entity_task(
                    display_obj, "invoices", "[cyan]Migrating invoices..."
                )
                summary.invoices_processed = self._migrate_invoices(
                    summary, display_obj, invoice_task
                )
                self._complete_task(
                    display_obj, invoice_task, "invoices", summary.invoices_processed
                )

                # Extended entity migrations (if enabled and extractors available)
                if include_extended_entities:
                    if self._quotes_extractor:
                        self._logger.info("Starting quote migration")
                        summary.quotes_processed = self._migrate_quotes(summary)
                    else:
                        self._logger.debug(
                            "Quote extraction skipped - no extractor provided"
                        )

                    # Process collected note references using deferred processing
                    if self._notes_extractor and self._note_reference_collector:
                        self._logger.info("Starting deferred note migration")
                        summary.notes_processed = self._migrate_deferred_notes(summary)
                    else:
                        self._logger.debug(
                            "Deferred note extraction skipped - no extractor or collector provided"
                        )

                    if self._attachment_downloader:
                        self._logger.info(
                            "Starting attachment migration with file downloads"
                        )
                        attachment_results = self._migrate_attachments(summary)
                        summary.attachments_processed = attachment_results["entities"]
                        summary.files_downloaded = attachment_results[
                            "files_downloaded"
                        ]
                        summary.total_bytes_downloaded = attachment_results[
                            "bytes_downloaded"
                        ]
                        summary.download_failures = attachment_results[
                            "download_failures"
                        ]
                    else:
                        self._logger.debug(
                            "Attachment extraction skipped - no downloader provided"
                        )
                else:
                    self._logger.info(
                        "Extended entity migration disabled - using legacy Client/Invoice only mode"
                    )

        except (RepositoryError, JobberApiError, MappingError) as e:
            self._logger.error(f"Critical migration error: {e}")
            summary.add_error(f"Critical error: {str(e)}")
            raise
        except Exception as e:
            self._logger.error(f"Unexpected migration error: {e}")
            summary.add_error(f"Unexpected error: {str(e)}")
            raise
        finally:
            # Calculate final timing
            end_time = time.time()
            summary.end_time = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time)
            )
            summary.duration_seconds = end_time - start_time

            # Update note reference count if collector was used
            if self._note_reference_collector:
                summary.note_references_collected = (
                    self._note_reference_collector.get_reference_count()
                )

            # Log comprehensive completion summary
            self._logger.info("Migration workflow completed")
            self._logger.info(summary.format_summary())

            # Log adaptive optimization performance summary
            if self._adaptive_optimizer:
                perf_summary = self._adaptive_optimizer.get_performance_summary()
                self._logger.info("🤖 Adaptive Optimization Performance Summary:")
                self._logger.info(
                    f"   • Total requests: {perf_summary['requests_made']}"
                )
                self._logger.info(
                    f"   • Throttle rate: {perf_summary['throttle_rate']}"
                )
                self._logger.info(
                    f"   • Final throughput: {perf_summary['current_throughput']}"
                )
                self._logger.info(
                    f"   • Final settings: {perf_summary['current_page_size']} per page, {perf_summary['current_page_delay']} delay"
                )
                self._logger.info(
                    f"   • Confidence: {perf_summary['confidence_score']}"
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
                self._logger.info(
                    f"🔄 Found saved cursor for {entity_type}: {migration_state.last_cursor}"
                )
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
        display_obj: Any = None,
        task_id: Optional[Any] = None,
    ) -> int:
        """
        Migrate all clients using cursor-based pagination.

        Implements GraphQL Connection specification cursor pagination to process
        all clients in batches, mapping and persisting each batch.
        Supports cursor resumption when resume mode is enabled.

        Args:
            summary: Migration summary for error tracking
            display_obj: Progress display object (optional)
            task_id: Task identifier for progress updates (optional)

        Returns:
            Total number of clients processed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If client data transformation fails
            RepositoryError: If database operations fail
        """
        # Initialize counter - if resuming, start from current database count
        cursor = self._get_resume_cursor("clients") if self._resume else None
        if self._resume and cursor:
            try:
                # Get current count from database when resuming
                existing_count = self._repository._connection.execute(
                    "SELECT COUNT(*) FROM clients"
                ).fetchone()[0]
                total_processed = existing_count
                self._logger.info(
                    f"🔄 Resuming client migration from saved cursor: {cursor}"
                )
                self._logger.info(
                    f"📊 Starting from {existing_count:,} existing clients in database"
                )
            except Exception as e:
                self._logger.error(f"Could not get existing client count: {e}")
                total_processed = 0
        else:
            total_processed = 0

        page_number = 1

        while True:
            # Track request timing for adaptive optimization
            request_start_time = time.time()
            was_throttled = False

            try:
                # Update progress display if available
                if display_obj and task_id is not None:
                    self._update_task_progress(
                        display_obj,
                        task_id,
                        f"[cyan]Fetching clients page {page_number}...",
                        completed=total_processed,
                    )

                self._logger.debug(f"Fetching clients page {page_number}")

                # Fetch page of clients from API
                try:
                    response = self._jobber_client.fetch_clients(cursor)
                    clients_data = response.get("data", {}).get("clients", {})
                except JobberApiError as e:
                    # Check if this was a throttling error
                    if "throttled" in str(e).lower():
                        was_throttled = True
                        # Re-raise to be handled by existing retry logic
                        raise
                    else:
                        # Non-throttling error, re-raise
                        raise

                request_time = time.time() - request_start_time

                # Extract edges and page info
                edges = clients_data.get("edges", [])
                page_info = clients_data.get("pageInfo", {})

                if not edges:
                    self._logger.debug("No more client data to process")
                    break

                # Update progress for processing
                if display_obj and task_id is not None:
                    self._update_task_progress(
                        display_obj,
                        task_id,
                        f"[cyan]Processing {len(edges)} clients from page {page_number}...",
                        completed=total_processed,
                    )

                # Map GraphQL nodes to domain models
                clients = []
                for edge in edges:
                    node = edge.get("node", {})
                    try:
                        client = self._entity_mapper.map_client(node)
                        clients.append(client)

                        # Collect note IDs for deferred processing if collector available
                        if self._note_reference_collector:
                            client_notes = node.get("notes", {}).get("edges", [])
                            self._note_reference_collector.collect_note_ids_from_edges(
                                client_notes, "client", client.id
                            )
                    except MappingError as e:
                        error_msg = (
                            f"Failed to map client {node.get('id', 'unknown')}: {e}"
                        )
                        self._logger.error(error_msg)
                        summary.add_error(error_msg)

                # Batch save clients to database
                if clients:
                    self._repository.save_clients(clients)
                    total_processed += len(clients)
                    self._logger.info(
                        f"Processed {len(clients)} clients (total: {total_processed})"
                    )

                    # Update progress with current count
                    if display_obj and task_id is not None:
                        self._update_task_progress(
                            display_obj,
                            task_id,
                            f"[cyan]Processed {total_processed:,} clients",
                            completed=total_processed,
                        )

                # Record performance metrics for adaptive optimization
                if self._adaptive_optimizer:
                    entities_received = len(clients) if clients else 0
                    self._adaptive_optimizer.record_request(
                        entities_received, request_time, was_throttled
                    )

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")

                # Save cursor progress after successful page processing
                if self._resume and cursor:
                    self._save_cursor_progress("clients", cursor)

                if not has_next_page:
                    self._logger.debug("Reached last page of clients")
                    break

                page_number += 1

                # Add delay between pages
                page_delay = self._config_manager.get_delay_config("page_delay")
                time.sleep(page_delay)

            except (JobberApiError, MappingError, RepositoryError) as e:
                # Record throttling for adaptive optimization if it was a throttling error
                if (
                    self._adaptive_optimizer
                    and isinstance(e, JobberApiError)
                    and "throttled" in str(e).lower()
                ):
                    # Estimate request time and record throttling
                    request_time = (
                        time.time() - request_start_time
                        if "request_start_time" in locals()
                        else 1.0
                    )
                    self._adaptive_optimizer.record_request(
                        0, request_time, was_throttled=True
                    )

                error_msg = f"Error processing clients page {page_number}: {e}"
                self._logger.error(error_msg)
                summary.add_error(error_msg)
                raise

        # Clean up cursor state after successful completion
        if self._resume:
            self._cleanup_cursor_state("clients")
            self._logger.debug(
                "✅ Completed client migration - cursor state cleaned up"
            )

        return total_processed

    def _migrate_invoices(
        self,
        summary: MigrationSummary,
        display_obj: Any = None,
        task_id: Optional[Any] = None,
    ) -> int:
        """
        Migrate all invoices using cursor-based pagination.

        Implements GraphQL Connection specification cursor pagination to process
        all invoices in batches, mapping and persisting each batch.
        Supports cursor resumption when resume mode is enabled.

        Args:
            summary: Migration summary for error tracking
            display_obj: Progress display object (optional)
            task_id: Task identifier for progress updates (optional)

        Returns:
            Total number of invoices processed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If invoice data transformation fails
            RepositoryError: If database operations fail
        """
        # Initialize counter - if resuming, start from current database count
        cursor = self._get_resume_cursor("invoices") if self._resume else None
        if self._resume and cursor:
            try:
                # Get current count from database when resuming
                existing_count = self._repository._connection.execute(
                    "SELECT COUNT(*) FROM invoices"
                ).fetchone()[0]
                total_processed = existing_count
                self._logger.info(
                    f"🔄 Resuming invoice migration from saved cursor: {cursor}"
                )
                self._logger.info(
                    f"📊 Starting from {existing_count:,} existing invoices in database"
                )
            except Exception as e:
                self._logger.error(f"Could not get existing invoice count: {e}")
                total_processed = 0
        else:
            total_processed = 0

        page_number = 1

        while True:
            try:
                # Update progress display if available
                if display_obj and task_id is not None:
                    self._update_task_progress(
                        display_obj,
                        task_id,
                        f"[cyan]Fetching invoices page {page_number}...",
                        completed=total_processed,
                    )

                self._logger.debug(f"Fetching invoices page {page_number}")

                # Fetch page of invoices from API
                response = self._jobber_client.fetch_invoices(cursor)
                invoices_data = response.get("data", {}).get("invoices", {})

                # Extract edges and page info
                edges = invoices_data.get("edges", [])
                page_info = invoices_data.get("pageInfo", {})

                if not edges:
                    self._logger.debug("No more invoice data to process")
                    break

                # Update progress for processing
                if display_obj and task_id is not None:
                    self._update_task_progress(
                        display_obj,
                        task_id,
                        f"[cyan]Processing {len(edges)} invoices from page {page_number}...",
                        completed=total_processed,
                    )

                # Map GraphQL nodes to domain models
                invoices = []
                for edge in edges:
                    node = edge.get("node", {})
                    try:
                        invoice = self._entity_mapper.map_invoice(node)
                        invoices.append(invoice)

                        # Collect note IDs for deferred processing if collector available
                        if self._note_reference_collector:
                            invoice_notes = node.get("notes", {}).get("edges", [])
                            self._note_reference_collector.collect_note_ids_from_edges(
                                invoice_notes, "invoice", invoice.id
                            )
                    except MappingError as e:
                        error_msg = (
                            f"Failed to map invoice {node.get('id', 'unknown')}: {e}"
                        )
                        self._logger.error(error_msg)
                        summary.add_error(error_msg)

                # Batch save invoices to database
                if invoices:
                    self._repository.save_invoices(invoices)
                    total_processed += len(invoices)
                    self._logger.info(
                        f"Processed {len(invoices)} invoices (total: {total_processed})"
                    )

                    # Update progress with current count
                    if display_obj and task_id is not None:
                        self._update_task_progress(
                            display_obj,
                            task_id,
                            f"[cyan]Processed {total_processed:,} invoices",
                            completed=total_processed,
                        )

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")

                # Save cursor progress after successful page processing
                if self._resume and cursor:
                    self._save_cursor_progress("invoices", cursor)

                if not has_next_page:
                    self._logger.debug("Reached last page of invoices")
                    break

                page_number += 1

                # Add delay between pages
                page_delay = self._config_manager.get_delay_config("page_delay")
                time.sleep(page_delay)

            except (JobberApiError, MappingError, RepositoryError) as e:
                error_msg = f"Error processing invoices page {page_number}: {e}"
                self._logger.error(error_msg)
                summary.add_error(error_msg)
                raise

        # Clean up cursor state after successful completion
        if self._resume:
            self._cleanup_cursor_state("invoices")
            self._logger.debug(
                "✅ Completed invoice migration - cursor state cleaned up"
            )

        return total_processed

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
            self._logger.debug(
                "Deferred note migration skipped - missing extractor or collector"
            )
            return 0

        try:
            # Get collected note references
            note_references = self._note_reference_collector.get_references()

            if not note_references:
                self._logger.info(
                    "No note references collected for deferred processing"
                )
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
                self._logger.info(
                    f"✅ Deferred note migration completed: {notes_processed} notes processed"
                )

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
            self._logger.info(
                "Quote migration requested but no QuotesExtractor provided"
            )
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

            self._logger.info(
                f"Quote migration completed: {result['entities_processed']} quotes processed"
            )
            return result["entities_processed"]

        except Exception as e:
            error_msg = f"Quote migration failed: {e}"
            self._logger.error(error_msg)
            summary.add_error(error_msg)
            raise

    def _migrate_attachments(self, summary: MigrationSummary) -> dict[str, int]:
        """
        Migrate all attachments using the dedicated AttachmentDownloader.

        Uses the injected AttachmentDownloader to handle cursor-based pagination,
        data transformation, file downloads, and persistence with comprehensive
        error handling.

        Args:
            summary: Migration summary for error tracking

        Returns:
            Dictionary with attachment migration metrics:
            - 'entities': Total number of attachments processed
            - 'files_downloaded': Number of files successfully downloaded
            - 'bytes_downloaded': Total bytes downloaded
            - 'download_failures': Number of download failures

        Raises:
            JobberApiError: If API communication fails
            MappingError: If attachment data transformation fails
            RepositoryError: If database operations fail
        """
        if not self._attachment_downloader:
            self._logger.info(
                "Attachment migration requested but no AttachmentDownloader provided"
            )
            return {
                "entities": 0,
                "files_downloaded": 0,
                "bytes_downloaded": 0,
                "download_failures": 0,
            }

        try:
            # Execute attachment extraction and download using dedicated downloader
            result = self._attachment_downloader.extract()

            # Track any errors from downloader summary
            downloader_summary = self._attachment_downloader.get_extraction_summary()
            if downloader_summary["error_count"] > 0:
                summary.add_error(
                    f"Attachment extraction completed with {downloader_summary['error_count']} recoverable errors"
                )

            files_downloaded = result.get("files_downloaded", 0)
            bytes_downloaded = result.get("total_bytes_downloaded", 0)
            download_failures = result.get("download_failures", 0)

            self._logger.info(
                f"Attachment migration completed: {result['entities_processed']} attachments processed, "
                f"{files_downloaded} files downloaded ({bytes_downloaded} bytes)"
            )

            return {
                "entities": result["entities_processed"],
                "files_downloaded": files_downloaded,
                "bytes_downloaded": bytes_downloaded,
                "download_failures": download_failures,
            }

        except Exception as e:
            error_msg = f"Attachment migration failed: {e}"
            self._logger.error(error_msg)
            summary.add_error(error_msg)
            raise
