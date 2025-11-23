"""
JobberClient module for GraphQL API communication with Jobber.

This module provides the JobberClient class which handles all communication
with the Jobber GraphQL API, including authentication, query execution,
and response handling. The client supports both environment token and
OAuth2 authentication with automatic token refresh.
"""

import time
from typing import Any, Optional

from ..auth.auth_provider import AuthProvider
from ..config import ConfigManagerImpl
from ..exceptions import ConfigurationError, JobberApiError, OAuth2Error
from ..interfaces import IHttpClient
from ..rate_limiting.metrics_collector import MetricsCollector
from ..utils.debug import debug_print
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

    def _get_clients_query(self) -> str:
        """Get GraphQL query for fetching clients with configurable pagination.

        Includes optimized nested notes query with configurable pagination to:
        - Reduce API costs by 60-70% (from ~100 points to ~50 points per client)
        - Eliminate individual note API calls
        - Provide predictable query costs

        See docs/architecture/notes-optimization.md for full analysis.
        """
        page_size = self._get_pagination_size("clients")
        nested_notes_size = self._get_pagination_size("nested_notes")
        return f"""
    query GetClients($cursor: String) {{
      clients(first: {page_size}, after: $cursor) {{
        edges {{
          node {{
            id
            firstName
            lastName
            emails {{
              address
            }}
            phones {{
              number
            }}
            notes(first: {nested_notes_size}) {{
              totalCount
              edges {{
                node {{
                  ... on ClientNote {{
                    id
                    message
                    createdAt
                  }}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            noteAttachments(first: {nested_notes_size}) {{
              totalCount
              edges {{
                node {{
                  id
                  note {{
                    id
                  }}
                  fileName
                  contentType
                  url
                  fileSize
                  createdAt
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            createdAt
            updatedAt
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
    """

    def _get_invoices_query(self) -> str:
        """Get GraphQL query for fetching invoices with configurable pagination and optimized nested notes."""
        page_size = self._get_pagination_size("invoices")
        nested_notes_limit = self._get_pagination_size("nested_notes")
        return f"""
    query GetInvoices($cursor: String) {{
      invoices(first: {page_size}, after: $cursor) {{
        edges {{
          node {{
            id
            client {{
              id
            }}
            invoiceNumber
            amounts {{
              total
              subtotal
            }}
            invoiceStatus
            issuedDate
            dueDate
            lineItems {{
              edges {{
                node {{
                  description
                  quantity
                  unitCost
                  total
                }}
              }}
            }}
            notes(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  ... on InvoiceNote {{
                    id
                    message
                    createdAt
                  }}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            noteAttachments(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  id
                  note {{
                    ... on InvoiceNote {{
                      id
                    }}
                  }}
                  fileName
                  contentType
                  url
                  fileSize
                  createdAt
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            createdAt
            updatedAt
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
    """

    def _get_quotes_query(self) -> str:
        """Get GraphQL query for fetching quotes with configurable pagination and optimized nested notes."""
        page_size = self._get_pagination_size("quotes")
        nested_notes_limit = self._get_pagination_size("nested_notes")
        return f"""
    query GetQuotes($cursor: String) {{
      quotes(first: {page_size}, after: $cursor) {{
        edges {{
          node {{
            id
            client {{
              id
            }}
            quoteNumber
            title
            amounts {{
              total
              subtotal
            }}
            message
            lineItems {{
              edges {{
                node {{
                  name
                  description
                  qty
                  unitCost
                  total
                }}
              }}
            }}
            notes(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  ... on QuoteNote {{
                    id
                    message
                    createdAt
                  }}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            noteAttachments(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  id
                  note {{
                    ... on QuoteNote {{
                      id
                    }}
                  }}
                  fileName
                  contentType
                  url
                  fileSize
                  createdAt
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            createdAt
            transitionedAt
            updatedAt
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
    """

    # NOTE: Bulk note fetching is not supported by Jobber's GraphQL API.
    # The API does not provide a top-level 'notes' or 'nodes' query for fetching all notes.
    # Notes are only accessible through parent entity connections (Client.notes, Job.notes, etc.)
    # or via the node(id:) interface for individual note fetching.
    #
    # Current implementation uses deferred loading pattern:
    # 1. Collect note IDs during parent entity extraction
    # 2. Fetch individual notes using node(id:) interface (see NOTE_BY_ID_QUERY)
    # This avoids nested query complexity that triggers API rate limiting.

    # NOTE: Attachments (noteAttachments) are NOT available as a top-level query.
    # They are fields on parent entities (Client.noteAttachments, Job.noteAttachments, etc.)
    # and must be fetched as part of the parent entity queries.
    # See individual entity queries (CLIENTS_QUERY, JOBS_QUERY, etc.) for noteAttachments.

    def _get_jobs_query(self) -> str:
        """Get GraphQL query for fetching jobs with configurable pagination and optimized nested notes."""
        page_size = self._get_pagination_size("jobs")
        nested_notes_limit = self._get_pagination_size("nested_notes")
        return f"""
    query GetJobs($cursor: String) {{
      jobs(first: {page_size}, after: $cursor) {{
        edges {{
          node {{
            id
            client {{
              id
            }}
            property {{
              id
            }}
            quote {{
              id
            }}
            jobNumber
            title
            instructions
            jobStatus
            startAt
            endAt
            completedAt
            total
            notes(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  ... on JobNote {{
                    id
                    message
                    createdAt
                  }}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            noteAttachments(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  id
                  note {{
                    ... on JobNote {{
                      id
                    }}
                  }}
                  fileName
                  contentType
                  url
                  fileSize
                  createdAt
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            createdAt
            updatedAt
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
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

    def _get_requests_query(self) -> str:
        """Get GraphQL query for fetching requests with configurable pagination and optimized nested notes."""
        page_size = self._get_pagination_size("requests")
        nested_notes_limit = self._get_pagination_size("nested_notes")
        return f"""
    query GetRequests($cursor: String) {{
      requests(first: {page_size}, after: $cursor) {{
        edges {{
          node {{
            id
            client {{
              id
            }}
            property {{
              id
            }}
            title
            description
            status
            priority
            source
            assignedTo
            convertedToQuote {{
              id
            }}
            convertedToJob {{
              id
            }}
            notes(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  ... on RequestNote {{
                    id
                    message
                    createdAt
                  }}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            noteAttachments(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  id
                  note {{
                    ... on RequestNote {{
                      id
                    }}
                  }}
                  fileName
                  contentType
                  url
                  fileSize
                  createdAt
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
            createdAt
            updatedAt
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
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
      productOrServices(first: 100, after: $cursor) {
        edges {
          node {
            id
            name
            description
            category
            defaultUnitCost
            internalUnitCost
            markup
            durationMinutes
            taxable
            visible
            onlineBookingsEnabled
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

    # GraphQL query for fetching individual note by ID
    NOTE_BY_ID_QUERY = """
    query GetNoteById($id: ID!) {
      node(id: $id) {
        ... on ClientNote {
          id
          message
          createdAt
          client {
            id
          }
        }
        ... on JobNote {
          id
          message
          createdAt
          job {
            id
          }
        }
        ... on QuoteNote {
          id
          message
          createdAt
          quote {
            id
          }
        }
        ... on InvoiceNote {
          id
          message
          createdAt
          invoice {
            id
          }
        }
        ... on RequestNote {
          id
          message
          createdAt
          request {
            id
          }
        }
      }
    }
    """

    # GraphQL query for fetching any entity by ID using node interface
    # Used for single entity extraction in extract mode
    ENTITY_BY_ID_QUERY = """
    query GetEntityById($id: ID!) {
      node(id: $id) {
        ... on Client {
          id
          firstName
          lastName
          emails {
            address
          }
          phones {
            number
          }
          notes(first: 10) {
            edges {
              node {
                ... on ClientNote {
                  id
                  message
                  createdAt
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          noteAttachments(first: 10) {
            edges {
              node {
                id
                note {
                  id
                }
                fileName
                contentType
                url
                fileSize
                createdAt
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          createdAt
          updatedAt
        }
        ... on Invoice {
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
          notes(first: 10) {
            edges {
              node {
                ... on InvoiceNote {
                  id
                  message
                  createdAt
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          noteAttachments(first: 10) {
            edges {
              node {
                id
                note {
                  ... on InvoiceNote {
                    id
                  }
                }
                fileName
                contentType
                url
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
        ... on Quote {
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
            totalCount
          }
          notes(first: 10) {
            edges {
              node {
                ... on QuoteNote {
                  id
                  message
                  createdAt
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          noteAttachments(first: 10) {
            edges {
              node {
                id
                note {
                  ... on QuoteNote {
                    id
                  }
                }
                fileName
                contentType
                url
                fileSize
                createdAt
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          createdAt
          transitionedAt
          updatedAt
        }
        ... on Job {
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
          notes(first: 10) {
            edges {
              node {
                ... on JobNote {
                  id
                  message
                  createdAt
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          noteAttachments(first: 10) {
            edges {
              node {
                id
                note {
                  ... on JobNote {
                    id
                  }
                }
                fileName
                contentType
                url
                fileSize
                createdAt
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          createdAt
          updatedAt
        }
        ... on Property {
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
        ... on Request {
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
          notes(first: 10) {
            edges {
              node {
                ... on RequestNote {
                  id
                  message
                  createdAt
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          noteAttachments(first: 10) {
            edges {
              node {
                id
                note {
                  ... on RequestNote {
                    id
                  }
                }
                fileName
                contentType
                url
                fileSize
                createdAt
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
          createdAt
          updatedAt
        }
        ... on User {
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
        ... on Expense {
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
        ... on Visit {
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
        ... on TimesheetEntry {
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
        ... on ProductOrService {
          id
          name
          description
          category
          defaultUnitCost
          internalUnitCost
          markup
          durationMinutes
          taxable
          visible
          onlineBookingsEnabled
          onlineBookingSortOrder
        }
        ... on TaxRate {
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
    }
    """

    def __init__(
        self,
        auth_provider: AuthProvider,
        http_client: Optional[IHttpClient] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        config_manager: Optional[ConfigManagerImpl] = None,
    ) -> None:
        """
        Initialize the JobberClient with authentication provider.

        Args:
            auth_provider: AuthProvider instance for API authentication.
                          Supports both environment token (JOBBER_TOKEN)
                          and OAuth2 authentication with automatic refresh.
            http_client: Optional IHttpClient instance. If not provided,
                        a new HttpClient instance will be created.
            metrics_collector: Optional MetricsCollector for GraphQL cost
                             and rate limit monitoring. If not provided,
                             monitoring features are disabled.
            config_manager: Optional ConfigManagerImpl for pagination settings.
                          If not provided, a new instance will be created.
        """
        self.auth_provider = auth_provider

        self.metrics_collector = metrics_collector
        self.config_manager = config_manager or ConfigManagerImpl()

        # Configure HTTP client with timeout settings
        if http_client:
            self.http_client = http_client
        else:
            # Get timeout from config (default to 30s if not set)
            try:
                request_timeout = self.config_manager.get_delay_config("request_timeout")
            except ConfigurationError:
                request_timeout = 30.0

            # Use default connect timeout (10s) and configured read timeout
            timeout = (10, request_timeout)
            self.http_client = HttpClient(timeout=timeout)

        # Track throttling events for performance optimization
        self._throttling_events = 0
        self._last_request_was_throttled = False

    def _get_pagination_size(self, entity_type: str) -> int:
        """Get pagination size for the specified entity type from configuration.

        Args:
            entity_type: The entity type (clients, invoices, quotes, etc.)

        Returns:
            Pagination size for the entity type
        """
        try:
            return self.config_manager.get_pagination_config(entity_type)
        except ConfigurationError:
            # Fallback to default if entity type not found
            return self.config_manager.get_pagination_config()

    def set_http_client(self, http_client: IHttpClient) -> None:
        """
        Set the HTTP client for this JobberClient instance.

        This method provides proper encapsulation for injecting a different
        HTTP client implementation (e.g., rate-limited client) after instantiation.

        Args:
            http_client: IHttpClient instance to use for API requests
        """
        self.http_client = http_client

    def _record_graphql_cost(
        self,
        response_data: dict[str, Any],
        query: str = "",
        query_type: str = "unknown",
    ) -> None:
        """
        Extract and record GraphQL cost information from response extensions.

        Args:
            response_data: The GraphQL response containing potential cost data
            query: The GraphQL query string to extract batch size from
            query_type: The type of query being executed (e.g., 'clients', 'invoices')
        """
        if not self.metrics_collector:
            return

        try:
            extensions = response_data.get("extensions", {})
            cost_info = extensions.get("cost", {})

            requested_cost = cost_info.get("requestedQueryCost")
            actual_cost = cost_info.get("actualQueryCost")

            if requested_cost is not None and actual_cost is not None:
                # Extract batch size from GraphQL query using regex
                import re

                batch_size = 30  # Default batch size
                batch_match = re.search(r"first:\s*(\d+)", query)
                if batch_match:
                    batch_size = int(batch_match.group(1))

                self.metrics_collector.record_graphql_cost(
                    int(requested_cost),
                    int(actual_cost),
                    query_type=query_type,
                    batch_size=batch_size,
                )
        except (KeyError, ValueError, TypeError):
            # Gracefully handle missing or invalid cost data
            pass

    def _extract_query_type(self, query: str) -> str:
        """
        Extract the entity type from a GraphQL query string.

        Args:
            query: GraphQL query string

        Returns:
            str: Entity type (e.g., 'clients', 'invoices', 'quotes') or 'unknown'
        """
        import re

        # Look for the main query field in the GraphQL query
        # Pattern matches: clients(, invoices(, quotes(, etc.
        match = re.search(r"(\w+)\s*\([^)]*first:", query)
        if match:
            return match.group(1)

        # Fallback patterns for other query types
        entity_patterns = [
            "clients",
            "invoices",
            "quotes",
            "jobs",
            "properties",
            "requests",
            "users",
            "expenses",
            "visits",
            "timesheetEntries",
            "products",
            "taxRates",
            "attachments",
            "notes",
        ]

        for entity in entity_patterns:
            if entity in query:
                return entity

        return "unknown"

    def _execute_graphql_request(
        self, query: str, cursor: Optional[str] = None, variables: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Execute a GraphQL request with comprehensive error handling and retry logic.

        This method handles authentication automatically, including OAuth2 token
        refresh when needed. For OAuth2 users, expired tokens are automatically
        refreshed transparently. Environment token users see no changes in behavior.

        Includes automatic retry logic for GraphQL throttling errors and network
        connection errors with exponential backoff.

        Args:
            query: GraphQL query string to execute
            cursor: Optional cursor for pagination
            variables: Optional custom variables dict (overrides cursor if provided)

        Returns:
            Dictionary containing GraphQL response data

        Raises:
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
            JobberApiError: If API communication fails after all retries
        """
        max_retries = 5
        base_delay = 2.0

        # Reset throttling flag for this request
        self._last_request_was_throttled = False

        for attempt in range(max_retries + 1):
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
                    f"Authentication failed: {e}. Please verify your authentication configuration."
                ) from e

            # Add required API version header - this is mandatory for all
            # Jobber API requests
            headers["X-JOBBER-GRAPHQL-VERSION"] = self.API_VERSION

            # Debug log headers (mask sensitive data)
            debug_headers = headers.copy()
            if "Authorization" in debug_headers:
                auth_value = debug_headers["Authorization"]
                if auth_value.startswith("Bearer "):
                    debug_headers["Authorization"] = f"Bearer {'*' * 10}..."
            debug_print(f"[DEBUG] Request headers: {debug_headers}")

            # Prepare GraphQL payload
            if variables is not None:
                payload = {"query": query, "variables": variables}
            else:
                payload = {"query": query, "variables": {"cursor": cursor}}

            debug_print(f"[DEBUG] GraphQL Query Length: {len(query)} characters")
            debug_print(f"[DEBUG] GraphQL Query Preview: {query[:200]}...")
            if cursor:
                debug_print(f"[DEBUG] Using cursor: {cursor}")

            try:
                # Use shared HttpClient for HTTP communication with optional header tracking
                response_data: dict[str, Any]
                if self.metrics_collector:
                    result = self.http_client.post(url=self.API_URL, headers=headers, json=payload, return_headers=True)

                    # Handle tuple unpacking for metrics-enabled path
                    # When return_headers=True, result is guaranteed to be a tuple
                    assert isinstance(result, tuple), "Expected tuple when return_headers=True"
                    response_data, rate_limit_headers = result

                    # Track rate limit headers if available
                    remaining = rate_limit_headers.get("x-ratelimit-remaining")
                    reset_time = rate_limit_headers.get("x-ratelimit-reset")
                    if remaining is not None:
                        try:
                            remaining_int = int(remaining)
                            reset_int = int(reset_time) if reset_time else None
                            self.metrics_collector.record_rate_limit_headers(remaining_int, reset_int)
                        except (ValueError, TypeError):
                            # Gracefully handle invalid header values
                            pass

                    # Extract and record GraphQL cost information
                    self._record_graphql_cost(response_data, query, self._extract_query_type(query))
                else:
                    # When return_headers=False (default), result is guaranteed to be a dict
                    result = self.http_client.post(url=self.API_URL, headers=headers, json=payload)
                    assert isinstance(result, dict), "Expected dict when return_headers=False"
                    response_data = result

                debug_print(f"[DEBUG] GraphQL Response Keys: {list(response_data.keys())}")
                if "errors" in response_data:
                    debug_print(f"[DEBUG] GraphQL Errors: {response_data['errors']}")
                    for error in response_data.get("errors", []):
                        if "extensions" in error:
                            debug_print(f"[DEBUG] Error extensions: {error['extensions']}")
                            if "documentation" in error.get("extensions", {}):
                                doc_url = error["extensions"]["documentation"]
                                debug_print(f"[DEBUG] API Documentation: {doc_url}")
                if "extensions" in response_data:
                    debug_print(f"[DEBUG] Response extensions: {response_data['extensions']}")

                # Validate response structure and check for GraphQL errors
                self._validate_graphql_response(response_data)

                return response_data

            except JobberApiError as e:
                # Check if this is a retryable error and we have retries left
                is_throttling = self._is_throttling_error(e)
                is_connection_error = self._is_connection_error(e)

                if (is_throttling or is_connection_error) and attempt < max_retries:
                    # Track throttling event if applicable
                    if is_throttling:
                        self._throttling_events += 1
                        self._last_request_was_throttled = True

                    delay = base_delay * (2**attempt)  # Exponential backoff

                    # Customize message based on error type
                    error_type = "GraphQL throttling" if is_throttling else "Network connection error"

                    debug_print(
                        f"[DEBUG] {error_type} detected, attempt {attempt + 1}/{max_retries + 1}. "
                        f"Retrying in {delay}s..."
                    )
                    print(
                        f"⏳ {error_type} detected, retrying in {delay:.1f}s... "
                        f"(attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    # Not a retryable error or out of retries
                    raise

        # This should never be reached due to the raise in the except block
        raise JobberApiError(f"GraphQL request failed after {max_retries} retries")

    def was_last_request_throttled(self) -> bool:
        """Check if the last request experienced throttling (even if it eventually succeeded).

        Returns:
            True if the last request was throttled at least once
        """
        return self._last_request_was_throttled

    def reset_throttling_flag(self) -> None:
        """Reset the throttling flag for the next request."""
        self._last_request_was_throttled = False

    def get_total_throttling_events(self) -> int:
        """Get total number of throttling events since client creation."""
        return self._throttling_events

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

                raise JobberApiError(f"GraphQL errors in response: {'; '.join(error_messages)}")

        # Check for data field
        if "data" not in response_data:
            raise JobberApiError("Invalid GraphQL response: missing 'data' field")

        # Data can be None for some valid GraphQL responses, so we don't check for that

    def _is_throttling_error(self, error: JobberApiError) -> bool:
        """
        Check if a JobberApiError is caused by GraphQL throttling.

        Args:
            error: JobberApiError to check

        Returns:
            bool: True if the error is caused by throttling
        """
        error_message = str(error).lower()
        throttling_patterns = ["throttled", "throttle", "rate limit", "too many requests"]
        return any(pattern in error_message for pattern in throttling_patterns)

    def _is_connection_error(self, error: JobberApiError) -> bool:
        """
        Check if a JobberApiError is caused by a network connection issue.

        Args:
            error: JobberApiError to check

        Returns:
            bool: True if the error is caused by a connection issue
        """
        error_message = str(error).lower()
        connection_patterns = [
            "failed to connect",
            "connection error",
            "connection refused",
            "network error",
            "request timed out",
            "timed out",
            "timeout",
        ]
        return any(pattern in error_message for pattern in connection_patterns)

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
            response_data = self._execute_graphql_request(self._get_clients_query(), cursor)

            # Validate that clients data exists in response
            if response_data.get("data") is not None and "clients" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'clients' field in data")

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
            response_data = self._execute_graphql_request(self._get_invoices_query(), cursor)

            # Validate that invoices data exists in response
            if response_data.get("data") is not None and "invoices" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'invoices' field in data")

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching invoices: {e}") from e

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
            response_data = self._execute_graphql_request(self._get_quotes_query(), cursor)

            # Validate that quotes data exists in response
            if response_data.get("data") is not None and "quotes" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'quotes' field in data")

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching quotes: {e}") from e

    # NOTE: Bulk note fetching is not supported by Jobber's GraphQL API.
    # Notes are fetched individually using fetch_note_by_id() as part of the
    # deferred loading pattern. See NOTE_BY_ID_QUERY for the implementation.

    # NOTE: Attachment fetching is NOT supported as a standalone query.
    # Attachments (noteAttachments field) are fetched as part of parent entity queries
    # (Client, Job, Request, Quote, Invoice). See parent entity extractors for
    # noteAttachments processing.

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
            response_data = self._execute_graphql_request(self._get_jobs_query(), cursor)

            # Validate that jobs data exists in response
            if response_data.get("data") is not None and "jobs" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'jobs' field in data")

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
            if response_data.get("data") is not None and "properties" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'properties' field in data")

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching properties: {e}") from e

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
            response_data = self._execute_graphql_request(self._get_requests_query(), cursor)

            # Validate that requests data exists in response
            if response_data.get("data") is not None and "requests" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'requests' field in data")

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching requests: {e}") from e

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
            if response_data.get("data") is not None and "users" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'users' field in data")

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
            if response_data.get("data") is not None and "expenses" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'expenses' field in data")

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching expenses: {e}") from e

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
            if response_data.get("data") is not None and "visits" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'visits' field in data")

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

        Retrieves timesheet entry information using cursor-based pagination with
        automatic authentication handling. For OAuth2 users, expired tokens are
        automatically refreshed during the request. Environment token users see
        no behavior changes.

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
            response_data = self._execute_graphql_request(self.TIMESHEET_ENTRIES_QUERY, cursor)

            # Validate that timesheet entries data exists in response
            if response_data.get("data") is not None and "timesheetEntries" not in response_data["data"]:
                raise JobberApiError(
                    "Invalid response structure: missing 'timesheetEntries' field in data"  # noqa: E501
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching timesheet entries: {e}") from e

    def fetch_products_services(self, cursor: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch products and services data from Jobber GraphQL API.

        Retrieves product and service catalog information using cursor-based pagination
        with automatic authentication handling. For OAuth2 users, expired tokens are
        automatically refreshed during the request. Environment token users see no
        behavior changes.

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
            response_data = self._execute_graphql_request(self.PRODUCTS_SERVICES_QUERY, cursor)

            # Validate that products and services data exists in response
            if response_data.get("data") is not None and "productOrServices" not in response_data["data"]:
                raise JobberApiError(
                    "Invalid response structure: missing 'productOrServices' field in data"  # noqa: E501
                )

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching products and services: {e}") from e

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
            if response_data.get("data") is not None and "taxRates" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'taxRates' field in data")

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching tax rates: {e}") from e

    def fetch_note_by_id(self, note_id: str) -> dict[str, Any]:
        """
        Fetch individual note by ID from Jobber GraphQL API.

        Retrieves a specific note with its full content and parent entity relationship
        using the node interface. Supports all note types: ClientNote, JobNote,
        QuoteNote, InvoiceNote, and RequestNote.

        Args:
            note_id: The unique identifier of the note to fetch

        Returns:
            Dictionary containing GraphQL response with note data

        Raises:
            JobberApiError: If API communication fails or note not found
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            # Use throttling-aware GraphQL request execution with note ID variable
            response_data = self._execute_graphql_request(query=self.NOTE_BY_ID_QUERY, variables={"id": note_id})

            # Validate that note data exists in response
            if response_data.get("data") is not None and "node" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'node' field in data")

            # Check if note was found
            node_data = response_data.get("data", {}).get("node")
            if node_data is None:
                raise JobberApiError(f"Note with ID '{note_id}' not found")

            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching note {note_id}: {e}") from e

    def _build_single_entity_query(self, entity_type: str, nested_notes_limit: int = 10) -> str:
        """
        Build a GraphQL query for fetching a single entity by ID.

        Jobber's API uses entity-specific queries (client, invoice, job, etc.)
        instead of a generic node interface.

        Args:
            entity_type: The entity type (e.g., "client", "invoice", "job")
            nested_notes_limit: Number of nested notes to fetch

        Returns:
            GraphQL query string for fetching single entity
        """
        # Entity-specific query templates based on existing pagination queries
        if entity_type == "client":
            return f"""
    query GetClient($id: EncodedId!) {{
      client(id: $id) {{
        id
        firstName
        lastName
        emails {{
          address
        }}
        phones {{
          number
        }}
        notes(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              ... on ClientNote {{
                id
                message
                createdAt
              }}
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
        noteAttachments(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              id
              note {{
                id
              }}
              fileName
              contentType
              url
              fileSize
              createdAt
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
        createdAt
        updatedAt
      }}
    }}
    """
        elif entity_type == "invoice":
            return f"""
    query GetInvoice($id: EncodedId!) {{
      invoice(id: $id) {{
        id
        client {{
          id
        }}
        invoiceNumber
        amounts {{
          total
        }}
        invoiceStatus
        issuedDate
        notes(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              ... on InvoiceNote {{
                id
                message
                createdAt
              }}
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
        noteAttachments(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              id
              note {{
                ... on InvoiceNote {{
                  id
                }}
              }}
              fileName
              contentType
              url
              fileSize
              createdAt
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
      }}
    }}
    """
        elif entity_type == "quote":
            return f"""
    query GetQuote($id: EncodedId!) {{
      quote(id: $id) {{
        id
        client {{
          id
        }}
        quoteNumber
        title
        amounts {{
          total
          subtotal
        }}
        message
        lineItems {{
          totalCount
        }}
        notes(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              ... on QuoteNote {{
                id
                message
                createdAt
              }}
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
        noteAttachments(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              id
              note {{
                ... on QuoteNote {{
                  id
                }}
              }}
              fileName
              contentType
              url
              fileSize
              createdAt
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
        createdAt
        transitionedAt
        updatedAt
      }}
    }}
    """
        elif entity_type == "job":
            return f"""
    query GetJob($id: EncodedId!) {{
      job(id: $id) {{
        id
        client {{
          id
        }}
        property {{
          id
        }}
        quote {{
          id
        }}
        jobNumber
        title
        instructions
        jobStatus
        startAt
        endAt
        completedAt
        total
        notes(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              ... on JobNote {{
                id
                message
                createdAt
              }}
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
        noteAttachments(first: {nested_notes_limit}) {{
          totalCount
          edges {{
            node {{
              id
              note {{
                ... on JobNote {{
                  id
                }}
              }}
              fileName
              contentType
              url
              fileSize
              createdAt
            }}
          }}
          pageInfo {{
            hasNextPage
            endCursor
          }}
        }}
        createdAt
        updatedAt
      }}
    }}
    """
        elif entity_type == "expense":
            return f"""
    query GetExpense($id: EncodedId!) {{
      expense(id: $id) {{
        id
        linkedJob {{
          id
        }}
        title
        description
        total
        date
        enteredBy {{
          id
        }}
        paidBy {{
          id
        }}
        reimbursableTo {{
          id
        }}
        createdAt
        updatedAt
      }}
    }}
    """
        elif entity_type == "productOrService":
            return f"""
    query GetProductService($id: EncodedId!) {{
      productOrService(id: $id) {{
        id
        name
        description
        category
        defaultUnitCost
        internalUnitCost
        markup
        durationMinutes
        taxable
        visible
        onlineBookingsEnabled
        onlineBookingSortOrder
      }}
    }}
    """
        else:
            # For other entity types, use a minimal query
            # This can be expanded as needed for specific entity types
            return f"""
    query GetEntity($id: EncodedId!) {{
      {entity_type}(id: $id) {{
        id
        createdAt
        updatedAt
      }}
    }}
    """

    def fetch_entity_by_id(self, entity_id: str, nested_notes_limit: int = 10) -> dict[str, Any]:
        """
        Fetch any entity by ID from Jobber GraphQL API using entity-specific queries.

        Jobber's API doesn't support the generic node(id:) interface. Instead,
        it uses entity-specific queries like client(id:), invoice(id:), etc.
        This method decodes the base64 ID to determine the entity type and
        uses the appropriate query.

        Args:
            entity_id: The base64-encoded unique identifier (e.g., "Z2lkOi8vSm9iYmVyL0NsaWVudC80...")
            nested_notes_limit: Number of nested notes to fetch (default: 10)

        Returns:
            Dictionary containing GraphQL response with entity data

        Raises:
            JobberApiError: If API communication fails or entity not found
            ConfigurationError: If authentication configuration is invalid
                               or OAuth2 token refresh fails
        """
        try:
            import base64

            # Decode the base64 ID to extract entity type
            # Format: gid://Jobber/Client/12345
            decoded_id = base64.b64decode(entity_id).decode("utf-8")
            entity_type = decoded_id.split("/")[3]  # Extract "Client" from gid://Jobber/Client/12345

            # Map entity type to query field name (lowercase)
            query_field = entity_type[0].lower() + entity_type[1:]  # Client -> client

            # Build entity-specific query based on type
            query = self._build_single_entity_query(query_field, nested_notes_limit)

            # Execute GraphQL request
            response_data = self._execute_graphql_request(query=query, variables={"id": entity_id})

            # Extract entity data from response
            entity_data = response_data.get("data", {}).get(query_field)

            if entity_data is None:
                raise JobberApiError(f"Entity with ID '{entity_id}' not found")

            # Wrap in same structure as pagination queries for consistency
            # This allows extractors to process single entities the same way as batch entities
            response_data["data"]["node"] = entity_data
            return response_data

        except (ConfigurationError, JobberApiError):
            # Re-raise our domain exceptions as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            raise JobberApiError(f"Unexpected error while fetching entity {entity_id}: {e}") from e

    def fetch_additional_notes(
        self, entity_id: str, entity_type: str, cursor: str, page_size: int = 100
    ) -> dict[str, Any]:
        """
        Fetch additional page of notes for an entity using cursor pagination.

        Args:
            entity_id: The entity's ID (e.g., client ID, invoice ID)
            entity_type: Type of entity ("client", "invoice", "job", "quote", "request")
            cursor: The endCursor from previous page's pageInfo
            page_size: Number of notes to fetch (default: 100)

        Returns:
            Dictionary with 'edges' and 'pageInfo' for the notes page

        Raises:
            JobberApiError: If API communication fails
        """
        note_type_map = {
            "client": "ClientNote",
            "invoice": "InvoiceNote",
            "job": "JobNote",
            "quote": "QuoteNote",
            "request": "RequestNote",
        }
        note_type = note_type_map.get(entity_type)
        if not note_type:
            raise ValueError(f"Unsupported entity type for notes: {entity_type}")

        query = f"""
        query GetAdditionalNotes($id: EncodedId!, $cursor: String!) {{
          {entity_type}(id: $id) {{
            notes(first: {page_size}, after: $cursor) {{
              totalCount
              edges {{
                node {{
                  ... on {note_type} {{
                    id
                    message
                    createdAt
                  }}
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
          }}
        }}
        """

        variables = {"id": entity_id, "cursor": cursor}
        response = self._execute_graphql_request(query, variables=variables)
        entity_data = response.get("data", {}).get(entity_type, {})
        return entity_data.get("notes", {})

    def fetch_additional_attachments(
        self, entity_id: str, entity_type: str, cursor: str, page_size: int = 100
    ) -> dict[str, Any]:
        """
        Fetch additional page of attachments for an entity using cursor pagination.

        Args:
            entity_id: The entity's ID (e.g., client ID, invoice ID)
            entity_type: Type of entity ("client", "invoice", "job", "quote", "request")
            cursor: The endCursor from previous page's pageInfo
            page_size: Number of attachments to fetch (default: 100)

        Returns:
            Dictionary with 'edges' and 'pageInfo' for the attachments page

        Raises:
            JobberApiError: If API communication fails
        """
        note_type_map = {
            "client": "ClientNote",
            "invoice": "InvoiceNote",
            "job": "JobNote",
            "quote": "QuoteNote",
            "request": "RequestNote",
        }
        note_type = note_type_map.get(entity_type)
        if not note_type:
            raise ValueError(f"Unsupported entity type for attachments: {entity_type}")

        query = f"""
        query GetAdditionalAttachments($id: EncodedId!, $cursor: String!) {{
          {entity_type}(id: $id) {{
            noteAttachments(first: {page_size}, after: $cursor) {{
              totalCount
              edges {{
                node {{
                  id
                  note {{
                    ... on {note_type} {{
                      id
                    }}
                  }}
                  fileName
                  contentType
                  url
                  fileSize
                  createdAt
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
          }}
        }}
        """

        variables = {"id": entity_id, "cursor": cursor}
        response = self._execute_graphql_request(query, variables=variables)
        entity_data = response.get("data", {}).get(entity_type, {})
        return entity_data.get("noteAttachments", {})

    # ========================================================================
    # Map Mode Query Variants - Lightweight queries for discovery pass
    # ========================================================================
    # These queries fetch minimal fields (id, updatedAt, totalCount) to enable
    # fast entity discovery and relation counting. Used in multi-pass migration
    # strategy to estimate extraction effort before full data retrieval.
    # Cost: ~5-10 points per query vs ~100-500 for full queries

    def _get_clients_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for clients map mode."""
        size = page_size or self._get_pagination_size("clients")
        return """
    query GetClientsMap($cursor: String) {{
      clients(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            updatedAt
            notes {{
              totalCount
            }}
            noteAttachments {{
              totalCount
            }}
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_invoices_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for invoices map mode."""
        size = page_size or self._get_pagination_size("invoices")
        return """
    query GetInvoicesMap($cursor: String) {{
      invoices(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            updatedAt
            notes {{
              totalCount
            }}
            noteAttachments {{
              totalCount
            }}
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_quotes_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for quotes map mode."""
        size = page_size or self._get_pagination_size("quotes")
        return """
    query GetQuotesMap($cursor: String) {{
      quotes(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            updatedAt
            lineItems {{
              totalCount
            }}
            notes {{
              totalCount
            }}
            noteAttachments {{
              totalCount
            }}
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_jobs_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for jobs map mode."""
        size = page_size or self._get_pagination_size("jobs")
        return """
    query GetJobsMap($cursor: String) {{
      jobs(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            updatedAt
            notes {{
              totalCount
            }}
            noteAttachments {{
              totalCount
            }}
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_properties_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for properties map mode."""
        size = page_size or self._get_pagination_size("properties")
        return """
    query GetPropertiesMap($cursor: String) {{
      properties(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_requests_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for requests map mode."""
        size = page_size or self._get_pagination_size("requests")
        return """
    query GetRequestsMap($cursor: String) {{
      requests(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            updatedAt
            notes {{
              totalCount
            }}
            noteAttachments {{
              totalCount
            }}
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_users_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for users map mode."""
        size = page_size or self._get_pagination_size("users")
        return """
    query GetUsersMap($cursor: String) {{
      users(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            lastLoginAt
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_expenses_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for expenses map mode."""
        size = page_size or self._get_pagination_size("expenses")
        return """
    query GetExpensesMap($cursor: String) {{
      expenses(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            updatedAt
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_visits_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for visits map mode."""
        size = page_size or self._get_pagination_size("visits")
        return """
    query GetVisitsMap($cursor: String) {{
      visits(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            createdAt
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_timesheet_entries_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for timesheet entries map mode."""
        size = page_size or self._get_pagination_size("timesheetEntries")
        return """
    query GetTimesheetEntriesMap($cursor: String) {{
      timeSheetEntries(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
            updatedAt
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_products_services_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for products/services map mode."""
        size = page_size or self._get_pagination_size("productsAndServices")
        return """
    query GetProductsServicesMap($cursor: String) {{
      productOrServices(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
          }}
        }}
      }}
    }}
    """.format(size=size)

    def _get_tax_rates_map_query(self, page_size: Optional[int] = None) -> str:
        """Get lightweight GraphQL query for tax rates map mode."""
        size = page_size or self._get_pagination_size("taxRates")
        return """
    query GetTaxRatesMap($cursor: String) {{
      taxRates(first: {size}, after: $cursor) {{
        totalCount
        pageInfo {{
          hasNextPage
          endCursor
        }}
        edges {{
          node {{
            id
          }}
        }}
      }}
    }}
    """.format(size=size)

    def fetch_clients_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch clients with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_clients_map_query(page_size), cursor)
            if response_data.get("data") is not None and "clients" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'clients' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching clients map: {e}") from e

    def fetch_invoices_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch invoices with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_invoices_map_query(page_size), cursor)
            if response_data.get("data") is not None and "invoices" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'invoices' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching invoices map: {e}") from e

    def fetch_quotes_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch quotes with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_quotes_map_query(page_size), cursor)
            if response_data.get("data") is not None and "quotes" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'quotes' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching quotes map: {e}") from e

    def fetch_jobs_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch jobs with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_jobs_map_query(page_size), cursor)
            if response_data.get("data") is not None and "jobs" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'jobs' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching jobs map: {e}") from e

    def fetch_properties_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch properties with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_properties_map_query(page_size), cursor)
            if response_data.get("data") is not None and "properties" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'properties' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching properties map: {e}") from e

    def fetch_requests_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch requests with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_requests_map_query(page_size), cursor)
            if response_data.get("data") is not None and "requests" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'requests' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching requests map: {e}") from e

    def fetch_users_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch users with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_users_map_query(page_size), cursor)
            if response_data.get("data") is not None and "users" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'users' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching users map: {e}") from e

    def fetch_expenses_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch expenses with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_expenses_map_query(page_size), cursor)
            if response_data.get("data") is not None and "expenses" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'expenses' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching expenses map: {e}") from e

    def fetch_visits_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch visits with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_visits_map_query(page_size), cursor)
            if response_data.get("data") is not None and "visits" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'visits' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching visits map: {e}") from e

    def fetch_timesheet_entries_map(
        self, cursor: Optional[str] = None, page_size: Optional[int] = None
    ) -> dict[str, Any]:
        """Fetch timesheet entries with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_timesheet_entries_map_query(page_size), cursor)
            if response_data.get("data") is not None and "timeSheetEntries" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'timeSheetEntries' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching timesheet entries map: {e}") from e

    def fetch_products_services_map(
        self, cursor: Optional[str] = None, page_size: Optional[int] = None
    ) -> dict[str, Any]:
        """Fetch products/services with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_products_services_map_query(page_size), cursor)
            if response_data.get("data") is not None and "productOrServices" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'productOrServices' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching products/services map: {e}") from e

    def fetch_tax_rates_map(self, cursor: Optional[str] = None, page_size: Optional[int] = None) -> dict[str, Any]:
        """Fetch tax rates with minimal fields for map mode (discovery pass)."""
        try:
            response_data = self._execute_graphql_request(self._get_tax_rates_map_query(page_size), cursor)
            if response_data.get("data") is not None and "taxRates" not in response_data["data"]:
                raise JobberApiError("Invalid response structure: missing 'taxRates' field in data")
            return response_data
        except (ConfigurationError, JobberApiError):
            raise
        except Exception as e:
            raise JobberApiError(f"Unexpected error while fetching tax rates map: {e}") from e
