"""AttachmentDownloader for downloading and managing attachment files."""

import os
import time
from pathlib import Path
from typing import Any, List, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..exceptions import (
    ConfigurationError,
    MappingError,
)
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import Attachment, Client, Invoice, Note, Quote
from ..repositories import Repository


class AttachmentDownloader:
    """
    Downloader for Attachment files implementing BaseExtractor protocol.

    Specialized extractor for handling binary file downloads from Jobber attachments
    with comprehensive file management, local storage organization, and metadata tracking.
    Addresses PRD Day 5 milestone for Note Attachments with complete file coverage.

    Features:
    - Binary file downloads with streaming for large files
    - Organized local storage: ./attachments/{note_id}/{filename}
    - File conflict handling and filename sanitization
    - Retry logic for failed downloads
    - Progress reporting and metadata tracking
    """  # noqa: E501

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        base_download_path: str = "./attachments",
        max_retries: int = 3,
        chunk_size: int = 8192,
        config_manager: ConfigManagerImpl | None = None,
        skip_existing_entities: bool = False,
    ) -> None:
        """Initialize AttachmentDownloader with required dependencies.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming GraphQL data to domain models
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            base_download_path: Base directory for attachment storage
            max_retries: Maximum retry attempts for failed downloads
            chunk_size: Chunk size in bytes for streaming downloads
            config_manager: Optional ConfigManager for delays and pagination settings
            skip_existing_entities: Whether to skip entities that already exist in database
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._base_download_path = base_download_path
        self._max_retries = max_retries
        self._chunk_size = chunk_size
        self._config_manager = config_manager or ConfigManagerImpl()
        self._skip_existing_entities = skip_existing_entities

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

        # Extraction state tracking
        self._last_extraction_summary = {
            "total_entities": 0,
            "total_pages": 0,
            "extraction_duration": 0.0,
            "average_page_size": 0.0,
            "entities_per_second": 0.0,
            "last_cursor": None,
            "extraction_status": "pending",
            "error_count": 0,
            "files_downloaded": 0,
            "total_bytes_downloaded": 0,
            "download_failures": 0,
        }

        # Ensure base download directory exists
        Path(self._base_download_path).mkdir(parents=True, exist_ok=True)

    def extract(
        self,
        cursor: str | None = None,
        page_limit: int | None = None,
    ) -> dict[str, Any]:
        """Extract attachments from Jobber GraphQL API with file downloads.

        Performs complete extraction workflow including:
        - GraphQL API calls with cursor pagination
        - Data transformation via EntityMapper
        - Binary file downloads with retry logic
        - Local file storage organization
        - Metadata persistence via Repository

        Args:
            cursor: Optional pagination cursor for continuing extraction
            page_limit: Optional limit on number of pages to process (for testing)

        Returns:
            Dictionary containing extraction results with keys:
            - 'entities_processed': int - Total number of entities extracted
            - 'pages_processed': int - Number of API pages processed
            - 'has_next_page': bool - Whether more pages are available
            - 'end_cursor': Optional[str] - Final cursor for continuation
            - 'extraction_time': float - Total extraction time in seconds
            - 'files_downloaded': int - Number of files successfully downloaded
            - 'total_bytes_downloaded': int - Total bytes downloaded
            - 'download_failures': int - Number of download failures

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
            RepositoryError: If database operations fail
        """
        start_time = time.time()
        entities_processed = 0
        pages_processed = 0
        current_cursor = cursor
        error_count = 0
        files_downloaded = 0
        total_bytes_downloaded = 0
        download_failures = 0
        page_info = {}  # Initialize page_info

        self._logger.info(f"Starting attachments extraction from cursor: {cursor}")

        try:
            while True:
                # Check page limit for testing
                if page_limit is not None and pages_processed >= page_limit:
                    self._logger.debug(f"Reached page limit: {page_limit}")
                    break

                # Fetch page of attachments from API
                self._logger.debug(f"Fetching attachments page {pages_processed + 1}")
                response = self._jobber_client.fetch_attachments(current_cursor)
                attachments_data = response.get("data", {}).get("attachments", {})

                # Extract edges and page info
                edges = attachments_data.get("edges", [])
                page_info = attachments_data.get("pageInfo", {})

                if not edges:
                    self._logger.debug("No more attachment data to process")
                    break

                # Map GraphQL nodes to domain models and download files
                attachments = []
                for edge in edges:
                    node = edge.get("node", {})
                    try:
                        # Map to attachment model
                        attachment = self._entity_mapper.map_attachment(node)

                        # Download the actual file
                        download_result = self._download_attachment_file(attachment)
                        if download_result["success"]:
                            files_downloaded += 1
                            total_bytes_downloaded += download_result[
                                "bytes_downloaded"
                            ]
                            # Update attachment with actual local file path
                            attachment = attachment.__class__(
                                **{
                                    **attachment.__dict__,
                                    "local_file_path": download_result[
                                        "local_file_path"
                                    ],
                                }
                            )
                        else:
                            download_failures += 1
                            error_count += 1

                        attachments.append(attachment)

                    except MappingError as e:
                        error_msg = (
                            f"Failed to map attachment {node.get('id', 'unknown')}: {e}"
                        )
                        self._logger.error(error_msg)
                        error_count += 1

                # Batch save attachments to database
                if attachments:
                    self._repository.save_attachments(attachments)
                    entities_processed += len(attachments)
                    self._logger.info(
                        f"Processed {len(attachments)} attachments "
                        f"(total: {entities_processed}, downloaded: {files_downloaded})"
                    )

                pages_processed += 1

                # Check for next page
                has_next_page = page_info.get("hasNextPage", False)
                end_cursor = page_info.get("endCursor")

                if not has_next_page:
                    self._logger.debug("Reached last page of attachments")
                    break

                # Update cursor for next iteration
                current_cursor = end_cursor

                # Add configurable delay between pages to prevent API overload
                page_delay = self._config_manager.get_delay_config("page_delay")
                time.sleep(page_delay)
                self._logger.debug(
                    f"Added {page_delay}s delay before page {pages_processed + 1}"
                )

            extraction_time = time.time() - start_time

            # Update extraction summary
            self._update_extraction_summary(
                entities_processed,
                pages_processed,
                extraction_time,
                current_cursor,
                "completed",
                error_count,
                files_downloaded,
                total_bytes_downloaded,
                download_failures,
            )

            result = {
                "entities_processed": entities_processed,
                "pages_processed": pages_processed,
                "has_next_page": page_info.get("hasNextPage", False),
                "end_cursor": current_cursor,
                "extraction_time": extraction_time,
                "files_downloaded": files_downloaded,
                "total_bytes_downloaded": total_bytes_downloaded,
                "download_failures": download_failures,
            }

            self._logger.info(
                f"Attachments extraction completed: {entities_processed} attachments, "
                f"{files_downloaded} files downloaded ({total_bytes_downloaded} bytes), "  # noqa: E501
                f"{pages_processed} pages in {extraction_time:.2f}s"
            )

            return result

        except Exception as e:
            extraction_time = time.time() - start_time
            self._update_extraction_summary(
                entities_processed,
                pages_processed,
                extraction_time,
                current_cursor,
                "failed",
                error_count,
                files_downloaded,
                total_bytes_downloaded,
                download_failures,
            )
            self._logger.error(f"Attachments extraction failed: {e}")
            raise

    def extract_all(self) -> List[Union[Client, Invoice, Quote, Note, Attachment]]:
        """Extract all attachments with automatic pagination and file downloads.

        Continuously calls extract() with cursor pagination until all available
        attachments are processed and downloaded. Provides complete dataset
        extraction with file management.

        Returns:
            List of all extracted Attachment objects

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
            RepositoryError: If database operations fail
        """
        all_attachments = []
        cursor = None

        self._logger.info("Starting complete attachments extraction and download")

        while True:
            result = self.extract(cursor=cursor)

            # Get attachments from database for this batch
            attachments_batch = self._repository.get_all_attachments()
            if attachments_batch:
                # Filter attachments for this extraction session
                batch_start = len(all_attachments)
                new_attachments = attachments_batch[
                    batch_start : batch_start + result["entities_processed"]
                ]
                all_attachments.extend(new_attachments)

            if not result["has_next_page"]:
                break

            cursor = result["end_cursor"]

        self._logger.info(
            f"Complete attachments extraction finished: {len(all_attachments)} attachments"
        )  # noqa: E501
        return all_attachments

    def get_entity_count(self) -> int:
        """Get total count of attachments available for extraction.

        Performs a lightweight API call to determine the total number of attachments
        available for extraction without actually downloading files.

        Returns:
            Total number of attachments available for extraction

        Raises:
            JobberApiError: If GraphQL API communication fails
            ConfigurationError: If authentication or configuration is invalid
        """
        total_count = 0
        cursor = None

        while True:
            response = self._jobber_client.fetch_attachments(cursor)
            attachments_data = response.get("data", {}).get("attachments", {})

            edges = attachments_data.get("edges", [])
            page_info = attachments_data.get("pageInfo", {})

            total_count += len(edges)

            if not page_info.get("hasNextPage", False):
                break

            cursor = page_info.get("endCursor")

        return total_count

    def validate_dependencies(self) -> bool:
        """Validate that all required dependencies are properly configured.

        Checks that JobberClient, EntityMapper, Repository, and Logger
        dependencies are properly injected and configured for extraction.
        Also validates download directory permissions.

        Returns:
            True if all dependencies are valid and ready for extraction

        Raises:
            ConfigurationError: If any required dependency is missing or invalid
        """
        if not self._jobber_client:
            raise ConfigurationError("JobberClient dependency is required")
        if not self._entity_mapper:
            raise ConfigurationError("EntityMapper dependency is required")
        if not self._repository:
            raise ConfigurationError("Repository dependency is required")
        if not self._logger:
            raise ConfigurationError("Logger dependency is required")

        # Test basic functionality
        try:
            # Verify JobberClient has required methods
            if not hasattr(self._jobber_client, "fetch_attachments"):
                raise ConfigurationError(
                    "JobberClient missing fetch_attachments method"
                )

            # Verify EntityMapper has required methods
            if not hasattr(self._entity_mapper, "map_attachment"):
                raise ConfigurationError("EntityMapper missing map_attachment method")

            # Verify Repository has required methods
            if not hasattr(self._repository, "save_attachments"):
                raise ConfigurationError("Repository missing save_attachments method")

            # Validate download directory
            base_path = Path(self._base_download_path)
            if not base_path.exists():
                base_path.mkdir(parents=True, exist_ok=True)

            if not os.access(base_path, os.W_OK):
                raise ConfigurationError(
                    f"Download directory not writable: {base_path}"
                )

            return True

        except Exception as e:
            raise ConfigurationError(f"Dependency validation failed: {e}") from e

    def get_extraction_summary(self) -> dict[str, Any]:
        """Get summary statistics of the last extraction operation.

        Provides detailed metrics and status information from the most recent
        extract() or extract_all() operation including file download statistics.

        Returns:
            Dictionary containing extraction summary with keys:
            - 'total_entities': int - Total entities processed
            - 'total_pages': int - Total API pages processed
            - 'extraction_duration': float - Total time in seconds
            - 'average_page_size': float - Average entities per page
            - 'entities_per_second': float - Processing rate
            - 'last_cursor': Optional[str] - Final pagination cursor
            - 'extraction_status': str - 'completed', 'partial', or 'failed'
            - 'error_count': int - Number of recoverable errors encountered
            - 'files_downloaded': int - Number of files successfully downloaded
            - 'total_bytes_downloaded': int - Total bytes downloaded
            - 'download_failures': int - Number of download failures
        """
        return self._last_extraction_summary.copy()

    def _download_attachment_file(self, attachment: Attachment) -> dict[str, Any]:
        """Download attachment file from remote URL to local storage.

        Args:
            attachment: Attachment entity with download URL and metadata

        Returns:
            Dictionary with download result:
            - 'success': bool - Whether download succeeded
            - 'local_file_path': str - Local file path (if successful)
            - 'bytes_downloaded': int - Number of bytes downloaded
            - 'error_message': str - Error message (if failed)
        """
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
            self._logger.debug(
                f"Downloading {attachment.original_url} -> {local_file_path}"
            )

            response = self._session.get(
                attachment.original_url,
                stream=True,
                timeout=(30, 300),  # Connect timeout 30s, read timeout 5min
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

    def _update_extraction_summary(
        self,
        total_entities: int,
        total_pages: int,
        extraction_duration: float,
        last_cursor: str | None,
        status: str,
        error_count: int,
        files_downloaded: int = 0,
        total_bytes_downloaded: int = 0,
        download_failures: int = 0,
    ) -> None:
        """Update internal extraction summary statistics."""
        average_page_size = total_entities / total_pages if total_pages > 0 else 0.0
        entities_per_second = (
            total_entities / extraction_duration if extraction_duration > 0 else 0.0
        )

        self._last_extraction_summary = {
            "total_entities": total_entities,
            "total_pages": total_pages,
            "extraction_duration": extraction_duration,
            "average_page_size": average_page_size,
            "entities_per_second": entities_per_second,
            "last_cursor": last_cursor,
            "extraction_status": status,
            "error_count": error_count,
            "files_downloaded": files_downloaded,
            "total_bytes_downloaded": total_bytes_downloaded,
            "download_failures": download_failures,
        }
