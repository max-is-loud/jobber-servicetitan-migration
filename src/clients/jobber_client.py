"""
JobberClient module for GraphQL API communication with Jobber.

This module provides the JobberClient class which handles all communication
with the Jobber GraphQL API, including authentication, query execution,
and response handling.
"""

from typing import Any, Optional

import requests

from ..auth.auth_provider import AuthProvider
from ..exceptions import ConfigurationError, JobberApiError


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

    # Jobber GraphQL API endpoint
    API_URL = "https://api.getjobber.com/api/graphql"

    # Request timeout configuration (connect, read) in seconds
    TIMEOUT = (10, 30)

    # GraphQL query for fetching clients with cursor pagination
    CLIENTS_QUERY = """
    query GetClients($cursor: String) {
      clients(first: 100, after: $cursor) {
        edges {
          node {
            id
            firstName
            lastName
            emails {
              address
            }
            phones {
              number
            }
            createdAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching invoices with cursor pagination
    INVOICES_QUERY = """
    query GetInvoices($cursor: String) {
      invoices(first: 100, after: $cursor) {
        edges {
          node {
            id
            client {
              id
            }
            invoiceNumber
            amounts {
              total
            }
            invoiceStatus
            issuedDate
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    def __init__(self, auth_provider: AuthProvider) -> None:
        """
        Initialize the JobberClient with authentication provider.

        Args:
            auth_provider: AuthProvider instance for API authentication
        """
        self.auth_provider = auth_provider

    def _execute_graphql_request(
        self, query: str, cursor: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Execute a GraphQL request with comprehensive error handling.

        Args:
            query: GraphQL query string to execute
            cursor: Optional cursor for pagination

        Returns:
            Dictionary containing GraphQL response data

        Raises:
            ConfigurationError: If authentication configuration is invalid
            JobberApiError: If API communication fails
        """
        try:
            # Get authentication headers (may raise ConfigurationError)
            headers = self.auth_provider.get_headers()
        except Exception as e:
            raise ConfigurationError(f"Authentication configuration failed: {e}") from e

        # Prepare GraphQL payload
        payload = {"query": query, "variables": {"cursor": cursor}}

        try:
            # Make HTTP POST request to Jobber API with timeout
            response = requests.post(
                self.API_URL, headers=headers, json=payload, timeout=self.TIMEOUT
            )

            # Handle HTTP status code errors
            if response.status_code == 401:
                raise ConfigurationError(
                    "Invalid or expired JOBBER_TOKEN. Please check your authentication credentials."
                )
            elif response.status_code == 403:
                raise ConfigurationError(
                    "Access forbidden. Your JOBBER_TOKEN may not have sufficient permissions."
                )
            elif response.status_code >= 400:
                raise JobberApiError(
                    f"Jobber API returned HTTP {response.status_code}: {response.text}"
                )

            # Check for successful status (will raise HTTPError for 4xx/5xx if we missed any)
            response.raise_for_status()

        except requests.exceptions.Timeout as e:
            raise JobberApiError(
                f"Request to Jobber API timed out after {self.TIMEOUT} seconds. "
                "Please check your network connection or try again later."
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise JobberApiError(
                f"Failed to connect to Jobber API at {self.API_URL}. "
                "Please check your network connection and API endpoint."
            ) from e
        except requests.exceptions.RequestException as e:
            raise JobberApiError(
                f"Network error occurred while contacting Jobber API: {e}"
            ) from e

        # Parse JSON response
        try:
            response_data = response.json()
        except requests.exceptions.JSONDecodeError as e:
            raise JobberApiError(
                f"Invalid JSON response from Jobber API. Response: {response.text[:200]}..."
            ) from e

        # Validate response structure and check for GraphQL errors
        self._validate_graphql_response(response_data)

        return response_data

    def _validate_graphql_response(self, response_data: dict[str, Any]) -> None:
        """
        Validate GraphQL response structure and check for errors.

        Args:
            response_data: Parsed JSON response from GraphQL API

        Raises:
            JobberApiError: If response is invalid or contains GraphQL errors
        """
        # Check if response is a dictionary
        if not isinstance(response_data, dict):
            raise JobberApiError(
                f"Invalid response format: expected dictionary, got {type(response_data)}"
            )

        # Check for GraphQL errors
        if "errors" in response_data:
            errors = response_data["errors"]
            if errors:
                error_messages = []
                for error in errors:
                    if isinstance(error, dict) and "message" in error:
                        error_messages.append(error["message"])
                    else:
                        error_messages.append(str(error))

                raise JobberApiError(
                    f"GraphQL errors in response: {'; '.join(error_messages)}"
                )

        # Check for data field
        if "data" not in response_data:
            raise JobberApiError("Invalid GraphQL response: missing 'data' field")

        # Data can be None for some valid GraphQL responses, so we don't check for that

    def fetch_clients(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch clients data from Jobber GraphQL API.

        Retrieves client information using cursor-based pagination.
        Constructs GraphQL query, makes HTTP POST request, and processes response.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with clients data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
        """
        try:
            response_data = self._execute_graphql_request(self.CLIENTS_QUERY, cursor)

            # Validate that clients data exists in response
            if (
                response_data.get("data") is not None
                and "clients" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'clients' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching clients: {e}") from e

    def fetch_invoices(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch invoices data from Jobber GraphQL API.

        Retrieves invoice information using cursor-based pagination.
        Constructs GraphQL query, makes HTTP POST request, and processes response.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with invoices data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
        """
        try:
            response_data = self._execute_graphql_request(self.INVOICES_QUERY, cursor)

            # Validate that invoices data exists in response
            if (
                response_data.get("data") is not None
                and "invoices" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'invoices' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching invoices: {e}"
            ) from e
