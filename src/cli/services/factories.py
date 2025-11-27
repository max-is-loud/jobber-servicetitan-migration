"""Service factory for dependency injection and service creation.

This module implements factory patterns for creating and managing
service dependencies used across CLI commands.
"""

import sqlite3
import atexit
from pathlib import Path
from typing import Optional

from src.auth import AuthProvider, OAuth2Manager
from src.clients import HttpClient, JobberClient
from src.config import ConfigManagerImpl
from src.interfaces import Logger
from src.loggers.rich_logger import RichLogger
from src.mappers import EntityMapper
from src.rate_limiting import (
    ExponentialBackoffStrategy,
    MetricsCollector,
    RateLimitedHttpClient,
    TokenBucketRateLimiter,
)
from src.repositories import Repository
from .shared import SharedServices


class ServiceFactory:
    """Factory class for creating and configuring services with dependency injection.

    This factory centralizes the creation of commonly used services like Repository,
    OAuth2Manager, and HttpClient to eliminate duplication across CLI commands.
    """

    @staticmethod
    def create_repository(db: Optional[Path] = None) -> Repository:
        """Create Repository with database connection and initialize schema.

        Args:
            db: Optional database path, defaults to SharedServices.DEFAULT_DB_PATH

        Returns:
            Repository: Configured repository with initialized schema
        """
        db_path = SharedServices.resolve_db_path(db)

        # Ensure parent directories exist
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create database connection
        connection = sqlite3.Connection(str(db_path))
        repository = Repository(connection)

        # Initialize schema including oauth_tokens table
        repository.init_schema()
        atexit.register(repository.close)

        return repository

    @staticmethod
    def create_oauth2_manager() -> OAuth2Manager:
        """Create OAuth2Manager with configuration from environment.

        Returns:
            OAuth2Manager: Configured OAuth2Manager with environment config
        """
        client_id, client_secret, redirect_uri = AuthProvider.get_oauth2_config()
        http_client = ServiceFactory.create_http_client()

        return OAuth2Manager(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            http_client=http_client,
        )

    @staticmethod
    def create_http_client() -> HttpClient:
        """Create HttpClient instance.

        Returns:
            HttpClient: Basic HTTP client instance
        """
        return HttpClient()

    @staticmethod
    def get_console():
        """Get shared console instance.

        Returns:
            Console: Shared Rich console for output
        """
        return SharedServices.get_console()

    @staticmethod
    def create_rate_limited_jobber_client(
        auth_provider: AuthProvider,
        repository: Repository,
        config_manager: ConfigManagerImpl,
        optimization_level: str = "moderate",
        enable_cost_monitoring: bool = True,
    ) -> JobberClient:
        """Create JobberClient with rate limiting and cost monitoring configured.

        This factory method centralizes the setup of rate-limited JobberClient instances,
        eliminating code duplication across CLI commands. The returned client has a
        shared TokenBucketRateLimiter that controls request flow across all extractors
        that use this client instance.

        Rate Limiting Architecture:
        - Creates a single TokenBucketRateLimiter with configured capacity and refill rate
        - Wraps base HttpClient with RateLimitedHttpClient for transparent rate limiting
        - Injects rate-limited client into JobberClient via set_http_client()
        - All extractors sharing this JobberClient share the same rate limiter

        Optimization Levels (from config/settings.yaml):
        - conservative: 250 capacity, 240/min (4 req/s), 52% safety margin
        - moderate: 600 capacity, 600/min (10 req/s), 28% safety margin (default)
        - aggressive: 500 capacity, 480/min (8 req/s), 4% safety margin

        Args:
            auth_provider: Authentication provider for API access and OAuth token refresh
            repository: Repository for metrics storage and OAuth token persistence
            config_manager: Configuration manager for rate limit and backoff settings
            optimization_level: Rate limiting optimization level - one of:
                              'conservative', 'moderate', 'aggressive'
                              (default: 'moderate')
            enable_cost_monitoring: Whether to enable GraphQL cost tracking and metrics
                                   collection (default: True)

        Returns:
            JobberClient: Fully configured client with rate limiting, backoff strategy,
                         and optional cost monitoring enabled

        Example:
            >>> auth_provider = AuthProvider(oauth_manager, repository)
            >>> config_manager = ConfigManagerImpl()
            >>> client = ServiceFactory.create_rate_limited_jobber_client(
            ...     auth_provider=auth_provider,
            ...     repository=repository,
            ...     config_manager=config_manager,
            ...     optimization_level="moderate",
            ...     enable_cost_monitoring=True
            ... )
        """
        # Create metrics collector if cost monitoring is enabled
        metrics_collector = MetricsCollector(repository=repository) if enable_cost_monitoring else None

        # Create base JobberClient with optional metrics collection
        jobber_client = JobberClient(
            auth_provider,
            metrics_collector=metrics_collector,
            config_manager=config_manager,
        )

        # Get rate limiting configuration based on optimization level
        rate_config = config_manager.get_rate_limit_config(optimization_level)
        capacity = rate_config["capacity"]
        refill_rate = rate_config["refill_rate"]
        initial_tokens = rate_config["initial_tokens"]

        # Create token bucket rate limiter with configured parameters
        rate_limiter = TokenBucketRateLimiter(capacity=capacity, refill_rate=refill_rate, initial_tokens=initial_tokens)

        # Get exponential backoff configuration for retry logic
        backoff_config = config_manager.get_backoff_config()
        backoff_strategy = ExponentialBackoffStrategy(
            initial_delay=backoff_config["initial_delay"],
            max_delay=backoff_config["max_delay"],
            multiplier=backoff_config["multiplier"],
            jitter_factor=backoff_config["jitter_factor"],
        )

        # Create rate-limited HTTP client wrapper
        # Max retries configurable via settings.yaml (default: 15)
        max_retries = config_manager.get_max_retries()
        rate_limited_client = RateLimitedHttpClient(
            HttpClient(),
            rate_limiter,
            backoff_strategy,
            max_retries=max_retries,
            metrics_collector=metrics_collector,
            auth_provider=auth_provider,  # Enable reactive OAuth token refresh on 401 errors
        )

        # Inject rate-limited client into JobberClient
        jobber_client.set_http_client(rate_limited_client)

        return jobber_client

    @staticmethod
    def create_auth_provider(repository: Repository, logger: Optional[Logger] = None) -> AuthProvider:
        """Create AuthProvider with OAuth2Manager and repository.

        Args:
            repository: Repository for OAuth token persistence
            logger: Optional logger for auth operations (currently unused)

        Returns:
            AuthProvider: Configured authentication provider
        """
        oauth_manager = ServiceFactory.create_oauth2_manager()
        return AuthProvider(oauth_manager, repository)

    @staticmethod
    def create_entity_mapper() -> EntityMapper:
        """Create EntityMapper for transforming GraphQL data to domain models.

        Returns:
            EntityMapper: Configured entity mapper instance
        """
        return EntityMapper()

    @staticmethod
    def create_logger(verbose: bool = False) -> RichLogger:
        """Create RichLogger with shared console.

        Args:
            verbose: Enable verbose logging

        Returns:
            RichLogger: Configured logger instance
        """
        return RichLogger(verbose=verbose, console=ServiceFactory.get_console())

    @staticmethod
    def create_config_manager() -> ConfigManagerImpl:
        """Create ConfigManager for application settings.

        Returns:
            ConfigManagerImpl: Configured config manager instance
        """
        return ConfigManagerImpl()
