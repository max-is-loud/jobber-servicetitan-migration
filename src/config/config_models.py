"""Configuration data models for validation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration for a specific optimization level."""

    capacity: int  # Token bucket capacity
    refill_rate: int  # Tokens per minute refill rate
    initial_tokens: int  # Initial token count
    safety_margin: float  # Safety margin percentage (0.0-1.0)

    def __post_init__(self) -> None:
        """Validate rate limit configuration values."""
        if not isinstance(self.capacity, int):
            raise ValueError(f"Rate limit capacity must be an integer, got {type(self.capacity).__name__}")
        if self.capacity <= 0:
            raise ValueError(f"Rate limit capacity must be positive, got {self.capacity}")
        if self.capacity > 10000:
            raise ValueError(f"Rate limit capacity seems too high ({self.capacity}), maximum recommended is 10000")

        if not isinstance(self.refill_rate, int):
            raise ValueError(f"Rate limit refill_rate must be an integer, got {type(self.refill_rate).__name__}")
        if self.refill_rate <= 0:
            raise ValueError(f"Rate limit refill_rate must be positive, got {self.refill_rate}")
        if self.refill_rate > 60000:  # 1000 per second max
            raise ValueError(
                f"Rate limit refill_rate seems too high ({self.refill_rate}), maximum recommended is 60000/minute"
            )

        if not isinstance(self.initial_tokens, int):
            raise ValueError(f"Initial tokens must be an integer, got {type(self.initial_tokens).__name__}")
        if self.initial_tokens < 0:
            raise ValueError(f"Initial tokens must be non-negative, got {self.initial_tokens}")
        if self.initial_tokens > self.capacity:
            raise ValueError(f"Initial tokens ({self.initial_tokens}) cannot exceed capacity ({self.capacity})")

        if not isinstance(self.safety_margin, (int, float)):
            raise ValueError(f"Safety margin must be a number, got {type(self.safety_margin).__name__}")
        if not 0.0 <= self.safety_margin <= 1.0:
            raise ValueError(f"Safety margin must be between 0.0 and 1.0, got {self.safety_margin}")


@dataclass(frozen=True)
class PaginationConfig:
    """Pagination configuration for all entity types."""

    clients: int
    invoices: int
    quotes: int
    jobs: int
    properties: int
    requests: int
    users: int
    expenses: int
    visits: int
    timesheet_entries: int
    product_services: int
    tax_rates: int
    nested_notes: int
    default: int

    def __post_init__(self) -> None:
        """Validate pagination configuration values."""
        for field, value in self.__dict__.items():
            if not isinstance(value, int):
                raise ValueError(f"Pagination size for {field} must be an integer, got {type(value).__name__}")
            if value <= 0:
                raise ValueError(f"Pagination size for {field} must be positive (minimum 1), got {value}")

            # Special validation for nested_notes (used in nested GraphQL queries)
            if field == "nested_notes":
                if value > 100:
                    raise ValueError(
                        f"nested_notes pagination must not exceed 100, got {value}. "
                        "Very high values significantly increase GraphQL query costs."
                    )
                continue

            if value > 1000:
                raise ValueError(f"Pagination size for {field} must not exceed 1000 (API limits), got {value}")
            if field != "default" and value > 100:
                # Warn for values over 100 (may hit API rate limits)
                import warnings

                warnings.warn(
                    f"Pagination size for {field} is {value} (>100). Consider using smaller values to avoid API rate limits.",
                    UserWarning,
                )


@dataclass(frozen=True)
class DelayConfig:
    """Timing and delay configuration."""

    page_delay: float  # Delay between pages in seconds
    request_timeout: float  # HTTP request timeout in seconds
    retry_base_delay: float  # Base retry delay in seconds

    def __post_init__(self) -> None:
        """Validate delay configuration values."""
        if not isinstance(self.page_delay, (int, float)):
            raise ValueError(f"Page delay must be a number, got {type(self.page_delay).__name__}")
        if self.page_delay < 0:
            raise ValueError(f"Page delay must be non-negative, got {self.page_delay}")
        if self.page_delay > 30:
            import warnings

            warnings.warn(
                f"Page delay is {self.page_delay}s (>30s). This may significantly slow down migrations.",
                UserWarning,
            )

        if not isinstance(self.request_timeout, (int, float)):
            raise ValueError(f"Request timeout must be a number, got {type(self.request_timeout).__name__}")
        if self.request_timeout <= 0:
            raise ValueError(f"Request timeout must be positive, got {self.request_timeout}")
        if self.request_timeout > 300:
            raise ValueError(f"Request timeout seems too high ({self.request_timeout}s), maximum recommended is 300s")

        if not isinstance(self.retry_base_delay, (int, float)):
            raise ValueError(f"Retry base delay must be a number, got {type(self.retry_base_delay).__name__}")
        if self.retry_base_delay <= 0:
            raise ValueError(f"Retry base delay must be positive, got {self.retry_base_delay}")
        if self.retry_base_delay > 60:
            raise ValueError(f"Retry base delay seems too high ({self.retry_base_delay}s), maximum recommended is 60s")


