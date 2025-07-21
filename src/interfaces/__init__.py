from typing import Any, Optional, Protocol

from ..exceptions import ConfigurationError, JobberApiError
from .base_extractor import BaseExtractor
from .logger import Logger

"""
Interfaces package for TightBeam application.

This package contains Protocol definitions that formalize interface contracts
used throughout the application. Protocols provide structural typing that
allows for better duck typing support without requiring inheritance.
"""


class IHttpClient(Protocol):
    """
    Protocol defining the HTTP client interface.

    This protocol formalizes the expected interface for HTTP client implementations,
    allowing both HttpClient and RateLimitedHttpClient to be used interchangeably
    without requiring inheritance. This improves type safety and eliminates the
    need for cast operations.

    Any class implementing this protocol must provide a post method with the
    specified signature and behavior.
    """

    def post(
        self,
        url: str,
        headers: dict[str, str],
        json: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        return_headers: bool = False,
    ) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Optional[str]]]:
        """
        Execute HTTP POST request with comprehensive error handling.

        Args:
            url: Target URL for the POST request
            headers: HTTP headers to include in the request
            json: Optional JSON payload for the request body
            data: Optional form data for the request body (mutually exclusive with json)
            return_headers: If True, return tuple (response_data, rate_limit_headers)

        Returns:
            Dictionary containing parsed JSON response, or tuple (response_data, headers)
            if return_headers=True. Rate limit headers include 'x-ratelimit-remaining'
            and 'x-ratelimit-reset' values (None if not present).

        Raises:
            ConfigurationError: If authentication is invalid (401/403 responses)
            JobberApiError: If API communication fails or returns errors
        """
        ...


__all__ = ["BaseExtractor", "IHttpClient", "Logger"]
