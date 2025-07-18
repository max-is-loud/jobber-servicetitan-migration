"""Token bucket rate limiter implementation for TightBeam application.

This module provides a thread-safe token bucket rate limiter that can handle
concurrent access safely while enforcing rate limits with burst capacity.
"""

import threading
import time
from typing import Optional


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter.

    Implements the token bucket algorithm with configurable capacity and refill rate.
    Allows burst requests up to the bucket capacity while maintaining a steady
    refill rate over time.

    The token bucket algorithm works by:
    1. Maintaining a bucket with a maximum capacity of tokens
    2. Refilling tokens at a steady rate (tokens per minute)
    3. Consuming tokens for each request
    4. Allowing burst requests when tokens are available
    5. Blocking requests when bucket is empty

    This implementation is thread-safe and can handle concurrent access from
    multiple threads safely using a threading lock.
    """

    def __init__(
        self,
        capacity: int = 100,
        refill_rate: float = 400,
        initial_tokens: Optional[float] = None,
    ):
        """Initialize the token bucket rate limiter.

        Args:
            capacity: Maximum number of tokens the bucket can hold (default: 100, aligned with production settings)
            refill_rate: Number of tokens to add per minute (default: 400)
            initial_tokens: Initial number of tokens (default: capacity // 4 for conservative start)
        """
        self._capacity = capacity
        # Start with conservative token count to prevent initial burst
        self._tokens = float(
            initial_tokens if initial_tokens is not None else capacity // 4
        )
        self._refill_rate = refill_rate  # tokens per minute
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume the specified number of tokens.

        This method is thread-safe and will:
        1. Acquire a lock to prevent race conditions
        2. Refill tokens based on elapsed time
        3. Check if enough tokens are available
        4. Consume tokens if available
        5. Return success/failure status

        Args:
            tokens: Number of tokens to consume (default: 1)

        Returns:
            bool: True if tokens were successfully consumed, False otherwise
        """
        with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
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
