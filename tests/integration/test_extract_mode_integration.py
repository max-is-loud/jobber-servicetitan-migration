"""Integration tests for Phase 3 Extract Mode."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.clients import JobberClient
from src.coordinators.extract_mode_coordinator import ExtractModeCoordinator
from src.extractors.clients_extractor import ClientsExtractor
from src.interfaces import Logger
from src.mappers import EntityMapper
from src.models import Attachment, Client, MapSnapshot, Note
from src.repositories import Repository
from src.reports.extract_report_generator import ExtractReportGenerator


class TestExtractModeIntegration:
    """Integration tests for end-to-end extract mode workflow."""

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient."""
        return Mock(spec=JobberClient)

    @pytest.fixture
    def mock_entity_mapper(self):
        """Create mock EntityMapper."""
        return Mock(spec=EntityMapper)

    @pytest.fixture
    def mock_repository(self):
        """Create mock Repository with comprehensive mocking."""
        repo = Mock(spec=Repository)

        # Default return values
        repo.get_extract_queue.return_value = []
        repo.get_attachment_queue.return_value = []
        repo.get_entity_inventory.return_value = []
        repo.entity_exists.return_value = False
        repo.save_clients.return_value = None
        repo.save_notes.return_value = None
        repo.save_attachments.return_value = None
        repo.create_extract_queue.return_value = None
        repo.create_attachment_queue.return_value = None
        repo.update_queue_status.return_value = None
        repo.update_attachment_queue_status.return_value = None
        repo.get_attachment_by_id.return_value = None

        return repo

    @pytest.fixture
    def mock_logger(self):
        """Create mock Logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        logger.warning = Mock()
        logger.error = Mock()
        return logger

    @pytest.fixture
    def coordinator(self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_logger):
        """Create ExtractModeCoordinator instance."""
        return ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

    @pytest.fixture
    def sample_snapshot(self):
        """Create sample MapSnapshot."""
        return MapSnapshot(
            id="snapshot_integration_123",
            created_at="2023-11-15T10:00:00Z",
            pass1_cutoff="2023-11-15T10:00:00Z",
            label="integration-test",
            entities_included='["clients"]',
        )

    # ==================== End-to-End Extract Pass Tests ====================

    def test_end_to_end_extract_pass_success(self, coordinator, mock_repository, mock_entity_mapper, sample_snapshot):
        """Test complete extract pass from map snapshot to completion."""
        # Setup map snapshot
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        # Setup entity inventory
        from src.models import EntityInventory

        inventory_items = [
            EntityInventory(
                id=1,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id="client_1",
                created_at="2023-11-15T10:00:00Z",
            ),
            EntityInventory(
                id=2,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id="client_2",
                created_at="2023-11-15T10:00:00Z",
            ),
        ]
        mock_repository.get_entity_inventory.return_value = inventory_items

        # Setup extract queue
        from src.models import ExtractQueueItem

        queue_items = [
            ExtractQueueItem(
                id=1,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id="client_1",
                status="pending",
                attempt_count=0,
                created_at="2023-11-15T10:00:00Z",
                updated_at="2023-11-15T10:00:00Z",
            ),
            ExtractQueueItem(
                id=2,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id="client_2",
                status="pending",
                attempt_count=0,
                created_at="2023-11-15T10:00:00Z",
                updated_at="2023-11-15T10:00:00Z",
            ),
        ]

        def queue_side_effect(snapshot_id, entity_type, status=None):
            if status == "pending":
                return queue_items
            return []

        mock_repository.get_extract_queue.side_effect = queue_side_effect
        mock_repository.get_attachment_queue.return_value = []

        # Setup entity mapping
        client_1 = Client(
            id="client_1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )
        client_2 = Client(
            id="client_2",
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            phone="555-0200",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )

        mock_entity_mapper.map_client.side_effect = [client_1, client_2]

        # Mock extractor's _fetch_single to return node data
        with patch.object(ClientsExtractor, "_fetch_single") as mock_fetch:
            mock_fetch.side_effect = [
                {"id": "client_1", "firstName": "John", "lastName": "Doe"},
                {"id": "client_2", "firstName": "Jane", "lastName": "Smith"},
            ]

            # Run extract pass
            result = coordinator.run_extract_pass("snapshot_integration_123")

        # Verify results
        assert result["snapshot_id"] == "snapshot_integration_123"
        assert result["entity_results"]["clients"]["extracted"] == 2
        assert result["entity_results"]["clients"]["failed"] == 0
        assert result["totals"]["total_extracted"] == 2
        assert result["totals"]["total_failed"] == 0
        assert len(result["discrepancies"]) == 0

        # Verify entities were saved
        assert mock_repository.save_clients.call_count == 2

    def test_end_to_end_extract_pass_with_attachments(
        self, coordinator, mock_repository, mock_entity_mapper, sample_snapshot
    ):
        """Test extract pass with attachment queuing and downloading."""
        # Setup map snapshot
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        # Setup entity inventory
        from src.models import EntityInventory

        inventory_items = [
            EntityInventory(
                id=1,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id="client_1",
                created_at="2023-11-15T10:00:00Z",
            ),
        ]
        mock_repository.get_entity_inventory.return_value = inventory_items

        # Setup extract queue
        from src.models import ExtractQueueItem

        queue_item = ExtractQueueItem(
            id=1,
            map_snapshot_id="snapshot_integration_123",
            entity_type="clients",
            entity_id="client_1",
            status="pending",
            attempt_count=0,
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        def queue_side_effect(snapshot_id, entity_type, status=None):
            if status == "pending":
                return [queue_item]
            return []

        mock_repository.get_extract_queue.side_effect = queue_side_effect

        # Setup attachment queue
        from src.models import AttachmentQueueItem

        attachment_queue_item = AttachmentQueueItem(
            id=1,
            map_snapshot_id="snapshot_integration_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="pending",
            attempt_count=0,
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        def attachment_queue_side_effect(snapshot_id, status=None):
            if status == "pending":
                return [attachment_queue_item]
            return []

        mock_repository.get_attachment_queue.side_effect = attachment_queue_side_effect

        # Setup attachment metadata
        attachment = Attachment(
            id="attach_1",
            note_id="client_1_note_1",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://example.com/test.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.return_value = attachment

        # Setup entity mapping
        client = Client(
            id="client_1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )
        mock_entity_mapper.map_client.return_value = client

        # Mock extractor's _fetch_single
        with patch.object(ClientsExtractor, "_fetch_single") as mock_fetch:
            mock_fetch.return_value = {"id": "client_1", "firstName": "John", "lastName": "Doe"}

            # Mock attachment downloader
            with patch("src.coordinators.extract_mode_coordinator.AttachmentDownloader") as mock_downloader_class:
                mock_downloader = Mock()
                mock_downloader.download_attachment.return_value = {
                    "success": True,
                    "local_file_path": "/tmp/test.pdf",
                }
                mock_downloader_class.return_value = mock_downloader

                # Run extract pass
                result = coordinator.run_extract_pass("snapshot_integration_123")

        # Verify results
        assert result["entity_results"]["clients"]["extracted"] == 1
        assert result["attachment_result"]["downloaded"] == 1
        assert result["attachment_result"]["failed"] == 0

        # Verify attachment was downloaded
        mock_downloader.download_attachment.assert_called_once()

    def test_end_to_end_extract_pass_validates_completeness(
        self, coordinator, mock_repository, mock_entity_mapper, sample_snapshot
    ):
        """Test extract pass validates completeness against map totals."""
        # Setup map snapshot
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        # Setup entity inventory with 3 entities
        from src.models import EntityInventory

        inventory_items = [
            EntityInventory(
                id=i,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id=f"client_{i}",
                created_at="2023-11-15T10:00:00Z",
            )
            for i in range(1, 4)
        ]
        mock_repository.get_entity_inventory.return_value = inventory_items

        # Setup extract queue with only 2 items (missing 1)
        from src.models import ExtractQueueItem

        queue_items = [
            ExtractQueueItem(
                id=i,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id=f"client_{i}",
                status="pending",
                attempt_count=0,
                created_at="2023-11-15T10:00:00Z",
                updated_at="2023-11-15T10:00:00Z",
            )
            for i in range(1, 3)
        ]

        def queue_side_effect(snapshot_id, entity_type, status=None):
            if status == "pending":
                return queue_items
            return []

        mock_repository.get_extract_queue.side_effect = queue_side_effect
        mock_repository.get_attachment_queue.return_value = []

        # Setup entity mapping
        clients = [
            Client(
                id=f"client_{i}",
                first_name="John",
                last_name="Doe",
                email=f"client{i}@example.com",
                phone="555-0100",
                created_at="2023-11-15T10:00:00Z",
                additional_emails="[]",
                additional_phones="[]",
            )
            for i in range(1, 3)
        ]
        mock_entity_mapper.map_client.side_effect = clients

        # Mock extractor's _fetch_single
        with patch.object(ClientsExtractor, "_fetch_single") as mock_fetch:
            mock_fetch.side_effect = [
                {"id": f"client_{i}", "firstName": "John"}
                for i in range(1, 3)
            ]

            # Run extract pass
            result = coordinator.run_extract_pass("snapshot_integration_123")

        # Verify discrepancies were detected
        assert len(result["discrepancies"]) > 0
        assert any(d["type"] == "entity_count_mismatch" for d in result["discrepancies"])

    # ==================== Resume Capability Tests ====================

    def test_resume_extract_pass_retries_failed_items(
        self, coordinator, mock_repository, mock_entity_mapper, sample_snapshot
    ):
        """Test resume capability retries failed items."""
        # Setup map snapshot
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        # Setup entity inventory
        from src.models import EntityInventory

        inventory_items = [
            EntityInventory(
                id=1,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id="client_1",
                created_at="2023-11-15T10:00:00Z",
            ),
        ]
        mock_repository.get_entity_inventory.return_value = inventory_items

        # Setup extract queue with failed item
        from src.models import ExtractQueueItem

        failed_item = ExtractQueueItem(
            id=1,
            map_snapshot_id="snapshot_integration_123",
            entity_type="clients",
            entity_id="client_1",
            status="failed",
            attempt_count=1,
            last_error="Previous error",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        def queue_side_effect(snapshot_id, entity_type, status=None):
            if status == "pending":
                return []
            elif status == "failed":
                return [failed_item]
            return []

        mock_repository.get_extract_queue.side_effect = queue_side_effect
        mock_repository.get_attachment_queue.return_value = []

        # Setup entity mapping
        client = Client(
            id="client_1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
            additional_emails="[]",
            additional_phones="[]",
        )
        mock_entity_mapper.map_client.return_value = client

        # Mock extractor's _fetch_single
        with patch.object(ClientsExtractor, "_fetch_single") as mock_fetch:
            mock_fetch.return_value = {"id": "client_1", "firstName": "John"}

            # Run extract pass in resume mode
            result = coordinator.run_extract_pass("snapshot_integration_123", resume=True)

        # Verify failed item was retried and succeeded
        assert result["entity_results"]["clients"]["extracted"] == 1
        assert result["entity_results"]["clients"]["failed"] == 0

        # Verify queue was not recreated (resume mode)
        mock_repository.create_extract_queue.assert_not_called()

    def test_resume_extract_pass_skips_done_items(self, coordinator, mock_repository, sample_snapshot):
        """Test resume capability skips already completed items."""
        # Setup map snapshot
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        # Setup entity inventory
        from src.models import EntityInventory

        inventory_items = [
            EntityInventory(
                id=1,
                map_snapshot_id="snapshot_integration_123",
                entity_type="clients",
                entity_id="client_1",
                created_at="2023-11-15T10:00:00Z",
            ),
        ]
        mock_repository.get_entity_inventory.return_value = inventory_items

        # Setup extract queue - all items are done
        mock_repository.get_extract_queue.return_value = []  # No pending or failed items
        mock_repository.get_attachment_queue.return_value = []

        # Run extract pass in resume mode
        result = coordinator.run_extract_pass("snapshot_integration_123", resume=True)

        # Verify no items were processed
        assert result["entity_results"]["clients"]["extracted"] == 0
        assert result["entity_results"]["clients"]["failed"] == 0

    # ==================== Report Generation Integration Tests ====================

    def test_generate_report_from_extract_results(self, tmp_path):
        """Test generating report from extract pass results."""
        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generator = ExtractReportGenerator(output_dir=output_dir)

        # Sample results from extract pass
        results = {
            "snapshot_id": "snapshot_integration_123",
            "label": "integration-test",
            "entity_results": {
                "clients": {"extracted": 100, "failed": 5, "skipped": 0},
            },
            "attachment_result": {"downloaded": 75, "failed": 3, "skipped": 0},
            "discrepancies": [],
            "totals": {"total_extracted": 100, "total_failed": 5, "entity_types_count": 1},
            "duration": 60.0,
        }

        md_path, json_path = generator.generate_report(**results)

        # Verify reports were created
        assert Path(md_path).exists()
        assert Path(json_path).exists()

        # Verify content
        md_content = Path(md_path).read_text(encoding="utf-8")
        assert "snapshot_integration_123" in md_content
        assert "integration-test" in md_content

        json_data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert json_data["snapshot_id"] == "snapshot_integration_123"
        assert json_data["summary"]["total_extracted"] == 100

    # ==================== Attachment Queue Processing Tests ====================

    def test_attachment_queue_processing_retries_failed_downloads(
        self, coordinator, mock_repository, sample_snapshot
    ):
        """Test attachment queue processing retries failed downloads."""
        # Setup map snapshot
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        # No entity extraction needed for this test
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        # Setup attachment queue with failed item
        from src.models import AttachmentQueueItem

        failed_attachment = AttachmentQueueItem(
            id=1,
            map_snapshot_id="snapshot_integration_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="failed",
            attempt_count=1,
            last_error="Network error",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        def attachment_queue_side_effect(snapshot_id, status=None):
            if status == "pending":
                return []
            elif status == "failed":
                return [failed_attachment]
            return []

        mock_repository.get_attachment_queue.side_effect = attachment_queue_side_effect

        # Setup attachment metadata
        attachment = Attachment(
            id="attach_1",
            note_id="client_1_note_1",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://example.com/test.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.return_value = attachment

        # Mock attachment downloader
        with patch("src.coordinators.extract_mode_coordinator.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/tmp/test.pdf",
            }
            mock_downloader_class.return_value = mock_downloader

            # Run extract pass
            result = coordinator.run_extract_pass("snapshot_integration_123")

        # Verify failed attachment was retried and succeeded
        assert result["attachment_result"]["downloaded"] == 1
        assert result["attachment_result"]["failed"] == 0
