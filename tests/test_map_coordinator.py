"""Unit tests for MapModeCoordinator."""

import json
from unittest.mock import Mock, MagicMock, patch, call
import pytest
from datetime import datetime

from src.coordinators.map_mode_coordinator import MapModeCoordinator
from src.extractors.map_mode import (
    ClientsMapExtractor,
    InvoicesMapExtractor,
    QuotesMapExtractor,
)
from src.clients import JobberClient
from src.interfaces import Logger
from src.models import MapSnapshot, EntityInventory
from src.repositories import Repository


class TestMapModeCoordinator:
    """Test suite for MapModeCoordinator."""

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
    def coordinator(self, mock_jobber_client, mock_repository, mock_logger):
        """Create MapModeCoordinator instance."""
        return MapModeCoordinator(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
        )

    def test_coordinator_initialization(self, coordinator, mock_jobber_client, mock_repository, mock_logger):
        """Test MapModeCoordinator initializes with correct dependencies."""
        assert coordinator._jobber_client == mock_jobber_client
        assert coordinator._repository == mock_repository
        assert coordinator._logger == mock_logger

    def test_create_snapshot_generates_correct_data(self, coordinator, mock_repository):
        """Test _create_snapshot creates MapSnapshot with correct fields."""
        entity_types = ["clients", "invoices"]

        with patch("src.coordinators.map_mode_coordinator.uuid.uuid4", return_value="test-uuid-123"):
            with patch("src.coordinators.map_mode_coordinator.datetime") as mock_datetime:
                mock_now = datetime(2023, 11, 15, 10, 0, 0)
                mock_datetime.utcnow.return_value = mock_now
                mock_datetime.strftime = datetime.strftime

                snapshot = coordinator._create_snapshot(entity_types, label="test-label")

        assert snapshot.id == "test-uuid-123"
        assert snapshot.label == "test-label"
        assert json.loads(snapshot.entities_included) == ["clients", "invoices"]

        # Verify repository was called
        mock_repository.save_map_snapshot.assert_called_once()

    def test_create_snapshot_generates_label_if_not_provided(self, coordinator, mock_repository):
        """Test _create_snapshot generates label if not provided."""
        entity_types = ["clients"]

        with patch("src.coordinators.map_mode_coordinator.uuid.uuid4", return_value="test-uuid"):
            with patch("src.coordinators.map_mode_coordinator.datetime") as mock_datetime:
                mock_now = datetime(2023, 11, 15, 10, 30, 45)
                mock_datetime.utcnow.return_value = mock_now
                mock_datetime.strftime = datetime.strftime

                snapshot = coordinator._create_snapshot(entity_types, label=None)

        assert snapshot.label.startswith("map-")
        assert "20231115" in snapshot.label

    def test_create_extractor_returns_correct_extractor_class(self, coordinator):
        """Test _create_extractor returns appropriate extractor instance."""
        extractor = coordinator._create_extractor("clients", "snapshot_123")

        assert isinstance(extractor, ClientsMapExtractor)

    def test_run_map_pass_validates_entity_types(self, coordinator):
        """Test run_map_pass raises error for invalid entity types."""
        invalid_types = ["clients", "invalid_type", "quotes"]

        with pytest.raises(ValueError, match="Invalid entity types"):
            coordinator.run_map_pass(invalid_types)

    def test_run_map_pass_creates_snapshot(self, coordinator, mock_repository):
        """Test run_map_pass creates a map snapshot."""
        entity_types = ["clients"]

        # Mock extractor
        mock_extractor = Mock()
        mock_extractor.extract.return_value = {
            "total_entities": 10,
            "total_pages": 1,
            "entity_type": "clients",
        }

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            with patch.object(coordinator, "_create_snapshot") as mock_create_snapshot:
                mock_snapshot = MapSnapshot(
                    id="snapshot_123",
                    created_at="2023-11-15T10:00:00Z",
                    pass1_cutoff="2023-11-15T10:00:00Z",
                    label="test-label",
                    entities_included='["clients"]',
                )
                mock_create_snapshot.return_value = mock_snapshot

                result = coordinator.run_map_pass(entity_types, label="test-label")

        mock_create_snapshot.assert_called_once_with(entity_types, "test-label")
        assert result["snapshot_id"] == "snapshot_123"

    def test_run_map_pass_runs_extractors(self, coordinator, mock_repository):
        """Test run_map_pass executes extractors for each entity type."""
        entity_types = ["clients", "invoices"]

        # Mock extractors
        mock_clients_extractor = Mock()
        mock_clients_extractor.extract.return_value = {
            "total_entities": 100,
            "total_pages": 2,
            "entity_type": "clients",
        }

        mock_invoices_extractor = Mock()
        mock_invoices_extractor.extract.return_value = {
            "total_entities": 50,
            "total_pages": 1,
            "entity_type": "invoices",
        }

        def create_extractor_side_effect(entity_type, snapshot_id, **kwargs):
            if entity_type == "clients":
                return mock_clients_extractor
            elif entity_type == "invoices":
                return mock_invoices_extractor

        with patch.object(coordinator, "_create_snapshot") as mock_create_snapshot:
            mock_snapshot = MapSnapshot(
                id="snapshot_xyz",
                created_at="2023-11-15T10:00:00Z",
                pass1_cutoff="2023-11-15T10:00:00Z",
                label="test",
                entities_included='["clients", "invoices"]',
            )
            mock_create_snapshot.return_value = mock_snapshot

            with patch.object(coordinator, "_create_extractor", side_effect=create_extractor_side_effect):
                result = coordinator.run_map_pass(entity_types)

        assert mock_clients_extractor.extract.called
        assert mock_invoices_extractor.extract.called

        assert result["entity_results"]["clients"]["total_entities"] == 100
        assert result["entity_results"]["invoices"]["total_entities"] == 50
        assert result["totals"]["total_entities"] == 150

    def test_run_map_pass_returns_summary(self, coordinator):
        """Test run_map_pass returns complete summary dictionary."""
        entity_types = ["clients"]

        mock_extractor = Mock()
        mock_extractor.extract.return_value = {
            "total_entities": 75,
            "total_pages": 2,
            "entity_type": "clients",
        }

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            with patch.object(coordinator, "_create_snapshot") as mock_create_snapshot:
                mock_snapshot = MapSnapshot(
                    id="snap_123",
                    created_at="2023-11-15T10:00:00Z",
                    pass1_cutoff="2023-11-15T10:00:00Z",
                    label="summary-test",
                    entities_included='["clients"]',
                )
                mock_create_snapshot.return_value = mock_snapshot

                result = coordinator.run_map_pass(entity_types, label="summary-test")

        assert "snapshot_id" in result
        assert "label" in result
        assert "entity_results" in result
        assert "totals" in result
        assert "duration" in result

        assert result["snapshot_id"] == "snap_123"
        assert result["label"] == "summary-test"
        assert result["totals"]["entity_types_count"] == 1

    def test_identify_hotspots_returns_top_entities(self, coordinator, mock_repository):
        """Test identify_hotspots returns entities with highest relation counts."""
        inventory_items = [
            EntityInventory(
                entity_type="clients",
                entity_id="client_1",
                discovered_at="2023-11-15T10:00:00Z",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
                estimated_relations_json=json.dumps({"notes": 50, "attachments": 25}),
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="client_2",
                discovered_at="2023-11-15T10:00:00Z",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
                estimated_relations_json=json.dumps({"notes": 10, "attachments": 5}),
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="client_3",
                discovered_at="2023-11-15T10:00:00Z",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
                estimated_relations_json=json.dumps({"notes": 100, "attachments": 50}),
            ),
        ]

        mock_repository.get_entity_inventory.return_value = inventory_items

        hotspots = coordinator.identify_hotspots("snap_123", "clients", top_n=2)

        assert len(hotspots) == 2
        assert hotspots[0]["entity_id"] == "client_3"  # Highest total (150)
        assert hotspots[0]["total_relations"] == 150
        assert hotspots[1]["entity_id"] == "client_1"  # Second highest (75)
        assert hotspots[1]["total_relations"] == 75

    def test_identify_hotspots_respects_top_n_limit(self, coordinator, mock_repository):
        """Test identify_hotspots limits results to top_n."""
        inventory_items = [
            EntityInventory(
                entity_type="clients",
                entity_id=f"client_{i}",
                discovered_at="2023-11-15T10:00:00Z",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
                estimated_relations_json=json.dumps({"notes": i, "attachments": i}),
            )
            for i in range(20)
        ]

        mock_repository.get_entity_inventory.return_value = inventory_items

        hotspots = coordinator.identify_hotspots("snap_123", "clients", top_n=5)

        assert len(hotspots) == 5

    def test_get_density_stats_calculates_correctly(self, coordinator, mock_repository):
        """Test get_density_stats calculates statistics correctly."""
        inventory_items = [
            EntityInventory(
                entity_type="clients",
                entity_id="client_1",
                discovered_at="2023-11-15T10:00:00Z",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
                estimated_relations_json=json.dumps({"notes": 10, "attachments": 5}),
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="client_2",
                discovered_at="2023-11-15T10:00:00Z",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
                estimated_relations_json=json.dumps({"notes": 20, "attachments": 10}),
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="client_3",
                discovered_at="2023-11-15T10:00:00Z",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
                estimated_relations_json=json.dumps({"notes": 0, "attachments": 0}),
            ),
        ]

        mock_repository.get_entity_inventory.return_value = inventory_items

        stats = coordinator.get_density_stats("snap_123", "clients")

        assert stats["total_entities"] == 3
        assert stats["avg_relations"] == 15.0  # (15 + 30 + 0) / 3
        assert stats["max_relations"] == 30
        assert stats["entities_with_relations"] == 2

    def test_get_density_stats_handles_empty_inventory(self, coordinator, mock_repository):
        """Test get_density_stats handles empty inventory correctly."""
        mock_repository.get_entity_inventory.return_value = []

        stats = coordinator.get_density_stats("snap_123", "clients")

        assert stats["total_entities"] == 0
        assert stats["avg_relations"] == 0.0
        assert stats["max_relations"] == 0
        assert stats["entities_with_relations"] == 0

    def test_extractor_map_contains_all_entity_types(self, coordinator):
        """Test _EXTRACTOR_MAP contains all supported entity types."""
        expected_types = [
            "clients",
            "invoices",
            "quotes",
            "jobs",
            "properties",
            "requests",
            "users",
            "expenses",
            "visits",
            "timesheetEntries",
            "productsAndServices",
            "taxRates",
        ]

        for entity_type in expected_types:
            assert entity_type in coordinator._EXTRACTOR_MAP
