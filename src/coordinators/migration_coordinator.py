"""Migration coordinator for orchestrating complete data migration workflow."""

import time

from ..clients import JobberClient
from ..exceptions import JobberApiError, MappingError, RepositoryError
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import MigrationSummary
from ..repositories import Repository


class MigrationCoordinator:
    """
    Orchestrates complete migration workflow from Jobber API to SQLite database.

    Coordinates the entire data migration process including initialization,
    cursor-based pagination, data transformation, persistence, and error handling.
    Maintains single responsibility by delegating business logic to injected
    dependencies.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
    ) -> None:
        """Initialize MigrationCoordinator with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger

    def migrate(self) -> MigrationSummary:
        """
        Execute complete migration workflow with error handling and progress tracking.

        Orchestrates the full migration process:
        1. Initialize database schema
        2. Migrate clients with cursor pagination
        3. Migrate invoices with cursor pagination
        4. Calculate timing and return structured summary

        Returns:
            MigrationSummary with processing counts, timing, and any errors

        Raises:
            RepositoryError: If database initialization fails
            JobberApiError: If API communication fails critically
            MappingError: If data transformation fails critically
        """
        start_time = time.time()
        start_time_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time))

        # Initialize summary for tracking
        summary = MigrationSummary(
            clients_processed=0,
            invoices_processed=0,
            start_time=start_time_iso,
            end_time="",
            duration_seconds=0.0,
            errors=[],
        )

        try:
            self._logger.info("Starting migration workflow")

            # Initialize database schema
            self._logger.info("Initializing database schema")
            self._repository.init_schema()

            # Migrate clients with cursor pagination
            self._logger.info("Starting client migration")
            summary.clients_processed = self._migrate_clients(summary)

            # Migrate invoices with cursor pagination
            self._logger.info("Starting invoice migration")
            summary.invoices_processed = self._migrate_invoices(summary)

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

    def _migrate_clients(self, summary: MigrationSummary) -> int:
        """
        Migrate all clients using cursor-based pagination.

        Implements GraphQL Connection specification cursor pagination to process
        all clients in batches, mapping and persisting each batch.

        Args:
            summary: Migration summary for error tracking

        Returns:
            Total number of clients processed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If client data transformation fails
            RepositoryError: If database operations fail
        """
        total_processed = 0
        cursor = None
        page_number = 1

        while True:
            try:
                self._logger.debug(f"Fetching clients page {page_number}")

                # Fetch page of clients from API
                response = self._jobber_client.fetch_clients(cursor)
                clients_data = response.get("data", {}).get("clients", {})

                # Extract edges and page info
                edges = clients_data.get("edges", [])
                page_info = clients_data.get("pageInfo", {})

                if not edges:
                    self._logger.debug("No more client data to process")
                    break

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
                    self._logger.info(
                        f"Processed {len(clients)} clients (total: {total_processed})"
                    )

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                if not has_next_page:
                    self._logger.debug("Reached last page of clients")
                    break

                # Update cursor for next iteration
                cursor = page_info.get("endCursor")
                page_number += 1

                # Add mandatory delay between pages to prevent API overload
                time.sleep(2.0)  # 2 second delay between pages
                self._logger.debug(f"Added 2s delay before page {page_number}")

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

    def _migrate_invoices(self, summary: MigrationSummary) -> int:
        """
        Migrate all invoices using cursor-based pagination.

        Implements GraphQL Connection specification cursor pagination to process
        all invoices in batches, mapping and persisting each batch.

        Args:
            summary: Migration summary for error tracking

        Returns:
            Total number of invoices processed

        Raises:
            JobberApiError: If API communication fails
            MappingError: If invoice data transformation fails
            RepositoryError: If database operations fail
        """
        total_processed = 0
        cursor = None
        page_number = 1

        while True:
            try:
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
                    self._logger.info(
                        f"Processed {len(invoices)} invoices (total: {total_processed})"
                    )

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                if not has_next_page:
                    self._logger.debug("Reached last page of invoices")
                    break

                # Update cursor for next iteration
                cursor = page_info.get("endCursor")
                page_number += 1

                # Add mandatory delay between pages to prevent API overload
                import time

                time.sleep(2.0)  # 2 second delay between pages
                self._logger.debug(f"Added 2s delay before invoice page {page_number}")

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