@dataclass(frozen=True)
class BackoffConfig:
    """Exponential backoff strategy configuration."""

    initial_delay: float  # Initial delay in seconds
    max_delay: float  # Maximum delay in seconds
    multiplier: float  # Backoff multiplier
    jitter_factor: float  # Jitter factor (0.0-1.0)

    def __post_init__(self) -> None:
        """Validate backoff configuration values."""
        if not isinstance(self.initial_delay, (int, float)):
            raise ValueError(f"Initial delay must be a number, got {type(self.initial_delay).__name__}")
        if self.initial_delay <= 0:
            raise ValueError(f"Initial delay must be positive, got {self.initial_delay}")
        if self.initial_delay > 60:
            raise ValueError(f"Initial delay seems too high ({self.initial_delay}s), maximum recommended is 60s")

        if not isinstance(self.max_delay, (int, float)):
            raise ValueError(f"Max delay must be a number, got {type(self.max_delay).__name__}")
        if self.max_delay <= 0:
            raise ValueError(f"Max delay must be positive, got {self.max_delay}")
        if self.max_delay > 3600:
            raise ValueError(f"Max delay seems too high ({self.max_delay}s), maximum recommended is 3600s (1 hour)")
        if self.max_delay < self.initial_delay:
            raise ValueError(f"Max delay ({self.max_delay}) must be >= initial delay ({self.initial_delay})")

        if not isinstance(self.multiplier, (int, float)):
            raise ValueError(f"Multiplier must be a number, got {type(self.multiplier).__name__}")
        if self.multiplier <= 1.0:
            raise ValueError(f"Multiplier must be > 1.0, got {self.multiplier}")
        if self.multiplier > 10.0:
            raise ValueError(f"Multiplier seems too high ({self.multiplier}), maximum recommended is 10.0")

        if not isinstance(self.jitter_factor, (int, float)):
            raise ValueError(f"Jitter factor must be a number, got {type(self.jitter_factor).__name__}")
        if not 0.0 <= self.jitter_factor <= 1.0:
            raise ValueError(f"Jitter factor must be between 0.0 and 1.0, got {self.jitter_factor}")


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    verbose_cost_monitoring: bool
    performance_logging: bool
    level: str

    def __post_init__(self) -> None:
        """Validate logging configuration values."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level not in valid_levels:
            raise ValueError(f"Invalid log level '{self.level}'. Must be one of: {valid_levels}")


@dataclass(frozen=True)
class DatabaseConfig:
    """Database configuration."""

    default_path: str
    timeout: float  # Connection timeout in seconds
    wal_mode: bool  # Enable WAL mode

    def __post_init__(self) -> None:
        """Validate database configuration values."""
        if not self.default_path:
            raise ValueError("Database path cannot be empty")
        if self.timeout <= 0:
            raise ValueError("Database timeout must be positive")


@dataclass(frozen=True)
class AttachmentConfig:
    """Attachment download configuration."""

    auto_download: bool  # Automatically download attachment files
    concurrent_downloads: int = 3  # Number of parallel downloads (1-10)
    max_concurrent_downloads: int = 10  # Upper limit for validation

    def __post_init__(self) -> None:
        """Validate attachment configuration values."""
        if not isinstance(self.auto_download, bool):
            raise ValueError(f"auto_download must be a boolean, got {type(self.auto_download).__name__}")

        # Validate max_concurrent_downloads first (before using it in range check)
        if not isinstance(self.max_concurrent_downloads, int):
            raise ValueError(
                f"max_concurrent_downloads must be an integer, got {type(self.max_concurrent_downloads).__name__}"
            )
        if self.max_concurrent_downloads < 1:
            raise ValueError(
                f"max_concurrent_downloads must be at least 1, got {self.max_concurrent_downloads}"
            )

        # Validate concurrent_downloads (using validated max_concurrent_downloads)
        if not isinstance(self.concurrent_downloads, int):
            raise ValueError(
                f"concurrent_downloads must be an integer, got {type(self.concurrent_downloads).__name__}"
            )
        if not 1 <= self.concurrent_downloads <= self.max_concurrent_downloads:
            raise ValueError(
                f"concurrent_downloads must be between 1 and {self.max_concurrent_downloads}, "
                f"got {self.concurrent_downloads}"
            )


@dataclass(frozen=True)
class AppConfig:
    """Complete application configuration."""

    rate_limits: dict[str, RateLimitConfig]
    max_retries: int
    pagination: PaginationConfig
    delays: DelayConfig
    backoff: BackoffConfig
    logging: LoggingConfig
    database: DatabaseConfig
    attachments: AttachmentConfig

    def __post_init__(self) -> None:
        """Validate application configuration."""
        # Validate max_retries with reasonable bounds
        if not isinstance(self.max_retries, int):
            raise ValueError(f"max_retries must be an integer, got {type(self.max_retries).__name__}")
        if not 1 <= self.max_retries <= 100:
            raise ValueError(
                f"max_retries must be between 1 and 100, got {self.max_retries}. "
                "Very high values may cause excessive delays during rate limiting."
            )

        required_rate_limit_levels = {"conservative", "moderate", "aggressive"}
        if not required_rate_limit_levels.issubset(self.rate_limits.keys()):
            missing = required_rate_limit_levels - self.rate_limits.keys()
            raise ValueError(f"Missing required rate limit levels: {missing}")
