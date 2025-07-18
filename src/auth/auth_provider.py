"""AuthProvider class for handling Jobber API authentication."""

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from ..exceptions import ConfigurationError, OAuth2Error
from .token_utils import is_token_expired

if TYPE_CHECKING:
    from ..repositories.repository import Repository
    from .oauth2_manager import OAuth2Manager


class AuthProvider:
    """
    Handles authentication for Jobber API with OAuth2 and environment token support.

    This class provides a clean interface for authentication concerns throughout
    the application, following the single responsibility principle by only
    handling token access and validation.

    The class supports two authentication modes:
    1. Environment token mode: Uses JOBBER_TOKEN environment variable (backward compatible)
    2. OAuth2 mode: Uses OAuth2 tokens with automatic refresh capability

    For backward compatibility, JOBBER_TOKEN always takes precedence when present.
    OAuth2 features are optional and additive only.
    """  # noqa: E501

    def __init__(
        self,
        oauth_manager: Optional["OAuth2Manager"] = None,
        repository: Optional["Repository"] = None,
    ) -> None:
        """
        Initialize AuthProvider with optional OAuth2 dependencies.

        Constructor maintains backward compatibility by requiring no dependencies.
        OAuth2 features are only available when both oauth_manager and repository
        are provided.

        Args:
            oauth_manager: Optional OAuth2Manager for token refresh operations
            repository: Optional Repository for OAuth token storage/retrieval
        """
        self.oauth_manager = oauth_manager
        self.repository = repository

    def get_token(self) -> str:
        """
        Get and validate the Jobber API token from environment.

        Legacy method maintained for backward compatibility. This method only
        reads from the JOBBER_TOKEN environment variable and does not support
        OAuth2 token management or automatic refresh.

        For applications requiring OAuth2 support, use get_valid_token() instead.

        Returns:
            str: The validated Jobber API token from environment

        Raises:
            ConfigurationError: If JOBBER_TOKEN environment variable is missing,
                               empty, or contains only whitespace
        """
        token = os.environ.get("JOBBER_TOKEN")

        if not token or not token.strip():
            raise ConfigurationError(
                "JOBBER_TOKEN environment variable is required but not set. "
                "Please set the JOBBER_TOKEN environment variable with a valid "
                "Jobber API access token."
            )

        return token.strip()

    def get_valid_token(self) -> str:
        """
        Get a valid Jobber API token with automatic OAuth2 refresh support.

        This method implements the primary authentication logic with OAuth2 support:
        1. First checks JOBBER_TOKEN environment variable (backward compatibility)
        2. If not found and OAuth2 is configured, retrieves stored OAuth tokens
        3. Checks token expiration and auto-refreshes if needed
        4. Returns a valid access token

        Returns:
            str: Valid Jobber API access token

        Raises:
            ConfigurationError: If no authentication method is available or configured
            OAuth2Error: If OAuth token operations fail
        """
        # Prioritize environment token for backward compatibility
        env_token = os.environ.get("JOBBER_TOKEN")
        if env_token and env_token.strip():
            return env_token.strip()

        # Check OAuth2 configuration
        if not self.is_oauth_configured():
            raise ConfigurationError(
                "No authentication method available. Please set JOBBER_TOKEN "
                "environment variable or configure OAuth2 authentication."
            )

        # Type narrowing: we know these are not None due to is_oauth_configured() check
        assert self.repository is not None
        assert self.oauth_manager is not None

        # Get stored OAuth tokens
        token_data = self.repository.get_oauth_tokens()
        if not token_data:
            raise ConfigurationError(
                "No OAuth2 tokens found. Please complete OAuth2 authorization "
                "using the CLI command 'tightbeam oauth init'."
            )

        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]

        # Check if token needs refreshing
        try:
            if is_token_expired(access_token):
                # Refresh the access token
                new_tokens = self.oauth_manager.refresh_access_token(refresh_token)

                # Convert expires_in to ISO 8601 timestamp
                expires_in = new_tokens["expires_in"]
                expires_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                ).isoformat()

                # Store the new tokens
                self.repository.save_oauth_tokens(
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens["refresh_token"],
                    expires_at=expires_at,
                )

                return new_tokens["access_token"]
        except OAuth2Error:
            # Token refresh failed, clear stored tokens
            self.repository.clear_oauth_tokens()
            raise ConfigurationError(
                "OAuth2 tokens are invalid and refresh failed. Please re-authorize "
                "using the CLI command 'tightbeam oauth init'."
            ) from None

        return access_token

    def get_headers(self) -> dict[str, str]:
        """
        Generate HTTP headers for Jobber API requests.

        Creates a dictionary containing the Authorization header with the Bearer
        token format required by Jobber's GraphQL API. Uses get_valid_token()
        to support both environment tokens and OAuth2 with automatic refresh.

        Returns:
            dict[str, str]: HTTP headers dictionary with Authorization header

        Raises:
            ConfigurationError: If no valid authentication method is available
            OAuth2Error: If OAuth token operations fail

        Example:
            >>> auth = AuthProvider()
            >>> headers = auth.get_headers()
            >>> headers
            {'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'}
        """
        token = self.get_valid_token()
        return {"Authorization": f"Bearer {token}"}

    def is_oauth_configured(self) -> bool:
        """
        Check if OAuth2 dependencies are properly configured.

        Returns True if both oauth_manager and repository are available,
        enabling OAuth2 token management features.

        Returns:
            bool: True if OAuth2 is configured, False otherwise
        """
        return self.oauth_manager is not None and self.repository is not None

    def clear_stored_tokens(self) -> None:
        """
        Clear OAuth tokens from storage.

        Removes all stored OAuth2 tokens, effectively logging out the user from
        OAuth2 authentication. This method only affects OAuth2 tokens and does
        not modify environment variables.

        Raises:
            ConfigurationError: If OAuth2 is not configured
        """
        if not self.is_oauth_configured():
            raise ConfigurationError(
                "OAuth2 is not configured. Cannot clear OAuth tokens."
            )

        # Type narrowing: we know repository is not None due to is_oauth_configured() check  # noqa: E501
        assert self.repository is not None
        self.repository.clear_oauth_tokens()
