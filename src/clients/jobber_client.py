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
from ..interfaces import IHttpClient
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

    # Jobber API version - required for all requests
    API_VERSION = "2023-11-15"

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
            notes {
              edges {
                node {
                  id
                  message
                  createdAt
                  updatedAt
                }
              }
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
            notes {
              edges {
                node {
                  id
                  message
                  createdAt
                  updatedAt
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching quotes with cursor pagination
    QUOTES_QUERY = """
    query GetQuotes($cursor: String) {
      quotes(first: 100, after: $cursor) {
        edges {
          node {
            id
            client {
              id
            }
            quoteNumber
            title
            amounts {
              total
              subtotal
            }
            message
            lineItems {
              edges {
                node {
                  id
                  name
                  quantity
                  unitCost
                  total
                }
              }
            }
            notes {
              edges {
                node {
                  id
                  message
                  createdAt
                  updatedAt
                }
              }
            }
            createdAt
            transitionedAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # NOTE: This query is deprecated - notes are now fetched with their parent entities
    # (clients, jobs, quotes, invoices)
    # NOTES_QUERY = """
    # query GetNotes($cursor: String) {
    #   nodes(first: 100, after: $cursor) {
    #     edges {
    #       node {
    #         ... on ClientNote {
    #           id
    #           message
    #           client {
    #             id
    #           }
    #           createdAt
    #           updatedAt
    #         }
    #         ... on JobNote {
    #           id
    #           message
    #           job {
    #             id
    #           }
    #           createdAt
    #           updatedAt
    #         }
    #         ... on QuoteNote {
    #           id
    #           message
    #           quote {
    #             id
    #           }
    #           createdAt
    #           updatedAt
    #         }
    #         ... on InvoiceNote {
    #           id
    #           message
    #           invoice {
    #             id
    #           }
    #           createdAt
    #           updatedAt
    #         }
    #       }
    #     }
    #     pageInfo {
    #       hasNextPage
    #       endCursor
    #     }
    #   }
    # }
    # """

    # GraphQL query for fetching attachments with cursor pagination
    # Attachments are file attachments linked to notes
    ATTACHMENTS_QUERY = """
    query GetAttachments($cursor: String) {
      noteFiles(first: 100, after: $cursor) {
        edges {
          node {
            id
            note {
              id
            }
            fileName
            contentType
            downloadUrl
            fileSize
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

    # GraphQL query for fetching jobs with cursor pagination
    JOBS_QUERY = """
    query GetJobs($cursor: String) {
      jobs(first: 100, after: $cursor) {
        edges {
          node {
            id
            client {
              id
            }
            property {
              id
            }
            quote {
              id
            }
            jobNumber
            title
            description
            status
            scheduledStartAt
            scheduledEndAt
            completedAt
            amounts {
              total
            }
            notes {
              edges {
                node {
                  id
                  message
                  createdAt
                  updatedAt
                }
              }
            }
            createdAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching properties with cursor pagination
    PROPERTIES_QUERY = """
    query GetProperties($cursor: String) {
      properties(first: 100, after: $cursor) {
        edges {
          node {
            id
            client {
              id
            }
            name
            address {
              line1
              line2
              city
              stateProvince
              postalCode
              country
            }
            coordinates {
              latitude
              longitude
            }
            createdAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching requests with cursor pagination
    REQUESTS_QUERY = """
    query GetRequests($cursor: String) {
      requests(first: 100, after: $cursor) {
        edges {
          node {
            id
            client {
              id
            }
            property {
              id
            }
            title
            description
            status
            priority
            source
            assignedTo
            convertedToQuote {
              id
            }
            convertedToJob {
              id
            }
            notes {
              edges {
                node {
                  id
                  message
                  createdAt
                  updatedAt
                }
              }
            }
            createdAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching users with cursor pagination
    USERS_QUERY = """
    query GetUsers($cursor: String) {
      users(first: 100, after: $cursor) {
        edges {
          node {
            id
            name {
              first
              last
            }
            email {
              email
            }
            isAccountAdmin
            isAccountOwner
            status
            phone {
              number
            }
            timezone {
              identifier
            }
            createdAt
            lastLoginAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching expenses with cursor pagination
    EXPENSES_QUERY = """
    query GetExpenses($cursor: String) {
      expenses(first: 100, after: $cursor) {
        edges {
          node {
            id
            linkedJob {
              id
            }
            title
            description
            total
            date
            enteredBy {
              id
            }
            paidBy {
              id
            }
            reimbursableTo {
              id
            }
            createdAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching visits with cursor pagination
    VISITS_QUERY = """
    query GetVisits($cursor: String) {
      visits(first: 100, after: $cursor) {
        edges {
          node {
            id
            job {
              id
            }
            client {
              id
            }
            property {
              id
            }
            assignedUsers {
              edges {
                node {
                  id
                }
              }
            }
            title
            instructions
            visitStatus
            allDay
            duration
            startAt
            endAt
            completedAt
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

    # GraphQL query for fetching timesheet entries with cursor pagination
    TIMESHEET_ENTRIES_QUERY = """
    query GetTimesheetEntries($cursor: String) {
      timesheetEntries(first: 100, after: $cursor) {
        edges {
          node {
            id
            user {
              id
            }
            job {
              id
            }
            visit {
              id
            }
            approvedBy {
              id
            }
            paidBy {
              id
            }
            label
            note
            labourRate
            finalDuration
            visitDurationTotal
            approved
            ticking
            startAt
            endAt
            createdAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching products or services with cursor pagination
    PRODUCTS_SERVICES_QUERY = """
    query GetProductsServices($cursor: String) {
      productsAndServices(first: 100, after: $cursor) {
        edges {
          node {
            id
            name
            description
            category {
              name
            }
            defaultUnitCost
            internalUnitCost
            markup
            durationMinutes
            taxable
            visible
            onlineBookingEnabled
            onlineBookingSortOrder
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # GraphQL query for fetching tax rates with cursor pagination
    TAX_RATES_QUERY = """
    query GetTaxRates($cursor: String) {
      taxRates(first: 100, after: $cursor) {
        edges {
          node {
            id
            name
            rate
            region
            compound
            active
            description
            taxNumber
            displayOrder
            defaultForRegion
            createdAt
            updatedAt
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    def __init__(
        self, auth_provider: AuthProvider, http_client: Optional[IHttpClient] = None
    ) -> None:
        """
        Initialize the JobberClient with authentication provider.

        Args:
            auth_provider: AuthProvider instance for API authentication.
                          Supports both environment token (JOBBER_TOKEN)
                          and OAuth2 authentication with automatic refresh.
            http_client: Optional IHttpClient instance. If not provided,
                        a new HttpClient instance will be created.
        """
        self.auth_provider = auth_provider
        self.http_client = http_client or HttpClient()

    def set_http_client(self, http_client: IHttpClient) -> None:
        """
        Set the HTTP client for this JobberClient instance.

        This method provides proper encapsulation for injecting a different
        HTTP client implementation (e.g., rate-limited client) after instantiation.

        Args:
            http_client: IHttpClient instance to use for API requests
        """
        self.http_client = http_client

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

        # Add required API version header - this is mandatory for all
        # Jobber API requests
        headers["X-JOBBER-GRAPHQL-VERSION"] = self.API_VERSION

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

    def fetch_quotes(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch quotes data from Jobber GraphQL API.

        Retrieves quote information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with quotes data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.QUOTES_QUERY, cursor)

            # Validate that quotes data exists in response
            if (
                response_data.get("data") is not None
                and "quotes" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'quotes' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching quotes: {e}") from e

    # NOTE: This method is deprecated - notes are now fetched with their parent entities
    # def fetch_notes(self, cursor: Optional[str] = None) -> dict[str, Any]:
    #     """Fetch notes from Jobber API with cursor pagination.
    #
    #     Notes in Jobber are polymorphic and can be attached to clients, jobs,
    #     quotes, or invoices. This method fetches all types of notes.
    #
    #     Args:
    #         cursor: Optional pagination cursor for fetching next page
    #
    #     Returns:
    #         dict[str, Any]: Raw GraphQL response containing notes data
    #
    #     Raises:
    #         JobberApiError: If API request fails with HTTP error or
    #                        invalid response structure
    #         ConfigurationError: If authentication configuration is invalid
    #                            or OAuth2 token refresh fails
    #     """
    #     try:
    #         response_data = self._execute_graphql_request(self.NOTES_QUERY, cursor)
    #
    #         # Validate that notes data exists in response
    #         if (
    #             response_data.get("data") is not None
    #             and "nodes" not in response_data["data"]
    #         ):
    #             raise JobberApiError(
    #                 "Invalid response structure: missing 'nodes' field in data"
    #             )
    #
    #         return response_data
    #
    #     except (ConfigurationError, JobberApiError):
    #         # Re-raise our domain exceptions as-is
    #         raise
    #     except Exception as e:
    #         # Wrap unexpected exceptions in JobberApiError
    #         raise JobberApiError(f"Unexpected error fetching notes: {str(e)}") from e

    def fetch_attachments(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch attachments data from Jobber GraphQL API.

        Retrieves attachment (note file) information using cursor-based pagination
        with automatic authentication handling. Attachments are files linked to notes.
        For OAuth2 users, expired tokens are automatically refreshed during the request.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with attachments data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(
                self.ATTACHMENTS_QUERY, cursor
            )

            # Validate that attachments data exists in response
            if (
                response_data.get("data") is not None
                and "noteFiles" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'noteFiles' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching attachments: {e}"
            ) from e

    def fetch_jobs(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch jobs data from Jobber GraphQL API.

        Retrieves job information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with jobs data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.JOBS_QUERY, cursor)

            # Validate that jobs data exists in response
            if (
                response_data.get("data") is not None
                and "jobs" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'jobs' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching jobs: {e}") from e

    def fetch_properties(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch properties data from Jobber GraphQL API.

        Retrieves property information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with properties data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.PROPERTIES_QUERY, cursor)

            # Validate that properties data exists in response
            if (
                response_data.get("data") is not None
                and "properties" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'properties' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching properties: {e}"
            ) from e

    def fetch_requests(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch requests data from Jobber GraphQL API.

        Retrieves service request information using cursor-based pagination with
        automatic authentication handling. For OAuth2 users, expired tokens are
        automatically refreshed during the request. Environment token users see
        no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with requests data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.REQUESTS_QUERY, cursor)

            # Validate that requests data exists in response
            if (
                response_data.get("data") is not None
                and "requests" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'requests' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching requests: {e}"
            ) from e

    def fetch_users(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch users data from Jobber GraphQL API.

        Retrieves user information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with users data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.USERS_QUERY, cursor)

            # Validate that users data exists in response
            if (
                response_data.get("data") is not None
                and "users" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'users' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching users: {e}") from e

    def fetch_expenses(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch expenses data from Jobber GraphQL API.

        Retrieves expense information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with expenses data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.EXPENSES_QUERY, cursor)

            # Validate that expenses data exists in response
            if (
                response_data.get("data") is not None
                and "expenses" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'expenses' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching expenses: {e}"
            ) from e

    def fetch_visits(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch visits data from Jobber GraphQL API.

        Retrieves visit information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with visits data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.VISITS_QUERY, cursor)

            # Validate that visits data exists in response
            if (
                response_data.get("data") is not None
                and "visits" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'visits' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching visits: {e}") from e

    def fetch_timesheet_entries(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch timesheet entries data from Jobber GraphQL API.

        Retrieves timesheet entry information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with timesheet entries data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(
                self.TIMESHEET_ENTRIES_QUERY, cursor
            )

            # Validate that timesheet entries data exists in response
            if (
                response_data.get("data") is not None
                and "timesheetEntries" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'timesheetEntries' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching timesheet entries: {e}"
            ) from e

    def fetch_products_services(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch products and services data from Jobber GraphQL API.

        Retrieves product and service catalog information using cursor-based pagination
        with automatic authentication handling. For OAuth2 users, expired tokens are
        automatically refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with products and services data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(
                self.PRODUCTS_SERVICES_QUERY, cursor
            )

            # Validate that products and services data exists in response
            if (
                response_data.get("data") is not None
                and "productsAndServices" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'productsAndServices' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching products and services: {e}"
            ) from e

    def fetch_tax_rates(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch tax rates data from Jobber GraphQL API.

        Retrieves tax rate information using cursor-based pagination with automatic
        authentication handling. For OAuth2 users, expired tokens are automatically
        refreshed during the request. Environment token users see no behavior changes.

        Args:
            cursor: Optional cursor for pagination (None for first page)

        Returns:
            Dictionary containing GraphQL response with tax rates data

        Raises:
            JobberApiError: If API communication fails
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            response_data = self._execute_graphql_request(self.TAX_RATES_QUERY, cursor)

            # Validate that tax rates data exists in response
            if (
                response_data.get("data") is not None
                and "taxRates" not in response_data["data"]
            ):
                raise JobberApiError(
                    "Invalid response structure: missing 'taxRates' field in data"
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(
                f"Unexpected error while fetching tax rates: {e}"
            ) from e
