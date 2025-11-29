"""Adaptive performance optimizer for maximizing API throughput.

This module implements an intelligent optimizer that dynamically adjusts
pagination sizes and page delays to achieve maximum throughput while
avoiding API throttling.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict

from ..config import ConfigManagerImpl
from ..interfaces import Logger


@dataclass
class PerformanceMetrics:
    """Metrics for tracking API performance."""

    requests_made: int = 0
    throttles_encountered: int = 0
    total_entities_processed: int = 0
    total_time_elapsed: float = 0.0
    current_throughput: float = 0.0  # entities per second
    average_request_time: float = 0.0
    throttle_rate: float = 0.0  # throttles per request

    def calculate_throughput(self) -> float:
        """Calculate current throughput in entities per second."""
        if self.total_time_elapsed > 0:
            self.current_throughput = self.total_entities_processed / self.total_time_elapsed
        return self.current_throughput

    def calculate_throttle_rate(self) -> float:
        """Calculate throttling rate as percentage of requests."""
        if self.requests_made > 0:
            self.throttle_rate = self.throttles_encountered / self.requests_made
        return self.throttle_rate


@dataclass
class OptimizationSettings:
    """Current optimization settings."""

    page_size: int = 30
    page_delay: float = 1.0
    confidence_score: float = 0.0  # How confident we are in these settings

    def calculate_theoretical_throughput(self) -> float:
        """Calculate theoretical entities per second with current settings."""
        if self.page_delay > 0:
            requests_per_second = 1.0 / self.page_delay
            return requests_per_second * self.page_size
        return 0.0


class AdaptivePerformanceOptimizer:
    """
    Adaptive performance optimizer for API requests.

    This optimizer automatically adjusts pagination size and page delays
    to maximize throughput while keeping throttling below acceptable thresholds.

    Algorithm:
    1. Monitor request performance and throttling rates
    2. If throttling is low and throughput can improve: increase page size or decrease delay
    3. If throttling is high: decrease page size or increase delay
    4. Use confidence scoring to make conservative vs aggressive adjustments
    """

    def __init__(
        self,
        config_manager: ConfigManagerImpl,
        logger: Logger,
        target_throttle_rate: float = 0.05,  # Allow up to 5% throttling
        optimization_interval: int = 10,  # Adjust every N requests
        min_page_size: int = 10,
        max_page_size: int = 100,
        min_page_delay: float = 0.1,
        max_page_delay: float = 10.0,
        persist_settings: bool = True,
    ):
        """Initialize the adaptive optimizer.

        Args:
            config_manager: Configuration manager for updating settings
            logger: Logger for status messages
            target_throttle_rate: Maximum acceptable throttle rate (0.0-1.0)
            optimization_interval: Number of requests between optimizations
            min_page_size: Minimum pagination size
            max_page_size: Maximum pagination size
            min_page_delay: Minimum page delay in seconds
            max_page_delay: Maximum page delay in seconds
        """
        self.config_manager = config_manager
        self.logger = logger
        self.target_throttle_rate = target_throttle_rate
        self.optimization_interval = optimization_interval
        self.min_page_size = min_page_size
        self.max_page_size = max_page_size
        self.min_page_delay = min_page_delay
        self.max_page_delay = max_page_delay
        self._persist_settings = persist_settings

        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.current_settings = OptimizationSettings()
        self.optimization_history = []
        self.last_optimization_request = 0
        self.start_time = time.time()

        # Load initial settings from config
        self._load_initial_settings()

        self.logger.info("🤖 Adaptive Performance Optimizer initialized")
        self.logger.info(f"   • Target throttle rate: {self.target_throttle_rate:.1%}")
        self.logger.info(f"   • Optimization interval: every {self.optimization_interval} requests")
        self.logger.info(f"   • Page size range: {self.min_page_size}-{self.max_page_size}")
        self.logger.info(f"   • Page delay range: {self.min_page_delay}-{self.max_page_delay}s")

    def _load_initial_settings(self) -> None:
        """Load initial settings from configuration."""
        try:
            self.current_settings.page_size = self.config_manager.get_pagination_config("clients")
            self.current_settings.page_delay = self.config_manager.get_delay_config("page_delay")
            self.current_settings.confidence_score = 0.5  # Start with medium confidence
        except Exception as e:
            self.logger.debug(f"Could not load initial settings: {e}")

    def record_request(self, entities_received: int, request_time: float, was_throttled: bool = False) -> None:
        """Record the results of an API request.

        Args:
            entities_received: Number of entities received in this request
            request_time: Time taken for the request in seconds
            was_throttled: Whether this request was throttled
        """
        self.metrics.requests_made += 1
        self.metrics.total_entities_processed += entities_received
        self.metrics.total_time_elapsed = time.time() - self.start_time

        if was_throttled:
            self.metrics.throttles_encountered += 1

        # Update average request time (exponential moving average)
        alpha = 0.1  # Smoothing factor
        if self.metrics.average_request_time == 0:
            self.metrics.average_request_time = request_time
        else:
            self.metrics.average_request_time = alpha * request_time + (1 - alpha) * self.metrics.average_request_time

        # Update metrics
        self.metrics.calculate_throughput()
        self.metrics.calculate_throttle_rate()

        # Check if we should optimize
        should_optimize = (self.metrics.requests_made - self.last_optimization_request) >= self.optimization_interval

        # Emergency optimization for severe throttling - don't wait for interval
        if was_throttled and self.metrics.requests_made > 5:
            recent_throttle_rate = self.metrics.calculate_throttle_rate()
            if recent_throttle_rate > (self.target_throttle_rate * 2.0):  # Emergency threshold
                should_optimize = True
                self.logger.debug(f"🚨 Emergency optimization triggered - throttle rate: {recent_throttle_rate:.1%}")

        if should_optimize:
            self._optimize_settings()
            self.last_optimization_request = self.metrics.requests_made

    def _optimize_settings(self) -> None:
        """Analyze performance and optimize settings."""
        old_settings = OptimizationSettings(
            page_size=self.current_settings.page_size,
            page_delay=self.current_settings.page_delay,
            confidence_score=self.current_settings.confidence_score,
        )

        # Calculate current performance
        current_throttle_rate = self.metrics.calculate_throttle_rate()
        current_throughput = self.metrics.calculate_throughput()

        # Determine optimization strategy
        if current_throttle_rate > self.target_throttle_rate:
            # Too much throttling - be more conservative
            self._reduce_load()
        elif current_throttle_rate < (self.target_throttle_rate * 0.5) and self.metrics.requests_made > 5:
            # Low throttling - we can be more aggressive, but with safety checks
            # Don't be too aggressive early in the learning process
            if self.metrics.requests_made < 20 and self.current_settings.page_size > 45:
                # Early learning phase with large page size - be cautious
                self._fine_tune()
            else:
                self._increase_load()
        else:
            # In the sweet spot - minor adjustments only
            self._fine_tune()

        # Apply settings if they changed
        if (
            self.current_settings.page_size != old_settings.page_size
            or abs(self.current_settings.page_delay - old_settings.page_delay) > 0.01
        ):
            self._apply_settings()

            # Log optimization
            theoretical_throughput = self.current_settings.calculate_theoretical_throughput()
            self.logger.info(
                f"🎯 Performance optimization: page_size={self.current_settings.page_size}, "
                f"page_delay={self.current_settings.page_delay:.2f}s"
            )
            self.logger.info(
                f"   • Current: {current_throughput:.1f} entities/sec, " f"throttle rate: {current_throttle_rate:.1%}"
            )
            self.logger.info(
                f"   • Theoretical: {theoretical_throughput:.1f} entities/sec "
                f"(confidence: {self.current_settings.confidence_score:.1%})"
            )

    def _reduce_load(self) -> None:
        """Reduce load to decrease throttling."""
        # Calculate severity - be more aggressive for higher throttling rates
        throttle_severity = min(self.metrics.throttle_rate / self.target_throttle_rate, 5.0)

        # For severe throttling (>3x target), reduce both page size AND increase delay
        if throttle_severity > 3.0:
            # Severe throttling - aggressive reduction
            if self.current_settings.page_size > self.min_page_size:
                # Reduce page size significantly
                reduction = max(10, int(self.current_settings.page_size * 0.3))
                self.current_settings.page_size = max(self.current_settings.page_size - reduction, self.min_page_size)

            if self.current_settings.page_delay < self.max_page_delay:
                # Also increase delay significantly
                increase_factor = 1.5 + (throttle_severity - 3.0) * 0.5  # 1.5x to 2.5x
                self.current_settings.page_delay = min(
                    self.current_settings.page_delay * increase_factor, self.max_page_delay
                )

        else:
            # Normal throttling - standard approach
            # Priority: increase delay first, then reduce page size
            if self.current_settings.page_delay < self.max_page_delay:
                # Increase delay by 20-50% depending on severity
                increase_factor = 1.2 + (throttle_severity - 1.0) * 0.3
                self.current_settings.page_delay = min(
                    self.current_settings.page_delay * increase_factor, self.max_page_delay
                )
            elif self.current_settings.page_size > self.min_page_size:
                # Reduce page size
                reduction = max(5, int(self.current_settings.page_size * 0.2))
                self.current_settings.page_size = max(self.current_settings.page_size - reduction, self.min_page_size)

        # Increase confidence when reducing load (safer direction)
        # More confidence gain for severe throttling responses
        confidence_gain = 0.1 + (0.1 if throttle_severity > 3.0 else 0.0)
        self.current_settings.confidence_score = min(1.0, self.current_settings.confidence_score + confidence_gain)

    def _increase_load(self) -> None:
        """Increase load to improve throughput."""
        # Be more conservative with increases, especially early on
        confidence_factor = self.current_settings.confidence_score

        # Priority: increase page size first (more efficient), then reduce delay
        if self.current_settings.page_size < self.max_page_size:
            # More conservative increases based on confidence and current size
            if self.current_settings.page_size <= 30:
                # Small increases for small page sizes
                increase = max(2, int(self.current_settings.page_size * 0.05 * confidence_factor))
            elif self.current_settings.page_size <= 50:
                # Even smaller increases for medium page sizes
                increase = max(1, int(self.current_settings.page_size * 0.03 * confidence_factor))
            else:
                # Very conservative for large page sizes
                increase = 1 if confidence_factor > 0.8 else 0

            self.current_settings.page_size = min(self.current_settings.page_size + increase, self.max_page_size)
        elif self.current_settings.page_delay > self.min_page_delay:
            # Reduce delay more conservatively
            reduction_factor = 0.95 - (0.05 * confidence_factor)  # 0.90-0.95 range
            self.current_settings.page_delay = max(
                self.current_settings.page_delay * reduction_factor, self.min_page_delay
            )

        # Decrease confidence when being more aggressive, but not as much
        self.current_settings.confidence_score = max(0.1, self.current_settings.confidence_score - 0.03)

    def _fine_tune(self) -> None:
        """Make minor adjustments when in optimal range."""
        # Small adjustments based on recent performance
        if self.metrics.requests_made > 20:  # Need enough data
            # Slightly favor larger page sizes for efficiency
            if (
                self.current_settings.page_size < self.max_page_size and self.metrics.average_request_time < 5.0
            ):  # If requests are fast
                self.current_settings.page_size = min(self.current_settings.page_size + 2, self.max_page_size)

    def _apply_settings(self) -> None:
        """Apply current settings to the configuration manager."""
        if not self._persist_settings:
            return
        try:
            # Update configuration (this will trigger hot-reload)
            from pathlib import Path

            import yaml

            # Read current config
            config_path = Path("config/settings.yaml")
            if config_path.exists():
                with open(config_path) as f:
                    config_data = yaml.safe_load(f)

                # Update settings
                config_data["delays"]["page_delay"] = round(self.current_settings.page_delay, 2)
                config_data["pagination"]["clients"] = self.current_settings.page_size
                config_data["pagination"]["invoices"] = self.current_settings.page_size

                # Write back to config
                with open(config_path, "w") as f:
                    yaml.safe_dump(config_data, f, default_flow_style=False, sort_keys=False)

        except Exception as e:
            self.logger.debug(f"Could not apply settings to config: {e}")

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get current performance summary."""
        return {
            "requests_made": self.metrics.requests_made,
            "entities_processed": self.metrics.total_entities_processed,
            "throttles_encountered": self.metrics.throttles_encountered,
            "throttle_rate": f"{self.metrics.throttle_rate:.1%}",
            "current_throughput": f"{self.metrics.current_throughput:.1f} entities/sec",
            "average_request_time": f"{self.metrics.average_request_time:.2f}s",
            "current_page_size": self.current_settings.page_size,
            "current_page_delay": f"{self.current_settings.page_delay:.2f}s",
            "confidence_score": f"{self.current_settings.confidence_score:.1%}",
            "theoretical_max": f"{self.current_settings.calculate_theoretical_throughput():.1f} entities/sec",
        }

    def force_optimization(self) -> None:
        """Force an immediate optimization cycle."""
        self._optimize_settings()

    def reset_metrics(self) -> None:
        """Reset performance metrics (useful for testing different phases)."""
        self.metrics = PerformanceMetrics()
        self.start_time = time.time()
        self.logger.info("🔄 Performance metrics reset")
