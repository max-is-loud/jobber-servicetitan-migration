"""AuthProvider class for handling Jobber API authentication."""

import os
from typing import Optional

from ..exceptions import ConfigurationError


class AuthProvider:
    """Handles reading and validating JOBBER_TOKEN environment variable."""

    def __init__(self) -> None:
        """Initialize AuthProvider."""
        pass

    def get_token(self) -> str:
        """Get and validate the Jobber API token from environment.

        Returns:
            str: The validated Jobber API token

        Raises:
            ConfigurationError: If JOBBER_TOKEN is missing or invalid
        """
        # TODO: Implement token retrieval and validation
        raise NotImplementedError("AuthProvider.get_token() not yet implemented")
