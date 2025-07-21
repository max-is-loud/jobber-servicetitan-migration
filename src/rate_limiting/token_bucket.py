"""Token bucket rate limiter implementation for TightBeam application.

This module provides a thread-safe token bucket rate limiter that can handle
concurrent access safely while enforcing rate limits with burst capacity.
"""

import threading
import time
from typing import Optional

from ..utils.debug import debug_print


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter optimized for Jobber GraphQL API.

    Implements the token bucket algorithm with configurable capacity and refill rate.
    Allows burst requests up to the bucket capacity while maintaining a steady
    refill rate over time. Designed specifically for TightBeam v2 performance
    optimization with three optimization levels (conservative, moderate, aggressive).

    The token bucket algorithm works by:
    1. Maintaining a bucket with a maximum capacity of tokens
    2. Refilling tokens at a steady rate (tokens per minute)
    3. Consuming tokens for each request
    4. Allowing burst requests when tokens are available
    5. Blocking requests when bucket is empty

    This implementation is thread-safe and can handle concurrent access from
    multiple threads safely using a threading lock.

    Optimization levels (see docs/JOBBER_API_OPTIMIZATION.md for detailed analysis):
    - Conservative: 250 capacity, 240/min (4 req/sec) - 52% safety margin
    - Moderate: 400 capacity, 360/min (6 req/sec) - 28% safety margin (default)
    - Aggressive: 500 capacity, 480/min (8 req/sec) - 4% safety margin
    """

    def __init__(
        self,
        capacity: int = 300,
        refill_rate: float = 180,
        initial_tokens: Optional[float] = None,
    ):
        """Initialize the token bucket rate limiter.

        Args:
            capacity: Maximum number of tokens the bucket can hold
                     (default: 300, moderate optimization for Jobber GraphQL API)
            refill_rate: Number of tokens to add per minute
                        (default: 180, ~3 req/sec - now configurable via CLI optimization levels)
            initial_tokens: Initial number of tokens (default: capacity // 4 for balanced start)

        Note:
            Default values represent moderate optimization level. For production deployments,
            consider using CLI --optimization-level argument for appropriate performance tuning.
            See docs/JOBBER_API_OPTIMIZATION.md for detailed configuration guidance.
        """
        self._capacity = capacity
        # Start with moderate token count optimized for Jobber GraphQL API
        self._tokens = float(
            initial_tokens if initial_tokens is not None else capacity // 4
        )

        self._refill_rate = refill_rate  # tokens per minute
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume tokens from the bucket.

        The method performs these steps:
        1. Acquire thread lock for thread safety
        2. Refill tokens based on elapsed time
        3. Check if requested tokens are available
        4. Consume tokens if available

        Args:
            tokens: Number of tokens to consume (default: 1.0)

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        with self._lock:
            self._refill()
            debug_print(
                f"[DEBUG] Token bucket - Before consume: {self._tokens:.1f} tokens available"
            )

            if self._tokens >= tokens:
                self._tokens -= tokens
                debug_print(
                    f"[DEBUG] Token bucket - Consumed {tokens} tokens, {self._tokens:.1f} remaining"
                )
                return True

            debug_print(
                f"[DEBUG] Token bucket - Not enough tokens: need {tokens}, have {self._tokens:.1f}"
            )
            return False

    def _refill(self) -> None:
        """Calculate and add tokens based on elapsed time.

        This method calculates how many tokens should be added based on:
        1. The time elapsed since last refill
        2. The configured refill rate (tokens per minute)
        3. Ensures bucket doesn't exceed maximum capacity

        Note: This method assumes the lock is already acquired by the caller.
        """
        current_time = time.time()
        elapsed_seconds = current_time - self._last_refill
        self._last_refill = current_time

        # Calculate tokens to add: (elapsed_seconds / 60) * refill_rate
        # This converts elapsed time to minutes and multiplies by tokens per minute
        tokens_to_add = (elapsed_seconds / 60.0) * self._refill_rate

        # Add tokens but don't exceed capacity
        self._tokens = min(self._capacity, self._tokens + tokens_to_add)

    def get_wait_time(self) -> float:
        """Return seconds until next token will be available.

        This method calculates how long a caller should wait before the next
        token becomes available. Useful for implementing delays or backoff
        strategies in consuming code.

        Returns:
            float: Seconds to wait until next token is available, or 0.0 if
                   tokens are currently available
        """
        with self._lock:
            self._refill()

            if self._tokens >= 1:
                return 0.0

            # Calculate time for next token: tokens_needed / (refill_rate / 60)
            # Since we need 1 token and have fractional tokens, calculate deficit
            tokens_needed = 1 - self._tokens
            tokens_per_second = self._refill_rate / 60.0

            return tokens_needed / tokens_per_second

    def get_available_tokens(self) -> float:
        """Return current number of available tokens.

        This method is useful for monitoring and debugging purposes.

        Returns:
            float: Current number of tokens available in the bucket
        """
        with self._lock:
            self._refill()
            return self._tokens

    def get_capacity(self) -> int:
        """Return the maximum bucket capacity.

        Returns:
            int: Maximum number of tokens the bucket can hold
        """
        return self._capacity

    def get_refill_rate(self) -> float:
        """Return the refill rate in tokens per minute.

        Returns:
            float: Number of tokens added per minute
        """
        return self._refill_rate
