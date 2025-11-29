"""Unit tests for DownloadModeCoordinator."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.coordinators.download_mode_coordinator import DownloadModeCoordinator
from src.interfaces import Logger
from src.models import Attachment, AttachmentQueueItem, DownloadFilters
from src.repositories import Repository


class TestDownloadModeCoordinator:
    """Test suite for DownloadModeCoordinator."""

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
    def mock_config_manager(self):
        """Create mock ConfigManager."""
        config = Mock()
        config.get_reports_dir.return_value = Path("./reports")
        config.get_attachment_config.return_value = {"concurrent_downloads": 3}
        return config

    @pytest.fixture
    def coordinator(self, mock_repository, mock_logger, mock_config_manager):
        """Create DownloadModeCoordinator instance."""
        return DownloadModeCoordinator(
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

    @pytest.fixture
    def sample_queue_items(self):
        """Create sample attachment queue items."""
        return [
            AttachmentQueueItem(
                attachment_id="att_1",
                parent_type="clients",
                parent_id="client_1",
                status="pending",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
            ),
            AttachmentQueueItem(
                attachment_id="att_2",
                parent_type="invoices",
                parent_id="invoice_1",
                status="pending",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
            ),
            AttachmentQueueItem(
                attachment_id="att_3",
                parent_type="clients",
                parent_id="client_2",
                status="pending",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
            ),
        ]

    @pytest.fixture
    def sample_attachment(self):
        """Create sample attachment."""
        return Attachment(
            id="att_1",
            note_id="note_1",
            file_name="document.pdf",
            content_type="application/pdf",
            original_url="https://jobber.s3.amazonaws.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )

    # ==================== Test run_download_pass() ====================

    def test_run_download_pass_success(self, coordinator, mock_repository, sample_queue_items, sample_attachment):
        """Test successful download pass with all items downloaded."""
        mock_repository.get_attachment_queue.return_value = sample_queue_items
        mock_repository.get_attachment_by_id.return_value = sample_attachment

        with patch("src.coordinators.download_mode_coordinator.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader_class.return_value = mock_downloader
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/tmp/document.pdf",
                "bytes_downloaded": 1024,
                "error_message": "",
            }

            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")

                result = coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    dry_run=False,
                )

        assert result["snapshot_id"] == "snap_123"
        assert result["total_attachments"] == 3
        assert result["downloaded"] == 3
        assert result["failed"] == 0
        assert result["total_bytes"] == 3072  # 3 * 1024

    def test_run_download_pass_with_failures(self, coordinator, mock_repository, sample_queue_items, sample_attachment):
        """Test download pass handles failures gracefully."""
        mock_repository.get_attachment_queue.return_value = sample_queue_items
        mock_repository.get_attachment_by_id.return_value = sample_attachment

        with patch("src.coordinators.download_mode_coordinator.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader_class.return_value = mock_downloader
            # First download succeeds, second fails, third succeeds
            mock_downloader.download_attachment.side_effect = [
                {"success": True, "local_file_path": "/tmp/doc1.pdf", "bytes_downloaded": 1024, "error_message": ""},
                {"success": False, "local_file_path": "", "bytes_downloaded": 0, "error_message": "Network timeout"},
                {"success": True, "local_file_path": "/tmp/doc3.pdf", "bytes_downloaded": 2048, "error_message": ""},
            ]

            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")

                result = coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    dry_run=False,
                )

        assert result["downloaded"] == 2
        assert result["failed"] == 1
        assert result["total_bytes"] == 3072  # 1024 + 2048

    def test_run_download_pass_empty_queue(self, coordinator, mock_repository):
        """Test download pass handles empty queue gracefully."""
        mock_repository.get_attachment_queue.return_value = []

        result = coordinator.run_download_pass(
            snapshot_id="snap_123",
            dry_run=False,
        )

        assert result["total_attachments"] == 0
        assert result["downloaded"] == 0
        assert result["failed"] == 0

    def test_run_download_pass_dry_run(self, coordinator, mock_repository, sample_queue_items):
        """Test dry run mode previews queue without downloading."""
        mock_repository.get_attachment_queue.return_value = sample_queue_items

        result = coordinator.run_download_pass(
            snapshot_id="snap_123",
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["total_attachments"] == 3
        assert "by_entity_type" in result
        assert result["by_entity_type"]["clients"] == 2
        assert result["by_entity_type"]["invoices"] == 1
        # Verify no actual downloads happened
        mock_repository.get_attachment_by_id.assert_not_called()

    # ==================== Test resume mode ====================

    def test_resume_mode_skips_completed(self, coordinator, mock_repository, sample_queue_items):
        """Test resume mode only processes pending and failed items."""
        pending_items = [sample_queue_items[0]]
        failed_items = [sample_queue_items[1]]
        mock_repository.get_attachment_queue.side_effect = [
            pending_items,  # First call for pending
            failed_items,  # Second call for failed
        ]

        with patch.object(coordinator, "_process_downloads") as mock_process:
            mock_process.return_value = {"downloaded": 2, "failed": 0, "total_bytes": 2048}
            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    resume=True,
                    dry_run=False,
                )

        # Should fetch pending + failed
        assert mock_repository.get_attachment_queue.call_count == 2
        mock_repository.get_attachment_queue.assert_any_call("snap_123", status="pending")
        mock_repository.get_attachment_queue.assert_any_call("snap_123", status="failed")

    def test_normal_mode_only_pending(self, coordinator, mock_repository, sample_queue_items):
        """Test normal mode only processes pending items."""
        mock_repository.get_attachment_queue.return_value = [sample_queue_items[0]]

        with patch.object(coordinator, "_process_downloads") as mock_process:
            mock_process.return_value = {"downloaded": 1, "failed": 0, "total_bytes": 1024}
            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    resume=False,
                    dry_run=False,
                )

        # Should only fetch pending, not failed
        mock_repository.get_attachment_queue.assert_called_once_with("snap_123", status="pending")

    # ==================== Test filtering ====================

    def test_filter_by_entity_type(self, coordinator, mock_repository, sample_queue_items):
        """Test filtering downloads by entity type."""
        mock_repository.get_attachment_queue.return_value = sample_queue_items

        with patch.object(coordinator, "_process_downloads") as mock_process:
            mock_process.return_value = {"downloaded": 2, "failed": 0, "total_bytes": 2048}
            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    entity_types=["clients"],
                    dry_run=False,
                )

        # Should only process client items
        call_args = mock_process.call_args[1]
        filtered_items = call_args["queue_items"]
        assert len(filtered_items) == 2
        assert all(item.parent_type == "clients" for item in filtered_items)

    def test_filter_by_file_type(self, coordinator, mock_repository):
        """Test filtering downloads by file type."""
        queue_items = [
            AttachmentQueueItem(
                attachment_id="att_pdf",
                parent_type="clients",
                parent_id="client_1",
                status="pending",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
            ),
            AttachmentQueueItem(
                attachment_id="att_jpg",
                parent_type="clients",
                parent_id="client_2",
                status="pending",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
            ),
        ]
        mock_repository.get_attachment_queue.return_value = queue_items

        # Mock attachments with different file types
        pdf_attachment = Attachment(
            id="att_pdf",
            note_id="note_1",
            file_name="document.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )
        jpg_attachment = Attachment(
            id="att_jpg",
            note_id="note_2",
            file_name="image.jpg",
            content_type="image/jpeg",
            original_url="https://example.com/image.jpg",
            local_file_path=None,
            file_size=2048,
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.side_effect = [pdf_attachment, jpg_attachment]

        filters = DownloadFilters(file_types=["pdf"])

        with patch.object(coordinator, "_process_downloads") as mock_process:
            mock_process.return_value = {"downloaded": 1, "failed": 0, "total_bytes": 1024}
            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    filters=filters,
                    dry_run=False,
                )

        # Should only process PDF items
        call_args = mock_process.call_args[1]
        filtered_items = call_args["queue_items"]
        assert len(filtered_items) == 1
        assert filtered_items[0].attachment_id == "att_pdf"

    def test_filter_by_size(self, coordinator, mock_repository):
        """Test filtering downloads by file size."""
        queue_items = [
            AttachmentQueueItem(
                attachment_id="att_small",
                parent_type="clients",
                parent_id="client_1",
                status="pending",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
            ),
            AttachmentQueueItem(
                attachment_id="att_large",
                parent_type="clients",
                parent_id="client_2",
                status="pending",
                map_snapshot_id="snap_123",
                updated_at="2023-11-15T10:00:00Z",
            ),
        ]
        mock_repository.get_attachment_queue.return_value = queue_items

        # Mock attachments with different sizes
        small_attachment = Attachment(
            id="att_small",
            note_id="note_1",
            file_name="small.pdf",
            content_type="application/pdf",
            original_url="https://example.com/small.pdf",
            local_file_path=None,
            file_size=512,  # 512 bytes
            created_at="2023-11-15T10:00:00Z",
        )
        large_attachment = Attachment(
            id="att_large",
            note_id="note_2",
            file_name="large.pdf",
            content_type="application/pdf",
            original_url="https://example.com/large.pdf",
            local_file_path=None,
            file_size=5 * 1024 * 1024,  # 5 MB
            created_at="2023-11-15T10:00:00Z",
        )
        mock_repository.get_attachment_by_id.side_effect = [small_attachment, large_attachment]

        # Filter: max_size = 1 MB
        filters = DownloadFilters(max_size=1 * 1024 * 1024)

        with patch.object(coordinator, "_process_downloads") as mock_process:
            mock_process.return_value = {"downloaded": 1, "failed": 0, "total_bytes": 512}
            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    filters=filters,
                    dry_run=False,
                )

        # Should only process small file
        call_args = mock_process.call_args[1]
        filtered_items = call_args["queue_items"]
        assert len(filtered_items) == 1
        assert filtered_items[0].attachment_id == "att_small"

    # ==================== Test attachment not found handling ====================

    def test_attachment_not_found_marked_as_failed(self, coordinator, mock_repository, sample_queue_items):
        """Test that missing attachments are marked as failed."""
        mock_repository.get_attachment_queue.return_value = [sample_queue_items[0]]
        mock_repository.get_attachment_by_id.return_value = None  # Attachment not found

        with patch("src.coordinators.download_mode_coordinator.AttachmentDownloader"):
            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                result = coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    dry_run=False,
                )

        assert result["downloaded"] == 0
        assert result["failed"] == 1
        # Verify status was updated
        assert mock_repository.update_attachment_queue_status.called

    # ==================== Test custom output directory ====================

    def test_custom_output_directory(self, coordinator, mock_repository, sample_queue_items, sample_attachment):
        """Test download pass respects custom output directory."""
        mock_repository.get_attachment_queue.return_value = sample_queue_items
        mock_repository.get_attachment_by_id.return_value = sample_attachment

        custom_dir = Path("/custom/downloads")

        with patch("src.coordinators.download_mode_coordinator.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader_class.return_value = mock_downloader
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/custom/downloads/document.pdf",
                "bytes_downloaded": 1024,
                "error_message": "",
            }

            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    output_dir=custom_dir,
                    dry_run=False,
                )

        # Verify downloader was created with custom path (3 times, once per attachment)
        assert mock_downloader_class.call_count == 3
        # Check that all calls used the custom path
        for call in mock_downloader_class.call_args_list:
            call_kwargs = call[1]
            assert call_kwargs["base_download_path"] == str(custom_dir)

    # ==================== Test progress tracking ====================

    def test_progress_tracking_updates(self, coordinator, mock_repository, sample_queue_items, sample_attachment):
        """Test that progress is tracked and status transitions occur."""
        mock_repository.get_attachment_queue.return_value = [sample_queue_items[0]]
        mock_repository.get_attachment_by_id.return_value = sample_attachment

        # Capture status values at time of each call
        captured_statuses = []

        def capture_status(queue_item):
            captured_statuses.append(queue_item.status)

        mock_repository.update_attachment_queue_status.side_effect = capture_status

        with patch("src.coordinators.download_mode_coordinator.AttachmentDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader_class.return_value = mock_downloader
            mock_downloader.download_attachment.return_value = {
                "success": True,
                "local_file_path": "/tmp/document.pdf",
                "bytes_downloaded": 1024,
                "error_message": "",
            }

            with patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator") as mock_report_gen_class:
                mock_report_gen = Mock()
                mock_report_gen_class.return_value = mock_report_gen
                mock_report_gen.generate_report.return_value = ("report.md", "report.json")
                coordinator.run_download_pass(
                    snapshot_id="snap_123",
                    dry_run=False,
                )

        # Verify status transitions: pending → done
        assert len(captured_statuses) >= 1  # At least done status
        assert captured_statuses[-1] == "done"  # Final status is done
