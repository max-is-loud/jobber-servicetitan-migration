"""Metrics collector for rate limiting statistics tracking.

This module provides metrics collection functionality to monitor rate limiting
performance, API response times, and throttling events for reporting and
observability in TightBeam v2 Jobber API operations.
"""

import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Optional

# Import Repository for type hints and dependency injection
if TYPE_CHECKING:
    from ..repositories.repository import Repository


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

    def __init__(
        self,
        max_response_times: int = 100,
        max_cost_history: int = 100,
        repository: Optional["Repository"] = None,
    ):
        """Initialize the metrics collector.

        Args:
            max_response_times: Maximum number of response times to keep for
                               average calculations (default: 100)
            max_cost_history: Maximum number of GraphQL cost entries to keep
                             for analysis (default: 100)
            repository: Optional Repository instance for persistent storage
                       of GraphQL cost data (default: None)
        """
        self._lock = threading.Lock()

        # Repository dependency for persistent storage (optional)
        self._repository = repository

        # Request tracking
        self._total_requests = 0
        self._successful_requests = 0
        self._throttled_requests = 0
        self._rate_limit_errors = 0

        # Timing tracking
        self._start_time = time.time()
        self._response_times = deque(maxlen=max_response_times)  # Efficient fixed-size queue

        # Throttling and delay tracking
        self._total_throttle_time = 0.0  # Total time spent waiting due to rate limiting
        self._max_throttle_time = 0.0  # Maximum single throttle delay

        # Advanced metrics
        self._retry_attempts = 0  # Total number of retry attempts
        self._successful_retries = 0  # Retries that eventually succeeded

        # GraphQL cost tracking
        self._graphql_costs = deque(maxlen=max_cost_history)  # Efficient fixed-size queue for cost history

        # Rate limit header tracking
        self._rate_limit_remaining = None  # Current remaining quota
        self._rate_limit_reset = None  # Reset timestamp

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

    def record_graphql_cost(
        self,
        requested_cost: int,
        actual_cost: int,
        query_type: str = "unknown",
        batch_size: int = 0,
    ) -> None:
        """Record GraphQL query cost information.

        Args:
            requested_cost: The cost requested/estimated for the query
            actual_cost: The actual cost returned in response extensions
            query_type: Type of GraphQL query (e.g., 'fetch_clients', 'fetch_invoices')
            batch_size: Number of records requested in the batch
        """
        with self._lock:
            timestamp = time.time()
            cost_difference = actual_cost - requested_cost

            # Maintain existing in-memory deque storage for immediate access
            self._graphql_costs.append(
                {
                    "requested": requested_cost,
                    "actual": actual_cost,
                    "timestamp": timestamp,
                    "difference": cost_difference,
                    "query_type": query_type,
                    "batch_size": batch_size,
                }
            )

            # Persist to database when Repository is available
            if self._repository is not None:
                try:
                    # Create ISO format timestamp for database storage
                    from datetime import datetime

                    created_at = datetime.fromtimestamp(timestamp).isoformat() + "Z"

                    cost_data = {
                        "query_type": query_type,
                        "batch_size": batch_size,
                        "requested_cost": requested_cost,
                        "actual_cost": actual_cost,
                        "cost_difference": cost_difference,
                        "timestamp": timestamp,
                        "created_at": created_at,
                    }

                    # Save to database using repository
                    self._repository.save_graphql_costs([cost_data])

                except Exception:
                    # Log error but don't interrupt the metrics collection flow
                    # This ensures that database issues don't break the application
                    pass  # Silent failure to maintain application stability

    def record_rate_limit_headers(self, remaining: int | None = None, reset_time: int | None = None) -> None:
        """Record rate limiting header values from API responses.

        Args:
            remaining: Number of requests remaining in current window
            reset_time: Timestamp when rate limit window resets
        """
        with self._lock:
            if remaining is not None:
                self._rate_limit_remaining = remaining
            if reset_time is not None:
                self._rate_limit_reset = reset_time

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

    def get_cost_statistics(self) -> dict[str, float | int]:
        """Get GraphQL cost statistics summary.

        Returns:
            dict: Cost statistics including averages, min/max, and trends
        """
        with self._lock:
            if not self._graphql_costs:
                return {
                    "total_queries": 0,
                    "avg_requested_cost": 0.0,
                    "avg_actual_cost": 0.0,
                    "min_actual_cost": 0,
                    "max_actual_cost": 0,
                    "avg_cost_difference": 0.0,
                    "cost_accuracy_percentage": 0.0,
                }

            requested_costs = [entry["requested"] for entry in self._graphql_costs]
            actual_costs = [entry["actual"] for entry in self._graphql_costs]
            differences = [entry["difference"] for entry in self._graphql_costs]

            # Calculate accuracy (how close requested was to actual)
            total_accuracy = sum(
                100 - abs(diff / actual) * 100 if actual > 0 else 100 for diff, actual in zip(differences, actual_costs)
            )
            avg_accuracy = total_accuracy / len(self._graphql_costs) if self._graphql_costs else 0

            return {
                "total_queries": len(self._graphql_costs),
                "avg_requested_cost": sum(requested_costs) / len(requested_costs),
                "avg_actual_cost": sum(actual_costs) / len(actual_costs),
                "min_actual_cost": min(actual_costs),
                "max_actual_cost": max(actual_costs),
                "avg_cost_difference": sum(differences) / len(differences),
                "cost_accuracy_percentage": avg_accuracy,
            }

    def get_rate_limit_status(self) -> dict[str, int | float | None]:
        """Get current rate limit status from headers.

        Returns:
            dict: Current rate limit status including remaining quota and reset time
        """
        with self._lock:
            return {
                "remaining_requests": self._rate_limit_remaining,
                "reset_timestamp": self._rate_limit_reset,
                "seconds_until_reset": (self._rate_limit_reset - time.time() if self._rate_limit_reset else None),
            }

    def get_summary(self) -> dict[str, float | int]:
        """Get comprehensive metrics summary as dictionary.

        Returns comprehensive metrics suitable for integration with
        MigrationSummary reporting and logging systems.

        Returns:
            dict: Complete metrics summary with all tracked statistics
        """
        with self._lock:
            uptime = self.get_uptime_seconds()
            cost_stats = self.get_cost_statistics()
            rate_limit_status = self.get_rate_limit_status()

            summary = {
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

            # Add GraphQL cost statistics
            summary.update(
                {
                    "graphql_total_queries": cost_stats["total_queries"],
                    "graphql_avg_requested_cost": cost_stats["avg_requested_cost"],
                    "graphql_avg_actual_cost": cost_stats["avg_actual_cost"],
                    "graphql_min_actual_cost": cost_stats["min_actual_cost"],
                    "graphql_max_actual_cost": cost_stats["max_actual_cost"],
                    "graphql_avg_cost_difference": cost_stats["avg_cost_difference"],
                    "graphql_cost_accuracy_percentage": cost_stats["cost_accuracy_percentage"],
                }
            )

            # Add rate limit status
            summary.update(
                {
                    "rate_limit_remaining": rate_limit_status["remaining_requests"],
                    "rate_limit_reset_timestamp": rate_limit_status["reset_timestamp"],
                    "rate_limit_seconds_until_reset": rate_limit_status["seconds_until_reset"],
                }
            )

            return summary

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
            # Reset GraphQL cost tracking
            self._graphql_costs.clear()
            # Reset rate limit header tracking
            self._rate_limit_remaining = None
            self._rate_limit_reset = None

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
