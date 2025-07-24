"""
Test module for enhanced token management functionality in AuthProvider.

This module tests the new database-based token expiration checking and in-memory
caching functionality that optimizes performance during long-running migrations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from src.auth.auth_provider import AuthProvider
from src.exceptions import ConfigurationError, OAuth2Error


class TestEnhancedTokenManagement:
    """Test enhanced token management with database-based expiration and caching."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_oauth_manager = Mock()
        self.mock_repository = Mock()

        # Create AuthProvider instance
        self.auth_provider = AuthProvider(
            oauth_manager=self.mock_oauth_manager,
            repository=self.mock_repository,
        )

    def test_database_expiration_checking_valid_token(self):
        """Test database-based expiration checking with valid token."""
        # Arrange - token expires in 1 hour
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        expires_at_iso = future_time.isoformat()

        # Act
        is_expired = self.auth_provider._is_token_expired_from_db(expires_at_iso)

        # Assert
        assert not is_expired

    def test_database_expiration_checking_expired_token(self):
        """Test database-based expiration checking with expired token."""
        # Arrange - token expired 1 hour ago
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expires_at_iso = past_time.isoformat()

        # Act
        is_expired = self.auth_provider._is_token_expired_from_db(expires_at_iso)

        # Assert
        assert is_expired

    def test_database_expiration_checking_with_buffer(self):
        """Test database-based expiration checking respects buffer seconds."""
        # Arrange - token expires in 15 seconds (less than 30-second default buffer)
        near_future = datetime.now(timezone.utc) + timedelta(seconds=15)
        expires_at_iso = near_future.isoformat()

        # Act
        is_expired = self.auth_provider._is_token_expired_from_db(expires_at_iso)

        # Assert - should be considered expired due to buffer
        assert is_expired

    def test_database_expiration_checking_custom_buffer(self):
        """Test database-based expiration checking with custom buffer."""
        # Arrange - token expires in 45 seconds
        near_future = datetime.now(timezone.utc) + timedelta(seconds=45)
        expires_at_iso = near_future.isoformat()

        # Act - use 60-second buffer
        is_expired = self.auth_provider._is_token_expired_from_db(expires_at_iso, buffer_seconds=60)

        # Assert - should be considered expired due to 60-second buffer
        assert is_expired

    def test_database_expiration_checking_z_suffix_handling(self):
        """Test database-based expiration checking handles Z suffix correctly."""
        # Arrange - ISO string with Z suffix
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        expires_at_iso = future_time.isoformat().replace("+00:00", "Z")

        # Act
        is_expired = self.auth_provider._is_token_expired_from_db(expires_at_iso)

        # Assert
        assert not is_expired

    def test_database_expiration_checking_invalid_format_raises_error(self):
        """Test database-based expiration checking raises OAuth2Error for invalid format."""
        # Arrange
        invalid_timestamp = "invalid-timestamp-format"

        # Act & Assert
        with pytest.raises(OAuth2Error) as exc_info:
            self.auth_provider._is_token_expired_from_db(invalid_timestamp)

        assert "Invalid expiration timestamp in database" in str(exc_info.value)

    def test_cache_initialization(self):
        """Test that cache is properly initialized as empty."""
        # Assert
        assert self.auth_provider._cached_token is None
        assert self.auth_provider._cached_expires_at is None

    def test_cached_token_validation_empty_cache(self):
        """Test cache validation returns False for empty cache."""
        # Act
        is_valid = self.auth_provider._is_cached_token_valid()

        # Assert
        assert not is_valid

    def test_cached_token_validation_valid_token(self):
        """Test cache validation with valid cached token."""
        # Arrange - cache token that expires in 1 hour
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        self.auth_provider._cached_token = "cached_token"
        self.auth_provider._cached_expires_at = future_time

        # Act
        is_valid = self.auth_provider._is_cached_token_valid()

        # Assert
        assert is_valid

    def test_cached_token_validation_expired_token(self):
        """Test cache validation with expired cached token."""
        # Arrange - cache token that expired 1 hour ago
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        self.auth_provider._cached_token = "expired_cached_token"
        self.auth_provider._cached_expires_at = past_time

        # Act
        is_valid = self.auth_provider._is_cached_token_valid()

        # Assert
        assert not is_valid

    def test_cached_token_validation_with_buffer(self):
        """Test cache validation respects buffer seconds."""
        # Arrange - cache token that expires in 15 seconds (less than 30-second buffer)
        near_future = datetime.now(timezone.utc) + timedelta(seconds=15)
        self.auth_provider._cached_token = "soon_expired_token"
        self.auth_provider._cached_expires_at = near_future

        # Act
        is_valid = self.auth_provider._is_cached_token_valid()

        # Assert - should be invalid due to buffer
        assert not is_valid

    def test_cache_update(self):
        """Test cache update functionality."""
        # Arrange
        token = "test_token"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        # Act
        self.auth_provider._update_cache(token, expires_at)

        # Assert
        assert self.auth_provider._cached_token == token
        assert self.auth_provider._cached_expires_at == expires_at

    def test_cache_clear(self):
        """Test cache clearing functionality."""
        # Arrange - set cache with some data
        self.auth_provider._cached_token = "test_token"
        self.auth_provider._cached_expires_at = datetime.now(timezone.utc)

        # Act
        self.auth_provider._clear_cache()

        # Assert
        assert self.auth_provider._cached_token is None
        assert self.auth_provider._cached_expires_at is None

    def test_get_token_cache_hit(self):
        """Test get_token returns cached token when cache is valid."""
        # Arrange - set valid cache
        cached_token = "cached_valid_token"
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        self.auth_provider._cached_token = cached_token
        self.auth_provider._cached_expires_at = future_time

        # Act
        result = self.auth_provider.get_token()

        # Assert
        assert result == cached_token
        # Repository should not be called for cache hit
        self.mock_repository.get_oauth_tokens.assert_not_called()

    def test_get_token_cache_miss_valid_db_token(self):
        """Test get_token with cache miss but valid database token."""
        # Arrange - empty cache, valid database token
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        expires_at_iso = future_time.isoformat()
        
        self.mock_repository.get_oauth_tokens.return_value = {
            "access_token": "db_token",
            "refresh_token": "refresh_token",
            "expires_at": expires_at_iso,
        }

        # Act
        result = self.auth_provider.get_token()

        # Assert
        assert result == "db_token"
        self.mock_repository.get_oauth_tokens.assert_called_once()
        # Cache should be updated
        assert self.auth_provider._cached_token == "db_token"
        assert self.auth_provider._cached_expires_at == future_time

    def test_get_token_cache_miss_expired_db_token_refresh_success(self):
        """Test get_token with cache miss, expired database token, successful refresh."""
        # Arrange - empty cache, expired database token
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expires_at_iso = past_time.isoformat()
        
        self.mock_repository.get_oauth_tokens.return_value = {
            "access_token": "expired_db_token",
            "refresh_token": "refresh_token",
            "expires_at": expires_at_iso,
        }

        # Mock successful token refresh
        new_tokens = {
            "access_token": "new_refreshed_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,  # 1 hour
        }
        self.mock_oauth_manager.refresh_access_token.return_value = new_tokens

        # Act
        result = self.auth_provider.get_token()

        # Assert
        assert result == "new_refreshed_token"
        self.mock_oauth_manager.refresh_access_token.assert_called_once_with("refresh_token")
        self.mock_repository.save_oauth_tokens.assert_called_once()
        # Cache should be updated with new token
        assert self.auth_provider._cached_token == "new_refreshed_token"
        assert self.auth_provider._cached_expires_at is not None

    def test_get_token_no_tokens_in_database(self):
        """Test get_token raises ConfigurationError when no tokens in database."""
        # Arrange
        self.mock_repository.get_oauth_tokens.return_value = None

        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            self.auth_provider.get_token()

        assert "No OAuth2 tokens found" in str(exc_info.value)
        # Cache should remain empty
        assert self.auth_provider._cached_token is None

    def test_get_token_refresh_failure_clears_cache_and_tokens(self):
        """Test get_token clears cache and tokens when refresh fails."""
        # Arrange - expired database token
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expires_at_iso = past_time.isoformat()
        
        self.mock_repository.get_oauth_tokens.return_value = {
            "access_token": "expired_db_token",
            "refresh_token": "refresh_token",
            "expires_at": expires_at_iso,
        }

        # Set some cache data
        self.auth_provider._cached_token = "old_cached_token"
        self.auth_provider._cached_expires_at = datetime.now(timezone.utc)

        # Mock failed token refresh
        self.mock_oauth_manager.refresh_access_token.side_effect = OAuth2Error("Refresh failed")

        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            self.auth_provider.get_token()

        assert "OAuth2 tokens are invalid and refresh failed" in str(exc_info.value)
        self.mock_repository.clear_oauth_tokens.assert_called_once()
        # Cache should be cleared
        assert self.auth_provider._cached_token is None
        assert self.auth_provider._cached_expires_at is None

    def test_get_token_missing_expires_in_field(self):
        """Test get_token handles missing expires_in field in refresh response."""
        # Arrange - expired database token
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expires_at_iso = past_time.isoformat()
        
        self.mock_repository.get_oauth_tokens.return_value = {
            "access_token": "expired_db_token",
            "refresh_token": "refresh_token",
            "expires_at": expires_at_iso,
        }

        # Mock refresh response without expires_in
        new_tokens = {
            "access_token": "new_token",
            "refresh_token": "new_refresh_token",
            # Missing expires_in field
        }
        self.mock_oauth_manager.refresh_access_token.return_value = new_tokens

        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            self.auth_provider.get_token()

        assert "OAuth2 tokens are invalid and refresh failed" in str(exc_info.value)

    def test_force_refresh_token_clears_cache(self):
        """Test force_refresh_token clears cache before refresh."""
        # Arrange - set cache with some data
        self.auth_provider._cached_token = "old_cached_token"
        self.auth_provider._cached_expires_at = datetime.now(timezone.utc)

        self.mock_repository.get_oauth_tokens.return_value = {
            "access_token": "current_token",
            "refresh_token": "refresh_token",
            "expires_at": datetime.now(timezone.utc).isoformat(),
        }

        # Mock successful token refresh
        new_tokens = {
            "access_token": "force_refreshed_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }
        self.mock_oauth_manager.refresh_access_token.return_value = new_tokens

        # Act
        result = self.auth_provider.force_refresh_token()

        # Assert
        assert result == "force_refreshed_token"
        # Cache should be updated with new token
        assert self.auth_provider._cached_token == "force_refreshed_token"
        assert self.auth_provider._cached_expires_at is not None

    def test_force_refresh_token_no_tokens_raises_error(self):
        """Test force_refresh_token raises ConfigurationError when no tokens exist."""
        # Arrange
        self.mock_repository.get_oauth_tokens.return_value = None

        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            self.auth_provider.force_refresh_token()

        assert "No OAuth2 tokens found" in str(exc_info.value)

    def test_force_refresh_token_refresh_failure(self):
        """Test force_refresh_token handles refresh failure properly."""
        # Arrange
        self.mock_repository.get_oauth_tokens.return_value = {
            "access_token": "current_token",
            "refresh_token": "refresh_token",
            "expires_at": datetime.now(timezone.utc).isoformat(),
        }

        # Set some cache data
        self.auth_provider._cached_token = "cached_token"
        self.auth_provider._cached_expires_at = datetime.now(timezone.utc)

        # Mock failed token refresh
        self.mock_oauth_manager.refresh_access_token.side_effect = OAuth2Error("Refresh failed")

        # Act & Assert
        with pytest.raises(ConfigurationError) as exc_info:
            self.auth_provider.force_refresh_token()

        assert "OAuth2 tokens are invalid and refresh failed" in str(exc_info.value)
        self.mock_repository.clear_oauth_tokens.assert_called_once()
        # Cache should be cleared
        assert self.auth_provider._cached_token is None
        assert self.auth_provider._cached_expires_at is None

    def test_clear_stored_tokens_clears_cache(self):
        """Test clear_stored_tokens clears both database and cache."""
        # Arrange - set cache with some data
        self.auth_provider._cached_token = "cached_token"
        self.auth_provider._cached_expires_at = datetime.now(timezone.utc)

        # Act
        self.auth_provider.clear_stored_tokens()

        # Assert
        self.mock_repository.clear_oauth_tokens.assert_called_once()
        # Cache should be cleared
        assert self.auth_provider._cached_token is None
        assert self.auth_provider._cached_expires_at is None

    def test_integration_cache_and_expiration_checking(self):
        """Test integration between caching and database expiration checking."""
        # Test scenario: cache miss -> database query -> valid token -> cache update -> cache hit

        # Step 1: Cache miss, query database with valid token
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        expires_at_iso = future_time.isoformat()
        
        self.mock_repository.get_oauth_tokens.return_value = {
            "access_token": "valid_db_token",
            "refresh_token": "refresh_token",
            "expires_at": expires_at_iso,
        }

        # First call should hit database
        result1 = self.auth_provider.get_token()
        assert result1 == "valid_db_token"
        assert self.mock_repository.get_oauth_tokens.call_count == 1

        # Step 2: Second call should hit cache
        result2 = self.auth_provider.get_token()
        assert result2 == "valid_db_token"
        # Repository should not be called again
        assert self.mock_repository.get_oauth_tokens.call_count == 1

    def test_timezone_aware_datetime_handling(self):
        """Test that all datetime operations are timezone-aware."""
        # Test database expiration checking with timezone-aware datetime
        utc_time = datetime.now(timezone.utc) + timedelta(hours=1)
        expires_at_iso = utc_time.isoformat()

        is_expired = self.auth_provider._is_token_expired_from_db(expires_at_iso)
        assert not is_expired

        # Test cache validation with timezone-aware datetime
        self.auth_provider._cached_token = "token"
        self.auth_provider._cached_expires_at = utc_time

        is_valid = self.auth_provider._is_cached_token_valid()
        assert is_valid

    def test_edge_case_exactly_at_buffer_time(self):
        """Test edge case where token expires exactly at buffer time."""
        # Arrange - token expires in exactly 30 seconds (default buffer)
        buffer_time = datetime.now(timezone.utc) + timedelta(seconds=30)
        expires_at_iso = buffer_time.isoformat()

        # Act - should be considered expired due to <= comparison
        is_expired = self.auth_provider._is_token_expired_from_db(expires_at_iso)

        # Assert
        assert is_expired 