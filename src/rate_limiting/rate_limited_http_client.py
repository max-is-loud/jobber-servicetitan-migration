"""Rate-limited HTTP client decorator for TightBeam application.

This module provides a decorator that wraps HttpClient to add transparent
rate limiting and exponential backoff retry logic for Jobber API calls.
"""

import re
import time
from typing import Any, Optional

from ..exceptions import RateLimitError
from ..interfaces import IHttpClient
from ..utils.debug import debug_print
from .backoff_strategy import ExponentialBackoffStrategy
from .metrics_collector import MetricsCollector
from .token_bucket import TokenBucketRateLimiter


class RateLimitedHttpClient:
    """Rate-limited HTTP client decorator.

    This decorator wraps an HttpClient to add automatic rate limiting, retry logic,
    and backoff strategies for handling API rate limits. It provides transparent
    rate limiting without requiring changes to existing client code.

    The rate limiter uses a token bucket algorithm to control request rates,
    and employs exponential backoff with jitter for retry logic when rate limits
    are encountered.

    This design allows rate limiting to be added without modifying existing
    HttpClient or JobberClient code - just replace the HttpClient instance
    with a RateLimitedHttpClient that wraps it.
    """

    # Default error patterns for rate limit detection
    DEFAULT_RATE_LIMIT_ERROR_PATTERNS = {
        "429",
        "too many requests",
        "rate limit",
        "throttled",
        "throttle",
        "graphql errors in response: throttled",
    }

    def __init__(
        self,
        http_client: IHttpClient,
        rate_limiter: TokenBucketRateLimiter,
        backoff_strategy: ExponentialBackoffStrategy,
        max_retries: int = 5,
        metrics_collector: Optional[MetricsCollector] = None,
        rate_limit_error_patterns: Optional[set[str]] = None,
    ):
        """Initialize the rate-limited HTTP client decorator.

        Args:
            http_client: The IHttpClient instance to wrap
            rate_limiter: TokenBucketRateLimiter for request rate limiting
            backoff_strategy: ExponentialBackoffStrategy for retry delays
            max_retries: Maximum number of retry attempts (default: 5)
            metrics_collector: Optional metrics collector for tracking statistics
            rate_limit_error_patterns: Optional set of error message patterns to detect
                        rate limiting. If not provided, uses default patterns.
        """
        self.http_client = http_client
        self.rate_limiter = rate_limiter
        self.backoff_strategy = backoff_strategy
        self.max_retries = max_retries
        self.metrics_collector = metrics_collector

        # Use provided patterns or fall back to defaults
        self.rate_limit_error_patterns = (
            rate_limit_error_patterns or self.DEFAULT_RATE_LIMIT_ERROR_PATTERNS.copy()
        )

    def post(
        self,
        url: str,
        headers: dict[str, str],
        json: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        return_headers: bool = False,
    ) -> dict[str, Any] | tuple[dict[str, Any], dict[str, str | None]]:
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
            return_headers: Whether to return response headers along with JSON data

        Returns:
            Dictionary containing parsed JSON response, or tuple of (response, headers)
            if return_headers is True

        Raises:
            RateLimitError: If rate limiting fails after max retries
            Other exceptions: Passed through from underlying HttpClient
        """
        attempt = 0

        while attempt <= self.max_retries:
            # Check rate limiter before making request
            debug_print(
                f"[DEBUG] Rate limiter check - Available tokens: {self.rate_limiter.get_available_tokens():.1f}/{self.rate_limiter.get_capacity()}"
            )
            if not self.rate_limiter.consume(1):
                # No tokens available, wait for next token
                wait_time = self.rate_limiter.get_wait_time()
                debug_print(
                    f"[DEBUG] No tokens available, waiting {wait_time:.2f} seconds"
                )
                if wait_time > 0:
                    # Record throttling event
                    if self.metrics_collector:
                        self.metrics_collector.record_throttled(wait_time)
                    time.sleep(wait_time)
                    continue  # Try again after waiting
            else:
                debug_print(
                    f"[DEBUG] Token consumed, remaining: {self.rate_limiter.get_available_tokens():.1f}"
                )

            try:
                # Execute request through wrapped HttpClient
                debug_print(f"[DEBUG] Making POST request to {url}")
                start_time = time.time()
                result = self.http_client.post(
                    url=url,
                    headers=headers,
                    json=json,
                    data=data,
                    return_headers=return_headers,
                )
                response_time = time.time() - start_time
                debug_print(
                    f"[DEBUG] Request successful, response time: {response_time:.2f}s"
                )

                # Record successful request
                if self.metrics_collector:
                    self.metrics_collector.record_request(response_time)

                return result

            except Exception as e:
                debug_print(
                    f"[DEBUG] Request failed with error: {type(e).__name__}: {str(e)}"
                )
                # Check if this is a rate limit error (HTTP 429)
                if self._is_rate_limit_error(e):
                    debug_print(
                        f"[DEBUG] Detected rate limit error, attempt {attempt + 1}/{self.max_retries}"
                    )
                    # Record rate limit error
                    if self.metrics_collector:
                        self.metrics_collector.record_rate_limit_error()

                    # Extract Retry-After header if available
                    retry_after = self._extract_retry_after(e)

                    # If we've exhausted retries, raise RateLimitError
                    if attempt >= self.max_retries:
                        raise RateLimitError(
                            f"Rate limit exceeded after {self.max_retries} retries. "
                            f"Last error: {e}",
                            retry_after=retry_after,
                        ) from e

                    # Record retry attempt
                    if self.metrics_collector:
                        self.metrics_collector.record_retry_attempt()

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
            f"Unexpected: Rate limit retry loop completed without result after {attempt} attempts"  # noqa: E501
        )

    def _is_rate_limit_error(self, exception: Exception) -> bool:
        """Check if an exception represents a rate limit error.

        Args:
            exception: Exception to check

        Returns:
            bool: True if the exception represents a rate limit error (HTTP 429
             or GraphQL throttled)
        """
        # Check if the exception message matches any of the configured error patterns
        error_message = str(exception).lower()
        return any(
            pattern in error_message for pattern in self.rate_limit_error_patterns
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
        # Attempt to parse a 'Retry-After' value from the error string.
        # This is a best-effort approach since the raw response headers are not
        # available.
        error_message = str(exception)
        match = re.search(r"retry-after[\"':=\s]*(\d+)", error_message, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                # If parsing fails, fall back to the default backoff strategy.
                return None

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

    def get_rate_limit_error_patterns(self) -> list[str]:
        """Get current rate limit error patterns.

        Returns:
            list[str]: List of error message patterns used for rate limit detection
        """
        return list(self.rate_limit_error_patterns)

    def set_rate_limit_error_patterns(self, patterns: list[str]) -> None:
        """Set new rate limit error patterns.

        This method allows runtime configuration of error patterns for
        rate limit detection, enabling adaptation to different API behaviors
        or adding new patterns without restarting the application.

        Args:
            patterns: List of error message patterns to use for rate limit detection
        """
        self.rate_limit_error_patterns = set(patterns)

    def add_rate_limit_error_pattern(self, pattern: str) -> None:
        """Add a new rate limit error pattern.

        Args:
            pattern: Error message pattern to add to the detection list
        """
        self.rate_limit_error_patterns.add(pattern)

    def remove_rate_limit_error_pattern(self, pattern: str) -> None:
        """Remove a rate limit error pattern.

        Args:
            pattern: Error message pattern to remove from the detection list
        """
        self.rate_limit_error_patterns.discard(pattern)

    def __repr__(self) -> str:
        """Return string representation of the rate-limited client."""
        return (
            f"RateLimitedHttpClient("
            f"http_client={self.http_client.__class__.__name__}, "
            f"rate_limiter={self.rate_limiter}, "
            f"backoff_strategy={self.backoff_strategy}, "
            f"max_retries={self.max_retries})"
        )
