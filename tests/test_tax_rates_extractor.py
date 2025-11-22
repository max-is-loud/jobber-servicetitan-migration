import pytest
from unittest.mock import Mock, MagicMock
from src.extractors.tax_rates_extractor import TaxRatesExtractor
from src.clients import JobberClient
from src.mappers import EntityMapper
from src.repositories import Repository
from src.interfaces import Logger
from src.config import ConfigManagerImpl


class TestTaxRatesExtractor:
    """Test suite for TaxRatesExtractor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)
        self.mock_config_manager = Mock(spec=ConfigManagerImpl)

    def test_init_with_kwargs(self):
        """Test initialization with skip_existing_entities and config_manager."""
        extractor = TaxRatesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
            config_manager=self.mock_config_manager,
            skip_existing_entities=True,
            some_other_kwarg="test",
        )

        assert extractor._jobber_client == self.mock_client
        assert extractor._entity_mapper == self.mock_mapper
        assert extractor._repository == self.mock_repository
        assert extractor._logger == self.mock_logger
        assert extractor._config_manager == self.mock_config_manager
        assert extractor._skip_existing_entities is True
        assert extractor._entity_name == "tax rate"

    def test_init_defaults(self):
        """Test initialization with default values."""
        extractor = TaxRatesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger,
        )

        assert extractor._skip_existing_entities is False
        # Config manager should be created if not provided, but we can't easily check it's a new instance without mocking the class
        assert extractor._config_manager is not None
