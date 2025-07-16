"""
JobberClient module for GraphQL API communication with Jobber.

This module provides the JobberClient class which handles all communication
with the Jobber GraphQL API, including authentication, query execution,
and response handling.
"""

from typing import Optional, Any
from ..auth.auth_provider import AuthProvider


class JobberClient:
    """
    Client for communicating with the Jobber GraphQL API.

    This class handles all GraphQL API communication with Jobber, including
    authentication, query execution, cursor-based pagination, and response
    processing. It provides methods to fetch clients and invoices data
    from the Jobber platform.

    The class follows the established dependency injection pattern and
    integrates with the AuthProvider for secure API authentication.
    """

    def __init__(self, auth_provider: AuthProvider) -> None:
        """
        Initialize the JobberClient with authentication provider.

        Args:
            auth_provider: AuthProvider instance for API authentication
        """
        self.auth_provider = auth_provider

    def fetch_clients(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch clients data from Jobber GraphQL API.

        Retrieves client information using cursor-based pagination.
        This method will be implemented in subsequent tasks to include
        GraphQL query construction, HTTP communication, and response processing.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with clients data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
        """
        # Implementation will be added in subsequent tasks
        raise NotImplementedError("fetch_clients implementation pending")

    def fetch_invoices(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch invoices data from Jobber GraphQL API.

        Retrieves invoice information using cursor-based pagination.
        This method will be implemented in subsequent tasks to include
        GraphQL query construction, HTTP communication, and response processing.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with invoices data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
        """
        # Implementation will be added in subsequent tasks
        raise NotImplementedError("fetch_invoices implementation pending")
