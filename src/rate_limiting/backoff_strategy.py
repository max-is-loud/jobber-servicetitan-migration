"""Exponential backoff strategy implementation for TightBeam application.

This module provides exponential backoff calculations with jitter to prevent
thundering herd problems when multiple clients retry API requests simultaneously.
"""

import random
from typing import Optional


class ExponentialBackoffStrategy:
    """Exponential backoff strategy with configurable parameters and jitter.

    Implements exponential backoff algorithm that increases delay between retries
    exponentially to reduce load on failing services. Includes jitter to prevent
    thundering herd problems when multiple clients retry simultaneously.

    The algorithm works by:
    1. Starting with an initial delay
    2. Multiplying the delay by a factor for each subsequent attempt
    3. Capping the maximum delay to prevent extremely long waits
    4. Adding random jitter to spread out retry attempts
    5. Honoring server-provided Retry-After headers when available

    This is particularly useful for handling HTTP 429 (Too Many Requests) responses
    and temporary service failures in distributed systems.
    """

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter_factor: float = 0.2,
    ):
        """Initialize the exponential backoff strategy.

        Args:
            initial_delay: Starting delay in seconds (default: 1.0)
            max_delay: Maximum delay cap in seconds (default: 60.0)
            multiplier: Factor to multiply delay by each attempt (default: 2.0)
            jitter_factor: Jitter range as percentage ±20% (default: 0.2)
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter_factor = jitter_factor

    def calculate_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """Calculate the delay for a retry attempt.

        Calculates exponential backoff delay with jitter and optionally honors
        server-provided Retry-After headers. The final delay will be the maximum
        of the calculated exponential delay and any server-provided retry delay.

        Args:
            attempt: The retry attempt number (0-based, where 0 is first retry)
            retry_after: Optional server-provided delay from Retry-After header

        Returns:
            float: Calculated delay in seconds with jitter applied

        Examples:
            >>> strategy = ExponentialBackoffStrategy()
            >>> strategy.calculate_delay(0)  # First retry: ~1.0s ± 20%
            >>> strategy.calculate_delay(3)  # Fourth retry: ~8.0s ± 20%
            >>> strategy.calculate_delay(10)  # Capped at max_delay: ~60s ± 20%
            >>> strategy.calculate_delay(2, retry_after=15.0)  # Uses max(4.0, 15.0) = 15.0s ± 20%
        """  # noqa: E501
        # Calculate exponential delay: initial * (multiplier ^ attempt)
        exponential_delay = self.initial_delay * (self.multiplier**attempt)

        # Cap at maximum delay
        exponential_delay = min(exponential_delay, self.max_delay)

        # If server provided Retry-After, use the maximum of both delays
        base_delay = max(exponential_delay, retry_after) if retry_after is not None else exponential_delay

        # Add jitter to prevent thundering herd
        return self._add_jitter(base_delay)

    def _add_jitter(self, delay: float) -> float:
        """Add random jitter to a delay value.

        Applies random jitter within the configured jitter_factor range to prevent
        multiple clients from retrying at exactly the same time. This helps
        distribute load and avoid thundering herd problems.

        Args:
            delay: Base delay in seconds

        Returns:
            float: Delay with random jitter applied

        Examples:
            With jitter_factor=0.2 (±20%):
            >>> strategy._add_jitter(10.0)  # Returns value between 8.0 and 12.0
        """
        # Generate random jitter factor between -jitter_factor and +jitter_factor
        jitter_multiplier = 1 + random.uniform(-self.jitter_factor, self.jitter_factor)

        # Apply jitter while ensuring delay never goes below 0
        jittered_delay = delay * jitter_multiplier
        return max(0.0, jittered_delay)

    def get_sequence(self, max_attempts: int, retry_after: Optional[float] = None) -> list[float]:
        """Get a sequence of delays for multiple retry attempts.

        Useful for testing, monitoring, or pre-calculating retry schedules.

        Args:
            max_attempts: Number of retry attempts to calculate
            retry_after: Optional server-provided delay to honor

        Returns:
            list[float]: List of calculated delays for each attempt
        """
        return [self.calculate_delay(attempt, retry_after) for attempt in range(max_attempts)]

    def get_total_delay(self, max_attempts: int, retry_after: Optional[float] = None) -> float:
        """Calculate total time for all retry attempts.

        Args:
            max_attempts: Number of retry attempts
            retry_after: Optional server-provided delay to honor

        Returns:
            float: Total delay time for all attempts
        """
        return sum(self.get_sequence(max_attempts, retry_after))

    def __repr__(self) -> str:
        """Return string representation of the backoff strategy."""
        return (
            f"ExponentialBackoffStrategy("
            f"initial_delay={self.initial_delay}, "
            f"max_delay={self.max_delay}, "
            f"multiplier={self.multiplier}, "
            f"jitter_factor={self.jitter_factor})"
        )
