"""Unit tests for map mode extractors."""

import json
from unittest.mock import Mock, MagicMock, patch, call
import pytest

from src.extractors.map_mode.base_map_extractor import BaseMapExtractor
from src.extractors.map_mode import (
    ClientsMapExtractor,
    InvoicesMapExtractor,
    QuotesMapExtractor,
    JobsMapExtractor,
    PropertiesMapExtractor,
)
from src.clients import JobberClient
from src.interfaces import Logger
from src.models import EntityInventory
from src.repositories import Repository
from src.exceptions import JobberApiError


class TestBaseMapExtractor:
    """Test suite for BaseMapExtractor abstract base class."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        return logger

    def test_base_map_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test BaseMapExtractor initializes with correct dependencies."""

        class ConcreteExtractor(BaseMapExtractor):
            def _fetch_page(self, cursor=None):
                return {}

            def _extract_edges_and_page_info(self, response):
                return [], {}

            def _map_entity(self, node):
                return Mock()

        extractor = ConcreteExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snapshot_123",
            entity_type_name="test_entities",
        )

        assert extractor._jobber_client == mock_jobber_client
        assert extractor._repository == mock_repository
        assert extractor._logger == mock_logger
        assert extractor._map_snapshot_id == "snapshot_123"
        assert extractor._entity_type_name == "test_entities"
        assert extractor._total_entities == 0
        assert extractor._total_pages == 0

    def test_save_entities_calls_repository(self, mock_jobber_client, mock_repository, mock_logger):
        """Test _save_entities calls repository.save_entity_inventory."""

        class ConcreteExtractor(BaseMapExtractor):
            def _fetch_page(self, cursor=None):
                return {}

            def _extract_edges_and_page_info(self, response):
                return [], {}

            def _map_entity(self, node):
                return Mock()

        extractor = ConcreteExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snapshot_123",
            entity_type_name="test_entities",
        )

        entities = [Mock(), Mock()]
        extractor._save_entities(entities)

        mock_repository.save_entity_inventory.assert_called_once_with(entities)


