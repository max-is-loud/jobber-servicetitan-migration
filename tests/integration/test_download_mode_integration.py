"""Integration tests for download pass workflow.

Tests the complete download pass workflow including Map → Extract → Download
with real database operations and mocked S3 downloads.
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, UTC

import pytest

from src.coordinators.download_mode_coordinator import DownloadModeCoordinator
from src.coordinators.extract_mode_coordinator import ExtractModeCoordinator
from src.coordinators.map_mode_coordinator import MapModeCoordinator
from src.interfaces import Logger
from src.models import (
    Attachment,
    AttachmentQueueItem,
    DownloadFilters,
    MapSnapshot,
)
from src.repositories import Repository


@pytest.mark.integration
class TestDownloadModeIntegration:
    """Integration tests for download mode coordinator."""

    @pytest.fixture
    def db_connection(self):
        """Create in-memory database connection."""
        conn = sqlite3.connect(":memory:")
        yield conn
        conn.close()

    @pytest.fixture
    def temp_download_dir(self):
        """Create temporary download directory."""
        import shutil

        temp_dir = tempfile.mkdtemp(prefix="test_downloads_")
        temp_path = Path(temp_dir)
        yield temp_path
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def repository(self, db_connection):
        """Create real repository with in-memory database."""
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
        logger.error = Mock()
        return logger

    @pytest.fixture
    def mock_config_manager(self, temp_download_dir):
        """Create mock config manager."""
        config = Mock()
        config.get_reports_dir.return_value = temp_download_dir / "reports"
        return config

    @pytest.fixture
    def coordinator(self, repository, mock_logger, mock_config_manager):
        """Create DownloadModeCoordinator with real repository."""
        return DownloadModeCoordinator(
            repository=repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

    @pytest.fixture
    def sample_snapshot(self, repository):
        """Create and save sample map snapshot."""
        snapshot = MapSnapshot(
            id="snap_integration_test",
            created_at=datetime.now(UTC).isoformat(),
            pass1_cutoff=datetime.now(UTC).isoformat(),
            label="integration-test",
            entities_included='["clients"]',
        )
        repository.save_map_snapshot(snapshot)
        return snapshot

    @pytest.fixture
    def sample_attachments_in_db(self, repository):
        """Create sample attachments in database."""
        attachments = [
            Attachment(
                id="att_pdf_1",
                note_id="note_1",
                file_name="document.pdf",
                content_type="application/pdf",
                original_url="https://jobber.s3.amazonaws.com/documents/doc1.pdf",
                local_file_path=None,
                file_size=2048,
                created_at=datetime.now(UTC).isoformat(),
            ),
            Attachment(
                id="att_jpg_1",
                note_id="note_2",
                file_name="photo.jpg",
                content_type="image/jpeg",
                original_url="https://jobber.s3.amazonaws.com/photos/photo1.jpg",
                local_file_path=None,
                file_size=512000,
                created_at=datetime.now(UTC).isoformat(),
            ),
            Attachment(
                id="att_pdf_2",
                note_id="note_3",
                file_name="invoice.pdf",
                content_type="application/pdf",
                original_url="https://jobber.s3.amazonaws.com/invoices/inv1.pdf",
                local_file_path=None,
                file_size=1024,
                created_at=datetime.now(UTC).isoformat(),
            ),
        ]
        repository.save_attachments(attachments)
        return attachments

    @pytest.fixture
    def sample_queue_items(self, repository, sample_snapshot, sample_attachments_in_db):
        """Create sample attachment queue items."""
        queue_data = [
            {
                "attachment_id": "att_pdf_1",
                "parent_type": "clients",
                "parent_id": "client_1",
            },
            {
                "attachment_id": "att_jpg_1",
                "parent_type": "invoices",
                "parent_id": "invoice_1",
            },
            {
                "attachment_id": "att_pdf_2",
                "parent_type": "invoices",
                "parent_id": "invoice_2",
            },
        ]
        repository.create_attachment_queue(sample_snapshot.id, queue_data)
        # Return the actual AttachmentQueueItem objects for test validation
        return repository.get_attachment_queue(sample_snapshot.id, status="pending")

    # ==================== Full Workflow Tests ====================

    @patch("src.coordinators.download_mode_coordinator.AttachmentDownloader")
    @patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator")
    def test_full_download_pass_workflow(
        self,
        mock_report_gen_class,
        mock_downloader_class,
        coordinator,
        repository,
        sample_snapshot,
        sample_queue_items,
        temp_download_dir,
    ):
        """Test complete Map → Extract → Download workflow end-to-end."""
        # Setup mocks
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader
        mock_downloader.download_attachment.return_value = {
            "success": True,
            "local_file_path": str(temp_download_dir / "downloaded.pdf"),
            "bytes_downloaded": 2048,
            "error_message": "",
        }

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen
        mock_report_gen.generate_report.return_value = ("report.md", "report.json")

        # Execute download pass
        result = coordinator.run_download_pass(
            snapshot_id=sample_snapshot.id,
            output_dir=temp_download_dir,
            dry_run=False,
        )

        # Verify results
        assert result["snapshot_id"] == sample_snapshot.id
        assert result["total_attachments"] == 3
        assert result["downloaded"] == 3
        assert result["failed"] == 0
        assert result["total_bytes"] == 3 * 2048  # 3 successful downloads

        # Verify queue status transitions in database
        completed_items = repository.get_attachment_queue(sample_snapshot.id, status="done")
        assert len(completed_items) == 3

        # Verify all items marked as done
        for item in completed_items:
            assert item.status == "done"
            assert item.last_error is None

    @patch("src.coordinators.download_mode_coordinator.AttachmentDownloader")
    @patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator")
    def test_download_resume_after_interruption(
        self,
        mock_report_gen_class,
        mock_downloader_class,
        coordinator,
        repository,
        sample_snapshot,
        sample_queue_items,
        temp_download_dir,
    ):
        """Test resume functionality after simulated interruption."""
        # Simulate partial completion - mark first item as done
        first_item = sample_queue_items[0]
        first_item.status = "done"
        first_item.updated_at = datetime.now(UTC).isoformat()
        repository.update_attachment_queue_status(first_item)

        # Setup mocks for remaining downloads
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader
        mock_downloader.download_attachment.return_value = {
            "success": True,
            "local_file_path": str(temp_download_dir / "resumed.pdf"),
            "bytes_downloaded": 1024,
            "error_message": "",
        }

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen
        mock_report_gen.generate_report.return_value = ("resume_report.md", "resume_report.json")

        # Execute download pass with resume=True
        result = coordinator.run_download_pass(
            snapshot_id=sample_snapshot.id,
            resume=True,
            output_dir=temp_download_dir,
            dry_run=False,
        )

        # Verify only pending items were processed (2 remaining)
        assert result["total_attachments"] == 2  # Only pending items
        assert result["downloaded"] == 2
        assert result["failed"] == 0

        # Verify all items now done
        completed_items = repository.get_attachment_queue(sample_snapshot.id, status="done")
        assert len(completed_items) == 3

    @patch("src.coordinators.download_mode_coordinator.AttachmentDownloader")
    @patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator")
    def test_download_with_entity_filter(
        self,
        mock_report_gen_class,
        mock_downloader_class,
        coordinator,
        repository,
        sample_snapshot,
        sample_queue_items,
        temp_download_dir,
    ):
        """Test filtering downloads by entity type."""
        # Setup mocks
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader
        mock_downloader.download_attachment.return_value = {
            "success": True,
            "local_file_path": str(temp_download_dir / "filtered.pdf"),
            "bytes_downloaded": 1024,
            "error_message": "",
        }

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen
        mock_report_gen.generate_report.return_value = ("filter_report.md", "filter_report.json")

        # Execute download pass filtered to only "clients"
        result = coordinator.run_download_pass(
            snapshot_id=sample_snapshot.id,
            entity_types=["clients"],
            output_dir=temp_download_dir,
            dry_run=False,
        )

        # Verify only client attachments downloaded (1 out of 3)
        assert result["total_attachments"] == 1
        assert result["downloaded"] == 1
        assert result["failed"] == 0

        # Verify correct items processed
        done_items = repository.get_attachment_queue(sample_snapshot.id, status="done")
        assert len(done_items) == 1
        assert done_items[0].parent_type == "clients"

        # Verify invoices still pending
        pending_items = repository.get_attachment_queue(sample_snapshot.id, status="pending")
        assert len(pending_items) == 2
        assert all(item.parent_type == "invoices" for item in pending_items)

    @patch("src.coordinators.download_mode_coordinator.AttachmentDownloader")
    @patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator")
    def test_download_with_multiple_filters(
        self,
        mock_report_gen_class,
        mock_downloader_class,
        coordinator,
        repository,
        sample_snapshot,
        sample_queue_items,
        temp_download_dir,
    ):
        """Test combining file type and size filters."""
        # Setup mocks
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader
        mock_downloader.download_attachment.return_value = {
            "success": True,
            "local_file_path": str(temp_download_dir / "multi_filtered.pdf"),
            "bytes_downloaded": 1024,
            "error_message": "",
        }

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen
        mock_report_gen.generate_report.return_value = ("multi_filter_report.md", "multi_filter_report.json")

        # Create filters: PDFs only, max 1500 bytes (to exclude att_pdf_1)
        filters = DownloadFilters(
            file_types=["pdf"],
            max_size=1500,  # Should only match att_pdf_2 (1024 bytes), not att_pdf_1 (2048 bytes)
        )

        # Execute download pass with combined filters
        result = coordinator.run_download_pass(
            snapshot_id=sample_snapshot.id,
            filters=filters,
            output_dir=temp_download_dir,
            dry_run=False,
        )

        # Should only download att_pdf_2 (1024 bytes, PDF, <= 1500 bytes)
        # att_pdf_1 is 2048 bytes (exceeds max_size)
        # att_jpg_1 is not PDF
        assert result["total_attachments"] == 1
        assert result["downloaded"] == 1

    @patch("src.coordinators.download_mode_coordinator.AttachmentDownloader")
    @patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator")
    def test_download_report_generation(
        self,
        mock_report_gen_class,
        mock_downloader_class,
        coordinator,
        repository,
        sample_snapshot,
        sample_queue_items,
        temp_download_dir,
    ):
        """Test that download reports are generated correctly."""
        # Setup mocks
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader
        # Simulate 2 successes and 1 failure
        mock_downloader.download_attachment.side_effect = [
            {"success": True, "local_file_path": str(temp_download_dir / "doc1.pdf"), "bytes_downloaded": 2048, "error_message": ""},
            {"success": False, "local_file_path": "", "bytes_downloaded": 0, "error_message": "Network timeout"},
            {"success": True, "local_file_path": str(temp_download_dir / "doc2.pdf"), "bytes_downloaded": 1024, "error_message": ""},
        ]

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen
        test_md_path = temp_download_dir / "test_report.md"
        test_json_path = temp_download_dir / "test_report.json"
        mock_report_gen.generate_report.return_value = (str(test_md_path), str(test_json_path))

        # Execute download pass
        result = coordinator.run_download_pass(
            snapshot_id=sample_snapshot.id,
            output_dir=temp_download_dir,
            dry_run=False,
        )

        # Verify report generation was called
        assert mock_report_gen.generate_report.called
        report_call_args = mock_report_gen.generate_report.call_args[1]

        # Verify report arguments
        assert report_call_args["snapshot_id"] == sample_snapshot.id
        assert report_call_args["total_attachments"] == 3
        assert report_call_args["downloaded"] == 2
        assert report_call_args["failed"] == 1
        assert report_call_args["total_bytes"] == 3072  # 2048 + 1024
        assert len(report_call_args["failed_items"]) == 1

        # Verify result includes report paths
        assert "report_markdown" in result
        assert "report_json" in result

    @patch("src.coordinators.download_mode_coordinator.AttachmentDownloader")
    @patch("src.coordinators.download_mode_coordinator.DownloadReportGenerator")
    def test_attachment_queue_status_transitions(
        self,
        mock_report_gen_class,
        mock_downloader_class,
        coordinator,
        repository,
        sample_snapshot,
        sample_queue_items,
        temp_download_dir,
    ):
        """Verify attachment_queue status transitions through workflow."""
        # Setup mocks
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader
        mock_downloader.download_attachment.return_value = {
            "success": True,
            "local_file_path": str(temp_download_dir / "status_test.pdf"),
            "bytes_downloaded": 1024,
            "error_message": "",
        }

        mock_report_gen = Mock()
        mock_report_gen_class.return_value = mock_report_gen
        mock_report_gen.generate_report.return_value = ("status_report.md", "status_report.json")

        # Verify initial state - all pending
        pending_items = repository.get_attachment_queue(sample_snapshot.id, status="pending")
        assert len(pending_items) == 3

        # Execute download pass
        coordinator.run_download_pass(
            snapshot_id=sample_snapshot.id,
            output_dir=temp_download_dir,
            dry_run=False,
        )

        # Verify final state - all done
        done_items = repository.get_attachment_queue(sample_snapshot.id, status="done")
        assert len(done_items) == 3

        # Verify no pending items remain
        pending_items = repository.get_attachment_queue(sample_snapshot.id, status="pending")
        assert len(pending_items) == 0

        # Verify attachments updated with local file paths
        for queue_item in done_items:
            attachment = repository.get_attachment_by_id(queue_item.attachment_id)
            assert attachment is not None
            assert attachment.local_file_path is not None

    def test_dry_run_preview_no_downloads(
        self,
        coordinator,
        repository,
        sample_snapshot,
        sample_queue_items,
    ):
        """Test dry run mode previews queue without actual downloads."""
        # Execute dry run
        result = coordinator.run_download_pass(
            snapshot_id=sample_snapshot.id,
            dry_run=True,
        )

        # Verify dry run results
        assert result["dry_run"] is True
        assert result["total_attachments"] == 3
        assert "by_entity_type" in result
        assert result["by_entity_type"]["clients"] == 1
        assert result["by_entity_type"]["invoices"] == 2

        # Verify no downloads occurred - all items still pending
        pending_items = repository.get_attachment_queue(sample_snapshot.id, status="pending")
        assert len(pending_items) == 3

        # Verify no attachments have local paths
        for queue_item in pending_items:
            attachment = repository.get_attachment_by_id(queue_item.attachment_id)
            assert attachment.local_file_path is None
