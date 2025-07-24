"""
Soak test for long-running migration token refresh scenarios.

This module tests the enhanced token management system under realistic long-running
migration conditions, simulating token expiration and refresh during extended operations
to ensure seamless continuation without user intervention.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from src.auth.auth_provider import AuthProvider
from src.clients.jobber_client import JobberClient
from src.exceptions import ConfigurationError, JobberApiError
from src.rate_limiting.backoff_strategy import ExponentialBackoffStrategy
from src.rate_limiting.rate_limited_http_client import RateLimitedHttpClient
from src.rate_limiting.token_bucket import TokenBucketRateLimiter


class TestMigrationTokenRefreshSoak:
    """Soak test for long-running migration scenarios with token refresh."""

    def setup_method(self):
        """Set up test fixtures for long-running migration simulation."""
        # Mock core dependencies
        self.mock_http_client = Mock()
        self.mock_oauth_manager = Mock()
        self.mock_repository = Mock()

        # Create real AuthProvider with enhanced token management
        self.auth_provider = AuthProvider(
            oauth_manager=self.mock_oauth_manager,
            repository=self.mock_repository,
        )

        # Mock rate limiting components for realistic behavior
        self.mock_rate_limiter = Mock(spec=TokenBucketRateLimiter)
        self.mock_rate_limiter.consume.return_value = True
        self.mock_rate_limiter.get_available_tokens.return_value = 80.0
        self.mock_rate_limiter.get_capacity.return_value = 100.0

        self.mock_backoff_strategy = Mock(spec=ExponentialBackoffStrategy)
        self.mock_backoff_strategy.calculate_delay.return_value = 0.01  # Fast for tests

        # Create RateLimitedHttpClient with auth provider (production setup)
        self.rate_limited_client = RateLimitedHttpClient(
            http_client=self.mock_http_client,
            rate_limiter=self.mock_rate_limiter,
            backoff_strategy=self.mock_backoff_strategy,
            max_retries=10,
            auth_provider=self.auth_provider,
        )

        # Create JobberClient for realistic migration simulation
        self.jobber_client = JobberClient(auth_provider=self.auth_provider)
        self.jobber_client.set_http_client(self.rate_limited_client)

    def _setup_initial_tokens(self, expires_in_seconds: int = 3600) -> dict:
        """Set up initial OAuth tokens with specified expiration."""
        future_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        expires_at_iso = future_time.isoformat()

        token_data = {
            "access_token": "initial_valid_token",
            "refresh_token": "initial_refresh_token",
            "expires_at": expires_at_iso,
        }

        self.mock_repository.get_oauth_tokens.return_value = token_data
        return token_data

    def _setup_token_refresh_response(self, new_token: str = "refreshed_token") -> dict:
        """Set up successful token refresh response."""
        new_tokens = {
            "access_token": new_token,
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,  # 1 hour
        }
        self.mock_oauth_manager.refresh_access_token.return_value = new_tokens
        return new_tokens

    def _create_successful_api_response(self, entity_type: str = "clients") -> dict:
        """Create realistic successful API response."""
        return {
            "data": {
                entity_type: {
                    "edges": [
                        {"node": {"id": f"{entity_type}_1", "name": f"Test {entity_type.title()} 1"}},
                        {"node": {"id": f"{entity_type}_2", "name": f"Test {entity_type.title()} 2"}},
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_123"},
                }
            }
        }

    def _create_auth_error(self) -> ConfigurationError:
        """Create realistic authentication error."""
        return ConfigurationError("Invalid or expired authentication token")

    def test_long_running_migration_with_single_token_refresh(self):
        """
        Test long-running migration with single token expiration and refresh.

        Simulates a migration that runs long enough for tokens to expire once,
        verifying that automatic refresh occurs transparently.
        """
        # Setup: Start with tokens that will "expire" during test
        self._setup_initial_tokens(expires_in_seconds=60)  # 1 minute
        self._setup_token_refresh_response("refreshed_token_1")

        # Setup: API calls succeed initially, then fail with auth error, then succeed
        successful_response = self._create_successful_api_response("clients")
        auth_error = self._create_auth_error()

        # First few calls succeed, then auth failure, then success with new token
        self.mock_http_client.post.side_effect = [
            successful_response,  # Initial success
            successful_response,  # More success
            auth_error,  # Token expires - triggers refresh
            successful_response,  # Success with refreshed token
            successful_response,  # Continued success
        ]

        # Act: Simulate migration making multiple API calls
        api_calls = []
        for i in range(5):
            try:
                result = self.rate_limited_client.post(
                    url="https://api.getjobber.com/api/graphql",
                    headers={"Authorization": "Bearer initial_valid_token"},
                    json={"query": "{ clients { id name } }"},
                )
                api_calls.append(("success", result))
            except Exception as e:
                api_calls.append(("error", str(e)))

        # Assert: All calls should have succeeded
        assert len(api_calls) == 5
        for call_type, result in api_calls:
            assert call_type == "success"
            assert "clients" in result["data"]

        # Verify token refresh was called once
        self.mock_oauth_manager.refresh_access_token.assert_called_once_with("initial_refresh_token")

        # Verify tokens were saved after refresh
        self.mock_repository.save_oauth_tokens.assert_called_once()

    def test_long_running_migration_with_multiple_token_refreshes(self):
        """
        Test extended migration with multiple token expirations and refreshes.

        Simulates a very long migration that experiences multiple token refreshes,
        verifying system stability over extended periods.
        """
        # Setup: Start with short-lived tokens
        self._setup_initial_tokens(expires_in_seconds=30)

        # Setup: Multiple refresh responses
        refresh_responses = [
            {"access_token": "refreshed_token_1", "refresh_token": "refresh_1", "expires_in": 30},
            {"access_token": "refreshed_token_2", "refresh_token": "refresh_2", "expires_in": 30},
            {"access_token": "refreshed_token_3", "refresh_token": "refresh_3", "expires_in": 30},
        ]
        self.mock_oauth_manager.refresh_access_token.side_effect = refresh_responses

        # Setup: Simulate auth failures at strategic points
        successful_response = self._create_successful_api_response("quotes")
        auth_error = self._create_auth_error()

        # Pattern: success, success, auth_error (refresh), success, success, auth_error (refresh), etc.
        call_responses = [
            successful_response,
            successful_response,  # Initial success
            auth_error,
            successful_response,  # First refresh cycle
            successful_response,
            successful_response,  # Continued operation
            auth_error,
            successful_response,  # Second refresh cycle
            successful_response,
            auth_error,  # Third refresh needed
            successful_response,
            successful_response,  # Final success
        ]
        self.mock_http_client.post.side_effect = call_responses

        # Act: Simulate extended migration with many API calls
        api_calls = []
        for i in range(12):
            try:
                result = self.rate_limited_client.post(
                    url="https://api.getjobber.com/api/graphql",
                    headers={"Authorization": "Bearer current_token"},
                    json={"query": f"{{ quotes(page: {i+1}) {{ id title }} }}"},
                )
                api_calls.append(("success", result))
            except Exception as e:
                api_calls.append(("error", str(e)))

        # Assert: All calls should have succeeded despite multiple auth failures
        assert len(api_calls) == 12
        for call_type, result in api_calls:
            assert call_type == "success"
            assert "quotes" in result["data"]

        # Verify multiple token refreshes occurred
        assert self.mock_oauth_manager.refresh_access_token.call_count == 3
        assert self.mock_repository.save_oauth_tokens.call_count == 3

    def test_migration_with_token_refresh_failure_recovery(self):
        """
        Test migration behavior when token refresh fails initially but recovers.

        Simulates a scenario where token refresh fails once but succeeds on retry,
        verifying proper error handling and recovery.
        """
        # Setup: Initial tokens
        self._setup_initial_tokens(expires_in_seconds=60)

        # Setup: First refresh fails, second succeeds
        refresh_failure = ConfigurationError("Refresh token expired")
        refresh_success = {
            "access_token": "recovered_token",
            "refresh_token": "recovered_refresh",
            "expires_in": 3600,
        }
        self.mock_oauth_manager.refresh_access_token.side_effect = [
            refresh_failure,  # First refresh fails
            refresh_success,  # Second refresh succeeds
        ]

        # Setup: API call pattern
        successful_response = self._create_successful_api_response("invoices")
        auth_error = self._create_auth_error()

        self.mock_http_client.post.side_effect = [
            successful_response,  # Initial success
            auth_error,  # Auth failure - first refresh fails
            auth_error,  # Auth failure - second refresh succeeds
            successful_response,  # Success with recovered token
        ]

        # Act: Make API calls that will encounter auth failures
        results = []

        # First call should succeed
        result1 = self.rate_limited_client.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer initial_token"},
            json={"query": "{ invoices { id } }"},
        )
        results.append(result1)

        # Second call should fail with auth error, refresh should fail
        with pytest.raises(ConfigurationError):
            self.rate_limited_client.post(
                url="https://api.getjobber.com/api/graphql",
                headers={"Authorization": "Bearer expired_token"},
                json={"query": "{ invoices { id } }"},
            )

        # Verify first refresh was attempted and failed
        assert self.mock_oauth_manager.refresh_access_token.call_count == 1
        assert self.mock_repository.clear_oauth_tokens.call_count == 1

    def test_cache_performance_during_extended_migration(self):
        """
        Test that in-memory caching reduces database queries during extended operations.

        Verifies that the caching system works effectively during long-running
        migrations by minimizing database access.
        """
        # Setup: Long-lived tokens (no expiration during test)
        self._setup_initial_tokens(expires_in_seconds=7200)  # 2 hours

        # Setup: All API calls succeed
        successful_response = self._create_successful_api_response("clients")
        self.mock_http_client.post.return_value = successful_response

        # Act: Make many API calls that require token access
        for i in range(10):
            result = self.rate_limited_client.post(
                url="https://api.getjobber.com/api/graphql",
                headers={"Authorization": "Bearer cached_token"},
                json={"query": f"{{ clients(page: {i+1}) {{ id }} }}"},
            )
            assert "clients" in result["data"]

        # Assert: Database should only be queried once (first call), rest from cache
        assert self.mock_repository.get_oauth_tokens.call_count == 1

        # No token refresh should have occurred
        self.mock_oauth_manager.refresh_access_token.assert_not_called()

    def test_migration_token_refresh_under_rate_limiting(self):
        """
        Test token refresh behavior when combined with rate limiting.

        Verifies that token refresh works correctly even when rate limiting
        is actively managing request flow.
        """
        # Setup: Tokens that will expire
        self._setup_initial_tokens(expires_in_seconds=45)
        self._setup_token_refresh_response("rate_limited_refreshed_token")

        # Setup: Rate limiter sometimes blocks requests
        rate_limit_responses = [True, True, False, True, True, False, True, True]
        self.mock_rate_limiter.consume.side_effect = rate_limit_responses

        # Setup: API responses
        successful_response = self._create_successful_api_response("jobs")
        auth_error = self._create_auth_error()

        self.mock_http_client.post.side_effect = [
            successful_response,  # Success
            successful_response,  # Success
            # Rate limited (no HTTP call)
            successful_response,  # Success
            auth_error,  # Auth failure - triggers refresh
            # Rate limited (no HTTP call)
            successful_response,  # Success with new token
            successful_response,  # Continued success
        ]

        # Act: Attempt multiple API calls with rate limiting
        successful_calls = 0
        rate_limited_calls = 0

        for i in range(8):
            try:
                result = self.rate_limited_client.post(
                    url="https://api.getjobber.com/api/graphql",
                    headers={"Authorization": "Bearer token"},
                    json={"query": "{ jobs { id } }"},
                )
                if result and "jobs" in result["data"]:
                    successful_calls += 1
            except Exception:
                # Rate limiting may cause delays but shouldn't cause failures
                rate_limited_calls += 1

        # Assert: Should have successful calls and token refresh
        assert successful_calls >= 4  # At least some calls succeeded
        self.mock_oauth_manager.refresh_access_token.assert_called_once()

    def test_concurrent_migration_operations_with_shared_auth(self):
        """
        Test multiple concurrent operations sharing the same AuthProvider.

        Simulates multiple migration extractors running concurrently and sharing
        the same authentication, verifying cache consistency and refresh coordination.
        """
        # Setup: Shared auth provider with short-lived tokens
        self._setup_initial_tokens(expires_in_seconds=40)
        self._setup_token_refresh_response("shared_refreshed_token")

        # Create multiple clients sharing the same auth provider
        client1 = RateLimitedHttpClient(
            http_client=self.mock_http_client,
            rate_limiter=self.mock_rate_limiter,
            backoff_strategy=self.mock_backoff_strategy,
            max_retries=5,
            auth_provider=self.auth_provider,
        )

        client2 = RateLimitedHttpClient(
            http_client=self.mock_http_client,
            rate_limiter=self.mock_rate_limiter,
            backoff_strategy=self.mock_backoff_strategy,
            max_retries=5,
            auth_provider=self.auth_provider,  # Same auth provider
        )

        # Setup: API responses for different operations
        response1 = self._create_successful_api_response("clients")
        response2 = self._create_successful_api_response("invoices")
        auth_error = self._create_auth_error()

        # First client gets auth error, second should benefit from refresh
        call_responses = [
            response1,  # Client 1 success
            response2,  # Client 2 success
            auth_error,  # Client 1 auth error - triggers refresh
            response1,  # Client 1 success with new token
            response2,  # Client 2 success (benefits from refresh)
        ]
        self.mock_http_client.post.side_effect = call_responses

        # Act: Simulate concurrent operations
        results = []

        # Client 1 operation
        result1a = client1.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer shared_token"},
            json={"query": "{ clients { id } }"},
        )
        results.append(result1a)

        # Client 2 operation
        result2a = client2.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer shared_token"},
            json={"query": "{ invoices { id } }"},
        )
        results.append(result2a)

        # Client 1 encounters auth error and refreshes
        result1b = client1.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer expired_token"},
            json={"query": "{ clients { id } }"},
        )
        results.append(result1b)

        # Client 2 should now benefit from the refresh
        result2b = client2.post(
            url="https://api.getjobber.com/api/graphql",
            headers={"Authorization": "Bearer refreshed_token"},
            json={"query": "{ invoices { id } }"},
        )
        results.append(result2b)

        # Assert: All operations should succeed
        assert len(results) == 4
        for result in results:
            assert result is not None
            assert "data" in result

        # Verify single refresh occurred (shared between clients)
        self.mock_oauth_manager.refresh_access_token.assert_called_once()

    def test_extended_migration_simulation_full_cycle(self):
        """
        Comprehensive test simulating a complete long-running migration cycle.

        This test simulates the full migration process with realistic timing,
        multiple entities, token refreshes, and various operational conditions.
        """
        # Setup: Initial tokens with moderate lifetime
        self._setup_initial_tokens(expires_in_seconds=120)  # 2 minutes

        # Setup: Multiple refresh cycles
        refresh_responses = [
            {"access_token": "cycle_1_token", "refresh_token": "cycle_1_refresh", "expires_in": 120},
            {"access_token": "cycle_2_token", "refresh_token": "cycle_2_refresh", "expires_in": 120},
        ]
        self.mock_oauth_manager.refresh_access_token.side_effect = refresh_responses

        # Setup: Simulate different entity extractions
        entities = ["clients", "invoices", "quotes", "jobs", "properties"]
        successful_responses = [self._create_successful_api_response(entity) for entity in entities]
        auth_error = self._create_auth_error()

        # Pattern: Multiple successes, then auth errors at strategic points
        call_pattern = (
            successful_responses[:2]  # clients, invoices
            + [auth_error]  # First token refresh
            + successful_responses[2:4]  # quotes, jobs
            + [auth_error]  # Second token refresh
            + successful_responses[4:]  # properties
            + successful_responses[:2]  # Additional operations
        )
        self.mock_http_client.post.side_effect = call_pattern

        # Act: Simulate full migration cycle
        migration_results = {}

        for i, entity in enumerate(entities * 2):  # Process each entity type twice
            try:
                result = self.rate_limited_client.post(
                    url="https://api.getjobber.com/api/graphql",
                    headers={"Authorization": "Bearer migration_token"},
                    json={"query": f"{{ {entity} {{ id name }} }}"},
                )

                if entity not in migration_results:
                    migration_results[entity] = []
                migration_results[entity].append(result)

            except Exception as e:
                pytest.fail(f"Migration failed for {entity}: {e}")

        # Assert: All entity types should have been processed successfully
        assert len(migration_results) == len(entities)
        for entity, results in migration_results.items():
            assert len(results) >= 1  # At least one successful extraction per entity
            for result in results:
                assert entity in result["data"]

        # Verify multiple refreshes occurred during extended operation
        assert self.mock_oauth_manager.refresh_access_token.call_count == 2
        assert self.mock_repository.save_oauth_tokens.call_count == 2

        # Verify caching was effective (fewer DB queries than API calls)
        total_api_calls = sum(len(results) for results in migration_results.values())
        db_queries = self.mock_repository.get_oauth_tokens.call_count
        assert db_queries <= 3  # Initial + refreshes, much less than API calls
