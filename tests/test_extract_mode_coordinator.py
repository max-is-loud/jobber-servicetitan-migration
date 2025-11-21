"""Unit tests for ExtractModeCoordinator."""

import json
from datetime import datetime
from unittest.mock import Mock, call, patch

import pytest

from src.clients import JobberClient
from src.coordinators.extract_mode_coordinator import ExtractModeCoordinator
from src.extractors import ClientsExtractor, InvoicesExtractor
from src.interfaces import Logger
from src.mappers import EntityMapper
from src.models import Attachment, ExtractQueueItem, MapSnapshot
from src.repositories import Repository


class TestExtractModeCoordinator:
    """Test suite for ExtractModeCoordinator."""

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
        """Create mock Repository."""
        return Mock(spec=Repository)

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
            id="snapshot_123",
            created_at="2023-11-15T10:00:00Z",
            pass1_cutoff="2023-11-15T10:00:00Z",
            label="test-snapshot",
            entities_included='["clients", "invoices"]',
        )

    # ==================== Test run_extract_pass() ====================

    def test_run_extract_pass_with_all_entity_types(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass with all entity types from snapshot."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_attachment_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        result = coordinator.run_extract_pass("snapshot_123")

        assert result["snapshot_id"] == "snapshot_123"
        assert "clients" in result["entity_results"]
        assert "invoices" in result["entity_results"]
        assert result["totals"]["entity_types_count"] == 2
        mock_repository.create_extract_queue.assert_any_call("snapshot_123", "clients")
        mock_repository.create_extract_queue.assert_any_call("snapshot_123", "invoices")

    def test_run_extract_pass_with_subset_of_entity_types(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass with subset of entity types."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_attachment_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        result = coordinator.run_extract_pass("snapshot_123", entity_types=["clients"])

        assert result["snapshot_id"] == "snapshot_123"
        assert "clients" in result["entity_results"]
        assert "invoices" not in result["entity_results"]
        assert result["totals"]["entity_types_count"] == 1
        mock_repository.create_extract_queue.assert_called_once_with("snapshot_123", "clients")

    def test_run_extract_pass_invalid_snapshot_id(self, coordinator, mock_repository):
        """Test run_extract_pass raises ValueError for invalid snapshot ID."""
        mock_repository.get_map_snapshot.return_value = None

        with pytest.raises(ValueError, match="Map snapshot not found"):
            coordinator.run_extract_pass("invalid_snapshot")

    def test_run_extract_pass_invalid_entity_types(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass raises ValueError for invalid entity types."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        with pytest.raises(ValueError, match="Entity types not in snapshot"):
            coordinator.run_extract_pass("snapshot_123", entity_types=["clients", "invalid_type"])

    def test_run_extract_pass_resume_mode(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass in resume mode doesn't create new queues."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_attachment_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        coordinator.run_extract_pass("snapshot_123", resume=True)

        # Should not create queues in resume mode
        mock_repository.create_extract_queue.assert_not_called()

    def test_run_extract_pass_fresh_mode_creates_queues(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass in fresh mode creates new queues."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_attachment_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        coordinator.run_extract_pass("snapshot_123", resume=False)

        # Should create queues in fresh mode
        assert mock_repository.create_extract_queue.call_count == 2

    def test_run_extract_pass_processes_entities_and_attachments(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass processes entities and then attachments."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_attachment_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        with patch.object(coordinator, "_process_queue") as mock_process_queue:
            with patch.object(coordinator, "_process_attachment_queue") as mock_process_attach:
                mock_process_queue.return_value = {"entity_type": "clients", "extracted": 5, "failed": 0, "skipped": 0}
                mock_process_attach.return_value = {"downloaded": 10, "failed": 0, "skipped": 0}

                result = coordinator.run_extract_pass("snapshot_123")

        # Verify entity processing was called for both types
        assert mock_process_queue.call_count == 2
        # Verify attachment processing was called once
        mock_process_attach.assert_called_once_with("snapshot_123")
        assert result["attachment_result"]["downloaded"] == 10

    def test_run_extract_pass_validates_completeness(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass validates completeness against map totals."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_attachment_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        with patch.object(coordinator, "_validate_completeness") as mock_validate:
            mock_validate.return_value = []

            result = coordinator.run_extract_pass("snapshot_123")

        mock_validate.assert_called_once()
        assert result["discrepancies"] == []

    def test_run_extract_pass_returns_duration(self, coordinator, mock_repository, sample_snapshot):
        """Test run_extract_pass returns execution duration."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []
        mock_repository.get_attachment_queue.return_value = []
        mock_repository.get_entity_inventory.return_value = []

        result = coordinator.run_extract_pass("snapshot_123")

        assert "duration" in result
        assert isinstance(result["duration"], float)
        assert result["duration"] >= 0

    # ==================== Test _process_queue() ====================

    def test_process_queue_with_empty_queue(self, coordinator, mock_repository):
        """Test _process_queue with no items returns zero counts."""
        mock_repository.get_extract_queue.return_value = []

        result = coordinator._process_queue("snapshot_123", "clients")

        assert result["entity_type"] == "clients"
        assert result["extracted"] == 0
        assert result["failed"] == 0
        assert result["skipped"] == 0

    def test_process_queue_with_pending_items(self, coordinator, mock_repository):
        """Test _process_queue processes pending items."""
        pending_item = ExtractQueueItem(
            map_snapshot_id="snapshot_123",
            entity_type="clients",
            entity_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_extract_queue.side_effect = [
            [pending_item],  # pending
            [],  # failed
        ]

        mock_extractor = Mock()
        mock_extractor.extract_single.return_value = {"success": True, "entity_id": "client_1", "entity_found": True}

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            result = coordinator._process_queue("snapshot_123", "clients")

        assert result["extracted"] == 1
        assert result["failed"] == 0
        mock_extractor.extract_single.assert_called_once_with("client_1")

    def test_process_queue_with_failed_items_retries(self, coordinator, mock_repository):
        """Test _process_queue retries failed items."""
        failed_item = ExtractQueueItem(
            map_snapshot_id="snapshot_123",
            entity_type="clients",
            entity_id="client_2",
            status="failed",
            attempt_count=1,
            last_error="Previous error",
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_extract_queue.side_effect = [
            [],  # pending
            [failed_item],  # failed
        ]

        mock_extractor = Mock()
        mock_extractor.extract_single.return_value = {"success": True, "entity_id": "client_2", "entity_found": True}

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            result = coordinator._process_queue("snapshot_123", "clients")

        assert result["extracted"] == 1
        mock_extractor.extract_single.assert_called_once_with("client_2")

    def test_process_queue_with_mix_of_pending_and_failed(self, coordinator, mock_repository):
        """Test _process_queue processes both pending and failed items."""
        pending_item = ExtractQueueItem(
            map_snapshot_id="snapshot_123",
            entity_type="clients",
            entity_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        failed_item = ExtractQueueItem(
            map_snapshot_id="snapshot_123",
            entity_type="clients",
            entity_id="client_2",
            status="failed",
            attempt_count=1,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_extract_queue.side_effect = [
            [pending_item],  # pending
            [failed_item],  # failed
        ]

        mock_extractor = Mock()
        mock_extractor.extract_single.return_value = {"success": True, "entity_id": "client_1", "entity_found": True}

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            result = coordinator._process_queue("snapshot_123", "clients")

        assert result["extracted"] == 2
        assert mock_extractor.extract_single.call_count == 2

    def test_process_queue_extraction_success(self, coordinator, mock_repository):
        """Test _process_queue marks item as done on successful extraction."""
        queue_item = ExtractQueueItem(
            map_snapshot_id="snapshot_123",
            entity_type="clients",
            entity_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_extract_queue.side_effect = [[queue_item], []]

        mock_extractor = Mock()
        mock_extractor.extract_single.return_value = {"success": True, "entity_id": "client_1"}

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            coordinator._process_queue("snapshot_123", "clients")

        # Verify status was updated to done
        update_calls = mock_repository.update_queue_status.call_args_list
        # Should be called twice: once for in_progress, once for done
        assert len(update_calls) == 2
        final_call = update_calls[1][0][0]
        assert final_call.status == "done"
        assert final_call.last_error is None

    def test_process_queue_extraction_failure(self, coordinator, mock_repository):
        """Test _process_queue marks item as failed on extraction failure."""
        queue_item = ExtractQueueItem(
            map_snapshot_id="snapshot_123",
            entity_type="clients",
            entity_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_extract_queue.side_effect = [[queue_item], []]

        mock_extractor = Mock()
        mock_extractor.extract_single.return_value = {
            "success": False,
            "entity_id": "client_1",
            "error": "API error",
        }

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            result = coordinator._process_queue("snapshot_123", "clients")

        assert result["failed"] == 1
        # Verify status was updated to failed
        update_calls = mock_repository.update_queue_status.call_args_list
        final_call = update_calls[1][0][0]
        assert final_call.status == "failed"
        assert final_call.last_error == "API error"
        assert final_call.attempt_count == 1

    def test_process_queue_status_transitions(self, coordinator, mock_repository):
        """Test _process_queue updates status: pending -> in_progress -> done/failed."""
        queue_item = ExtractQueueItem(
            map_snapshot_id="snapshot_123",
            entity_type="clients",
            entity_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_extract_queue.side_effect = [[queue_item], []]

        mock_extractor = Mock()
        mock_extractor.extract_single.return_value = {"success": True, "entity_id": "client_1"}

        with patch.object(coordinator, "_create_extractor", return_value=mock_extractor):
            coordinator._process_queue("snapshot_123", "clients")

        # Verify status transitions occurred (2 updates per item)
        update_calls = mock_repository.update_queue_status.call_args_list
        assert len(update_calls) == 2  # One for in_progress, one for done/failed
        # Final status should be done (since extraction succeeded)
        assert queue_item.status == "done"

    # ==================== Test _process_attachment_queue() ====================

    def test_process_attachment_queue_empty(self, coordinator, mock_repository):
        """Test _process_attachment_queue with no attachments."""
        mock_repository.get_attachment_queue.return_value = []

        result = coordinator._process_attachment_queue("snapshot_123")

        assert result["downloaded"] == 0
        assert result["failed"] == 0
        assert result["skipped"] == 0

    def test_process_attachment_queue_with_pending_attachments(self, coordinator, mock_repository):
        """Test _process_attachment_queue downloads pending attachments."""
        from src.models import AttachmentQueueItem

        queue_item = AttachmentQueueItem(
            map_snapshot_id="snapshot_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_queue.side_effect = [
            [queue_item],  # pending
            [],  # failed
        ]

        attachment = Attachment(
            id="attach_1",
            note_id="client_1_note_1",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.return_value = attachment

        with patch("src.extractors.attachment_downloader.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/path/to/file.pdf",
            }
            mock_downloader_class.return_value = mock_downloader

            result = coordinator._process_attachment_queue("snapshot_123")

        assert result["downloaded"] == 1
        assert result["failed"] == 0
        mock_downloader.download_attachment.assert_called_once_with(attachment)

    def test_process_attachment_queue_with_failed_attachments_retries(self, coordinator, mock_repository):
        """Test _process_attachment_queue retries failed attachments."""
        from src.models import AttachmentQueueItem

        queue_item = AttachmentQueueItem(
            map_snapshot_id="snapshot_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="failed",
            attempt_count=1,
            last_error="Previous download error",
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_queue.side_effect = [
            [],  # pending
            [queue_item],  # failed
        ]

        attachment = Attachment(
            id="attach_1",
            note_id="client_1_note_1",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.return_value = attachment

        with patch("src.extractors.attachment_downloader.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/path/to/file.pdf",
            }
            mock_downloader_class.return_value = mock_downloader

            result = coordinator._process_attachment_queue("snapshot_123")

        assert result["downloaded"] == 1
        assert result["failed"] == 0

    def test_process_attachment_queue_successful_download(self, coordinator, mock_repository):
        """Test _process_attachment_queue updates attachment metadata on success."""
        from src.models import AttachmentQueueItem

        queue_item = AttachmentQueueItem(
            map_snapshot_id="snapshot_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_queue.side_effect = [[queue_item], []]

        attachment = Attachment(
            id="attach_1",
            note_id="client_1_note_1",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.return_value = attachment

        with patch("src.extractors.attachment_downloader.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/downloads/test.pdf",
            }
            mock_downloader_class.return_value = mock_downloader

            coordinator._process_attachment_queue("snapshot_123")

        # Verify attachment was saved with updated file path
        save_calls = mock_repository.save_attachments.call_args_list
        assert len(save_calls) == 1
        saved_attachment = save_calls[0][0][0][0]
        assert saved_attachment.local_file_path == "/downloads/test.pdf"

    def test_process_attachment_queue_failed_download(self, coordinator, mock_repository):
        """Test _process_attachment_queue handles download failures."""
        from src.models import AttachmentQueueItem

        queue_item = AttachmentQueueItem(
            map_snapshot_id="snapshot_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_queue.side_effect = [[queue_item], []]

        attachment = Attachment(
            id="attach_1",
            note_id="client_1_note_1",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.return_value = attachment

        with patch("src.extractors.attachment_downloader.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader.download_attachment.return_value = {
                "success": False,
                "error_message": "Network error",
            }
            mock_downloader_class.return_value = mock_downloader

            result = coordinator._process_attachment_queue("snapshot_123")

        assert result["downloaded"] == 0
        assert result["failed"] == 1

        # Verify queue item was marked as failed
        update_calls = mock_repository.update_attachment_queue_status.call_args_list
        final_call = update_calls[1][0][0]
        assert final_call.status == "failed"
        assert final_call.last_error == "Network error"

    def test_process_attachment_queue_attachment_not_found(self, coordinator, mock_repository):
        """Test _process_attachment_queue handles missing attachment in database."""
        from src.models import AttachmentQueueItem

        queue_item = AttachmentQueueItem(
            map_snapshot_id="snapshot_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_queue.side_effect = [[queue_item], []]
        mock_repository.get_attachment_by_id.return_value = None

        result = coordinator._process_attachment_queue("snapshot_123")

        assert result["downloaded"] == 0
        assert result["failed"] == 1

        # Verify queue item was marked as failed
        update_calls = mock_repository.update_attachment_queue_status.call_args_list
        final_call = update_calls[1][0][0]
        assert final_call.status == "failed"
        assert "Attachment not found" in final_call.last_error

    def test_process_attachment_queue_status_transitions(self, coordinator, mock_repository):
        """Test _process_attachment_queue updates status transitions."""
        from src.models import AttachmentQueueItem

        queue_item = AttachmentQueueItem(
            map_snapshot_id="snapshot_123",
            attachment_id="attach_1",
            parent_type="clients",
            parent_id="client_1",
            status="pending",
            attempt_count=0,
            updated_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_queue.side_effect = [[queue_item], []]

        attachment = Attachment(
            id="attach_1",
            note_id="client_1_note_1",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.return_value = attachment

        with patch("src.extractors.attachment_downloader.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/path/to/file.pdf",
            }
            mock_downloader_class.return_value = mock_downloader

            coordinator._process_attachment_queue("snapshot_123")

        # Verify status transitions occurred (2 updates per item)
        update_calls = mock_repository.update_attachment_queue_status.call_args_list
        assert len(update_calls) == 2  # One for in_progress, one for done/failed
        # Final status should be done (since download succeeded)
        assert queue_item.status == "done"

    # ==================== Test _validate_completeness() ====================

    def test_validate_completeness_no_discrepancies(self, coordinator, mock_repository):
        """Test _validate_completeness with perfect extraction."""
        mock_repository.get_entity_inventory.return_value = [
            Mock(entity_id="client_1"),
            Mock(entity_id="client_2"),
        ]

        entity_results = {"clients": {"extracted": 2, "failed": 0}}
        attachment_result = {"downloaded": 5, "failed": 0, "skipped": 0}

        discrepancies = coordinator._validate_completeness(
            "snapshot_123", ["clients"], entity_results, attachment_result
        )

        assert len(discrepancies) == 0

    def test_validate_completeness_entity_count_mismatch(self, coordinator, mock_repository):
        """Test _validate_completeness detects entity count mismatch."""
        mock_repository.get_entity_inventory.return_value = [
            Mock(entity_id="client_1"),
            Mock(entity_id="client_2"),
            Mock(entity_id="client_3"),
        ]

        entity_results = {"clients": {"extracted": 2, "failed": 0}}
        attachment_result = {"downloaded": 0, "failed": 0, "skipped": 0}

        discrepancies = coordinator._validate_completeness(
            "snapshot_123", ["clients"], entity_results, attachment_result
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "entity_count_mismatch"
        assert discrepancies[0]["severity"] == "error"
        assert discrepancies[0]["expected"] == 3
        assert discrepancies[0]["actual"] == 2

    def test_validate_completeness_failed_entities_warning(self, coordinator, mock_repository):
        """Test _validate_completeness creates warning for <10% failed."""
        mock_repository.get_entity_inventory.return_value = [Mock(entity_id=f"client_{i}") for i in range(100)]

        entity_results = {"clients": {"extracted": 95, "failed": 5}}
        attachment_result = {"downloaded": 0, "failed": 0, "skipped": 0}

        discrepancies = coordinator._validate_completeness(
            "snapshot_123", ["clients"], entity_results, attachment_result
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "failed_entities"
        assert discrepancies[0]["severity"] == "warning"
        assert discrepancies[0]["difference"] == 5

    def test_validate_completeness_failed_entities_error(self, coordinator, mock_repository):
        """Test _validate_completeness creates error for >10% failed."""
        mock_repository.get_entity_inventory.return_value = [Mock(entity_id=f"client_{i}") for i in range(100)]

        entity_results = {"clients": {"extracted": 85, "failed": 15}}
        attachment_result = {"downloaded": 0, "failed": 0, "skipped": 0}

        discrepancies = coordinator._validate_completeness(
            "snapshot_123", ["clients"], entity_results, attachment_result
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "failed_entities"
        assert discrepancies[0]["severity"] == "error"
        assert discrepancies[0]["difference"] == 15

    def test_validate_completeness_failed_attachments(self, coordinator, mock_repository):
        """Test _validate_completeness detects failed attachments."""
        mock_repository.get_entity_inventory.return_value = []

        entity_results = {}
        attachment_result = {"downloaded": 90, "failed": 10, "skipped": 0}

        discrepancies = coordinator._validate_completeness(
            "snapshot_123", [], entity_results, attachment_result
        )

        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "failed_attachments"
        assert discrepancies[0]["severity"] == "error"
        assert discrepancies[0]["difference"] == 10

    def test_validate_completeness_multiple_discrepancies(self, coordinator, mock_repository):
        """Test _validate_completeness detects multiple discrepancies."""
        mock_repository.get_entity_inventory.side_effect = [
            [Mock(entity_id="client_1"), Mock(entity_id="client_2")],  # clients
            [Mock(entity_id="invoice_1")],  # invoices
        ]

        entity_results = {
            "clients": {"extracted": 1, "failed": 1},
            "invoices": {"extracted": 0, "failed": 0},
        }
        attachment_result = {"downloaded": 5, "failed": 5, "skipped": 0}

        discrepancies = coordinator._validate_completeness(
            "snapshot_123", ["clients", "invoices"], entity_results, attachment_result
        )

        # Should have: clients failed (1), invoices count mismatch (1), failed attachments (1)
        assert len(discrepancies) == 3
        types = [d["type"] for d in discrepancies]
        assert "failed_entities" in types
        assert "entity_count_mismatch" in types
        assert "failed_attachments" in types

    # ==================== Test get_queue_status() ====================

    def test_get_queue_status_for_single_entity_type(self, coordinator, mock_repository, sample_snapshot):
        """Test get_queue_status returns status for single entity type."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot

        # Mock queue items for different statuses
        def queue_side_effect(snapshot_id, entity_type, status=None):
            if status == "pending":
                return [Mock(), Mock()]
            elif status == "in_progress":
                return [Mock()]
            elif status == "done":
                return [Mock(), Mock(), Mock()]
            elif status == "failed":
                return [Mock()]
            return []

        mock_repository.get_extract_queue.side_effect = queue_side_effect

        result = coordinator.get_queue_status("snapshot_123", "clients")

        assert "clients" in result
        assert result["clients"]["pending"] == 2
        assert result["clients"]["in_progress"] == 1
        assert result["clients"]["done"] == 3
        assert result["clients"]["failed"] == 1
        assert result["clients"]["total"] == 7

    def test_get_queue_status_for_all_entity_types(self, coordinator, mock_repository, sample_snapshot):
        """Test get_queue_status returns status for all entity types."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []

        result = coordinator.get_queue_status("snapshot_123")

        assert "clients" in result
        assert "invoices" in result

    def test_get_queue_status_empty_queues(self, coordinator, mock_repository, sample_snapshot):
        """Test get_queue_status with empty queues."""
        mock_repository.get_map_snapshot.return_value = sample_snapshot
        mock_repository.get_extract_queue.return_value = []

        result = coordinator.get_queue_status("snapshot_123", "clients")

        assert result["clients"]["total"] == 0
        assert result["clients"]["pending"] == 0

    def test_get_queue_status_invalid_snapshot(self, coordinator, mock_repository):
        """Test get_queue_status raises error for invalid snapshot."""
        mock_repository.get_map_snapshot.return_value = None

        with pytest.raises(ValueError, match="Map snapshot not found"):
            coordinator.get_queue_status("invalid_snapshot")

    # ==================== Test _create_extractor() ====================

    def test_create_extractor_returns_correct_class(self, coordinator):
        """Test _create_extractor returns appropriate extractor instance."""
        extractor = coordinator._create_extractor("clients", "snapshot_123")

        assert isinstance(extractor, ClientsExtractor)

    @pytest.mark.skip(reason="Attachment queuing feature not yet implemented in extractors")
    def test_create_extractor_enables_attachment_queuing(self, coordinator):
        """Test _create_extractor enables attachment queuing."""
        extractor = coordinator._create_extractor("clients", "snapshot_123")

        assert extractor._queue_attachments is True
        assert extractor._map_snapshot_id == "snapshot_123"

    def test_create_extractor_invalid_entity_type(self, coordinator):
        """Test _create_extractor raises error for invalid entity type."""
        with pytest.raises(ValueError, match="No extractor found"):
            coordinator._create_extractor("invalid_type", "snapshot_123")
