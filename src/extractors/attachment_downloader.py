"""AttachmentDownloader helper for downloading and managing attachment files."""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..exceptions import ConfigurationError
from ..interfaces import Logger
from ..models import Attachment
from ..repositories import Repository


class AttachmentDownloader:
    """
    Phase 6 Pass 2: Binary attachment downloader with hash-based storage.

    Downloads attachment files from Jobber using a two-phase ETL pattern:
    - Phase 1 (metadata): Extractors collect attachment metadata and URLs
    - Phase 2 (binaries): AttachmentDownloader fetches files and updates database

    Features:
    - Streaming downloads with SHA256 hash computation
    - Content-addressed storage: ./attachments/{sha256_hash}.{ext}
    - Database updates with hash, status, and timestamps
    - Retry logic with exponential backoff (via requests.Session)
    - SSRF protection with domain allowlisting
    """

    # HTTP timeout constants (in seconds)
    DEFAULT_CONNECT_TIMEOUT = 30  # Connection establishment timeout
    DEFAULT_READ_TIMEOUT = 300  # Read timeout for large file downloads (5 minutes)

    def __init__(
        self,
        repository: Repository,
        logger: Logger,
        base_download_path: str = "./attachments",
        max_retries: int = 3,
        chunk_size: int = 8192,
        connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: int = DEFAULT_READ_TIMEOUT,
    ) -> None:
        """Initialize AttachmentDownloader with required dependencies.

        Args:
            repository: Repository for database updates
            logger: Logger for structured output and progress tracking
            base_download_path: Base directory for hash-based attachment storage
            max_retries: Maximum retry attempts for failed downloads
            chunk_size: Chunk size in bytes for streaming downloads
            connect_timeout: HTTP connection timeout in seconds
            read_timeout: HTTP read timeout in seconds
        """
        self._repository = repository
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
            - 'hash': str - SHA256 hash of downloaded content
            - 'error_message': str - Error message (if failed)
        """
        return self._download_attachment_file(attachment)

    def download_all_pending(self, batch_size: int = 100) -> dict[str, int]:
        """Download all pending attachments in batches.

        Retrieves pending attachments from the database and downloads them
        in batches. Updates database with download status after each file.

        Args:
            batch_size: Number of attachments to fetch per batch

        Returns:
            Dictionary with download statistics:
            - 'success': Number of successful downloads
            - 'failed': Number of failed downloads
            - 'skipped': Number of skipped attachments
            - 'total_bytes': Total bytes downloaded
        """
        stats = {"success": 0, "failed": 0, "skipped": 0, "total_bytes": 0}

        while True:
            # Fetch next batch of pending attachments
            batch = self._repository.get_pending_attachments()
            if not batch:
                break

            # Limit batch size
            batch = batch[:batch_size]

            for attachment in batch:
                result = self._download_attachment_file(attachment)

                if result["success"]:
                    stats["success"] += 1
                    stats["total_bytes"] += result["bytes_downloaded"]
                else:
                    stats["failed"] += 1

            # If we got fewer than batch_size, we're done
            if len(batch) < batch_size:
                break

        return stats

    def validate_dependencies(self) -> bool:
        """Validate that all required dependencies are properly configured.

        Validates download directory permissions and that the logger/repository are available.

        Returns:
            True if all dependencies are valid and ready for file downloads

        Raises:
            ConfigurationError: If any required dependency is missing or invalid
        """
        if not self._logger:
            raise ConfigurationError("Logger dependency is required")

        if not self._repository:
            raise ConfigurationError("Repository dependency is required")

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
        """Download attachment file from remote URL to hash-based local storage.

        Implements Phase 6 Pass 2 binary download pattern:
        - Stream download with SHA256 hash computation
        - Hash-based file naming: {sha256_hash}.{original_extension}
        - Database update with hash, local_path, status, timestamp
        - Retry logic with exponential backoff (via requests.Session)

        Validates URL for security (SSRF protection) before downloading.

        Args:
            attachment: Attachment entity with download URL and metadata

        Returns:
            Dictionary with download result:
            - 'success': bool - Whether download succeeded
            - 'local_file_path': str - Local file path (if successful)
            - 'bytes_downloaded': int - Number of bytes downloaded
            - 'hash': str - SHA256 hash of downloaded content
            - 'error_message': str - Error message (if failed)
        """
        # Validate URL for security (prevent SSRF attacks)
        is_valid, validation_error = self._validate_url(attachment.original_url)
        if not is_valid:
            error_msg = f"URL validation failed for {attachment.file_name}: {validation_error}"
            self._logger.error(error_msg)

            # Update database with failure status
            self._repository.update_attachment_download(
                attachment_id=attachment.id,
                download_status="failed",
                download_error=error_msg,
            )

            return {
                "success": False,
                "local_file_path": "",
                "bytes_downloaded": 0,
                "hash": "",
                "error_message": error_msg,
            }

        try:
            # Stream download with hash computation
            self._logger.debug(f"Downloading {attachment.original_url}")

            response = self._session.get(
                attachment.original_url,
                stream=True,
                timeout=(self._connect_timeout, self._read_timeout),
                allow_redirects=True,  # Follow redirects for CDN URLs
            )
            response.raise_for_status()

            # Stream to memory while computing hash
            hash_obj = hashlib.sha256()
            chunks = []
            bytes_downloaded = 0

            for chunk in response.iter_content(chunk_size=self._chunk_size):
                if chunk:  # Filter out keep-alive chunks
                    chunks.append(chunk)
                    hash_obj.update(chunk)
                    bytes_downloaded += len(chunk)

            # Get hash and determine filename
            file_hash = hash_obj.hexdigest()
            file_ext = Path(attachment.file_name).suffix or ".bin"
            filename = f"{file_hash}{file_ext}"

            # Write to hash-based flat directory
            base_path = Path(self._base_download_path)
            base_path.mkdir(parents=True, exist_ok=True)
            local_file_path = base_path / filename

            # Write file content
            with open(local_file_path, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)

            # Update database with success
            downloaded_at = datetime.utcnow().isoformat() + "Z"
            self._repository.update_attachment_download(
                attachment_id=attachment.id,
                local_file_path=str(local_file_path),
                hash=file_hash,
                download_status="completed",
                downloaded_at=downloaded_at,
            )

            self._logger.info(f"Downloaded {attachment.file_name} → {filename} ({bytes_downloaded} bytes, hash: {file_hash[:8]}...)")

            return {
                "success": True,
                "local_file_path": str(local_file_path),
                "bytes_downloaded": bytes_downloaded,
                "hash": file_hash,
                "error_message": "",
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"Download failed for {attachment.file_name}: {e}"
            self._logger.error(error_msg)

            # Update database with failure status
            self._repository.update_attachment_download(
                attachment_id=attachment.id,
                download_status="failed",
                download_error=error_msg,
            )

            return {
                "success": False,
                "local_file_path": "",
                "bytes_downloaded": 0,
                "hash": "",
                "error_message": error_msg,
            }
        except OSError as e:
            error_msg = f"File write failed for {attachment.file_name}: {e}"
            self._logger.error(error_msg)

            # Update database with failure status
            self._repository.update_attachment_download(
                attachment_id=attachment.id,
                download_status="failed",
                download_error=error_msg,
            )

            return {
                "success": False,
                "local_file_path": "",
                "bytes_downloaded": 0,
                "hash": "",
                "error_message": error_msg,
            }

