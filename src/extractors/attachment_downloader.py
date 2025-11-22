"""AttachmentDownloader helper for downloading and managing attachment files."""

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..exceptions import ConfigurationError
from ..interfaces import Logger
from ..models import Attachment


class AttachmentDownloader:
    """
    Helper class for downloading attachment files from Jobber.

    Provides file download utilities for entity extractors to download
    attachment files after extracting metadata from noteAttachments fields.
    Attachments are now fetched inline with parent entities (Client, Job,
    Quote, Request, Invoice) rather than via a separate query.

    Features:
    - Binary file downloads with streaming for large files
    - Organized local storage: ./attachments/{note_id}/{filename}
    - File conflict handling and filename sanitization
    - Retry logic for failed downloads
    """

    # HTTP timeout constants (in seconds)
    DEFAULT_CONNECT_TIMEOUT = 30  # Connection establishment timeout
    DEFAULT_READ_TIMEOUT = 300  # Read timeout for large file downloads (5 minutes)

    def __init__(
        self,
        logger: Logger,
        base_download_path: str = "./attachments",
        max_retries: int = 3,
        chunk_size: int = 8192,
        connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: int = DEFAULT_READ_TIMEOUT,
    ) -> None:
        """Initialize AttachmentDownloader with required dependencies.

        Args:
            logger: Logger for structured output and progress tracking
            base_download_path: Base directory for attachment storage
            max_retries: Maximum retry attempts for failed downloads
            chunk_size: Chunk size in bytes for streaming downloads
            connect_timeout: HTTP connection timeout in seconds
            read_timeout: HTTP read timeout in seconds
        """
        self._logger = logger
        self._base_download_path = base_download_path
        self._max_retries = max_retries
        self._chunk_size = chunk_size
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout

        # Setup HTTP session with retry logic
        self._session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        # Ensure base download directory exists
        Path(self._base_download_path).mkdir(parents=True, exist_ok=True)

        # Configure allowed domains for SSRF protection
        # NOTE: These domains should be verified against actual Jobber attachment URLs
        # and narrowed to specific S3 buckets/CloudFront distributions if possible.
        # Current configuration allows known Jobber domains and their specific CDN endpoints.
        self._allowed_domains = {
            # Jobber main domains
            "getjobber.com",
            "cdn.getjobber.com",
            "assets.getjobber.com",
            # Jobber-specific S3 buckets (narrowed from broad s3.amazonaws.com)
            "jobber.s3.amazonaws.com",  # Generic Jobber S3 bucket
            "jobber-attachments.s3.amazonaws.com",
            "jobber-assets.s3.amazonaws.com",
            # Jobber-specific CloudFront distributions (narrowed from broad cloudfront.net)
            # TODO: Replace with actual CloudFront distribution IDs once identified
            "d123456abcdef.cloudfront.net",  # Example - replace with actual distribution
        }

    def _validate_url(self, url: str) -> tuple[bool, str]:
        """Validate URL is safe for download to prevent SSRF attacks.

        Validates that the URL:
        - Uses HTTPS protocol only (prevents protocol confusion)
        - Points to a trusted Jobber domain (prevents SSRF to internal resources)
        - Has a valid hostname (prevents malformed URLs)

        Args:
            url: The URL to validate

        Returns:
            Tuple of (is_valid, error_message). error_message is empty if valid.
        """
        if not url:
            return False, "URL is empty or None"

        try:
            parsed = urlparse(url)

            # Only allow HTTPS to prevent protocol confusion attacks
            if parsed.scheme != "https":
                return False, f"Invalid URL scheme '{parsed.scheme}'. Only HTTPS is allowed for security."

            # Ensure hostname exists
            if not parsed.hostname:
                return False, "URL has no hostname"

            # Check if domain is in allowed list (supports subdomains)
            hostname_lower = parsed.hostname.lower()
            is_allowed = False

            for allowed_domain in self._allowed_domains:
                # Check exact match or subdomain match
                if hostname_lower == allowed_domain or hostname_lower.endswith(f".{allowed_domain}"):
                    is_allowed = True
                    break

            if not is_allowed:
                return (
                    False,
                    f"Domain '{parsed.hostname}' is not in the allowed domains list. Allowed: {', '.join(sorted(self._allowed_domains))}",
                )

            return True, ""

        except Exception as e:
            return False, f"URL parsing failed: {e}"

    def download_attachment(self, attachment: Attachment) -> dict[str, Any]:
        """Download attachment file from remote URL to local storage.

        Public wrapper around _download_attachment_file for use by extractors.

        Args:
            attachment: Attachment entity with download URL and metadata

        Returns:
            Dictionary with download result:
            - 'success': bool - Whether download succeeded
            - 'local_file_path': str - Local file path (if successful)
            - 'bytes_downloaded': int - Number of bytes downloaded
            - 'error_message': str - Error message (if failed)
        """
        return self._download_attachment_file(attachment)

    def validate_dependencies(self) -> bool:
        """Validate that all required dependencies are properly configured.

        Validates download directory permissions and that the logger is available.

        Returns:
            True if all dependencies are valid and ready for file downloads

        Raises:
            ConfigurationError: If any required dependency is missing or invalid
        """
        if not self._logger:
            raise ConfigurationError("Logger dependency is required")

        # Validate download directory
        try:
            base_path = Path(self._base_download_path)
            if not base_path.exists():
                base_path.mkdir(parents=True, exist_ok=True)

            if not os.access(base_path, os.W_OK):
                raise ConfigurationError(f"Download directory not writable: {base_path}")

            return True

        except Exception as e:
            raise ConfigurationError(f"Dependency validation failed: {e}") from e

    def _download_attachment_file(self, attachment: Attachment) -> dict[str, Any]:
        """Download attachment file from remote URL to local storage.

        Validates URL for security (SSRF protection) before downloading.

        Args:
            attachment: Attachment entity with download URL and metadata

        Returns:
            Dictionary with download result:
            - 'success': bool - Whether download succeeded
            - 'local_file_path': str - Local file path (if successful)
            - 'bytes_downloaded': int - Number of bytes downloaded
            - 'error_message': str - Error message (if failed)
        """
        # Validate URL for security (prevent SSRF attacks)
        is_valid, validation_error = self._validate_url(attachment.original_url)
        if not is_valid:
            error_msg = f"URL validation failed for {attachment.file_name}: {validation_error}"
            self._logger.error(error_msg)
            return {
                "success": False,
                "local_file_path": "",
                "bytes_downloaded": 0,
                "error_message": error_msg,
            }

        try:
            # Create note-specific directory
            note_dir = Path(self._base_download_path) / attachment.note_id
            note_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize filename to prevent directory traversal and filesystem issues
            safe_filename = self._sanitize_filename(attachment.file_name)
            local_file_path = note_dir / safe_filename

            # Handle file conflicts by adding counter
            if local_file_path.exists():
                local_file_path = self._resolve_file_conflict(local_file_path)

            # Download file with streaming for large files
            self._logger.debug(f"Downloading {attachment.original_url} -> {local_file_path}")

            response = self._session.get(
                attachment.original_url,
                stream=True,
                timeout=(self._connect_timeout, self._read_timeout),
                allow_redirects=False,  # Prevent redirect following for additional security
            )
            response.raise_for_status()

            bytes_downloaded = 0
            with open(local_file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=self._chunk_size):
                    if chunk:  # Filter out keep-alive chunks
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

            self._logger.info(f"Downloaded {safe_filename} ({bytes_downloaded} bytes)")

            return {
                "success": True,
                "local_file_path": str(local_file_path),
                "bytes_downloaded": bytes_downloaded,
                "error_message": "",
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"Download failed for {attachment.file_name}: {e}"
            self._logger.error(error_msg)
            return {
                "success": False,
                "local_file_path": "",
                "bytes_downloaded": 0,
                "error_message": error_msg,
            }
        except OSError as e:
            error_msg = f"File write failed for {attachment.file_name}: {e}"
            self._logger.error(error_msg)
            return {
                "success": False,
                "local_file_path": "",
                "bytes_downloaded": 0,
                "error_message": error_msg,
            }

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent filesystem issues.

        Args:
            filename: Original filename from attachment

        Returns:
            Sanitized filename safe for filesystem use
        """
        if not filename:
            return "unknown_file"

        # Remove or replace dangerous characters
        dangerous_chars = '<>:"/\\|?*'
        safe_filename = filename
        for char in dangerous_chars:
            safe_filename = safe_filename.replace(char, "_")

        # Limit length and ensure it's not empty
        safe_filename = safe_filename[:255].strip()
        if not safe_filename:
            safe_filename = "unknown_file"

        return safe_filename

    def _resolve_file_conflict(self, file_path: Path) -> Path:
        """Resolve file naming conflicts by adding counter suffix.

        Args:
            file_path: Original file path that already exists

        Returns:
            New file path with counter suffix
        """
        stem = file_path.stem
        suffix = file_path.suffix
        parent = file_path.parent

        counter = 1
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
