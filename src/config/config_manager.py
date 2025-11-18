"""Configuration manager implementation for TightBeam v2."""

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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


class ConfigFileHandler(FileSystemEventHandler):
    """File system event handler for configuration file changes."""

    def __init__(self, config_manager: "ConfigManagerImpl", config_file_path: str):
        super().__init__()
        self.config_manager = config_manager
        self.config_file_path = config_file_path
        self._last_reload = 0
        self._reload_cooldown = 1.0  # Minimum 1 second between reloads

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        if event.src_path == self.config_file_path:
            current_time = time.time()
            if current_time - self._last_reload > self._reload_cooldown:
                self._last_reload = current_time
                # Use a small delay to ensure file write is complete
                threading.Timer(0.1, self.config_manager._reload_config).start()


class ConfigManagerImpl:
    """ConfigManager implementation for loading YAML-based configuration.

    Provides centralized configuration management with environment-specific overrides
    and comprehensive validation using dataclasses. Follows the project's Protocol-based
    dependency injection architecture.
    """

    def __init__(self, config_dir: str = "config", environment: str | None = None, enable_hot_reload: bool = True):
        """Initialize ConfigManager with configuration directory and environment.

        Args:
            config_dir: Directory containing configuration files (default: "config")
            environment: Environment override (dev, prod), or None for base config only
            enable_hot_reload: Enable automatic configuration reloading (default: True)

        Raises:
            ConfigurationError: If config files cannot be loaded or are invalid
        """
        self.config_dir = Path(config_dir)
        self.environment = environment
        self.config: AppConfig | None = None
        self.enable_hot_reload = enable_hot_reload
        self._config_lock = threading.Lock()
        self._observer: Optional[Observer] = None
        self._reload_callbacks: list[Callable[[AppConfig | None, AppConfig | None], None]] = []
        self._load_config()

        # Start file watcher if hot reload is enabled
        if self.enable_hot_reload:
            self._start_file_watcher()

    def _load_config(self) -> None:
        """Load and validate configuration from YAML files.

        Raises:
            ConfigurationError: If config files cannot be loaded or are invalid
        """
        try:
            # Load base configuration
            base_config_path = self.config_dir / "settings.yaml"
            if not base_config_path.exists():
                raise ConfigurationError(f"Base config file not found: {base_config_path}")

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

    def _merge_configs(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Merge environment-specific overrides into base configuration.

        Args:
            base: Base configuration dictionary
            override: Environment-specific overrides

        Returns:
            Merged configuration dictionary
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
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
                nested_notes=pagination_data["nested_notes"],
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
                max_retries=config_data["max_retries"],
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
            raise ConfigurationError(f"Invalid optimization level '{optimization_level}'. Available: {available}")

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
                raise ConfigurationError(f"Invalid entity type '{entity_type}'. Using default pagination size.")

    def get_delay_config(self, delay_type: str) -> float:
        """Get delay configuration for the specified type."""
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        if hasattr(self.config.delays, delay_type):
            return getattr(self.config.delays, delay_type)
        else:
            available = ["page_delay", "request_timeout", "retry_base_delay"]
            raise ConfigurationError(f"Invalid delay type '{delay_type}'. Available: {available}")

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

    def get_max_retries(self) -> int:
        """Get maximum retry attempts for rate-limited requests.

        Returns:
            Maximum number of retry attempts for exponential backoff
        """
        if not self.config:
            raise ConfigurationError("Configuration not loaded")

        return self.config.max_retries

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

    def _start_file_watcher(self) -> None:
        """Start file system watcher for configuration files."""
        try:
            self._observer = Observer()
            config_file_path = str(self.config_dir / "settings.yaml")
            handler = ConfigFileHandler(self, config_file_path)

            # Watch the config directory for changes
            self._observer.schedule(handler, str(self.config_dir), recursive=False)
            self._observer.start()
        except Exception as e:
            # Silently disable hot reload if watchdog is not available
            self.enable_hot_reload = False

    def _reload_config(self) -> None:
        """Internal method to reload configuration with thread safety."""
        with self._config_lock:
            try:
                old_config = self.config
                self._load_config()

                # Notify callbacks of configuration change
                for callback in self._reload_callbacks:
                    try:
                        callback(old_config, self.config)
                    except Exception:
                        # Don't let callback errors break the reload
                        pass

                print(f"🔄 Configuration reloaded from {self.config_dir / 'settings.yaml'}")

            except Exception as e:
                print(f"❌ Failed to reload configuration: {e}")

    def add_reload_callback(self, callback: Callable[[AppConfig | None, AppConfig | None], None]) -> None:
        """Add a callback to be called when configuration is reloaded.

        Args:
            callback: Function that takes (old_config, new_config) as arguments
        """
        self._reload_callbacks.append(callback)

    def stop_file_watcher(self) -> None:
        """Stop the file system watcher."""
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()

    def __del__(self):
        """Cleanup file watcher on destruction."""
        self.stop_file_watcher()

    def get_current_page_delay(self) -> float:
        """Get current page delay setting for hot-reload updates."""
        return self.get_delay_config("page_delay")

    def get_current_rate_limit_settings(self, optimization_level: str) -> dict[str, Any]:
        """Get current rate limiting settings for hot-reload updates."""
        return self.get_rate_limit_config(optimization_level)
