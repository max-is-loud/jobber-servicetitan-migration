"""Unit tests for AttachmentDownloader."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open
import hashlib

import pytest
import requests

from src.extractors.attachment_downloader import AttachmentDownloader
from src.repositories import Repository
from src.interfaces import Logger
from src.models import Attachment
from src.exceptions import ConfigurationError


class TestAttachmentDownloader:
    """Test suite for AttachmentDownloader."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_init_creates_download_directory(self):
        """Test initialization creates download directory."""
        download_path = os.path.join(self.temp_dir, "attachments")

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=download_path,
        )

        assert os.path.exists(download_path)
        assert os.path.isdir(download_path)
        assert downloader._base_download_path == download_path

    def test_init_with_custom_parameters(self):
        """Test initialization with custom retry and timeout settings."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
            max_retries=5,
            chunk_size=4096,
            connect_timeout=60,
            read_timeout=600,
        )

        assert downloader._max_retries == 5
        assert downloader._chunk_size == 4096
        assert downloader._connect_timeout == 60
        assert downloader._read_timeout == 600

    def test_init_creates_http_session_with_retry(self):
        """Test HTTP session is configured with retry strategy."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        assert downloader._session is not None
        assert isinstance(downloader._session, requests.Session)

    def test_validate_url_accepts_https_jobber_domains(self):
        """Test URL validation accepts HTTPS URLs from allowed Jobber domains."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        valid_urls = [
            "https://getjobber.com/files/test.pdf",
            "https://cdn.getjobber.com/attachments/image.png",
            "https://assets.getjobber.com/docs/file.docx",
            "https://jobber.s3.amazonaws.com/bucket/file.jpg",
            "https://jobber-attachments.s3.amazonaws.com/file.pdf",
            "https://subdomain.getjobber.com/file.txt",
        ]

        for url in valid_urls:
            is_valid, error = downloader._validate_url(url)
            assert is_valid, f"URL {url} should be valid, got error: {error}"
            assert error == ""

    def test_validate_url_rejects_http_protocol(self):
        """Test URL validation rejects HTTP (non-HTTPS) URLs."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        is_valid, error = downloader._validate_url("http://getjobber.com/file.pdf")

        assert not is_valid
        assert "HTTPS" in error
        assert "http" in error.lower()

    def test_validate_url_rejects_unauthorized_domains(self):
        """Test URL validation rejects URLs from unauthorized domains."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        unauthorized_urls = [
            "https://evil.com/file.pdf",
            "https://malicious.example.com/steal.exe",
            "https://internal.company.local/secrets.txt",
            "https://192.168.1.1/admin",
        ]

        for url in unauthorized_urls:
            is_valid, error = downloader._validate_url(url)
            assert not is_valid, f"URL {url} should be rejected"
            assert "not in the allowed domains" in error

    def test_validate_url_rejects_empty_url(self):
        """Test URL validation rejects empty or None URLs."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        is_valid, error = downloader._validate_url("")
        assert not is_valid
        assert "empty" in error.lower()

        is_valid, error = downloader._validate_url(None)
        assert not is_valid

    def test_validate_url_rejects_malformed_urls(self):
        """Test URL validation rejects malformed URLs."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        malformed_urls = [
            "not-a-url",
            "ftp://getjobber.com/file.pdf",
            "javascript:alert('xss')",
            "file:///etc/passwd",
        ]

        for url in malformed_urls:
            is_valid, error = downloader._validate_url(url)
            assert not is_valid, f"Malformed URL {url} should be rejected"

    def test_validate_dependencies_success(self):
        """Test validate_dependencies succeeds with valid configuration."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        result = downloader.validate_dependencies()
        assert result is True

    def test_validate_dependencies_fails_without_logger(self):
        """Test validate_dependencies raises error if logger is missing."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=None,
            base_download_path=self.temp_dir,
        )

        with pytest.raises(ConfigurationError, match="Logger dependency is required"):
            downloader.validate_dependencies()

    def test_validate_dependencies_fails_without_repository(self):
        """Test validate_dependencies raises error if repository is missing."""
        downloader = AttachmentDownloader(
            repository=None,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        with pytest.raises(ConfigurationError, match="Repository dependency is required"):
            downloader.validate_dependencies()

    def test_validate_dependencies_fails_with_readonly_directory(self):
        """Test validate_dependencies raises error if directory is not writable."""
        readonly_dir = os.path.join(self.temp_dir, "readonly")
        os.makedirs(readonly_dir, mode=0o444)  # Read-only directory

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=readonly_dir,
        )

        try:
            with pytest.raises(ConfigurationError, match="not writable"):
                downloader.validate_dependencies()
        finally:
            # Cleanup: restore permissions
            os.chmod(readonly_dir, 0o755)

    @patch("requests.Session.get")
    def test_download_attachment_success(self, mock_get):
        """Test successful attachment download with hash calculation."""
        # Setup mock response
        test_content = b"Test file content for attachment"
        test_hash = hashlib.sha256(test_content).hexdigest()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [test_content]
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_response

        # Setup attachment
        attachment = Attachment(
            id="att_123",
            note_id="note_456",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://getjobber.com/files/test.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2024-01-01T00:00:00Z",
        )

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        # Execute download
        result = downloader.download_attachment(attachment)

        # Verify result
        assert result["success"] is True
        assert result["bytes_downloaded"] == len(test_content)
        assert result["hash"] == test_hash
        assert "local_file_path" in result
        assert result["local_file_path"].endswith(".pdf")
        assert test_hash in result["local_file_path"]

        # Verify HTTP call
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_download_attachment_invalid_url(self, mock_get):
        """Test download fails with invalid URL."""
        attachment = Attachment(
            id="att_123",
            note_id="note_456",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="http://evil.com/malware.exe",  # HTTP + unauthorized domain
            local_file_path=None,
            file_size=1024,
            created_at="2024-01-01T00:00:00Z",
        )

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        result = downloader.download_attachment(attachment)

        # Verify failure
        assert result["success"] is False
        assert "error_message" in result
        assert "HTTPS" in result["error_message"] or "allowed domains" in result["error_message"]

        # Verify no HTTP call was made
        mock_get.assert_not_called()

    @patch("requests.Session.get")
    def test_download_attachment_http_error(self, mock_get):
        """Test download handles HTTP errors gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_response

        attachment = Attachment(
            id="att_123",
            note_id="note_456",
            file_name="test.pdf",
            content_type="application/pdf",
            original_url="https://getjobber.com/files/missing.pdf",
            local_file_path=None,
            file_size=1024,
            created_at="2024-01-01T00:00:00Z",
        )

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        result = downloader.download_attachment(attachment)

        # Verify failure
        assert result["success"] is False
        assert "error_message" in result
        assert "404" in result["error_message"] or "Not Found" in result["error_message"]

    def test_download_all_pending_empty_queue(self):
        """Test download_all_pending handles empty queue gracefully."""
        self.mock_repository.get_pending_attachments.return_value = []

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        stats = downloader.download_all_pending(batch_size=10)

        # Verify stats
        assert stats["success"] == 0
        assert stats["failed"] == 0
        assert stats["skipped"] == 0
        assert stats["total_bytes"] == 0

    @patch("requests.Session.get")
    def test_download_all_pending_batch_processing(self, mock_get):
        """Test download_all_pending processes attachments in batches."""
        # Setup mock response
        test_content = b"Test content"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [test_content]
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_response

        # Setup attachments
        attachments = [
            Attachment(
                id=f"att_{i}",
                note_id="note_1",
                file_name=f"file_{i}.pdf",
                content_type="application/pdf",
                original_url=f"https://getjobber.com/files/file_{i}.pdf",
                local_file_path=None,
                file_size=100,
                created_at="2024-01-01T00:00:00Z",
            )
            for i in range(5)
        ]

        # Mock repository to return batch then empty
        self.mock_repository.get_pending_attachments.side_effect = [
            attachments,
            [],
        ]

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        stats = downloader.download_all_pending(batch_size=10)

        # Verify stats
        assert stats["success"] == 5
        assert stats["failed"] == 0
        assert stats["total_bytes"] == len(test_content) * 5

    def test_allowed_domains_configuration(self):
        """Test that allowed domains are properly configured."""
        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
        )

        # Verify key Jobber domains are allowed
        assert "getjobber.com" in downloader._allowed_domains
        assert "cdn.getjobber.com" in downloader._allowed_domains
        assert "assets.getjobber.com" in downloader._allowed_domains

        # Verify S3 buckets are configured
        assert any("s3.amazonaws.com" in domain for domain in downloader._allowed_domains)

    def test_timeout_configuration(self):
        """Test that HTTP timeouts are configurable."""
        custom_connect = 45
        custom_read = 400

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
            connect_timeout=custom_connect,
            read_timeout=custom_read,
        )

        assert downloader._connect_timeout == custom_connect
        assert downloader._read_timeout == custom_read

    def test_chunk_size_configuration(self):
        """Test that download chunk size is configurable."""
        custom_chunk_size = 16384

        downloader = AttachmentDownloader(
            repository=self.mock_repository,
            logger=self.mock_logger,
            base_download_path=self.temp_dir,
            chunk_size=custom_chunk_size,
        )

        assert downloader._chunk_size == custom_chunk_size
