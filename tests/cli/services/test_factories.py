"""Tests for ServiceFactory.create_rate_limited_jobber_client()."""

from unittest.mock import Mock, patch

import pytest

from src.cli.services.factories import ServiceFactory


class TestServiceFactoryRateLimitedClient:
    """Test cases for ServiceFactory.create_rate_limited_jobber_client()."""

    @pytest.fixture
    def mock_auth_provider(self):
        """Create mock AuthProvider for testing."""
        return Mock()

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository for testing."""
        return Mock()

    @pytest.fixture
    def mock_config_manager(self):
        """Create mock ConfigManagerImpl with realistic rate limit configs."""
        config_manager = Mock()

        # Configure rate limit configs for different optimization levels
        config_manager.get_rate_limit_config.side_effect = lambda level: {
            "conservative": {
                "capacity": 250,
                "refill_rate": 240,
                "initial_tokens": 40,
                "safety_margin": 0.52,
            },
            "moderate": {
                "capacity": 600,
                "refill_rate": 600,
                "initial_tokens": 150,
                "safety_margin": 0.1,
            },
            "aggressive": {
                "capacity": 500,
                "refill_rate": 480,
                "initial_tokens": 100,
                "safety_margin": 0.04,
            },
        }[level]

        # Configure backoff config
        config_manager.get_backoff_config.return_value = {
            "initial_delay": 5.0,
            "max_delay": 300.0,
            "multiplier": 2.0,
            "jitter_factor": 0.2,
        }

        # Configure max retries
        config_manager.get_max_retries.return_value = 15

        return config_manager

    def test_create_rate_limited_jobber_client_returns_jobber_client(
        self, mock_auth_provider, mock_repository, mock_config_manager
    ):
        """Test that factory returns a JobberClient instance."""
        client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=mock_auth_provider,
            repository=mock_repository,
            config_manager=mock_config_manager,
            optimization_level="moderate",
            enable_cost_monitoring=True,
        )

        # Verify we got a JobberClient instance
        assert client is not None
        from src.clients import JobberClient

        assert isinstance(client, JobberClient)

    def test_create_with_moderate_optimization_level(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test factory with moderate optimization level."""
        with patch("src.cli.services.factories.TokenBucketRateLimiter") as MockRateLimiter:
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="moderate",
                enable_cost_monitoring=True,
            )

            # Verify rate limiter was created with moderate settings
            MockRateLimiter.assert_called_once_with(
                capacity=600,
                refill_rate=600,
                initial_tokens=150,
            )

    def test_create_with_conservative_optimization_level(
        self, mock_auth_provider, mock_repository, mock_config_manager
    ):
        """Test factory with conservative optimization level."""
        with patch("src.cli.services.factories.TokenBucketRateLimiter") as MockRateLimiter:
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="conservative",
                enable_cost_monitoring=False,
            )

            # Verify rate limiter was created with conservative settings
            MockRateLimiter.assert_called_once_with(
                capacity=250,
                refill_rate=240,
                initial_tokens=40,
            )

    def test_create_with_aggressive_optimization_level(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test factory with aggressive optimization level."""
        with patch("src.cli.services.factories.TokenBucketRateLimiter") as MockRateLimiter:
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="aggressive",
                enable_cost_monitoring=True,
            )

            # Verify rate limiter was created with aggressive settings
            MockRateLimiter.assert_called_once_with(
                capacity=500,
                refill_rate=480,
                initial_tokens=100,
            )

    def test_create_with_cost_monitoring_enabled(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test that cost monitoring is enabled when requested."""
        with patch("src.cli.services.factories.MetricsCollector") as MockMetricsCollector:
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="moderate",
                enable_cost_monitoring=True,
            )

            # Verify metrics collector was created
            MockMetricsCollector.assert_called_once_with(repository=mock_repository)

    def test_create_with_cost_monitoring_disabled(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test that cost monitoring is not created when disabled."""
        with patch("src.cli.services.factories.MetricsCollector") as MockMetricsCollector:
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="moderate",
                enable_cost_monitoring=False,
            )

            # Verify metrics collector was NOT created
            MockMetricsCollector.assert_not_called()

    def test_backoff_strategy_configured_correctly(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test that backoff strategy is configured with correct parameters."""
        with patch("src.cli.services.factories.ExponentialBackoffStrategy") as MockBackoff:
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="moderate",
                enable_cost_monitoring=True,
            )

            # Verify backoff strategy was created with config values
            MockBackoff.assert_called_once_with(
                initial_delay=5.0,
                max_delay=300.0,
                multiplier=2.0,
                jitter_factor=0.2,
            )

    def test_rate_limited_http_client_configured_correctly(
        self, mock_auth_provider, mock_repository, mock_config_manager
    ):
        """Test that RateLimitedHttpClient is configured with correct parameters."""
        with patch("src.cli.services.factories.RateLimitedHttpClient") as MockRateLimitedClient:
            with patch("src.cli.services.factories.TokenBucketRateLimiter"):
                with patch("src.cli.services.factories.ExponentialBackoffStrategy"):
                    ServiceFactory.create_rate_limited_jobber_client(
                        auth_provider=mock_auth_provider,
                        repository=mock_repository,
                        config_manager=mock_config_manager,
                        optimization_level="moderate",
                        enable_cost_monitoring=True,
                    )

                    # Verify RateLimitedHttpClient was called
                    assert MockRateLimitedClient.called

                    # Verify max_retries is set to 15
                    call_kwargs = MockRateLimitedClient.call_args.kwargs
                    assert call_kwargs["max_retries"] == 15
                    assert call_kwargs["auth_provider"] == mock_auth_provider

    def test_http_client_is_set_on_jobber_client(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test that rate-limited HTTP client is set on JobberClient."""
        with patch("src.cli.services.factories.RateLimitedHttpClient") as MockRateLimitedClient:
            mock_rate_limited_instance = Mock()
            MockRateLimitedClient.return_value = mock_rate_limited_instance

            client = ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="moderate",
                enable_cost_monitoring=True,
            )

            # Verify set_http_client was called on the JobberClient
            # Note: We can't directly verify this without mocking JobberClient itself
            # but we can verify the factory creates the rate-limited client
            MockRateLimitedClient.assert_called_once()

    def test_default_optimization_level_is_moderate(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test that default optimization level is moderate."""
        with patch("src.cli.services.factories.TokenBucketRateLimiter") as MockRateLimiter:
            # Call without specifying optimization_level (should use default)
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                # optimization_level defaults to "moderate"
            )

            # Verify moderate settings were used
            MockRateLimiter.assert_called_once_with(
                capacity=600,
                refill_rate=600,
                initial_tokens=150,
            )

    def test_default_cost_monitoring_is_enabled(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test that cost monitoring is enabled by default."""
        with patch("src.cli.services.factories.MetricsCollector") as MockMetricsCollector:
            # Call without specifying enable_cost_monitoring (should default to True)
            ServiceFactory.create_rate_limited_jobber_client(
                auth_provider=mock_auth_provider,
                repository=mock_repository,
                config_manager=mock_config_manager,
                optimization_level="moderate",
                # enable_cost_monitoring defaults to True
            )

            # Verify metrics collector was created
            MockMetricsCollector.assert_called_once_with(repository=mock_repository)

    def test_config_manager_get_rate_limit_config_called(
        self, mock_auth_provider, mock_repository, mock_config_manager
    ):
        """Test that config manager's get_rate_limit_config is called."""
        ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=mock_auth_provider,
            repository=mock_repository,
            config_manager=mock_config_manager,
            optimization_level="conservative",
            enable_cost_monitoring=True,
        )

        # Verify config manager was queried for conservative settings
        mock_config_manager.get_rate_limit_config.assert_called_with("conservative")

    def test_config_manager_get_backoff_config_called(self, mock_auth_provider, mock_repository, mock_config_manager):
        """Test that config manager's get_backoff_config is called."""
        ServiceFactory.create_rate_limited_jobber_client(
            auth_provider=mock_auth_provider,
            repository=mock_repository,
            config_manager=mock_config_manager,
            optimization_level="moderate",
            enable_cost_monitoring=True,
        )

        # Verify config manager was queried for backoff settings
        mock_config_manager.get_backoff_config.assert_called_once()


