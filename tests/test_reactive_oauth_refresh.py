"""
Test module for reactive OAuth token refresh functionality in RateLimitedHttpClient.

This module tests the enhanced RateLimitedHttpClient that automatically attempts
OAuth token refresh when receiving HTTP 401 Unauthorized responses.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from src.auth.auth_provider import AuthProvider
from src.exceptions import ConfigurationError, JobberApiError
from src.rate_limiting.backoff_strategy import ExponentialBackoffStrategy
from src.rate_limiting.rate_limited_http_client import RateLimitedHttpClient
from src.rate_limiting.token_bucket import TokenBucketRateLimiter


class TestReactiveOAuthRefresh:
    """Test reactive OAuth token refresh in RateLimitedHttpClient."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock HTTP client
        self.mock_http_client = Mock()

        # Mock rate limiting components
        self.mock_rate_limiter = Mock(spec=TokenBucketRateLimiter)
        self.mock_rate_limiter.consume.return_value = True  # Always have tokens
        self.mock_rate_limiter.get_available_tokens.return_value = 10.0
        self.mock_rate_limiter.get_capacity.return_value = 100.0

        self.mock_backoff_strategy = Mock(spec=ExponentialBackoffStrategy)
        self.mock_backoff_strategy.calculate_delay.return_value = (
            0.1  # Short delay for tests
        )

        # Mock auth provider
        self.mock_auth_provider = Mock(spec=AuthProvider)

        # Create RateLimitedHttpClient with auth provider
        self.rate_limited_client = RateLimitedHttpClient(
            http_client=self.mock_http_client,
            rate_limiter=self.mock_rate_limiter,
            backoff_strategy=self.mock_backoff_strategy,
            max_retries=3,
            auth_provider=self.mock_auth_provider,
        )

    def test_successful_request_no_refresh_needed(self):
        """Test that successful requests don't trigger token refresh."""
        # Arrange
        expected_response = {"data": {"clients": []}}
        self.mock_http_client.post.return_value = expected_response

        # Act
        result = self.rate_limited_client.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer valid_token"},
            json={"query": "{ clients { id } }"},
        )

        # Assert
        assert result == expected_response
        self.mock_http_client.post.assert_called_once()
        self.mock_auth_provider.force_refresh_token.assert_not_called()

    def test_401_error_triggers_token_refresh_success(self):
        """Test that 401 error triggers token refresh and successful retry."""
        # Arrange
        auth_error = ConfigurationError("Invalid or expired authentication token")
        success_response = {"data": {"clients": []}}

        # First call fails with 401, second call succeeds
        self.mock_http_client.post.side_effect = [auth_error, success_response]

        # Mock successful token refresh
        new_token = "new_fresh_token"
        self.mock_auth_provider.force_refresh_token.return_value = new_token

        # Act
        result = self.rate_limited_client.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer expired_token"},
            json={"query": "{ clients { id } }"},
        )

        # Assert
        assert result == success_response
        assert self.mock_http_client.post.call_count == 2
        self.mock_auth_provider.force_refresh_token.assert_called_once()

        # Verify the second call used the new token
        second_call_args = self.mock_http_client.post.call_args_list[1]
        assert second_call_args[1]["headers"]["Authorization"] == f"Bearer {new_token}"

    def test_401_error_refresh_fails_raises_original_error(self):
        """Test that if token refresh fails, original error is raised."""
        # Arrange
        auth_error = ConfigurationError("Invalid or expired authentication token")
        refresh_error = ConfigurationError(
            "OAuth2 tokens are invalid and refresh failed"
        )

        self.mock_http_client.post.side_effect = auth_error
        self.mock_auth_provider.force_refresh_token.side_effect = refresh_error

        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            self.rate_limited_client.post(
                url="https://api.getjobber.com/api/graphql",
                headers={"Authorization": "Bearer expired_token"},
                json={"query": "{ clients { id } }"},
            )

        # Should raise original auth error with refresh error as cause
        assert "Invalid or expired authentication token" in str(exc_info.value)
        self.mock_auth_provider.force_refresh_token.assert_called_once()

    def test_401_error_without_auth_provider_raises_immediately(self):
        """Test that 401 error without auth provider raises immediately."""
        # Arrange
        auth_error = ConfigurationError("Invalid or expired authentication token")
        self.mock_http_client.post.side_effect = auth_error

        # Create client without auth provider
        client_without_auth = RateLimitedHttpClient(
            http_client=self.mock_http_client,
            rate_limiter=self.mock_rate_limiter,
            backoff_strategy=self.mock_backoff_strategy,
            max_retries=3,
            auth_provider=None,  # No auth provider
        )

        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            client_without_auth.post(
                url="https://api.getjobber.com/api/graphql",
                headers={"Authorization": "Bearer expired_token"},
                json={"query": "{ clients { id } }"},
            )

        assert "Invalid or expired authentication token" in str(exc_info.value)
        self.mock_http_client.post.assert_called_once()

    def test_401_error_refresh_success_but_still_401_raises_error(self):
        """Test that if refresh succeeds but retry still gets 401, error is raised."""
        # Arrange
        auth_error = ConfigurationError("Invalid or expired authentication token")

        # Both calls fail with 401
        self.mock_http_client.post.side_effect = [auth_error, auth_error]

        # Mock successful token refresh
        new_token = "new_fresh_token"
        self.mock_auth_provider.force_refresh_token.return_value = new_token

        # Act & Assert
        with pytest.raises(ConfigurationError):
            self.rate_limited_client.post(
                url="https://api.getjobber.com/api/graphql",
                headers={"Authorization": "Bearer expired_token"},
                json={"query": "{ clients { id } }"},
            )

        # Should have called refresh and attempted retry
        self.mock_auth_provider.force_refresh_token.assert_called_once()
        assert self.mock_http_client.post.call_count == 2

    def test_non_auth_error_does_not_trigger_refresh(self):
        """Test that non-authentication errors don't trigger token refresh."""
        # Arrange
        network_error = JobberApiError("Network timeout")
        self.mock_http_client.post.side_effect = network_error

        # Act & Assert
        with pytest.raises(JobberApiError):
            self.rate_limited_client.post(
                url="https://api.getjobber.com/api/graphql",
                headers={"Authorization": "Bearer valid_token"},
                json={"query": "{ clients { id } }"},
            )

        self.mock_auth_provider.force_refresh_token.assert_not_called()

    def test_rate_limit_error_does_not_trigger_auth_refresh(self):
        """Test that rate limit errors use normal retry logic, not auth refresh."""
        # Arrange
        rate_limit_error = JobberApiError("API returned HTTP 429: Too Many Requests")
        success_response = {"data": {"clients": []}}

        # First call rate limited, second succeeds
        self.mock_http_client.post.side_effect = [rate_limit_error, success_response]

        # Act
        result = self.rate_limited_client.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer valid_token"},
            json={"query": "{ clients { id } }"},
        )

        # Assert
        assert result == success_response
        assert self.mock_http_client.post.call_count == 2
        self.mock_auth_provider.force_refresh_token.assert_not_called()

    @pytest.mark.parametrize(
        "auth_error_message",
        [
            "Invalid or expired authentication token",
            "401",
            "unauthorized",
            "authentication failed",
        ],
    )
    def test_various_auth_error_patterns_trigger_refresh(self, auth_error_message):
        """Test that various authentication error patterns trigger refresh."""
        # Arrange
        auth_error = ConfigurationError(auth_error_message)
        success_response = {"data": {"clients": []}}

        self.mock_http_client.post.side_effect = [auth_error, success_response]
        self.mock_auth_provider.force_refresh_token.return_value = "new_token"

        # Act
        result = self.rate_limited_client.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer expired_token"},
            json={"query": "{ clients { id } }"},
        )

        # Assert
        assert result == success_response
        self.mock_auth_provider.force_refresh_token.assert_called_once()

    def test_auth_refresh_only_attempted_on_first_attempt(self):
        """Test that auth refresh is only attempted on the first attempt to prevent loops."""
        # Arrange
        auth_error = ConfigurationError("Invalid or expired authentication token")

        # All calls fail with 401
        self.mock_http_client.post.side_effect = auth_error
        self.mock_auth_provider.force_refresh_token.return_value = "new_token"

        # Act & Assert
        with pytest.raises(ConfigurationError):
            self.rate_limited_client.post(
                url="https://api.getjobber.com/api/graphql",
                headers={"Authorization": "Bearer expired_token"},
                json={"query": "{ clients { id } }"},
            )

        # Should only attempt refresh once (on first attempt)
        self.mock_auth_provider.force_refresh_token.assert_called_once()
        # Should make initial call + one retry after refresh
        assert self.mock_http_client.post.call_count == 2

    def test_integration_with_real_auth_provider_mock(self):
        """Integration test with more realistic AuthProvider behavior."""
        # Arrange
        mock_oauth_manager = Mock()
        mock_repository = Mock()

        # Create real AuthProvider with mocked dependencies
        auth_provider = AuthProvider(mock_oauth_manager, mock_repository)

        # Mock repository to return valid tokens
        mock_repository.get_oauth_tokens.return_value = {
            "access_token": "old_token",
            "refresh_token": "valid_refresh_token",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Mock successful token refresh
        mock_oauth_manager.refresh_access_token.return_value = {
            "access_token": "new_fresh_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }

        # Create client with real auth provider
        client = RateLimitedHttpClient(
            http_client=self.mock_http_client,
            rate_limiter=self.mock_rate_limiter,
            backoff_strategy=self.mock_backoff_strategy,
            max_retries=3,
            auth_provider=auth_provider,
        )

        # Mock HTTP responses
        auth_error = ConfigurationError("Invalid or expired authentication token")
        success_response = {"data": {"clients": []}}
        self.mock_http_client.post.side_effect = [auth_error, success_response]

        # Act
        result = client.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer expired_token"},
            json={"query": "{ clients { id } }"},
        )

        # Assert
        assert result == success_response
        mock_oauth_manager.refresh_access_token.assert_called_once_with(
            "valid_refresh_token"
        )
        mock_repository.save_oauth_tokens.assert_called_once()

        # Verify new token was used in retry
        second_call_args = self.mock_http_client.post.call_args_list[1]
        assert (
            second_call_args[1]["headers"]["Authorization"] == "Bearer new_fresh_token"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
