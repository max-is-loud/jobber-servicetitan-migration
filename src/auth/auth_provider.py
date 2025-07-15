"""AuthProvider class for handling Jobber API authentication."""

import os

from ..exceptions import ConfigurationError


class AuthProvider:
    """
    Handles reading and validating JOBBER_TOKEN environment variable.

    This class provides a clean interface for authentication concerns throughout
    the application, following the single responsibility principle by only
    handling token access and validation.

    The class reads the JOBBER_TOKEN environment variable and provides methods
    to access the token and generate proper Authorization headers for Jobber API
    requests.
    """

    def __init__(self) -> None:
        """
        Initialize AuthProvider.

        Constructor requires no dependencies and performs no setup operations.
        Token validation is deferred to method calls for lazy evaluation.
        """
        pass

    def get_token(self) -> str:
        """
        Get and validate the Jobber API token from environment.

        Reads the JOBBER_TOKEN environment variable and validates it exists.
        The token should be a valid Jobber API access token obtained through
        the OAuth 2.0 authorization flow.

        Returns:
            str: The validated Jobber API token

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

    def get_headers(self) -> dict[str, str]:
        """
        Generate HTTP headers for Jobber API requests.

        Creates a dictionary containing the Authorization header with the Bearer
        token format required by Jobber's GraphQL API. The format follows the
        pattern: Authorization: Bearer <access_token>

        Returns:
            dict[str, str]: HTTP headers dictionary with Authorization header

        Raises:
            ConfigurationError: If JOBBER_TOKEN environment variable is missing
                               (propagated from get_token method)

        Example:
            >>> auth = AuthProvider()
            >>> headers = auth.get_headers()
            >>> headers
            {'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'}
        """
        token = self.get_token()
        return {"Authorization": f"Bearer {token}"}
