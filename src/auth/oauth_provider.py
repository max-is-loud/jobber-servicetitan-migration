"""OAuthProvider class for handling Jobber OAuth authentication configuration."""

import os
from typing import Any, Optional

from ..exceptions import ConfigurationError


class OAuthProvider:
    """
    Handles OAuth configuration validation for Jobber API authentication.

    This class validates OAuth-related configuration including required environment
    variables and dependency injection parameters. It ensures that all required
    OAuth credentials and dependencies are properly configured before any OAuth
    operations are performed.

    The class follows the same pattern as AuthProvider but for OAuth flow instead
    of token-based authentication.
    """

    def __init__(
        self, oauth_manager: Optional[Any] = None, repository: Optional[Any] = None
    ) -> None:
        """
        Initialize OAuthProvider with required dependencies and validation.

        Validates that oauth_manager and repository dependencies are provided
        and that all required OAuth environment variables are set.

        Args:
            oauth_manager: OAuth manager instance for handling OAuth flow
            repository: Repository instance for database operations

        Raises:
            ConfigurationError: If oauth_manager or repository are None, or if
                               required OAuth environment variables are missing
        """
        # Validate required dependencies
        if oauth_manager is None:
            raise ConfigurationError(
                "oauth_manager is required but not provided. "
                "Please provide a valid oauth_manager instance."
            )

        if repository is None:
            raise ConfigurationError(
                "repository is required but not provided. "
                "Please provide a valid repository instance."
            )

        # Validate required environment variables
        self._validate_oauth_environment()

        # Store dependencies
        self._oauth_manager = oauth_manager
        self._repository = repository

    def _validate_oauth_environment(self) -> None:
        """
        Validate that all required OAuth environment variables are set.

        Raises:
            ConfigurationError: If any required OAuth environment variable is
                               missing, empty, or contains only whitespace
        """
        required_vars = [
            "JOBBER_CLIENT_ID",
            "JOBBER_CLIENT_SECRET",
            "JOBBER_REDIRECT_URI",
        ]

        missing_vars = []
        empty_vars = []

        for var_name in required_vars:
            value = os.environ.get(var_name)
            if value is None:
                missing_vars.append(var_name)
            elif not value.strip():
                empty_vars.append(var_name)

        if missing_vars or empty_vars:
            error_parts = []

            if missing_vars:
                error_parts.append(
                    f"Missing environment variables: {', '.join(missing_vars)}"
                )

            if empty_vars:
                error_parts.append(
                    f"Empty environment variables: {', '.join(empty_vars)}"
                )

            error_message = ". ".join(error_parts)
            error_message += (
                ". Please set all required OAuth environment variables with "
                "valid values: JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, and "
                "JOBBER_REDIRECT_URI."
            )

            raise ConfigurationError(error_message)

    @property
    def oauth_manager(self) -> Any:
        """Get the OAuth manager instance."""
        return self._oauth_manager

    @property
    def repository(self) -> Any:
        """Get the repository instance."""
        return self._repository

    def get_client_id(self) -> str:
        """
        Get the OAuth client ID from environment.

        Returns:
            str: The OAuth client ID

        Raises:
            ConfigurationError: If JOBBER_CLIENT_ID is not set or empty
        """
        client_id = os.environ.get("JOBBER_CLIENT_ID")
        if not client_id or not client_id.strip():
            raise ConfigurationError(
                "JOBBER_CLIENT_ID environment variable is required but not set."
            )
        return client_id.strip()

    def get_client_secret(self) -> str:
        """
        Get the OAuth client secret from environment.

        Returns:
            str: The OAuth client secret

        Raises:
            ConfigurationError: If JOBBER_CLIENT_SECRET is not set or empty
        """
        client_secret = os.environ.get("JOBBER_CLIENT_SECRET")
        if not client_secret or not client_secret.strip():
            raise ConfigurationError(
                "JOBBER_CLIENT_SECRET environment variable is required but not set."
            )
        return client_secret.strip()

    def get_redirect_uri(self) -> str:
        """
        Get the OAuth redirect URI from environment.

        Returns:
            str: The OAuth redirect URI

        Raises:
            ConfigurationError: If JOBBER_REDIRECT_URI is not set or empty
        """
        redirect_uri = os.environ.get("JOBBER_REDIRECT_URI")
        if not redirect_uri or not redirect_uri.strip():
            raise ConfigurationError(
                "JOBBER_REDIRECT_URI environment variable is required but not set."
            )
        return redirect_uri.strip()
