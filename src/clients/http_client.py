"""
HttpClient module for shared HTTP request patterns.

This module provides the HttpClient class which handles common HTTP communication
patterns used by both JobberClient and OAuth2Manager, including error handling,
timeout configuration, and response processing.
"""

from typing import Any, Optional

import requests

from ..exceptions import ConfigurationError, JobberApiError


class HttpClient:
    """
    Shared HTTP client for consistent request handling patterns.

    This class provides common HTTP request functionality used by multiple
    components in the system, including JobberClient and OAuth2Manager.
    It encapsulates timeout configuration, error handling, and response
    processing to ensure consistent behavior across all HTTP communications.
    """

    # Default request timeout configuration (connect, read) in seconds
    DEFAULT_TIMEOUT = (10, 30)

    def __init__(self, timeout: tuple[int, int] | tuple[float, float] | None = None) -> None:
        """
        Initialize HttpClient with optional custom timeout.

        Args:
            timeout: Optional tuple of (connect_timeout, read_timeout) in seconds.
                    If None, uses DEFAULT_TIMEOUT (10, 30).
        """
        self.timeout = timeout or self.DEFAULT_TIMEOUT

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
        if json is not None and data is not None:
            raise ValueError("Cannot specify both 'json' and 'data' parameters")

        try:
            # Make HTTP POST request with timeout
            response = requests.post(url, headers=headers, json=json, data=data, timeout=self.timeout)

            # Handle HTTP status code errors
            if response.status_code == 401:
                raise ConfigurationError(
                    "Invalid or expired authentication token. Please check your authentication credentials."  # noqa: E501
                )
            elif response.status_code == 403:
                raise ConfigurationError(
                    "Access forbidden. Your authentication token may not have sufficient permissions."  # noqa: E501
                )
            elif response.status_code >= 400:
                raise JobberApiError(f"API returned HTTP {response.status_code}: {response.text}")

            # Check for successful status (will raise HTTPError for 4xx/5xx if we missed any)  # noqa: E501
            response.raise_for_status()

        except requests.exceptions.Timeout as e:
            raise JobberApiError(
                f"Request timed out after {self.timeout} seconds. "
                "Please check your network connection or try again later."
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise JobberApiError(
                f"Failed to connect to {url}. Please check your network connection and API endpoint."
            ) from e
        except requests.exceptions.RequestException as e:
            raise JobberApiError(f"Network error occurred while contacting API: {e}") from e

        # Parse JSON response
        try:
            response_data = response.json()
        except requests.exceptions.JSONDecodeError as e:
            raise JobberApiError(f"Invalid JSON response from API. Response: {response.text[:200]}...") from e

        # Return response data with optional headers
        if return_headers:
            # Extract rate limiting headers for performance monitoring
            rate_limit_headers = {
                "x-ratelimit-remaining": response.headers.get("x-ratelimit-remaining"),
                "x-ratelimit-reset": response.headers.get("x-ratelimit-reset"),
            }
            return response_data, rate_limit_headers

        return response_data
