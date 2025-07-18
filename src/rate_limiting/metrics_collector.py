"""Metrics collector for rate limiting statistics tracking.

This module provides metrics collection functionality to monitor rate limiting
performance, API response times, and throttling events for reporting and
observability in TightBeam v2 Jobber API operations.
"""

import threading
import time
from collections import deque


class MetricsCollector:
    """Thread-safe metrics collector for rate limiting statistics.

    Tracks various metrics related to rate limiting and API performance:
    - Total requests and successful completions
    - Rate limiting throttling events and delays
    - HTTP 429 error rates and retry attempts
    - Response time statistics for performance monitoring
    - Requests per minute calculations for throughput analysis

    Designed to integrate with TightBeam's MigrationSummary reporting pattern
    while maintaining thread safety for concurrent usage scenarios.

    Memory is managed efficiently by limiting response time history to the
    most recent 100 entries to prevent unbounded growth during long operations.
    """

    def __init__(self, max_response_times: int = 100):
        """Initialize the metrics collector.

        Args:
            max_response_times: Maximum number of response times to keep for
                               average calculations (default: 100)
        """
        self._lock = threading.Lock()

        # Request tracking
        self._total_requests = 0
        self._successful_requests = 0
        self._throttled_requests = 0
        self._rate_limit_errors = 0

        # Timing tracking
        self._start_time = time.time()
        self._response_times = deque(
            maxlen=max_response_times
        )  # Efficient fixed-size queue

        # Throttling and delay tracking
        self._total_throttle_time = 0.0  # Total time spent waiting due to rate limiting
        self._max_throttle_time = 0.0  # Maximum single throttle delay

        # Advanced metrics
        self._retry_attempts = 0  # Total number of retry attempts
        self._successful_retries = 0  # Retries that eventually succeeded

    def record_request(self, response_time: float) -> None:
        """Record a successful API request completion.

        Args:
            response_time: Time taken for the request in seconds
        """
        with self._lock:
            self._total_requests += 1
            self._successful_requests += 1
            self._response_times.append(response_time)

    def record_throttled(self, throttle_time: float = 0.0) -> None:
        """Record when rate limiter delays a request.

        Args:
            throttle_time: Time spent waiting due to rate limiting (seconds)
        """
        with self._lock:
            self._throttled_requests += 1
            self._total_throttle_time += throttle_time
            self._max_throttle_time = max(self._max_throttle_time, throttle_time)

    def record_rate_limit_error(self) -> None:
        """Record when a rate limit error (HTTP 429) occurs."""
        with self._lock:
            self._rate_limit_errors += 1
            self._total_requests += 1  # Count failed requests too

    def record_retry_attempt(self, successful: bool = False) -> None:
        """Record retry attempt statistics.

        Args:
            successful: Whether the retry eventually succeeded
        """
        with self._lock:
            self._retry_attempts += 1
            if successful:
                self._successful_retries += 1

    def get_requests_per_minute(self) -> float:
        """Calculate current requests per minute rate.

        Returns:
            float: Requests per minute based on elapsed time
        """
        with self._lock:
            elapsed_time = time.time() - self._start_time
            if elapsed_time <= 0:
                return 0.0

            # Convert to requests per minute
            return (self._total_requests / elapsed_time) * 60.0

    def get_successful_requests_per_minute(self) -> float:
        """Calculate successful requests per minute rate.

        Returns:
            float: Successful requests per minute (excluding 429 errors)
        """
        with self._lock:
            elapsed_time = time.time() - self._start_time
            if elapsed_time <= 0:
                return 0.0

            return (self._successful_requests / elapsed_time) * 60.0

    def get_average_response_time(self) -> float:
        """Calculate average response time for recent requests.

        Returns:
            float: Average response time in seconds, or 0.0 if no data
        """
        with self._lock:
            if not self._response_times:
                return 0.0
            return sum(self._response_times) / len(self._response_times)

    def get_error_rate_percentage(self) -> float:
        """Calculate rate limit error percentage.

        Returns:
            float: Percentage of requests that resulted in rate limit errors
        """
        with self._lock:
            if self._total_requests == 0:
                return 0.0
            return (self._rate_limit_errors / self._total_requests) * 100.0

    def get_throttle_rate_percentage(self) -> float:
        """Calculate throttling rate percentage.

        Returns:
            float: Percentage of requests that were throttled by rate limiter
        """
        with self._lock:
            total_attempts = self._total_requests + self._throttled_requests
            if total_attempts == 0:
                return 0.0
            return (self._throttled_requests / total_attempts) * 100.0

    def get_average_throttle_time(self) -> float:
        """Calculate average time spent waiting due to throttling.

        Returns:
            float: Average throttle time in seconds per throttled request
        """
        with self._lock:
            if self._throttled_requests == 0:
                return 0.0
            return self._total_throttle_time / self._throttled_requests

    def get_retry_success_rate(self) -> float:
        """Calculate retry success rate percentage.

        Returns:
            float: Percentage of retries that eventually succeeded
        """
        with self._lock:
            if self._retry_attempts == 0:
                return 0.0
            return (self._successful_retries / self._retry_attempts) * 100.0

    def get_uptime_seconds(self) -> float:
        """Get total uptime since metrics collection started.

        Returns:
            float: Elapsed time in seconds since initialization
        """
        with self._lock:
            return time.time() - self._start_time

    def get_summary(self) -> dict[str, float | int]:
        """Get comprehensive metrics summary as dictionary.

        Returns comprehensive metrics suitable for integration with
        MigrationSummary reporting and logging systems.

        Returns:
            dict: Complete metrics summary with all tracked statistics
        """
        with self._lock:
            uptime = self.get_uptime_seconds()

            return {
                # Request statistics
                "total_requests": self._total_requests,
                "successful_requests": self._successful_requests,
                "rate_limit_errors": self._rate_limit_errors,
                "throttled_requests": self._throttled_requests,
                # Rate calculations
                "requests_per_minute": self.get_requests_per_minute(),
                "successful_requests_per_minute": self.get_successful_requests_per_minute(),  # noqa: E501
                # Response time statistics
                "average_response_time_seconds": self.get_average_response_time(),
                "response_time_samples": len(self._response_times),
                # Error and throttling rates
                "error_rate_percentage": self.get_error_rate_percentage(),
                "throttle_rate_percentage": self.get_throttle_rate_percentage(),
                # Throttling time statistics
                "total_throttle_time_seconds": self._total_throttle_time,
                "max_throttle_time_seconds": self._max_throttle_time,
                "average_throttle_time_seconds": self.get_average_throttle_time(),
                # Retry statistics
                "retry_attempts": self._retry_attempts,
                "successful_retries": self._successful_retries,
                "retry_success_rate_percentage": self.get_retry_success_rate(),
                # Timing
                "uptime_seconds": uptime,
                "start_time": self._start_time,
            }

    def get_human_readable_summary(self) -> dict[str, str]:
        """Get human-readable metrics summary.

        Returns:
            dict: Formatted metrics suitable for CLI display
        """
        summary = self.get_summary()
        uptime = summary["uptime_seconds"]

        # Format uptime similar to MigrationSummary.format_duration()
        if uptime < 60:
            uptime_str = f"{uptime:.1f} seconds"
        else:
            minutes = int(uptime // 60)
            seconds = uptime % 60
            uptime_str = f"{minutes}m {seconds:.1f}s"

        return {
            "requests_per_minute": f"{summary['requests_per_minute']:.1f}",
            "successful_requests_per_minute": f"{summary['successful_requests_per_minute']:.1f}",  # noqa: E501
            "average_response_time": f"{summary['average_response_time_seconds']:.3f}s",
            "error_rate": f"{summary['error_rate_percentage']:.1f}%",
            "throttle_rate": f"{summary['throttle_rate_percentage']:.1f}%",
            "retry_success_rate": f"{summary['retry_success_rate_percentage']:.1f}%",
            "uptime": uptime_str,
            "total_requests": str(summary["total_requests"]),
            "rate_limit_errors": str(summary["rate_limit_errors"]),
            "throttled_requests": str(summary["throttled_requests"]),
        }

    def reset(self) -> None:
        """Reset all metrics to initial state.

        Useful for testing or restarting metrics collection during long operations.
        """
        with self._lock:
            self._total_requests = 0
            self._successful_requests = 0
            self._throttled_requests = 0
            self._rate_limit_errors = 0
            self._start_time = time.time()
            self._response_times.clear()
            self._total_throttle_time = 0.0
            self._max_throttle_time = 0.0
            self._retry_attempts = 0
            self._successful_retries = 0

    def __repr__(self) -> str:
        """Return string representation of the metrics collector."""
        summary = self.get_summary()
        return (
            f"MetricsCollector("
            f"requests={summary['total_requests']}, "
            f"rpm={summary['requests_per_minute']:.1f}, "
            f"errors={summary['rate_limit_errors']}, "
            f"throttled={summary['throttled_requests']}, "
            f"uptime={summary['uptime_seconds']:.1f}s)"
        )
