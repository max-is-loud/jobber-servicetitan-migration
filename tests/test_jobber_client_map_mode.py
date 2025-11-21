"""Unit tests for JobberClient map mode query methods."""

from unittest.mock import Mock, patch
import pytest

from src.clients.jobber_client import JobberClient
from src.exceptions import JobberApiError, ConfigurationError


class TestJobberClientMapModeQueries:
    """Test suite for JobberClient map mode (lightweight) query methods."""

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration provider."""
        config = Mock()
        config.get_jobber_api_url.return_value = "https://api.getjobber.com/api/graphql"
        config.get_jobber_access_token.return_value = "test_token_123"
        return config

    @pytest.fixture
    def mock_oauth_provider(self):
        """Create mock OAuth provider."""
        provider = Mock()
        provider.get_access_token.return_value = "test_token_123"
        return provider

    @pytest.fixture
    def jobber_client(self, mock_config, mock_oauth_provider):
        """Create JobberClient instance with mocked dependencies."""
        return JobberClient(mock_config, mock_oauth_provider)

    # Test clients map mode query
    def test_fetch_clients_map_returns_valid_response(self, jobber_client):
        """Test fetch_clients_map returns properly structured response."""
        mock_response = {
            "data": {
                "clients": {
                    "totalCount": 150,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_abc"},
                    "edges": [
                        {
                            "node": {
                                "id": "client_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 5},
                                "noteAttachments": {"totalCount": 3},
                            }
                        },
                        {
                            "node": {
                                "id": "client_2",
                                "updatedAt": "2023-11-16T10:00:00Z",
                                "notes": {"totalCount": 2},
                                "noteAttachments": {"totalCount": 1},
                            }
                        },
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_clients_map()

        assert result == mock_response
        assert "data" in result
        assert "clients" in result["data"]
        assert result["data"]["clients"]["totalCount"] == 150

    def test_fetch_clients_map_with_cursor_pagination(self, jobber_client):
        """Test fetch_clients_map handles cursor-based pagination."""
        mock_response = {
            "data": {
                "clients": {
                    "totalCount": 150,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response) as mock_execute:
            result = jobber_client.fetch_clients_map(cursor="cursor_xyz")

        mock_execute.assert_called_once()
        assert "cursor_xyz" in str(mock_execute.call_args)

    def test_fetch_clients_map_raises_error_on_invalid_response(self, jobber_client):
        """Test fetch_clients_map raises error when response structure is invalid."""
        mock_response = {"data": {}}  # Missing 'clients' field

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            with pytest.raises(JobberApiError, match="missing 'clients' field"):
                jobber_client.fetch_clients_map()

    # Test invoices map mode query
    def test_fetch_invoices_map_returns_valid_response(self, jobber_client):
        """Test fetch_invoices_map returns properly structured response."""
        mock_response = {
            "data": {
                "invoices": {
                    "totalCount": 200,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_inv"},
                    "edges": [
                        {
                            "node": {
                                "id": "invoice_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 1},
                                "noteAttachments": {"totalCount": 0},
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_invoices_map()

        assert result == mock_response
        assert result["data"]["invoices"]["totalCount"] == 200

    # Test quotes map mode query
    def test_fetch_quotes_map_includes_line_items_count(self, jobber_client):
        """Test fetch_quotes_map includes lineItems totalCount."""
        mock_response = {
            "data": {
                "quotes": {
                    "totalCount": 50,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "quote_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "lineItems": {"totalCount": 10},
                                "notes": {"totalCount": 2},
                                "noteAttachments": {"totalCount": 1},
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_quotes_map()

        quote_node = result["data"]["quotes"]["edges"][0]["node"]
        assert "lineItems" in quote_node
        assert quote_node["lineItems"]["totalCount"] == 10

    # Test jobs map mode query
    def test_fetch_jobs_map_returns_valid_response(self, jobber_client):
        """Test fetch_jobs_map returns properly structured response."""
        mock_response = {
            "data": {
                "jobs": {
                    "totalCount": 300,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_job"},
                    "edges": [
                        {
                            "node": {
                                "id": "job_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "visits": {"totalCount": 3},
                                "notes": {"totalCount": 5},
                                "noteAttachments": {"totalCount": 2},
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_jobs_map()

        assert result["data"]["jobs"]["totalCount"] == 300

    # Test properties map mode query
    def test_fetch_properties_map_returns_valid_response(self, jobber_client):
        """Test fetch_properties_map returns properly structured response."""
        mock_response = {
            "data": {
                "properties": {
                    "totalCount": 175,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "property_1",
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_properties_map()

        assert result["data"]["properties"]["totalCount"] == 175

    # Test requests map mode query
    def test_fetch_requests_map_returns_valid_response(self, jobber_client):
        """Test fetch_requests_map returns properly structured response."""
        mock_response = {
            "data": {
                "requests": {
                    "totalCount": 80,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_req"},
                    "edges": [
                        {
                            "node": {
                                "id": "request_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 0},
                                "noteAttachments": {"totalCount": 0},
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_requests_map()

        assert result["data"]["requests"]["totalCount"] == 80

    # Test users map mode query
    def test_fetch_users_map_returns_valid_response(self, jobber_client):
        """Test fetch_users_map returns properly structured response."""
        mock_response = {
            "data": {
                "users": {
                    "totalCount": 15,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "user_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_users_map()

        assert result["data"]["users"]["totalCount"] == 15

    # Test expenses map mode query
    def test_fetch_expenses_map_returns_valid_response(self, jobber_client):
        """Test fetch_expenses_map returns properly structured response."""
        mock_response = {
            "data": {
                "expenses": {
                    "totalCount": 120,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_exp"},
                    "edges": [
                        {
                            "node": {
                                "id": "expense_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 1},
                                "noteAttachments": {"totalCount": 2},
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_expenses_map()

        assert result["data"]["expenses"]["totalCount"] == 120

    # Test visits map mode query
    def test_fetch_visits_map_returns_valid_response(self, jobber_client):
        """Test fetch_visits_map returns properly structured response."""
        mock_response = {
            "data": {
                "visits": {
                    "totalCount": 250,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_visit"},
                    "edges": [
                        {
                            "node": {
                                "id": "visit_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 3},
                                "noteAttachments": {"totalCount": 1},
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_visits_map()

        assert result["data"]["visits"]["totalCount"] == 250

    # Test timesheet entries map mode query
    def test_fetch_timesheet_entries_map_returns_valid_response(self, jobber_client):
        """Test fetch_timesheet_entries_map returns properly structured response."""
        mock_response = {
            "data": {
                "timeSheetEntries": {
                    "totalCount": 400,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "timesheet_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 0},
                                "noteAttachments": {"totalCount": 0},
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_timesheet_entries_map()

        assert result["data"]["timeSheetEntries"]["totalCount"] == 400

    # Test products & services map mode query
    def test_fetch_products_services_map_returns_valid_response(self, jobber_client):
        """Test fetch_products_services_map returns properly structured response."""
        mock_response = {
            "data": {
                "productOrServices": {
                    "totalCount": 75,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_prod"},
                    "edges": [
                        {
                            "node": {
                                "id": "product_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_products_services_map()

        assert result["data"]["productOrServices"]["totalCount"] == 75

    # Test tax rates map mode query
    def test_fetch_tax_rates_map_returns_valid_response(self, jobber_client):
        """Test fetch_tax_rates_map returns properly structured response."""
        mock_response = {
            "data": {
                "taxRates": {
                    "totalCount": 10,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "tax_1",
                            }
                        }
                    ],
                }
            }
        }

        with patch.object(jobber_client, "_execute_graphql_request", return_value=mock_response):
            result = jobber_client.fetch_tax_rates_map()

        assert result["data"]["taxRates"]["totalCount"] == 10

    # Test error handling across all map mode queries
    def test_map_mode_query_handles_api_error(self, jobber_client):
        """Test map mode query propagates API errors."""
        with patch.object(jobber_client, "_execute_graphql_request", side_effect=JobberApiError("API Error")):
            with pytest.raises(JobberApiError, match="API Error"):
                jobber_client.fetch_clients_map()

    def test_map_mode_query_handles_unexpected_exception(self, jobber_client):
        """Test map mode query wraps unexpected exceptions."""
        with patch.object(jobber_client, "_execute_graphql_request", side_effect=ValueError("Unexpected")):
            with pytest.raises(JobberApiError, match="Unexpected error"):
                jobber_client.fetch_clients_map()

    # Test that queries contain minimal fields
    def test_clients_map_query_contains_minimal_fields(self, jobber_client):
        """Test clients map query contains only essential fields."""
        query = jobber_client._get_clients_map_query()

        # Should have minimal fields
        assert "id" in query
        assert "updatedAt" in query
        assert "totalCount" in query
        assert "pageInfo" in query

        # Should NOT have heavy fields
        assert "firstName" not in query
        assert "lastName" not in query
        assert "email" not in query
        assert "companyName" not in query

    def test_quotes_map_query_contains_line_items_count(self, jobber_client):
        """Test quotes map query includes line items totalCount."""
        query = jobber_client._get_quotes_map_query()

        assert "lineItems" in query
        assert "totalCount" in query

    def test_jobs_map_query_contains_visits_count(self, jobber_client):
        """Test jobs map query includes visits totalCount."""
        query = jobber_client._get_jobs_map_query()

        assert "visits" in query or "totalCount" in query

    def test_properties_map_query_contains_minimal_fields(self, jobber_client):
        """Test properties map query contains minimal fields."""
        query = jobber_client._get_properties_map_query()
        assert "id" in query
        assert "totalCount" in query
        assert "address" not in query  # Heavy field

    def test_requests_map_query_contains_minimal_fields(self, jobber_client):
        """Test requests map query contains minimal fields."""
        query = jobber_client._get_requests_map_query()
        assert "id" in query
        assert "updatedAt" in query
        assert "notes" in query
        assert "description" not in query  # Heavy field

    def test_users_map_query_contains_minimal_fields(self, jobber_client):
        """Test users map query contains minimal fields."""
        query = jobber_client._get_users_map_query()
        assert "id" in query
        assert "lastLoginAt" in query
        assert "email" not in query  # Heavy field

    def test_expenses_map_query_contains_minimal_fields(self, jobber_client):
        """Test expenses map query contains minimal fields."""
        query = jobber_client._get_expenses_map_query()
        assert "id" in query
        assert "updatedAt" in query
        assert "description" not in query  # Heavy field

    def test_visits_map_query_contains_minimal_fields(self, jobber_client):
        """Test visits map query contains minimal fields."""
        query = jobber_client._get_visits_map_query()
        assert "id" in query
        assert "createdAt" in query
        assert "instructions" not in query  # Heavy field

    def test_timesheet_entries_map_query_contains_minimal_fields(self, jobber_client):
        """Test timesheet entries map query contains minimal fields."""
        query = jobber_client._get_timesheet_entries_map_query()
        assert "id" in query
        assert "updatedAt" in query
        assert "note" not in query  # Heavy field

    def test_products_services_map_query_contains_minimal_fields(self, jobber_client):
        """Test products/services map query contains minimal fields."""
        query = jobber_client._get_products_services_map_query()
        assert "id" in query
        assert "description" not in query  # Heavy field

    def test_tax_rates_map_query_contains_minimal_fields(self, jobber_client):
        """Test tax rates map query contains minimal fields."""
        query = jobber_client._get_tax_rates_map_query()
        assert "id" in query
        assert "description" not in query  # Heavy field
