"""QuotesExtractor for extracting Quote entities from Jobber GraphQL API."""

import time
from typing import Any, List, Union

from ..clients import JobberClient
from ..exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    RepositoryError,
)
from ..interfaces import BaseExtractor, Logger
from ..mappers import EntityMapper
from ..models import Attachment, Client, Invoice, Note, Quote
from ..repositories import Repository


class QuotesExtractor:
    """
    Extractor for Quote entities implementing BaseExtractor protocol.

    Provides modular OO extraction as specified in PRD Section 3.1, handling
    cursor-based pagination and data transformation for Quote entities from
    Jobber GraphQL API. Uses dependency injection for testability and modularity.
    """

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
    ) -> None:
        """Initialize QuotesExtractor with required dependencies.

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

        # Extraction state tracking
        self._last_extraction_summary = {
            "total_entities": 0,
            "total_pages": 0,
            "extraction_duration": 0.0,
            "average_page_size": 0.0,
            "entities_per_second": 0.0,
            "last_cursor": None,
            "extraction_status": "pending",
            "error_count": 0,
        }

    def extract(
        self,
        cursor: str | None = None,
        page_limit: int | None = None,
    ) -> dict[str, Any]:
        """Extract quotes from Jobber GraphQL API with cursor-based pagination.

        Performs complete extraction workflow including:
        - GraphQL API calls with cursor pagination
        - Data transformation via EntityMapper
        - Batch persistence via Repository
        - Progress logging and error handling

        Args:
            cursor: Optional pagination cursor for continuing extraction
            page_limit: Optional limit on number of pages to process (for testing)

        Returns:
            Dictionary containing extraction results with keys:
            - 'entities_processed': int - Total number of entities extracted
            - 'pages_processed': int - Number of API pages processed
            - 'has_next_page': bool - Whether more pages are available
            - 'end_cursor': Optional[str] - Final cursor for continuation
            - 'extraction_time': float - Total extraction time in seconds

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
            RepositoryError: If database operations fail
        """
        start_time = time.time()
        entities_processed = 0
        pages_processed = 0
        current_cursor = cursor
        error_count = 0
        page_info = {}  # Initialize page_info

        self._logger.info(f"Starting quotes extraction from cursor: {cursor}")

        try:
            while True:
                # Check page limit for testing
                if page_limit is not None and pages_processed >= page_limit:
                    self._logger.debug(f"Reached page limit: {page_limit}")
                    break

                # Fetch page of quotes from API
                self._logger.debug(f"Fetching quotes page {pages_processed + 1}")
                response = self._jobber_client.fetch_quotes(current_cursor)
                quotes_data = response.get("data", {}).get("quotes", {})

                # Extract edges and page info
                edges = quotes_data.get("edges", [])
                page_info = quotes_data.get("pageInfo", {})

                if not edges:
                    self._logger.debug("No more quote data to process")
                    break

                # Map GraphQL nodes to domain models
                quotes = []
                for edge in edges:
                    node = edge.get("node", {})
                    try:
                        quote = self._entity_mapper.map_quote(node)
                        quotes.append(quote)
                    except MappingError as e:
                        error_msg = (
                            f"Failed to map quote {node.get('id', 'unknown')}: {e}"
                        )
                        self._logger.error(error_msg)
                        error_count += 1

                # Batch save quotes to database
                if quotes:
                    self._repository.save_quotes(quotes)
                    entities_processed += len(quotes)
                    self._logger.info(
                        f"Processed {len(quotes)} quotes "
                        f"(total: {entities_processed})"
                    )

                pages_processed += 1

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                end_cursor = page_info.get("endCursor")

                if not has_next_page:
                    self._logger.debug("Reached last page of quotes")
                    break

                # Update cursor for next iteration
                current_cursor = end_cursor

                # Add delay between pages to prevent API overload
                time.sleep(1.0)
                self._logger.debug(f"Added 1s delay before page {pages_processed + 1}")

            extraction_time = time.time() - start_time

            # Update extraction summary
            self._update_extraction_summary(
                entities_processed,
                pages_processed,
                extraction_time,
                current_cursor,
                "completed",
                error_count,
            )

            result = {
                "entities_processed": entities_processed,
                "pages_processed": pages_processed,
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": current_cursor,
                "extraction_time": extraction_time,
            }

            self._logger.info(
                f"Quotes extraction completed: {entities_processed} quotes, "
                f"{pages_processed} pages in {extraction_time:.2f}s"
            )

            return result

        except Exception as e:
            extraction_time = time.time() - start_time
            self._update_extraction_summary(
                entities_processed,
                pages_processed,
                extraction_time,
                current_cursor,
                "failed",
                error_count,
            )
            self._logger.error(f"Quotes extraction failed: {e}")
            raise

    def extract_all(self) -> List[Union[Client, Invoice, Quote, Note, Attachment]]:
        """Extract all quotes with automatic pagination until completion.

        Continuously calls extract() with cursor pagination until all available
        quotes are processed. Provides complete dataset extraction with
        comprehensive progress logging and error recovery.

        Returns:
            List of all extracted Quote objects

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
            RepositoryError: If database operations fail
        """
        all_quotes = []
        cursor = None

        self._logger.info("Starting complete quotes extraction")

        while True:
            result = self.extract(cursor=cursor)

            # Get quotes from database for this batch
            quotes_batch = self._repository.get_all_quotes()
            if quotes_batch:
                # Filter quotes for this extraction session
                batch_start = len(all_quotes)
                new_quotes = quotes_batch[
                    batch_start : batch_start + result["entities_processed"]
                ]
                all_quotes.extend(new_quotes)

            if not result["has_next_page"]:
                break

            cursor = result["end_cursor"]

        self._logger.info(
            f"Complete quotes extraction finished: {len(all_quotes)} quotes"
        )
        return all_quotes

    def get_entity_count(self) -> int:
        """Get total count of quotes available for extraction.

        Performs a lightweight API call to determine the total number of quotes
        available for extraction without actually extracting data. Useful for
        progress estimation and extraction planning.

        Returns:
            Total number of quotes available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        # For now, we'll use the complete extraction approach
        # In a production system, this could use a count-only GraphQL query
        total_count = 0
        cursor = None

        while True:
            response = self._jobber_client.fetch_quotes(cursor)
            quotes_data = response.get("data", {}).get("quotes", {})

            edges = quotes_data.get("edges", [])
            page_info = quotes_data.get("pageInfo", {})

            total_count += len(edges)

            if not page_info.get("hasNextPage", False):
                break

            cursor = page_info.get("endCursor")

        return total_count

    def validate_dependencies(self) -> bool:
        """Validate that all required dependencies are properly configured.

        Checks that JobberClient, EntityMapper, Repository, and Logger
        dependencies are properly injected and configured for extraction.
        Ensures extraction can proceed without runtime failures.

        Returns:
            True if all dependencies are valid and ready for extraction

        Raises:
            ConfigurationError: If any required dependency is missing or invalid
        """
        if not self._jobber_client:
            raise ConfigurationError("JobberClient dependency is required")
        if not self._entity_mapper:
            raise ConfigurationError("EntityMapper dependency is required")
        if not self._repository:
            raise ConfigurationError("Repository dependency is required")
        if not self._logger:
            raise ConfigurationError("Logger dependency is required")

        # Test basic functionality
        try:
            # Verify JobberClient has required methods
            if not hasattr(self._jobber_client, "fetch_quotes"):
                raise ConfigurationError("JobberClient missing fetch_quotes method")

            # Verify EntityMapper has required methods
            if not hasattr(self._entity_mapper, "map_quote"):
                raise ConfigurationError("EntityMapper missing map_quote method")

            # Verify Repository has required methods
            if not hasattr(self._repository, "save_quotes"):
                raise ConfigurationError("Repository missing save_quotes method")

            return True

        except Exception as e:
            raise ConfigurationError(f"Dependency validation failed: {e}") from e

    def get_extraction_summary(self) -> dict[str, Any]:
        """Get summary statistics of the last extraction operation.

        Provides detailed metrics and status information from the most recent
        extract() or extract_all() operation for monitoring and reporting.

        Returns:
            Dictionary containing extraction summary with keys:
            - 'total_entities': int - Total entities processed
            - 'total_pages': int - Total API pages processed
            - 'extraction_duration': float - Total time in seconds
            - 'average_page_size': float - Average entities per page
            - 'entities_per_second': float - Processing rate
            - 'last_cursor': Optional[str] - Final pagination cursor
            - 'extraction_status': str - 'completed', 'partial', or 'failed'
            - 'error_count': int - Number of recoverable errors encountered
        """
        return self._last_extraction_summary.copy()

    def _update_extraction_summary(
        self,
        total_entities: int,
        total_pages: int,
        extraction_duration: float,
        last_cursor: str | None,
        status: str,
        error_count: int,
    ) -> None:
        """Update internal extraction summary statistics."""
        average_page_size = total_entities / total_pages if total_pages > 0 else 0.0
        entities_per_second = (
            total_entities / extraction_duration if extraction_duration > 0 else 0.0
        )

        self._last_extraction_summary = {
            "total_entities": total_entities,
            "total_pages": total_pages,
            "extraction_duration": extraction_duration,
            "average_page_size": average_page_size,
            "entities_per_second": entities_per_second,
            "last_cursor": last_cursor,
            "extraction_status": status,
            "error_count": error_count,
        }
