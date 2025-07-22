"""Enhanced migration coordinator with Rich progress bars and status displays."""

import time

from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

from ..clients import JobberClient
from ..exceptions import JobberApiError, MappingError, RepositoryError
from ..interfaces import Logger
from ..loggers import RichLogger
from ..mappers import EntityMapper
from ..models import MigrationSummary
from ..repositories import Repository


class RichMigrationCoordinator:
    """Enhanced migration coordinator with Rich progress bars and visual feedback.

    Provides the same functionality as MigrationCoordinator but with enhanced
    visual feedback using Rich progress bars, status displays, and real-time
    updates during migration operations.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
    ) -> None:
        """Initialize migration coordinator with Rich enhancements.

        Args:
            jobber_client: Client for Jobber API operations
            entity_mapper: Mapper for transforming API data to domain models
            repository: Repository for database operations
            logger: Logger for progress and error reporting
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._console = Console()

        # Check if we have a RichLogger for enhanced features
        self._rich_logger = isinstance(logger, RichLogger)

    def migrate(self) -> MigrationSummary:
        """
        Execute complete migration workflow with Rich progress tracking.

        Coordinates the full migration process: schema initialization,
        client migration, and invoice migration with visual progress feedback.

        Returns:
            MigrationSummary containing migration results and statistics

        Raises:
            RepositoryError: If database operations fail
            JobberApiError: If API communication fails
            MappingError: If data transformation fails
        """
        # Initialize migration summary with start time
        start_time = time.time()
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
            start_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
            end_time="",
            duration_seconds=0.0,
            errors=[],
        )

        try:
            self._logger.info("Starting migration workflow")

            # Initialize database schema
            self._logger.info("Initializing database schema")
            self._repository.init_schema()

            # Create overall progress display
            progress = self._create_migration_progress()
            with Live(progress, console=self._console, refresh_per_second=4):
                # Migrate clients with visual progress
                client_task = progress.add_task(
                    "[cyan]Migrating clients...", total=None
                )

                self._logger.info("Starting client migration")
                summary.clients_processed = self._migrate_clients_with_progress(
                    summary, progress, client_task
                )
                progress.update(client_task, description="[green]✓ Clients complete")

                # Migrate invoices with visual progress
                invoice_task = progress.add_task(
                    "[cyan]Migrating invoices...", total=None
                )

                self._logger.info("Starting invoice migration")
                summary.invoices_processed = self._migrate_invoices_with_progress(
                    summary, progress, invoice_task
                )
                progress.update(invoice_task, description="[green]✓ Invoices complete")

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

            # Log completion summary
            self._logger.info(
                f"Migration completed: {summary.clients_processed} clients, "
                f"{summary.invoices_processed} invoices in {summary.format_duration()}"
            )

        return summary

    def _create_migration_progress(self) -> Progress:
        """Create a Rich Progress display for migration tracking."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self._console,
        )

    def _migrate_clients_with_progress(
        self, summary: MigrationSummary, progress: Progress, task_id: TaskID
    ) -> int:
        """Migrate clients with Rich progress tracking."""
        total_processed = 0
        cursor = None
        page_number = 1

        while True:
            try:
                # Update progress description
                progress.update(
                    task_id,
                    description=f"[cyan]Fetching clients page {page_number}...",
                )

                # Fetch page of clients from API
                response = self._jobber_client.fetch_clients(cursor)
                clients_data = response.get("data", {}).get("clients", {})

                # Extract edges and page info
                edges = clients_data.get("edges", [])
                page_info = clients_data.get("pageInfo", {})

                if not edges:
                    break

                # Update progress description for processing
                progress.update(
                    task_id,
                    description=f"[cyan]Processing {len(edges)} clients from page {page_number}...",  # noqa: E501
                )

                # Map GraphQL nodes to domain models
                clients = []
                for edge in edges:
                    node = edge.get("node", {})
                    try:
                        client = self._entity_mapper.map_client(node)
                        clients.append(client)
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

                    # Update progress with current count
                    progress.update(
                        task_id,
                        completed=total_processed,
                        description=f"[cyan]Processed {total_processed:,} clients",
                    )

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                if not has_next_page:
                    break

                # Update cursor for next iteration
                cursor = page_info.get("endCursor")
                page_number += 1

                # Add mandatory delay between pages
                time.sleep(2.0)

            except JobberApiError as e:
                error_msg = f"API error during client migration page {page_number}: {e}"
                self._logger.error(error_msg)
                summary.add_error(error_msg)
                raise
            except RepositoryError as e:
                error_msg = (
                    f"Database error during client migration page {page_number}: {e}"
                )
                self._logger.error(error_msg)
                summary.add_error(error_msg)
                raise

        return total_processed

    def _migrate_invoices_with_progress(
        self, summary: MigrationSummary, progress: Progress, task_id: TaskID
    ) -> int:
        """Migrate invoices with Rich progress tracking."""
        total_processed = 0
        cursor = None
        page_number = 1

        while True:
            try:
                # Update progress description
                progress.update(
                    task_id,
                    description=f"[cyan]Fetching invoices page {page_number}...",
                )

                # Fetch page of invoices from API
                response = self._jobber_client.fetch_invoices(cursor)
                invoices_data = response.get("data", {}).get("invoices", {})

                # Extract edges and page info
                edges = invoices_data.get("edges", [])
                page_info = invoices_data.get("pageInfo", {})

                if not edges:
                    break

                # Update progress description for processing
                progress.update(
                    task_id,
                    description=f"[cyan]Processing {len(edges)} invoices from page {page_number}...",  # noqa: E501
                )

                # Map GraphQL nodes to domain models
                invoices = []
                for edge in edges:
                    node = edge.get("node", {})
                    try:
                        invoice = self._entity_mapper.map_invoice(node)
                        invoices.append(invoice)
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

                    # Update progress with current count
                    progress.update(
                        task_id,
                        completed=total_processed,
                        description=f"[cyan]Processed {total_processed:,} invoices",
                    )

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                if not has_next_page:
                    break

                # Update cursor for next iteration
                cursor = page_info.get("endCursor")
                page_number += 1

                # Add mandatory delay between pages
                time.sleep(2.0)

            except JobberApiError as e:
                error_msg = (
                    f"API error during invoice migration page {page_number}: {e}"
                )
                self._logger.error(error_msg)
                summary.add_error(error_msg)
                raise
            except RepositoryError as e:
                error_msg = (
                    f"Database error during invoice migration page {page_number}: {e}"
                )
                self._logger.error(error_msg)
                summary.add_error(error_msg)
                raise

        return total_processed