class TestClientsMapExtractor:
    """Test suite for ClientsMapExtractor."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        return logger

    @pytest.fixture
    def clients_extractor(self, mock_jobber_client, mock_repository, mock_logger):
        """Create ClientsMapExtractor instance."""
        return ClientsMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snapshot_abc",
        )

    def test_clients_extractor_initialization(self, clients_extractor):
        """Test ClientsMapExtractor initializes with correct entity type."""
        assert clients_extractor._entity_type_name == "clients"

    def test_fetch_page_calls_jobber_client(self, clients_extractor, mock_jobber_client):
        """Test _fetch_page calls jobber_client.fetch_clients_map."""
        mock_jobber_client.fetch_clients_map.return_value = {"data": {"clients": {}}}

        result = clients_extractor._fetch_page(cursor="cursor_123")

        mock_jobber_client.fetch_clients_map.assert_called_once_with("cursor_123")
        assert result == {"data": {"clients": {}}}

    def test_extract_edges_and_page_info(self, clients_extractor):
        """Test _extract_edges_and_page_info extracts correct data."""
        response = {
            "data": {
                "clients": {
                    "edges": [{"node": {"id": "1"}}, {"node": {"id": "2"}}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_xyz"},
                }
            }
        }

        edges, page_info = clients_extractor._extract_edges_and_page_info(response)

        assert len(edges) == 2
        assert edges[0]["node"]["id"] == "1"
        assert page_info["hasNextPage"] is True
        assert page_info["endCursor"] == "cursor_xyz"

    def test_map_entity_creates_entity_inventory(self, clients_extractor):
        """Test _map_entity creates EntityInventory with correct relation counts."""
        node = {
            "id": "client_123",
            "updatedAt": "2023-11-15T10:00:00Z",
            "notes": {"totalCount": 5},
            "noteAttachments": {"totalCount": 3},
        }

        with patch.object(clients_extractor, "_get_current_timestamp", return_value="2023-11-16T10:00:00Z"):
            inventory = clients_extractor._map_entity(node)

        assert isinstance(inventory, EntityInventory)
        assert inventory.entity_type == "clients"
        assert inventory.entity_id == "client_123"
        assert inventory.map_snapshot_id == "snapshot_abc"
        assert inventory.updated_at == "2023-11-15T10:00:00Z"
        assert inventory.discovered_at == "2023-11-16T10:00:00Z"

        relations = json.loads(inventory.estimated_relations_json)
        assert relations["notes"] == 5
        assert relations["attachments"] == 3

    def test_extract_single_page(self, clients_extractor, mock_jobber_client, mock_repository):
        """Test extract() with single page of results."""
        mock_response = {
            "data": {
                "clients": {
                    "edges": [
                        {
                            "node": {
                                "id": "client_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 2},
                                "noteAttachments": {"totalCount": 1},
                            }
                        },
                        {
                            "node": {
                                "id": "client_2",
                                "updatedAt": "2023-11-16T10:00:00Z",
                                "notes": {"totalCount": 0},
                                "noteAttachments": {"totalCount": 0},
                            }
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        mock_jobber_client.fetch_clients_map.return_value = mock_response

        result = clients_extractor.extract()

        assert result["total_entities"] == 2
        assert result["total_pages"] == 1
        assert result["entity_type"] == "clients"

        # Verify repository was called to save entities
        mock_repository.save_entity_inventory.assert_called_once()
        saved_entities = mock_repository.save_entity_inventory.call_args[0][0]
        assert len(saved_entities) == 2

    def test_extract_multiple_pages(self, clients_extractor, mock_jobber_client, mock_repository):
        """Test extract() with pagination across multiple pages."""
        # First page
        page1_response = {
            "data": {
                "clients": {
                    "edges": [
                        {
                            "node": {
                                "id": "client_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 1},
                                "noteAttachments": {"totalCount": 0},
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_1"},
                }
            }
        }

        # Second page
        page2_response = {
            "data": {
                "clients": {
                    "edges": [
                        {
                            "node": {
                                "id": "client_2",
                                "updatedAt": "2023-11-16T10:00:00Z",
                                "notes": {"totalCount": 2},
                                "noteAttachments": {"totalCount": 1},
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        mock_jobber_client.fetch_clients_map.side_effect = [page1_response, page2_response]

        result = clients_extractor.extract()

        assert result["total_entities"] == 2
        assert result["total_pages"] == 2
        assert mock_jobber_client.fetch_clients_map.call_count == 2

        # Verify repository was called for each page
        assert mock_repository.save_entity_inventory.call_count == 2

    def test_extract_empty_page(self, clients_extractor, mock_jobber_client, mock_repository):
        """Test extract() handles empty page correctly."""
        mock_response = {
            "data": {
                "clients": {
                    "edges": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        mock_jobber_client.fetch_clients_map.return_value = mock_response

        result = clients_extractor.extract()

        assert result["total_entities"] == 0
        assert result["total_pages"] == 1

        # Repository should not be called when no entities
        mock_repository.save_entity_inventory.assert_not_called()


class TestQuotesMapExtractor:
    """Test suite for QuotesMapExtractor."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        return logger

    @pytest.fixture
    def quotes_extractor(self, mock_jobber_client, mock_repository, mock_logger):
        """Create QuotesMapExtractor instance."""
        return QuotesMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snapshot_xyz",
        )

    def test_quotes_extractor_initialization(self, quotes_extractor):
        """Test QuotesMapExtractor initializes with correct entity type."""
        assert quotes_extractor._entity_type_name == "quotes"

    def test_map_entity_includes_line_items_count(self, quotes_extractor):
        """Test _map_entity includes lineItems count in relations."""
        node = {
            "id": "quote_123",
            "updatedAt": "2023-11-15T10:00:00Z",
            "lineItems": {"totalCount": 10},
            "notes": {"totalCount": 2},
            "noteAttachments": {"totalCount": 1},
        }

        with patch.object(quotes_extractor, "_get_current_timestamp", return_value="2023-11-16T10:00:00Z"):
            inventory = quotes_extractor._map_entity(node)

        relations = json.loads(inventory.estimated_relations_json)
        assert relations["line_items"] == 10
        assert relations["notes"] == 2
        assert relations["attachments"] == 1


class TestJobsMapExtractor:
    """Test suite for JobsMapExtractor."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        return logger

    @pytest.fixture
    def jobs_extractor(self, mock_jobber_client, mock_repository, mock_logger):
        """Create JobsMapExtractor instance."""
        return JobsMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snapshot_jobs",
        )

    def test_jobs_extractor_initialization(self, jobs_extractor):
        """Test JobsMapExtractor initializes with correct entity type."""
        assert jobs_extractor._entity_type_name == "jobs"

    def test_fetch_page_calls_correct_method(self, jobs_extractor, mock_jobber_client):
        """Test _fetch_page calls jobber_client.fetch_jobs_map."""
        mock_jobber_client.fetch_jobs_map.return_value = {"data": {"jobs": {}}}

        result = jobs_extractor._fetch_page(cursor="cursor_jobs")

        mock_jobber_client.fetch_jobs_map.assert_called_once_with("cursor_jobs")


class TestInvoicesMapExtractor:
    """Test suite for InvoicesMapExtractor."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        return logger

    @pytest.fixture
    def invoices_extractor(self, mock_jobber_client, mock_repository, mock_logger):
        """Create InvoicesMapExtractor instance."""
        return InvoicesMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snapshot_inv",
        )

    def test_invoices_extractor_initialization(self, invoices_extractor):
        """Test InvoicesMapExtractor initializes with correct entity type."""
        assert invoices_extractor._entity_type_name == "invoices"


class TestPropertiesMapExtractor:
    """Test suite for PropertiesMapExtractor."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository."""
        return Mock(spec=Repository)

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        return logger

    @pytest.fixture
    def properties_extractor(self, mock_jobber_client, mock_repository, mock_logger):
        """Create PropertiesMapExtractor instance."""
        return PropertiesMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snapshot_prop",
        )

    def test_properties_extractor_initialization(self, properties_extractor):
        """Test PropertiesMapExtractor initializes with correct entity type."""
        assert properties_extractor._entity_type_name == "properties"
