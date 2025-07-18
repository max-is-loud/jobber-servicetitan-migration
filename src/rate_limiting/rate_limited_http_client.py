"""Rate-limited HTTP client decorator for TightBeam application.

This module provides a decorator that wraps HttpClient to add transparent
rate limiting and exponential backoff retry logic for Jobber API calls.
"""

import time
from typing import Any, Optional

from ..clients.http_client import HttpClient
from ..exceptions import RateLimitError
from .token_bucket import TokenBucketRateLimiter
from .backoff_strategy import ExponentialBackoffStrategy


class RateLimitedHttpClient:
    """Rate-limited HTTP client decorator.

    This decorator wraps an HttpClient to add transparent rate limiting and
    exponential backoff retry logic. It maintains the exact same interface
    as HttpClient while intercepting post() calls to apply rate limiting
    and handle HTTP 429 (Too Many Requests) responses.

    The decorator uses the token bucket algorithm to prevent exceeding
    Jobber API rate limits and implements exponential backoff with jitter
    to handle temporary failures and rate limit errors gracefully.

    This design allows rate limiting to be added without modifying existing
    HttpClient or JobberClient code - just replace the HttpClient instance
    with a RateLimitedHttpClient that wraps it.
    """

    def __init__(
        self,
        http_client: HttpClient,
        rate_limiter: TokenBucketRateLimiter,
        backoff_strategy: ExponentialBackoffStrategy,
        max_retries: int = 5,
    ):
        """Initialize the rate-limited HTTP client decorator.

        Args:
            http_client: The HttpClient instance to wrap
            rate_limiter: TokenBucketRateLimiter for request rate limiting
            backoff_strategy: ExponentialBackoffStrategy for retry delays
            max_retries: Maximum number of retry attempts (default: 5)
        """
        self.http_client = http_client
        self.rate_limiter = rate_limiter
        self.backoff_strategy = backoff_strategy
        self.max_retries = max_retries

    def post(
        self,
        url: str,
        headers: dict[str, str],
        json: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute HTTP POST request with rate limiting and retry logic.

        This method maintains the exact same signature as HttpClient.post()
        while adding transparent rate limiting and exponential backoff retry
        logic for handling rate limit errors.

        Rate limiting flow:
        1. Check token bucket for available tokens
        2. If no tokens, wait using rate_limiter.get_wait_time()
        3. Execute HTTP request through wrapped HttpClient
        4. On HTTP 429 response, extract Retry-After header if present
        5. Apply exponential backoff with jitter and retry
        6. Raise RateLimitError after max_retries exceeded

        Args:
            url: Target URL for the POST request
            headers: HTTP headers to include in the request
            json: Optional JSON payload for the request body
            data: Optional form data for the request body

        Returns:
            Dictionary containing parsed JSON response

        Raises:
            RateLimitError: If rate limiting fails after max retries
            Other exceptions: Passed through from underlying HttpClient
        """
        attempt = 0

        while attempt <= self.max_retries:
            # Check rate limiter before making request
            if not self.rate_limiter.consume(1):
                # No tokens available, wait for next token
                wait_time = self.rate_limiter.get_wait_time()
                if wait_time > 0:
                    time.sleep(wait_time)
                    continue  # Try again after waiting

            try:
                # Execute request through wrapped HttpClient
                return self.http_client.post(
                    url=url, headers=headers, json=json, data=data
                )

            except Exception as e:
                # Check if this is a rate limit error (HTTP 429)
                if self._is_rate_limit_error(e):
                    # Extract Retry-After header if available
                    retry_after = self._extract_retry_after(e)

                    # If we've exhausted retries, raise RateLimitError
                    if attempt >= self.max_retries:
                        raise RateLimitError(
                            f"Rate limit exceeded after {self.max_retries} retries. "
                            f"Last error: {e}",
                            retry_after=retry_after,
                        ) from e

                    # Calculate backoff delay with exponential backoff
                    delay = self.backoff_strategy.calculate_delay(attempt, retry_after)
                    time.sleep(delay)
                    attempt += 1
                    continue

                else:
                    # Non-rate-limit error, re-raise immediately
                    raise

        # This should never be reached due to the loop logic above
        raise RateLimitError(
            f"Unexpected: Rate limit retry loop completed without result after {attempt} attempts"
        )

    def _is_rate_limit_error(self, exception: Exception) -> bool:
        """Check if an exception represents a rate limit error.

        Args:
            exception: Exception to check

        Returns:
            bool: True if the exception represents an HTTP 429 rate limit error
        """
        # Check for JobberApiError with HTTP 429 status code
        error_message = str(exception).lower()
        return (
            "429" in error_message
            or "too many requests" in error_message
            or "rate limit" in error_message
        )

    def _extract_retry_after(self, exception: Exception) -> Optional[float]:
        """Extract Retry-After header value from a rate limit error.

        This method attempts to parse Retry-After values from the exception
        message or any attached response data. Jobber API may include this
        header in HTTP 429 responses to indicate when to retry.

        Args:
            exception: Rate limit exception to parse

        Returns:
            Optional[float]: Retry-After delay in seconds, or None if not found
        """
        # This is a simplified implementation - in production you might want
        # to access the actual HTTP response object if available
        error_message = str(exception)

        # Look for common Retry-After patterns in error messages
        # This could be enhanced to parse actual HTTP response headers
        # if the HttpClient was modified to preserve them

        # For now, return None - the backoff strategy will handle delays
        return None

    def get_rate_limiter(self) -> TokenBucketRateLimiter:
        """Get the underlying rate limiter for monitoring.

        Returns:
            TokenBucketRateLimiter: The rate limiter instance
        """
        return self.rate_limiter

    def get_backoff_strategy(self) -> ExponentialBackoffStrategy:
        """Get the underlying backoff strategy for monitoring.

        Returns:
            ExponentialBackoffStrategy: The backoff strategy instance
        """
        return self.backoff_strategy

    def get_available_tokens(self) -> float:
        """Get current number of available rate limit tokens.

        Returns:
            float: Number of tokens currently available
        """
        return self.rate_limiter.get_available_tokens()

    def __repr__(self) -> str:
        """Return string representation of the rate-limited client."""
        return (
            f"RateLimitedHttpClient("
            f"http_client={self.http_client.__class__.__name__}, "
            f"rate_limiter={self.rate_limiter}, "
            f"backoff_strategy={self.backoff_strategy}, "
            f"max_retries={self.max_retries})"
        )
