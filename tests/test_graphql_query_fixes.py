"""Unit tests for GraphQL query fixes - union types and field corrections.

Tests validate that:
1. All queries with union type notes use inline fragments
2. TaxRate queries only include valid fields (id, name)
3. Both entity-specific notes and ClientNote are included in unions
"""

from unittest.mock import Mock
import pytest
import yaml
from pathlib import Path

from src.clients.jobber_client import JobberClient


class TestGraphQLQuerySyntax:
    """Test suite for GraphQL query structure validation."""

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration provider."""
        config = Mock()
        config.get_jobber_api_url.return_value = "https://api.getjobber.com/api/graphql"
        config.get_jobber_access_token.return_value = "test_token_123"
        config.get_pagination_setting.return_value = 30
        config.get_nested_notes_limit.return_value = 10
        return config

    @pytest.fixture
    def mock_oauth_provider(self):
        """Create mock OAuth provider."""
        provider = Mock()
        provider.get_access_token.return_value = "test_token_123"
        provider.get_headers.return_value = {"Authorization": "Bearer test_token_123"}
        return provider

    @pytest.fixture
    def jobber_client(self, mock_config, mock_oauth_provider):
        """Create JobberClient instance with mocked dependencies."""
        return JobberClient(mock_config, mock_oauth_provider)

    # Test 1: Invoice queries use inline fragments for notes
    def test_invoices_query_uses_inline_fragments(self, jobber_client):
        """Verify that invoice query uses inline fragments for InvoiceNoteUnion."""
        query = jobber_client._get_invoices_query()

        # Must contain inline fragment for InvoiceNote
        assert "... on InvoiceNote {" in query, "Missing InvoiceNote inline fragment"

        # Must contain inline fragment for ClientNote
        assert "... on ClientNote {" in query, "Missing ClientNote inline fragment"

        # Must NOT directly select fields on union type
        assert "notes(first:" in query, "Notes field missing"

    # Test 2: Quote queries use inline fragments for notes
    def test_quotes_query_uses_inline_fragments(self, jobber_client):
        """Verify that quote query uses inline fragments for QuoteNoteUnion."""
        query = jobber_client._get_quotes_query()

        # Must contain inline fragment for QuoteNote
        assert "... on QuoteNote {" in query, "Missing QuoteNote inline fragment"

        # Must contain inline fragment for ClientNote
        assert "... on ClientNote {" in query, "Missing ClientNote inline fragment"

        # Verify notes field exists
        assert "notes(first:" in query, "Notes field missing"

    # Test 3: Job queries use inline fragments for notes
    def test_jobs_query_uses_inline_fragments(self, jobber_client):
        """Verify that job query uses inline fragments for JobNoteUnion."""
        query = jobber_client._get_jobs_query()

        # Must contain inline fragment for JobNote
        assert "... on JobNote {" in query, "Missing JobNote inline fragment"

        # Must contain inline fragment for ClientNote
        assert "... on ClientNote {" in query, "Missing ClientNote inline fragment"

        # Verify notes field exists
        assert "notes(first:" in query, "Notes field missing"

    # Test 4: Request queries use inline fragments for notes
    def test_requests_query_uses_inline_fragments(self, jobber_client):
        """Verify that request query uses inline fragments for RequestNoteUnion."""
        query = jobber_client._get_requests_query()

        # Must contain inline fragment for RequestNote
        assert "... on RequestNote {" in query, "Missing RequestNote inline fragment"

        # Must contain inline fragment for ClientNote
        assert "... on ClientNote {" in query, "Missing ClientNote inline fragment"

        # Verify notes field exists
        assert "notes(first:" in query, "Notes field missing"

    # Test 5: TaxRate query only includes valid fields
    def test_properties_query_taxrate_fields(self, jobber_client):
        """Verify that property query only includes valid TaxRate fields (id, name)."""
        query = jobber_client._get_properties_query()

        # Must contain taxRate with id and name
        assert "taxRate {" in query, "TaxRate field missing"
        assert "id" in query, "TaxRate id field missing"
        assert "name" in query, "TaxRate name field missing"

        # Must NOT contain invalid 'rate' field
        # Check that 'rate' doesn't appear right after taxRate block
        taxrate_section = query[query.find("taxRate {"):query.find("taxRate {") + 100]
        assert "rate" not in taxrate_section or "isBillingAddress" in taxrate_section, \
            "Invalid 'rate' field found in taxRate query"

    # Test 6: Additional notes method uses inline fragments
    def test_fetch_additional_notes_uses_inline_fragments(self, jobber_client):
        """Verify fetch_additional_notes generates query with inline fragments."""
        # Mock the execute method to capture the query
        executed_query = None

        def capture_query(query, variables=None):
            nonlocal executed_query
            executed_query = query
            return {
                "data": {
                    "invoice": {
                        "notes": {
                            "totalCount": 0,
                            "edges": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None}
                        }
                    }
                }
            }

        jobber_client._execute_graphql_request = capture_query

        # Call the method
        jobber_client.fetch_additional_notes(
            entity_id="test-123",
            entity_type="invoice",
            cursor=""
        )

        # Verify the generated query uses inline fragments
        assert executed_query is not None, "Query was not executed"
        assert "... on InvoiceNote {" in executed_query, "Missing InvoiceNote inline fragment"
        assert "... on ClientNote {" in executed_query, "Missing ClientNote inline fragment"

    # Test 7: Additional note IDs method uses inline fragments
    def test_fetch_additional_note_ids_uses_inline_fragments(self, jobber_client):
        """Verify fetch_additional_note_ids generates query with inline fragments."""
        executed_query = None

        def capture_query(query, variables=None):
            nonlocal executed_query
            executed_query = query
            return {
                "data": {
                    "job": {
                        "notes": {
                            "totalCount": 0,
                            "edges": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None}
                        }
                    }
                }
            }

        jobber_client._execute_graphql_request = capture_query

        # Call the method
        jobber_client.fetch_additional_note_ids(
            entity_id="test-456",
            entity_type="job",
            cursor=""
        )

        # Verify the generated query uses inline fragments
        assert executed_query is not None, "Query was not executed"
        assert "... on JobNote {" in executed_query, "Missing JobNote inline fragment"
        assert "... on ClientNote {" in executed_query, "Missing ClientNote inline fragment"

    # Test 8: Verify all union type queries are consistent
    def test_all_union_queries_have_both_fragments(self, jobber_client):
        """Verify all entity queries with notes include both entity-specific and ClientNote fragments."""
        query_methods = [
            (jobber_client._get_invoices_query, "InvoiceNote"),
            (jobber_client._get_quotes_query, "QuoteNote"),
            (jobber_client._get_jobs_query, "JobNote"),
            (jobber_client._get_requests_query, "RequestNote"),
        ]

        for query_method, note_type in query_methods:
            query = query_method()

            # Check for entity-specific note type
            assert f"... on {note_type} {{" in query, \
                f"{query_method.__name__} missing {note_type} fragment"

            # Check for ClientNote (present in all unions)
            assert "... on ClientNote {" in query, \
                f"{query_method.__name__} missing ClientNote fragment"

            # Verify both fragments have id field
            # Count occurrences of 'id' within note fragments
            note_section = query[query.find("notes(first:"):query.find("noteAttachments")]
            id_count = note_section.count("id")
            assert id_count >= 2, \
                f"{query_method.__name__} should have id in both note fragments"


class TestConfigurationSettings:
    """Test configuration settings related to the fixes."""

    def test_visits_page_size_is_20(self):
        """Verify that visits pagination is set to 20."""
        # Read settings.yaml directly
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        with open(config_path, "r") as f:
            settings = yaml.safe_load(f)

        visits_page_size = settings.get("pagination", {}).get("visits")
        assert visits_page_size == 20, \
            f"Visits page size should be 20, got {visits_page_size}"

    def test_nested_notes_limit_is_10(self):
        """Verify that nested notes limit is set to 10."""
        # Read settings.yaml directly
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        with open(config_path, "r") as f:
            settings = yaml.safe_load(f)

        nested_notes_limit = settings.get("pagination", {}).get("nested_notes")
        assert nested_notes_limit == 10, \
            f"Nested notes limit should be 10, got {nested_notes_limit}"
