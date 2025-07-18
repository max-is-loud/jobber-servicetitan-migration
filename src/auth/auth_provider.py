"""AuthProvider class for handling Jobber API OAuth2 authentication."""

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ..exceptions import ConfigurationError, OAuth2Error
from .token_utils import is_token_expired

if TYPE_CHECKING:
    from ..repositories.repository import Repository
    from .oauth2_manager import OAuth2Manager


class AuthProvider:
    """
    Handles OAuth2 authentication for Jobber API with automatic token management.

    This class provides a clean interface for OAuth2 authentication concerns throughout
    the application, following the single responsibility principle by only handling
    token access, validation, and automatic refresh.

    The class requires OAuth2 configuration through environment variables:
    - JOBBER_CLIENT_ID: OAuth2 client ID from Jobber Developer Center
    - JOBBER_CLIENT_SECRET: OAuth2 client secret from Jobber Developer Center
    - JOBBER_REDIRECT_URI: OAuth2 redirect URI for authorization flow

    OAuth2 tokens are automatically refreshed when expired, and the class will
    initiate new authorization flows when needed.
    """

    def __init__(
        self,
        oauth_manager: "OAuth2Manager",
        repository: "Repository",
    ) -> None:
        """
        Initialize AuthProvider with required OAuth2 dependencies.

        Args:
            oauth_manager: OAuth2Manager for token refresh and authorization operations
            repository: Repository for OAuth token storage/retrieval

        Raises:
            ConfigurationError: If required dependencies are not provided
        """
        if oauth_manager is None:
            raise ConfigurationError(
                "OAuth2Manager is required. AuthProvider only supports OAuth2 authentication."  # noqa: E501
            )
        if repository is None:
            raise ConfigurationError("Repository is required for OAuth2 token storage.")

        self.oauth_manager = oauth_manager
        self.repository = repository

    def get_token(self) -> str:
        """
        Get a valid Jobber API OAuth2 access token with automatic refresh.

        This method implements the primary authentication logic:
        1. Retrieves stored OAuth2 tokens from repository
        2. Checks token expiration and auto-refreshes if needed
        3. Returns a valid access token
        4. If no tokens exist, raises ConfigurationError with setup instructions

        Returns:
            str: Valid Jobber API OAuth2 access token

        Raises:
            ConfigurationError: If no OAuth2 tokens are found or refresh fails
            OAuth2Error: If OAuth token operations fail
        """
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
                expires_in = new_tokens.get("expires_in")
                if expires_in is None:
                    raise OAuth2Error("The 'expires_in' field is missing in the token response.")
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
        token format required by Jobber's GraphQL API. Uses OAuth2 tokens with
        automatic refresh capability.

        Returns:
            dict[str, str]: HTTP headers dictionary with Authorization header

        Raises:
            ConfigurationError: If OAuth2 tokens are not available or refresh fails
            OAuth2Error: If OAuth token operations fail

        Example:
            >>> auth = AuthProvider(oauth_manager, repository)
            >>> headers = auth.get_headers()
            >>> headers
            {'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'}
        """
        token = self.get_token()
        return {"Authorization": f"Bearer {token}"}

    def clear_stored_tokens(self) -> None:
        """
        Clear OAuth tokens from storage.

        Removes all stored OAuth2 tokens, effectively logging out the user from
        OAuth2 authentication. The user will need to re-authorize using the
        'tightbeam oauth init' command.
        """
        self.repository.clear_oauth_tokens()

    @staticmethod
    def get_oauth2_config() -> tuple[str, str, str]:
        """
        Get OAuth2 configuration from environment variables.

        Returns:
            Tuple of (client_id, client_secret, redirect_uri)

        Raises:
            ConfigurationError: If required OAuth2 environment variables are missing
        """
        client_id = os.environ.get("JOBBER_CLIENT_ID")
        client_secret = os.environ.get("JOBBER_CLIENT_SECRET")
        redirect_uri = os.environ.get("JOBBER_REDIRECT_URI")

        missing_vars = []
        if not client_id:
            missing_vars.append("JOBBER_CLIENT_ID")
        if not client_secret:
            missing_vars.append("JOBBER_CLIENT_SECRET")
        if not redirect_uri:
            missing_vars.append("JOBBER_REDIRECT_URI")

        if missing_vars:
            raise ConfigurationError(
                f"Missing required OAuth2 environment variables: {', '.join(missing_vars)}. "  # noqa: E501
                "Please set these variables and run 'tightbeam oauth init' to authorize."  # noqa: E501
            )

        # Type narrowing: after the check above, we know these are not None
        assert client_id is not None
        assert client_secret is not None
        assert redirect_uri is not None

        return client_id, client_secret, redirect_uri
