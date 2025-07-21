"""ConfigManager implementation for centralized configuration management."""

from pathlib import Path
from typing import Any

import yaml

from ..exceptions import ConfigurationError
from .config_models import (
    AppConfig,
    BackoffConfig,
    DatabaseConfig,
    DelayConfig,
    LoggingConfig,
    PaginationConfig,
    RateLimitConfig,
)


class ConfigManagerImpl:
    """ConfigManager implementation for loading YAML-based configuration.

    Provides centralized configuration management with environment-specific overrides
    and comprehensive validation using dataclasses. Follows the project's Protocol-based
    dependency injection architecture.
    """

    def __init__(self, config_dir: str = "config", environment: str | None = None):
        """Initialize ConfigManager with configuration directory and environment.

        Args:
            config_dir: Directory containing configuration files (default: "config")
            environment: Environment override (dev, prod), or None for base config only

        Raises:
            ConfigurationError: If config files cannot be loaded or are invalid
        """
        self.config_dir = Path(config_dir)
        self.environment = environment
        self.config: AppConfig | None = None
        self._load_config()

    def _load_config(self) -> None:
        """Load and validate configuration from YAML files.

        Raises:
            ConfigurationError: If config files cannot be loaded or are invalid
        """
        try:
            # Load base configuration
            base_config_path = self.config_dir / "settings.yaml"
            if not base_config_path.exists():
                raise ConfigurationError(
                    f"Base config file not found: {base_config_path}"
                )

            with open(base_config_path) as f:
                config_data = yaml.safe_load(f)

            # Apply environment-specific overrides if specified
            if self.environment:
                env_config_path = self.config_dir / f"settings_{self.environment}.yaml"
                if env_config_path.exists():
                    with open(env_config_path) as f:
                        env_data = yaml.safe_load(f)
                    config_data = self._merge_configs(config_data, env_data)

            # Validate and create configuration objects
            self.config = self._create_app_config(config_data)

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML configuration: {e}") from e
        except OSError as e:
            raise ConfigurationError(f"Cannot read configuration files: {e}") from e
        except (ValueError, TypeError) as e:
            raise ConfigurationError(f"Invalid configuration values: {e}") from e

    def _merge_configs(
        self, base: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge environment-specific overrides into base configuration.

        Args:
            base: Base configuration dictionary
            override: Environment-specific overrides

        Returns:
            Merged configuration dictionary
        """
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def _create_app_config(self, config_data: dict[str, Any]) -> AppConfig:
        """Create validated AppConfig from configuration data.

        Args:
            config_data: Raw configuration dictionary

        Returns:
            Validated AppConfig instance

        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            # Create rate limit configurations
            rate_limits = {}
            for level, rate_config in config_data["rate_limits"].items():
                rate_limits[level] = RateLimitConfig(
                    capacity=rate_config["capacity"],
                    refill_rate=rate_config["refill_rate"],
                    initial_tokens=rate_config["initial_tokens"],
                    safety_margin=rate_config["safety_margin"],
                )

            # Create pagination configuration
            pagination_data = config_data["pagination"]
            pagination = PaginationConfig(
                clients=pagination_data["clients"],
                invoices=pagination_data["invoices"],
                quotes=pagination_data["quotes"],
                jobs=pagination_data["jobs"],
                properties=pagination_data["properties"],
                requests=pagination_data["requests"],
                users=pagination_data["users"],
                expenses=pagination_data["expenses"],
                visits=pagination_data["visits"],
                timesheet_entries=pagination_data["timesheet_entries"],
                product_services=pagination_data["product_services"],
                tax_rates=pagination_data["tax_rates"],
                default=pagination_data["default"],
            )

            # Create delay configuration
            delay_data = config_data["delays"]
            delays = DelayConfig(
                page_delay=delay_data["page_delay"],
                request_timeout=delay_data["request_timeout"],
                retry_base_delay=delay_data["retry_base_delay"],
            )

            # Create backoff configuration
            backoff_data = config_data["backoff"]
            backoff = BackoffConfig(
                initial_delay=backoff_data["initial_delay"],
                max_delay=backoff_data["max_delay"],
                multiplier=backoff_data["multiplier"],
                jitter_factor=backoff_data["jitter_factor"],
            )

            # Create logging configuration
            logging_data = config_data["logging"]
            logging = LoggingConfig(
                verbose_cost_monitoring=logging_data["verbose_cost_monitoring"],
                performance_logging=logging_data["performance_logging"],
                level=logging_data["level"],
            )

            # Create database configuration
            database_data = config_data["database"]
            database = DatabaseConfig(
                default_path=database_data["default_path"],
                timeout=database_data["timeout"],
                wal_mode=database_data["wal_mode"],
            )

            return AppConfig(
                rate_limits=rate_limits,
                pagination=pagination,
                delays=delays,
                backoff=backoff,
                logging=logging,
                database=database,
            )

        except KeyError as e:
            raise ConfigurationError(f"Missing required configuration key: {e}") from e

    def get_rate_limit_config(self, optimization_level: str) -> dict[str, Any]:
        """Get rate limiting configuration for the specified optimization level."""
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        if optimization_level not in self.config.rate_limits:
            available = list(self.config.rate_limits.keys())
            raise ConfigurationError(
                f"Invalid optimization level '{optimization_level}'. Available: {available}"
            )

        rate_config = self.config.rate_limits[optimization_level]
        return {
            "capacity": rate_config.capacity,
            "refill_rate": rate_config.refill_rate,
            "initial_tokens": rate_config.initial_tokens,
            "safety_margin": rate_config.safety_margin,
        }

    def get_pagination_config(self, entity_type: str | None = None) -> int:
        """Get pagination size for the specified entity type."""
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        if entity_type is None:
            return self.config.pagination.default

        # Convert entity_type to match dataclass field names
        if hasattr(self.config.pagination, entity_type):
            return getattr(self.config.pagination, entity_type)
        else:
            # Try with snake_case conversion
            snake_case = entity_type.replace("-", "_")
            if hasattr(self.config.pagination, snake_case):
                return getattr(self.config.pagination, snake_case)
            else:
                raise ConfigurationError(
                    f"Invalid entity type '{entity_type}'. Using default pagination size."
                )

    def get_delay_config(self, delay_type: str) -> float:
        """Get delay configuration for the specified type."""
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        if hasattr(self.config.delays, delay_type):
            return getattr(self.config.delays, delay_type)
        else:
            available = ["page_delay", "request_timeout", "retry_base_delay"]
            raise ConfigurationError(
                f"Invalid delay type '{delay_type}'. Available: {available}"
            )

    def get_backoff_config(self) -> dict[str, Any]:
        """Get exponential backoff strategy configuration."""
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        return {
            "initial_delay": self.config.backoff.initial_delay,
            "max_delay": self.config.backoff.max_delay,
            "multiplier": self.config.backoff.multiplier,
            "jitter_factor": self.config.backoff.jitter_factor,
        }

    def get_logging_config(self) -> dict[str, Any]:
        """Get logging configuration."""
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        return {
            "verbose_cost_monitoring": self.config.logging.verbose_cost_monitoring,
            "performance_logging": self.config.logging.performance_logging,
            "level": self.config.logging.level,
        }

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration."""
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        return {
            "default_path": self.config.database.default_path,
            "timeout": self.config.database.timeout,
            "wal_mode": self.config.database.wal_mode,
        }

    def reload_config(self, environment: str | None = None) -> None:
        """Reload configuration from YAML files."""
        if environment is not None:
            self.environment = environment
        self._load_config()
