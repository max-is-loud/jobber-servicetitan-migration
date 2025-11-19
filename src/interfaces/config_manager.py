"""ConfigManager Protocol for centralized configuration management."""

from typing import Any, Protocol


class ConfigManager(Protocol):
    """ConfigManager interface for loading and managing application configuration.

    This Protocol enables dependency injection of configuration management implementations,
    providing centralized access to YAML-based configuration with environment-specific
    overrides and comprehensive validation.
    """

    def get_rate_limit_config(self, optimization_level: str) -> dict[str, Any]:
        """Get rate limiting configuration for the specified optimization level.

        Args:
            optimization_level: The optimization level (conservative, moderate, aggressive)

        Returns:
            Dictionary containing rate limit configuration (capacity, refill_rate, safety_margin)

        Raises:
            ConfigurationError: If optimization level is invalid or config is malformed
        """
        ...

    def get_pagination_config(self, entity_type: str | None = None) -> int:
        """Get pagination size for the specified entity type.

        Args:
            entity_type: The entity type (clients, invoices, etc.), or None for default

        Returns:
            Pagination size for the specified entity type

        Raises:
            ConfigurationError: If entity type is invalid or config is malformed
        """
        ...

    def get_delay_config(self, delay_type: str) -> float:
        """Get delay configuration for the specified type.

        Args:
            delay_type: The delay type (page_delay, request_timeout, retry_base_delay)

        Returns:
            Delay value in seconds

        Raises:
            ConfigurationError: If delay type is invalid or config is malformed
        """
        ...

    def get_backoff_config(self) -> dict[str, Any]:
        """Get exponential backoff strategy configuration.

        Returns:
            Dictionary containing backoff configuration (initial_delay, max_delay,
            multiplier, max_attempts, jitter)

        Raises:
            ConfigurationError: If backoff config is malformed
        """
        ...

    def get_logging_config(self) -> dict[str, Any]:
        """Get logging configuration.

        Returns:
            Dictionary containing logging configuration (verbose_cost_monitoring,
            performance_logging, level)

        Raises:
            ConfigurationError: If logging config is malformed
        """
        ...

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration.

        Returns:
            Dictionary containing database configuration (default_path, timeout, wal_mode)

        Raises:
            ConfigurationError: If database config is malformed
        """
        ...

    def get_attachment_config(self) -> dict[str, Any]:
        """Get attachment download configuration.

        Returns:
            Dictionary containing attachment configuration (auto_download)

        Raises:
            ConfigurationError: If attachment config is malformed
        """
        ...

    def reload_config(self, environment: str | None = None) -> None:
        """Reload configuration from YAML files.

        Args:
            environment: Environment override (dev, prod), or None for base config only

        Raises:
            ConfigurationError: If config files cannot be loaded or are malformed
        """
        ...
