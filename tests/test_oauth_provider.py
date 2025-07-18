"""Tests for OAuthProvider configuration validation."""

import os
from unittest.mock import Mock

import pytest

from src.auth.oauth_provider import OAuthProvider
from src.exceptions import ConfigurationError


class TestOAuthProvider:
    """Test cases for OAuthProvider class."""

    def setup_method(self):
        """Clean up environment variables before each test."""
        oauth_vars = ["JOBBER_CLIENT_ID", "JOBBER_CLIENT_SECRET", "JOBBER_REDIRECT_URI"]
        for var in oauth_vars:
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Clean up environment variables after each test."""
        oauth_vars = ["JOBBER_CLIENT_ID", "JOBBER_CLIENT_SECRET", "JOBBER_REDIRECT_URI"]
        for var in oauth_vars:
            if var in os.environ:
                del os.environ[var]

    def test_init_with_none_oauth_manager_raises_error(self):
        """Test that providing None oauth_manager raises ConfigurationError."""
        repository = Mock()

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=None, repository=repository)

        assert "oauth_manager is required but not provided" in str(exc_info.value)

    def test_init_with_none_repository_raises_error(self):
        """Test that providing None repository raises ConfigurationError."""
        oauth_manager = Mock()

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=oauth_manager, repository=None)

        assert "repository is required but not provided" in str(exc_info.value)

    def test_init_with_missing_client_id_raises_error(self):
        """Test that missing JOBBER_CLIENT_ID raises ConfigurationError."""
        oauth_manager = Mock()
        repository = Mock()

        # Set other required vars but not CLIENT_ID
        os.environ["JOBBER_CLIENT_SECRET"] = "test_secret"
        os.environ["JOBBER_REDIRECT_URI"] = "https://example.com/callback"

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        assert "JOBBER_CLIENT_ID" in str(exc_info.value)
        assert "Missing environment variables" in str(exc_info.value)

    def test_init_with_missing_client_secret_raises_error(self):
        """Test that missing JOBBER_CLIENT_SECRET raises ConfigurationError."""
        oauth_manager = Mock()
        repository = Mock()

        # Set other required vars but not CLIENT_SECRET
        os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
        os.environ["JOBBER_REDIRECT_URI"] = "https://example.com/callback"

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        assert "JOBBER_CLIENT_SECRET" in str(exc_info.value)
        assert "Missing environment variables" in str(exc_info.value)

    def test_init_with_missing_redirect_uri_raises_error(self):
        """Test that missing JOBBER_REDIRECT_URI raises ConfigurationError."""
        oauth_manager = Mock()
        repository = Mock()

        # Set other required vars but not REDIRECT_URI
        os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
        os.environ["JOBBER_CLIENT_SECRET"] = "test_secret"

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        assert "JOBBER_REDIRECT_URI" in str(exc_info.value)
        assert "Missing environment variables" in str(exc_info.value)

    def test_init_with_empty_client_id_raises_error(self):
        """Test that empty JOBBER_CLIENT_ID raises ConfigurationError."""
        oauth_manager = Mock()
        repository = Mock()

        # Set empty CLIENT_ID
        os.environ["JOBBER_CLIENT_ID"] = ""
        os.environ["JOBBER_CLIENT_SECRET"] = "test_secret"
        os.environ["JOBBER_REDIRECT_URI"] = "https://example.com/callback"

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        assert "JOBBER_CLIENT_ID" in str(exc_info.value)
        assert "Empty environment variables" in str(exc_info.value)

    def test_init_with_whitespace_only_vars_raises_error(self):
        """Test that whitespace-only environment variables raise ConfigurationError."""
        oauth_manager = Mock()
        repository = Mock()

        # Set variables with only whitespace
        os.environ["JOBBER_CLIENT_ID"] = "   "
        os.environ["JOBBER_CLIENT_SECRET"] = "\t\n"
        os.environ["JOBBER_REDIRECT_URI"] = " "

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        error_message = str(exc_info.value)
        assert "Empty environment variables" in error_message
        assert "JOBBER_CLIENT_ID" in error_message
        assert "JOBBER_CLIENT_SECRET" in error_message
        assert "JOBBER_REDIRECT_URI" in error_message

    def test_init_with_multiple_missing_vars_lists_all(self):
        """Test that multiple missing variables are all listed in the error."""
        oauth_manager = Mock()
        repository = Mock()

        # Don't set any environment variables

        with pytest.raises(ConfigurationError) as exc_info:
            OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        error_message = str(exc_info.value)
        assert "JOBBER_CLIENT_ID" in error_message
        assert "JOBBER_CLIENT_SECRET" in error_message
        assert "JOBBER_REDIRECT_URI" in error_message
        assert "Missing environment variables" in error_message

    def test_init_success_with_all_requirements(self):
        """Test successful initialization with all requirements met."""
        oauth_manager = Mock()
        repository = Mock()

        # Set all required environment variables
        os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
        os.environ["JOBBER_CLIENT_SECRET"] = "test_secret"
        os.environ["JOBBER_REDIRECT_URI"] = "https://example.com/callback"

        # Should not raise any exception
        provider = OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        # Verify properties are accessible
        assert provider.oauth_manager is oauth_manager
        assert provider.repository is repository

    def test_get_client_id_returns_correct_value(self):
        """Test that get_client_id returns the correct environment variable value."""
        oauth_manager = Mock()
        repository = Mock()

        # Set all required environment variables
        test_client_id = "test_client_id_123"
        os.environ["JOBBER_CLIENT_ID"] = test_client_id
        os.environ["JOBBER_CLIENT_SECRET"] = "test_secret"
        os.environ["JOBBER_REDIRECT_URI"] = "https://example.com/callback"

        provider = OAuthProvider(oauth_manager=oauth_manager, repository=repository)
        assert provider.get_client_id() == test_client_id

    def test_get_client_secret_returns_correct_value(self):
        """Test that get_client_secret returns the correct environment variable value."""
        oauth_manager = Mock()
        repository = Mock()

        # Set all required environment variables
        test_secret = "test_secret_456"
        os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
        os.environ["JOBBER_CLIENT_SECRET"] = test_secret
        os.environ["JOBBER_REDIRECT_URI"] = "https://example.com/callback"

        provider = OAuthProvider(oauth_manager=oauth_manager, repository=repository)
        assert provider.get_client_secret() == test_secret

    def test_get_redirect_uri_returns_correct_value(self):
        """Test that get_redirect_uri returns the correct environment variable value."""
        oauth_manager = Mock()
        repository = Mock()

        # Set all required environment variables
        test_uri = "https://example.com/oauth/callback"
        os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
        os.environ["JOBBER_CLIENT_SECRET"] = "test_secret"
        os.environ["JOBBER_REDIRECT_URI"] = test_uri

        provider = OAuthProvider(oauth_manager=oauth_manager, repository=repository)
        assert provider.get_redirect_uri() == test_uri

    def test_getter_methods_strip_whitespace(self):
        """Test that getter methods strip leading and trailing whitespace."""
        oauth_manager = Mock()
        repository = Mock()

        # Set environment variables with extra whitespace
        os.environ["JOBBER_CLIENT_ID"] = "  test_client_id  "
        os.environ["JOBBER_CLIENT_SECRET"] = "\ttest_secret\n"
        os.environ["JOBBER_REDIRECT_URI"] = " https://example.com/callback "

        provider = OAuthProvider(oauth_manager=oauth_manager, repository=repository)

        assert provider.get_client_id() == "test_client_id"
        assert provider.get_client_secret() == "test_secret"
        assert provider.get_redirect_uri() == "https://example.com/callback"
