"""Unit tests for extended map mode extractors."""

import json
from unittest.mock import Mock, patch
import pytest

from src.extractors.map_mode import (
    ExpensesMapExtractor,
    RequestsMapExtractor,
    UsersMapExtractor,
    VisitsMapExtractor,
    TimesheetEntriesMapExtractor,
    ProductsServicesMapExtractor,
    TaxRatesMapExtractor,
)
from src.clients import JobberClient
from src.interfaces import Logger
from src.models import EntityInventory
from src.repositories import Repository


class TestExtendedMapExtractors:
    """Test suite for extended map mode extractors."""

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

    # Expenses Tests
    def test_expenses_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test ExpensesMapExtractor initializes correctly."""
        extractor = ExpensesMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snap_exp",
        )
        assert extractor._entity_type_name == "expenses"

    def test_expenses_fetch_page(self, mock_jobber_client, mock_repository, mock_logger):
        """Test ExpensesMapExtractor calls correct client method."""
        extractor = ExpensesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_exp")
        mock_jobber_client.fetch_expenses_map.return_value = {"data": {"expenses": {}}}

        extractor._fetch_page(cursor="cursor_1")
        mock_jobber_client.fetch_expenses_map.assert_called_once_with("cursor_1", None)

    def test_expenses_map_entity(self, mock_jobber_client, mock_repository, mock_logger):
        """Test ExpensesMapExtractor maps entity correctly."""
        extractor = ExpensesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_exp")
        node = {
            "id": "exp_1",
            "updatedAt": "2023-01-01T00:00:00Z",
            "notes": {"totalCount": 2},
            "noteAttachments": {"totalCount": 1},
        }

        with patch.object(extractor, "_get_current_timestamp", return_value="2023-01-02T00:00:00Z"):
            inventory = extractor._map_entity(node)

        assert inventory.entity_type == "expenses"
        assert inventory.entity_id == "exp_1"
        relations = json.loads(inventory.estimated_relations_json)
        assert relations["notes"] == 2
        assert relations["attachments"] == 1

    # Requests Tests
    def test_requests_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test RequestsMapExtractor initializes correctly."""
        extractor = RequestsMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snap_req",
        )
        assert extractor._entity_type_name == "requests"

    def test_requests_fetch_page(self, mock_jobber_client, mock_repository, mock_logger):
        """Test RequestsMapExtractor calls correct client method."""
        extractor = RequestsMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_req")
        mock_jobber_client.fetch_requests_map.return_value = {"data": {"requests": {}}}

        extractor._fetch_page(cursor="cursor_1")
        mock_jobber_client.fetch_requests_map.assert_called_once_with("cursor_1", None)

    def test_requests_map_entity(self, mock_jobber_client, mock_repository, mock_logger):
        """Test RequestsMapExtractor maps entity correctly."""
        extractor = RequestsMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_req")
        node = {
            "id": "req_1",
            "updatedAt": "2023-01-01T00:00:00Z",
            "notes": {"totalCount": 5},
            "noteAttachments": {"totalCount": 0},
        }

        with patch.object(extractor, "_get_current_timestamp", return_value="2023-01-02T00:00:00Z"):
            inventory = extractor._map_entity(node)

        assert inventory.entity_type == "requests"
        relations = json.loads(inventory.estimated_relations_json)
        assert relations["notes"] == 5

    # Users Tests
    def test_users_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test UsersMapExtractor initializes correctly."""
        extractor = UsersMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snap_user",
        )
        assert extractor._entity_type_name == "users"

    def test_users_fetch_page(self, mock_jobber_client, mock_repository, mock_logger):
        """Test UsersMapExtractor calls correct client method."""
        extractor = UsersMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_user")
        mock_jobber_client.fetch_users_map.return_value = {"data": {"users": {}}}

        extractor._fetch_page(cursor="cursor_1")
        mock_jobber_client.fetch_users_map.assert_called_once_with("cursor_1", None)

    def test_users_map_entity(self, mock_jobber_client, mock_repository, mock_logger):
        """Test UsersMapExtractor maps entity correctly (no relations)."""
        extractor = UsersMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_user")
        node = {"id": "user_1", "updatedAt": "2023-01-01T00:00:00Z"}

        with patch.object(extractor, "_get_current_timestamp", return_value="2023-01-02T00:00:00Z"):
            inventory = extractor._map_entity(node)

        assert inventory.entity_type == "users"
        relations = json.loads(inventory.estimated_relations_json)
        assert relations == {}  # Users typically don't have relations in map mode

    # Visits Tests
    def test_visits_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test VisitsMapExtractor initializes correctly."""
        extractor = VisitsMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snap_visit",
        )
        assert extractor._entity_type_name == "visits"

    def test_visits_fetch_page(self, mock_jobber_client, mock_repository, mock_logger):
        """Test VisitsMapExtractor calls correct client method."""
        extractor = VisitsMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_visit")
        mock_jobber_client.fetch_visits_map.return_value = {"data": {"visits": {}}}

        extractor._fetch_page(cursor="cursor_1")
        mock_jobber_client.fetch_visits_map.assert_called_once_with("cursor_1", None)

    def test_visits_map_entity(self, mock_jobber_client, mock_repository, mock_logger):
        """Test VisitsMapExtractor maps entity correctly."""
        extractor = VisitsMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_visit")
        node = {
            "id": "visit_1",
            "updatedAt": "2023-01-01T00:00:00Z",
            "notes": {"totalCount": 1},
            "noteAttachments": {"totalCount": 1},
        }

        with patch.object(extractor, "_get_current_timestamp", return_value="2023-01-02T00:00:00Z"):
            inventory = extractor._map_entity(node)

        assert inventory.entity_type == "visits"
        relations = json.loads(inventory.estimated_relations_json)
        assert relations["notes"] == 1
        assert relations["attachments"] == 1

    # TimesheetEntries Tests
    def test_timesheet_entries_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test TimesheetEntriesMapExtractor initializes correctly."""
        extractor = TimesheetEntriesMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snap_ts",
        )
        assert extractor._entity_type_name == "timesheetEntries"

    def test_timesheet_entries_fetch_page(self, mock_jobber_client, mock_repository, mock_logger):
        """Test TimesheetEntriesMapExtractor calls correct client method."""
        extractor = TimesheetEntriesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_ts")
        mock_jobber_client.fetch_timesheet_entries_map.return_value = {"data": {"timeSheetEntries": {}}}

        extractor._fetch_page(cursor="cursor_1")
        mock_jobber_client.fetch_timesheet_entries_map.assert_called_once_with("cursor_1", None)

    def test_timesheet_entries_map_entity(self, mock_jobber_client, mock_repository, mock_logger):
        """Test TimesheetEntriesMapExtractor maps entity correctly."""
        extractor = TimesheetEntriesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_ts")
        node = {
            "id": "ts_1",
            "updatedAt": "2023-01-01T00:00:00Z",
            "notes": {"totalCount": 0},
            "noteAttachments": {"totalCount": 0},
        }

        with patch.object(extractor, "_get_current_timestamp", return_value="2023-01-02T00:00:00Z"):
            inventory = extractor._map_entity(node)

        assert inventory.entity_type == "timesheetEntries"

    # ProductsServices Tests
    def test_products_services_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test ProductsServicesMapExtractor initializes correctly."""
        extractor = ProductsServicesMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snap_prod",
        )
        assert extractor._entity_type_name == "productsAndServices"

    def test_products_services_fetch_page(self, mock_jobber_client, mock_repository, mock_logger):
        """Test ProductsServicesMapExtractor calls correct client method."""
        extractor = ProductsServicesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_prod")
        mock_jobber_client.fetch_products_services_map.return_value = {"data": {"productOrServices": {}}}

        extractor._fetch_page(cursor="cursor_1")
        mock_jobber_client.fetch_products_services_map.assert_called_once_with("cursor_1", None)

    def test_products_services_map_entity(self, mock_jobber_client, mock_repository, mock_logger):
        """Test ProductsServicesMapExtractor maps entity correctly."""
        extractor = ProductsServicesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_prod")
        node = {"id": "prod_1", "updatedAt": "2023-01-01T00:00:00Z"}

        with patch.object(extractor, "_get_current_timestamp", return_value="2023-01-02T00:00:00Z"):
            inventory = extractor._map_entity(node)

        assert inventory.entity_type == "productsAndServices"

    # TaxRates Tests
    def test_tax_rates_extractor_initialization(self, mock_jobber_client, mock_repository, mock_logger):
        """Test TaxRatesMapExtractor initializes correctly."""
        extractor = TaxRatesMapExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            map_snapshot_id="snap_tax",
        )
        assert extractor._entity_type_name == "taxRates"

    def test_tax_rates_fetch_page(self, mock_jobber_client, mock_repository, mock_logger):
        """Test TaxRatesMapExtractor calls correct client method."""
        extractor = TaxRatesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_tax")
        mock_jobber_client.fetch_tax_rates_map.return_value = {"data": {"taxRates": {}}}

        extractor._fetch_page(cursor="cursor_1")
        mock_jobber_client.fetch_tax_rates_map.assert_called_once_with("cursor_1", None)

    def test_tax_rates_map_entity(self, mock_jobber_client, mock_repository, mock_logger):
        """Test TaxRatesMapExtractor maps entity correctly."""
        extractor = TaxRatesMapExtractor(mock_jobber_client, mock_repository, mock_logger, "snap_tax")
        node = {
            "id": "tax_1",
            # Tax rates might not have updatedAt in some API versions, but we check if it handles it
            "updatedAt": "2023-01-01T00:00:00Z",
        }

        with patch.object(extractor, "_get_current_timestamp", return_value="2023-01-02T00:00:00Z"):
            inventory = extractor._map_entity(node)

        assert inventory.entity_type == "taxRates"