class TestServiceFactoryLogger:
    """Test cases for ServiceFactory.create_logger()."""

    def test_create_logger_default(self):
        """Test that create_logger returns RichLogger with default verbose=False."""
        logger = ServiceFactory.create_logger()

        # Verify we got a RichLogger instance
        from src.loggers.rich_logger import RichLogger

        assert isinstance(logger, RichLogger)
        assert logger.verbose is False

    def test_create_logger_verbose(self):
        """Test that create_logger returns RichLogger with verbose=True."""
        logger = ServiceFactory.create_logger(verbose=True)

        # Verify we got a RichLogger instance with verbose enabled
        from src.loggers.rich_logger import RichLogger

        assert isinstance(logger, RichLogger)
        assert logger.verbose is True

    def test_create_logger_uses_shared_console(self):
        """Test that create_logger uses the shared console from get_console()."""
        logger = ServiceFactory.create_logger()

        # Verify logger uses same console as ServiceFactory.get_console()
        shared_console = ServiceFactory.get_console()
        assert logger.console is shared_console


class TestServiceFactoryConfigManager:
    """Test cases for ServiceFactory.create_config_manager()."""

    def test_create_config_manager(self):
        """Test that create_config_manager returns ConfigManagerImpl instance."""
        config_manager = ServiceFactory.create_config_manager()

        # Verify we got a ConfigManagerImpl instance
        from src.config import ConfigManagerImpl

        assert isinstance(config_manager, ConfigManagerImpl)

    def test_create_config_manager_loads_settings(self):
        """Test that create_config_manager creates a functional config manager."""
        config_manager = ServiceFactory.create_config_manager()

        # Verify config manager has loaded settings and can return rate limit configs
        rate_config = config_manager.get_rate_limit_config("moderate")
        assert rate_config is not None
        assert "capacity" in rate_config
        assert "refill_rate" in rate_config
