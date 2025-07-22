"""BaseExtractor Protocol for modular data extraction architecture."""

from typing import Any, List, Optional, Protocol, Union

from ..models import Attachment, Client, Invoice, Note, Quote


class BaseExtractor(Protocol):
    """BaseExtractor interface for modular OO data extraction from Jobber GraphQL API.

    This Protocol establishes the foundational architecture for modular extractors
    as specified in PRD Section 3.1, enabling consistent extraction patterns across
    Quote, Note, and Attachment entities. All extractors implement cursor-based
    pagination and provide standardized data transformation workflows.

    The interface supports dependency injection of JobberClient, EntityMapper,
    Repository, and Logger components, ensuring testable and maintainable
    extraction implementations.
    """

    def extract(self, cursor: Optional[str] = None, page_limit: Optional[int] = None) -> dict[str, Any]:
        """Extract entities from Jobber GraphQL API with cursor-based pagination.

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
        ...

    def extract_all(self) -> List[Union[Client, Invoice, Quote, Note, Attachment]]:
        """Extract all entities with automatic pagination until completion.

        Continuously calls extract() with cursor pagination until all available
        entities are processed. Provides complete dataset extraction with
        comprehensive progress logging and error recovery.

        Returns:
            List of all extracted entity objects (Client, Invoice, Quote,
            Note, or Attachment)

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
            RepositoryError: If database operations fail
        """
        ...

    def get_entity_count(self) -> int:
        """Get total count of entities available for extraction.

        Performs a lightweight API call to determine the total number of entities
        available for extraction without actually extracting data. Useful for
        progress estimation and extraction planning.

        Returns:
            Total number of entities available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        ...

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
        ...

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
        ...
