"""
JobberClient module for GraphQL API communication with Jobber.

This module provides the JobberClient class which handles all communication
with the Jobber GraphQL API, including authentication, query execution,
and response handling. The client supports both environment token and
OAuth2 authentication with automatic token refresh.
"""

from typing import Any, Optional

from ..auth.auth_provider import AuthProvider
from ..exceptions import ConfigurationError, JobberApiError, OAuth2Error
from .http_client import HttpClient


class JobberClient:
    """
    Client for communicating with the Jobber GraphQL API.

    This class handles all GraphQL API communication with Jobber, including
    authentication, query execution, cursor-based pagination, and response
    processing. It provides methods to fetch clients and invoices data
    from the Jobber platform.

    The class integrates with the enhanced AuthProvider to support both
    environment token authentication (JOBBER_TOKEN) and OAuth2 authentication
    with automatic token refresh. OAuth2 tokens are automatically refreshed
    when expired, providing seamless API access without user intervention.

    The class follows the established dependency injection pattern and
    maintains full backward compatibility with existing authentication methods.
    """

    # Jobber GraphQL API endpoint
    API_URL = "https://api.getjobber.com/api/graphql"

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
            auth_provider: AuthProvider instance for API authentication.
                          Supports both environment token (JOBBER_TOKEN)
                          and OAuth2 authentication with automatic refresh.
        """
        self.auth_provider = auth_provider
        self.http_client = HttpClient()

    def _execute_graphql_request(
        self, query: str, cursor: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Execute a GraphQL request with comprehensive error handling.

        This method handles authentication automatically, including OAuth2 token
        refresh when needed. For OAuth2 users, expired tokens are automatically
        refreshed transparently. Environment token users see no changes in behavior.

        Args:
            query: GraphQL query string to execute
            cursor: Optional cursor for pagination

        Returns:
            Dictionary containing GraphQL response data

        Raises:
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
            JobberApiError: If API communication fails
        """
        try:
            # Get authentication headers with automatic OAuth2 token refresh
            # This may raise ConfigurationError or OAuth2Error
            headers = self.auth_provider.get_headers()

        except ConfigurationError:
            # Re-raise configuration errors as-is (includes OAuth2 auth failures)
            raise

        except OAuth2Error as e:
            # Convert OAuth2 errors to user-friendly configuration errors
            raise ConfigurationError(
                f"OAuth2 authentication failed: {e}. "
                "Please re-authorize using 'tightbeam oauth init' or set JOBBER_TOKEN."
            ) from None

        except Exception as e:
            # Catch any other unexpected authentication errors
            raise ConfigurationError(
                f"Authentication failed: {e}. "
                "Please verify your authentication configuration."
            ) from e

        # Prepare GraphQL payload
        payload = {"query": query, "variables": {"cursor": cursor}}

        # Use shared HttpClient for HTTP communication
        response_data = self.http_client.post(
            url=self.API_URL, headers=headers, json=payload
        )

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
                f"Invalid response format: expected dictionary, got {type(response_data)}"  # noqa: E501
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

        Retrieves client information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with clients data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
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

        Retrieves invoice information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with invoices data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
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
