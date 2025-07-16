"""
JobberClient module for GraphQL API communication with Jobber.

This module provides the JobberClient class which handles all communication
with the Jobber GraphQL API, including authentication, query execution,
and response handling.
"""

from typing import Any, Optional

import requests

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
            auth_provider: AuthProvider instance for API authentication
        """
        self.auth_provider = auth_provider

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
        # Prepare GraphQL payload
        payload = {"query": self.CLIENTS_QUERY, "variables": {"cursor": cursor}}

        # Make HTTP POST request to Jobber API
        response = requests.post(
            self.API_URL, headers=self.auth_provider.get_headers(), json=payload
        )

        # Check for HTTP errors
        response.raise_for_status()

        # Parse and return JSON response
        return response.json()

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
        # Prepare GraphQL payload
        payload = {"query": self.INVOICES_QUERY, "variables": {"cursor": cursor}}

        # Make HTTP POST request to Jobber API
        response = requests.post(
            self.API_URL, headers=self.auth_provider.get_headers(), json=payload
        )

        # Check for HTTP errors
        response.raise_for_status()

        # Parse and return JSON response
        return response.json()
