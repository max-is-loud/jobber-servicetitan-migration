"""
OAuth2Manager module for OAuth2 authorization flow with Jobber API.

This module provides the OAuth2Manager class which handles the complete
OAuth2 authorization code flow, including authorization URL generation,
code exchange for tokens, and token refresh operations.
"""

import logging
import secrets
from typing import Any, Optional
from urllib.parse import urlencode

from ..clients.http_client import HttpClient
from ..exceptions import ConfigurationError, OAuth2Error
from ..interfaces import IHttpClient

logger = logging.getLogger(__name__)


class OAuth2Manager:
    """
    Manager for OAuth2 authorization flow with Jobber API.

    This class implements the complete OAuth2 authorization code flow according
    to the Jobber API OAuth2 specification. It handles authorization URL generation,
    authorization code exchange for access tokens, and refresh token operations.

    The class follows established dependency injection patterns and uses the shared
    HttpClient for consistent error handling and timeout behavior.
    """

    # Jobber OAuth2 API endpoints
    AUTHORIZATION_URL = "https://api.getjobber.com/api/oauth/authorize"
    TOKEN_URL = "https://api.getjobber.com/api/oauth/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http_client: Optional[IHttpClient] = None,
    ) -> None:
        """
        Initialize OAuth2Manager with application credentials.

        Args:
            client_id: OAuth2 client ID from Jobber Developer Center
            client_secret: OAuth2 client secret from Jobber Developer Center
            redirect_uri: Callback URL for authorization flow
            http_client: Optional IHttpClient instance for HTTP requests

        Raises:
            ConfigurationError: If required credentials are missing or invalid
        """
        if not client_id or not client_id.strip():
            raise ConfigurationError("OAuth2 client_id is required and cannot be empty")
        if not client_secret or not client_secret.strip():
            raise ConfigurationError("OAuth2 client_secret is required and cannot be empty")
        if not redirect_uri or not redirect_uri.strip():
            raise ConfigurationError("OAuth2 redirect_uri is required and cannot be empty")

        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.redirect_uri = redirect_uri.strip()
        self.http_client = http_client or HttpClient()

    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """
        Generate OAuth2 authorization URL for user authorization.

        This method creates the authorization URL that users must visit to grant
        permission to your application. The user will be redirected to your
        redirect_uri with an authorization code upon successful authorization.

        Args:
            state: Optional state parameter for CSRF protection. If None, a secure
                  random state will be generated using secrets.token_urlsafe()

        Returns:
            Tuple containing (authorization_url, state) for CSRF protection

        Example:
            >>> manager = OAuth2Manager(client_id, client_secret, redirect_uri)
            >>> auth_url, state = manager.get_authorization_url("my_custom_state")
            >>> # User visits auth_url and authorizes the application
        """
        if state is None:
            state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
        }

        query_string = urlencode(params)
        authorization_url = f"{self.AUTHORIZATION_URL}?{query_string}"

        return authorization_url, state

    def exchange_code_for_tokens(self, authorization_code: str) -> dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        This method performs the second step of the OAuth2 authorization code flow
        by exchanging the authorization code received from the authorization server
        for access and refresh tokens.

        Args:
            authorization_code: Authorization code received from authorization callback

        Returns:
            Dictionary containing token information with keys:
            - access_token: Bearer token for API requests
            - refresh_token: Token for refreshing access tokens
            - expires_in: Token expiration time in seconds
            - token_type: Token type (typically "Bearer")

        Raises:
            ConfigurationError: If authorization code is invalid or credentials are wrong
            OAuth2Error: If token exchange fails or returns unexpected response

        Example:
            >>> manager = OAuth2Manager(client_id, client_secret, redirect_uri)
            >>> tokens = manager.exchange_code_for_tokens("auth_code_from_callback")
            >>> access_token = tokens["access_token"]
        """  # noqa: E501
        if not authorization_code or not authorization_code.strip():
            raise ConfigurationError("Authorization code is required and cannot be empty")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": authorization_code.strip(),
            "redirect_uri": self.redirect_uri,
        }

        try:
            response_data = self.http_client.post(
                url=self.TOKEN_URL,
                headers=headers,
                data=payload,
                return_headers=False,
            )
        except Exception as e:
            if "Invalid or expired" in str(e) or "Access forbidden" in str(e):
                raise ConfigurationError(
                    f"OAuth2 token exchange failed - invalid credentials or authorization code: {e}"  # noqa: E501
                ) from e
            raise OAuth2Error(f"Failed to exchange authorization code for tokens: {e}") from e

        # Validate token response structure
        self._validate_token_response(response_data)
        return response_data

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """
        Refresh access token using refresh token.

        This method uses a refresh token to obtain a new access token when the
        current access token has expired. This is essential for maintaining
        long-term API access without requiring user re-authorization.

        Args:
            refresh_token: Valid refresh token from previous token exchange

        Returns:
            Dictionary containing refreshed token information with keys:
            - access_token: New bearer token for API requests
            - refresh_token: New refresh token (may be the same or rotated)
            - expires_in: Token expiration time in seconds

        Raises:
            ConfigurationError: If refresh token is invalid or expired
            OAuth2Error: If token refresh fails or returns unexpected response

        Example:
            >>> manager = OAuth2Manager(client_id, client_secret, redirect_uri)
            >>> new_tokens = manager.refresh_access_token("current_refresh_token")
            >>> new_access_token = new_tokens["access_token"]
        """
        if not refresh_token or not refresh_token.strip():
            raise ConfigurationError("Refresh token is required and cannot be empty")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token.strip(),
        }

        try:
            response_data = self.http_client.post(
                url=self.TOKEN_URL,
                headers=headers,
                data=payload,
                return_headers=False,
            )

            # Log the response for diagnosing token rotation issues (debug level)
            logger.debug("Token refresh response keys: %s", list(response_data.keys()))
            # Don't log the full response as it may contain sensitive token data

        except Exception as e:
            if "Invalid or expired" in str(e) or "Access forbidden" in str(e):
                raise ConfigurationError(
                    f"OAuth2 token refresh failed - invalid or expired refresh token: {e}"  # noqa: E501
                ) from e
            raise OAuth2Error(f"Failed to refresh access token: {e}") from e

        # Validate token response structure
        self._validate_token_response(response_data)

        # DEFENSIVE: If Jobber doesn't return a new refresh_token, preserve the old one
        # Per OAuth 2.0 spec, refresh_token is optional in refresh responses.
        # However, Jobber has Refresh Token Rotation ON by default (required for App Marketplace),
        # which means each refresh SHOULD return a new refresh token.
        if "refresh_token" not in response_data:
            logger.warning(
                "Jobber did not return a new refresh_token in refresh response. "
                "This is unexpected - Jobber has Refresh Token Rotation enabled by default. "
                "Preserving existing refresh_token - this may fail on next refresh."
            )
            response_data["refresh_token"] = refresh_token
        elif response_data["refresh_token"] != refresh_token:
            logger.info("Refresh token rotated successfully (old token is now invalid)")
        else:
            logger.info("Refresh token unchanged (rotation may be disabled for this app)")

        return response_data

    def _validate_token_response(self, response_data: dict[str, Any]) -> None:
        """
        Validate OAuth2 token response structure.

        Args:
            response_data: Response dictionary from token endpoint

        Raises:
            OAuth2Error: If response structure is invalid or missing required fields
        """
        if not isinstance(response_data, dict):
            raise OAuth2Error(
                f"Invalid token response format: expected dictionary, got {type(response_data)}"  # noqa: E501
            )

        # Check for OAuth2 error response
        if "error" in response_data:
            error_description = response_data.get("error_description", "No description provided")
            error_code = response_data.get("error", "unknown_error")
            raise OAuth2Error(f"OAuth2 error response: {error_code} - {error_description}")

        # Validate required token fields
        required_fields = ["access_token"]  # Only access_token is strictly required
        missing_fields = [field for field in required_fields if field not in response_data]

        if missing_fields:
            raise OAuth2Error(f"Invalid token response: missing required fields {missing_fields}")

        # Validate token type if present (optional for some providers like Jobber)
        token_type = response_data.get("token_type", "bearer")
        if token_type and token_type.casefold() != "bearer".casefold():
            raise OAuth2Error(f"Unsupported token type: expected 'Bearer', got '{token_type}'")

        # Warn about missing optional but important fields
        if "refresh_token" not in response_data:
            # Don't raise error - per OAuth 2.0 spec this is optional
            # But log warning since Jobber rotation requires it
            logger.warning("Token response missing 'refresh_token' field")

        if "expires_in" not in response_data:
            logger.warning("Token response missing 'expires_in' field, will use default (3600s)")
