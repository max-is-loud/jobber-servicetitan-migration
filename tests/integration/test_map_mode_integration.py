"""Integration tests for map mode end-to-end workflow."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from src.auth import AuthProvider
from src.clients import JobberClient
from src.config import ConfigManagerImpl
from src.coordinators.map_mode_coordinator import MapModeCoordinator
from src.extractors.map_mode import ClientsMapExtractor, InvoicesMapExtractor
from src.interfaces import Logger
from src.reports.map_report_generator import MapReportGenerator
from src.repositories import Repository


class TestMapModeIntegration:
    """Integration test suite for complete map mode workflow."""

    @pytest.fixture
    def db_connection(self):
        """Create in-memory SQLite database."""
        conn = sqlite3.connect(":memory:")
        yield conn
        conn.close()

    @pytest.fixture
    def repository(self, db_connection):
        """Create repository with initialized schema."""
        repo = Repository(db_connection)
        repo.init_schema()
        return repo

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        logger.warning = Mock()
        return logger

    @pytest.fixture
    def mock_config_manager(self):
        """Create mock configuration manager for pagination sizes."""
        config_manager = Mock(spec=ConfigManagerImpl)
        config_manager.get_pagination_config.return_value = 50
        return config_manager

    @pytest.fixture
    def mock_auth_provider(self):
        """Create mock AuthProvider."""
        return Mock(spec=AuthProvider)

    @pytest.fixture
    def jobber_client(self, mock_auth_provider, mock_config_manager):
        """Create JobberClient with mocked dependencies."""
        http_client = Mock()
        return JobberClient(
            auth_provider=mock_auth_provider,
            http_client=http_client,
            config_manager=mock_config_manager,
        )

    @pytest.fixture
    def coordinator(self, jobber_client, repository, mock_logger):
        """Create MapModeCoordinator with real dependencies."""
        return MapModeCoordinator(
            jobber_client=jobber_client,
            repository=repository,
            logger=mock_logger,
        )

    @pytest.fixture
    def mock_clients_response_page1(self):
        """Create mock API response for clients page 1."""
        return {
            "data": {
                "clients": {
                    "totalCount": 5,
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_page2"},
                    "edges": [
                        {
                            "node": {
                                "id": "client_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 10},
                                "noteAttachments": {"totalCount": 5},
                            }
                        },
                        {
                            "node": {
                                "id": "client_2",
                                "updatedAt": "2023-11-16T10:00:00Z",
                                "notes": {"totalCount": 20},
                                "noteAttachments": {"totalCount": 8},
                            }
                        },
                        {
                            "node": {
                                "id": "client_3",
                                "updatedAt": "2023-11-17T10:00:00Z",
                                "notes": {"totalCount": 0},
                                "noteAttachments": {"totalCount": 0},
                            }
                        },
                    ],
                }
            }
        }

    @pytest.fixture
    def mock_clients_response_page2(self):
        """Create mock API response for clients page 2."""
        return {
            "data": {
                "clients": {
                    "totalCount": 5,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "client_4",
                                "updatedAt": "2023-11-18T10:00:00Z",
                                "notes": {"totalCount": 15},
                                "noteAttachments": {"totalCount": 3},
                            }
                        },
                        {
                            "node": {
                                "id": "client_5",
                                "updatedAt": "2023-11-19T10:00:00Z",
                                "notes": {"totalCount": 30},
                                "noteAttachments": {"totalCount": 12},
                            }
                        },
                    ],
                }
            }
        }

    @pytest.fixture
    def mock_invoices_response(self):
        """Create mock API response for invoices."""
        return {
            "data": {
                "invoices": {
                    "totalCount": 2,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "edges": [
                        {
                            "node": {
                                "id": "invoice_1",
                                "updatedAt": "2023-11-15T10:00:00Z",
                                "notes": {"totalCount": 5},
                                "noteAttachments": {"totalCount": 2},
                            }
                        },
                        {
                            "node": {
                                "id": "invoice_2",
                                "updatedAt": "2023-11-16T10:00:00Z",
                                "notes": {"totalCount": 3},
                                "noteAttachments": {"totalCount": 1},
                            }
                        },
                    ],
                }
            }
        }

    def test_complete_map_pass_workflow(
        self,
        coordinator,
        repository,
        jobber_client,
        mock_clients_response_page1,
        mock_clients_response_page2,
        mock_invoices_response,
    ):
        """Test complete map pass workflow from extraction to database storage."""

        # Mock API responses
        def mock_execute_request(query, cursor=None):
            if "clients" in query:
                if cursor == "cursor_page2":
                    return mock_clients_response_page2
                else:
                    return mock_clients_response_page1
            elif "invoices" in query:
                return mock_invoices_response

        with patch.object(jobber_client, "_execute_graphql_request", side_effect=mock_execute_request):
            # Run map pass
            result = coordinator.run_map_pass(
                entity_types=["clients", "invoices"],
                label="integration-test",
            )

        # Verify result structure
        assert result["snapshot_id"] is not None
        assert result["label"] == "integration-test"
        assert "entity_results" in result
        assert "totals" in result
        assert "duration" in result

        # Verify entity counts
        assert result["entity_results"]["clients"]["total_entities"] == 5
        assert result["entity_results"]["clients"]["total_pages"] == 2
        assert result["entity_results"]["invoices"]["total_entities"] == 2
        assert result["entity_results"]["invoices"]["total_pages"] == 1
        assert result["totals"]["total_entities"] == 7

        # Verify database storage
        snapshot_id = result["snapshot_id"]

        # Check map snapshot exists
        cursor = repository._connection.cursor()
        cursor.execute("SELECT * FROM map_snapshot WHERE id = ?", (snapshot_id,))
        snapshot_row = cursor.fetchone()
        assert snapshot_row is not None

        # Check entity inventory records
        clients_inventory = repository.get_entity_inventory(snapshot_id, "clients")
        assert len(clients_inventory) == 5

        invoices_inventory = repository.get_entity_inventory(snapshot_id, "invoices")
        assert len(invoices_inventory) == 2

        # Verify relation counts stored correctly
        client_5_inventory = [inv for inv in clients_inventory if inv.entity_id == "client_5"][0]
        relations = json.loads(client_5_inventory.estimated_relations_json)
        assert relations["notes"] == 30
        assert relations["attachments"] == 12

    def test_hotspot_identification_integration(
        self,
        coordinator,
        repository,
        jobber_client,
        mock_clients_response_page1,
        mock_clients_response_page2,
    ):
        """Test hotspot identification after map pass extraction."""

        # Mock API responses
        def mock_execute_request(query, cursor=None):
            if cursor == "cursor_page2":
                return mock_clients_response_page2
            else:
                return mock_clients_response_page1

        with patch.object(jobber_client, "_execute_graphql_request", side_effect=mock_execute_request):
            # Run map pass
            result = coordinator.run_map_pass(
                entity_types=["clients"],
                label="hotspot-test",
            )

        snapshot_id = result["snapshot_id"]

        # Identify hotspots
        hotspots = coordinator.identify_hotspots(snapshot_id, "clients", top_n=3)

        # Verify hotspots are sorted by total relations
        assert len(hotspots) == 3
        assert hotspots[0]["entity_id"] == "client_5"  # 30 + 12 = 42
        assert hotspots[0]["total_relations"] == 42
        assert hotspots[1]["entity_id"] == "client_2"  # 20 + 8 = 28
        assert hotspots[1]["total_relations"] == 28

    def test_density_stats_calculation_integration(
        self,
        coordinator,
        repository,
        jobber_client,
        mock_clients_response_page1,
        mock_clients_response_page2,
    ):
        """Test density statistics calculation after map pass extraction."""

        # Mock API responses
        def mock_execute_request(query, cursor=None):
            if cursor == "cursor_page2":
                return mock_clients_response_page2
            else:
                return mock_clients_response_page1

        with patch.object(jobber_client, "_execute_graphql_request", side_effect=mock_execute_request):
            # Run map pass
            result = coordinator.run_map_pass(
                entity_types=["clients"],
                label="density-test",
            )

        snapshot_id = result["snapshot_id"]

        # Get density stats
        stats = coordinator.get_density_stats(snapshot_id, "clients")

        # Verify statistics
        assert stats["total_entities"] == 5
        assert stats["max_relations"] == 42  # client_5: 30 + 12
        assert stats["entities_with_relations"] == 4  # client_3 has 0
        # Average: (15 + 28 + 0 + 18 + 42) / 5 = 20.6
        assert 20.0 <= stats["avg_relations"] <= 21.0

    def test_report_generation_integration(
        self,
        coordinator,
        repository,
        jobber_client,
        mock_clients_response_page1,
        mock_clients_response_page2,
        mock_invoices_response,
        tmp_path,
    ):
        """Test report generation from map pass results."""

        # Mock API responses
        def mock_execute_request(query, cursor=None):
            if "clients" in query:
                if cursor == "cursor_page2":
                    return mock_clients_response_page2
                else:
                    return mock_clients_response_page1
            elif "invoices" in query:
                return mock_invoices_response

        with patch.object(jobber_client, "_execute_graphql_request", side_effect=mock_execute_request):
            # Run map pass
            result = coordinator.run_map_pass(
                entity_types=["clients", "invoices"],
                label="report-test",
            )

        snapshot_id = result["snapshot_id"]

        # Get hotspots and density stats
        hotspots_by_type = {
            "clients": coordinator.identify_hotspots(snapshot_id, "clients", top_n=5),
            "invoices": coordinator.identify_hotspots(snapshot_id, "invoices", top_n=5),
        }

        density_stats_by_type = {
            "clients": coordinator.get_density_stats(snapshot_id, "clients"),
            "invoices": coordinator.get_density_stats(snapshot_id, "invoices"),
        }

        # Generate report
        report_generator = MapReportGenerator(output_dir=tmp_path)
        markdown_path, json_path = report_generator.generate_report(
            snapshot_id=result["snapshot_id"],
            label=result["label"],
            entity_results=result["entity_results"],
            totals=result["totals"],
            duration=result["duration"],
            hotspots_by_type=hotspots_by_type,
            density_stats_by_type=density_stats_by_type,
        )

        # Verify reports exist
        assert Path(markdown_path).exists()
        assert Path(json_path).exists()

        # Verify Markdown content
        markdown_content = Path(markdown_path).read_text()
        assert "report-test" in markdown_content
        assert "clients" in markdown_content
        assert "invoices" in markdown_content
        assert "client_5" in markdown_content  # Hotspot entity

        # Verify JSON content
        with open(json_path, "r") as f:
            json_data = json.load(f)

        assert json_data["snapshot_id"] == snapshot_id
        assert json_data["label"] == "report-test"
        assert json_data["summary"]["total_entities"] == 7
        assert "clients" in json_data["hotspots"]

    def test_multiple_entity_types_extraction(
        self,
        coordinator,
        repository,
        jobber_client,
        mock_clients_response_page1,
        mock_clients_response_page2,
        mock_invoices_response,
    ):
        """Test extraction of multiple entity types in single map pass."""

        # Mock API responses
        def mock_execute_request(query, cursor=None):
            if "clients" in query:
                if cursor == "cursor_page2":
                    return mock_clients_response_page2
                else:
                    return mock_clients_response_page1
            elif "invoices" in query:
                return mock_invoices_response

        with patch.object(jobber_client, "_execute_graphql_request", side_effect=mock_execute_request):
            # Run map pass
            result = coordinator.run_map_pass(
                entity_types=["clients", "invoices"],
                label="multi-type-test",
            )

        # Verify both entity types extracted
        assert "clients" in result["entity_results"]
        assert "invoices" in result["entity_results"]

        # Verify correct totals
        assert result["totals"]["entity_types_count"] == 2
        assert result["totals"]["total_entities"] == 7

    def test_error_handling_invalid_entity_type(self, coordinator):
        """Test error handling for invalid entity types."""
        with pytest.raises(ValueError, match="Invalid entity types"):
            coordinator.run_map_pass(
                entity_types=["clients", "invalid_type"],
                label="error-test",
            )
