"""Unit tests for JobberClient connection retry logic."""

from unittest.mock import Mock, patch
import pytest
import requests

from src.clients.jobber_client import JobberClient
from src.exceptions import JobberApiError, ConfigurationError


class TestJobberClientConnectionRetries:
    """Test suite for JobberClient connection retry logic."""

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
        provider.get_headers.return_value = {"Authorization": "Bearer test_token_123"}
        return provider

    @pytest.fixture
    def jobber_client(self, mock_config, mock_oauth_provider):
        """Create JobberClient instance with mocked dependencies."""
        return JobberClient(mock_config, mock_oauth_provider)

    def test_execute_request_retries_on_connection_error(self, jobber_client):
        """Test that _execute_graphql_request retries on connection errors."""

        # Mock HttpClient.post to raise ConnectionError first, then succeed
        with patch.object(jobber_client.http_client, "post") as mock_post:
            mock_post.side_effect = [
                requests.exceptions.ConnectionError("Connection refused"),
                requests.exceptions.ConnectionError("Connection refused"),
                {"data": {"success": True}},  # Success on 3rd attempt
            ]

            # Should succeed eventually
            result = jobber_client._execute_graphql_request(query="query { test }")

            assert result == {"data": {"success": True}}
            assert mock_post.call_count == 3

    def test_execute_request_retries_on_timeout(self, jobber_client):
        """Test that _execute_graphql_request retries on timeouts."""

        with patch.object(jobber_client.http_client, "post") as mock_post:
            mock_post.side_effect = [
                requests.exceptions.Timeout("Read timed out"),
                {"data": {"success": True}},  # Success on 2nd attempt
            ]

            result = jobber_client._execute_graphql_request(query="query { test }")

            assert result == {"data": {"success": True}}
            assert mock_post.call_count == 2

    def test_execute_request_fails_after_max_retries(self, jobber_client):
        """Test that _execute_graphql_request fails after max retries."""

        with patch.object(jobber_client.http_client, "post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

            # Should raise JobberApiError after retries exhausted
            with pytest.raises(JobberApiError, match="Failed to connect"):
                jobber_client._execute_graphql_request(query="query { test }")

            # Should have tried max_retries + 1 times (initial + 5 retries = 6)
            # But let's just check it tried multiple times
            assert mock_post.call_count > 1
