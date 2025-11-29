"""Download mode coordinator for orchestrating binary attachment downloads."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..cli.services.shared import SharedServices
from ..config import ConfigManagerImpl
from ..extractors.attachment_downloader import AttachmentDownloader
from ..interfaces import Logger
from ..models import Attachment, AttachmentQueueItem, DownloadFilters
from ..reports import DownloadReportGenerator
from ..repositories import Repository
from ..ui import MultiProgressDisplay


class DownloadModeCoordinator:
    """
    Coordinator for download mode orchestration.

    Handles the binary download pass of multi-pass migration strategy, processing
    queued attachment downloads separately from entity metadata extraction.
    Enables pause/resume, selective downloading, and independent control over
    network-intensive operations.
    """

    def __init__(
        self,
        repository: Repository,
        logger: Logger,
        config_manager: Optional[ConfigManagerImpl] = None,
    ) -> None:
        """Initialize DownloadModeCoordinator.

        Args:
            repository: Repository for database operations
            logger: Logger for structured output and progress tracking
            config_manager: Optional configuration manager for settings
        """
        self._repository = repository
        self._logger = logger
        self._console = SharedServices.get_console()
        self._config_manager = config_manager or ConfigManagerImpl()

    def run_download_pass(
        self,
        snapshot_id: str,
        entity_types: Optional[List[str]] = None,
        resume: bool = False,
        filters: Optional[DownloadFilters] = None,
        output_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute binary download pass for queued attachments.

        Processes attachment_queue entries for the specified snapshot,
        downloading binaries with retry logic and status tracking.

        Args:
            snapshot_id: Map snapshot UUID
            entity_types: Optional filter for parent entity types (e.g., ["clients", "invoices"])
            resume: If True, skip completed downloads and only process pending/failed
            filters: Optional DownloadFilters for advanced filtering (file types, sizes, etc.)
            output_dir: Optional custom download directory (default: ./attachments)
            dry_run: If True, preview download queue without downloading

        Returns:
            Dictionary with download pass results:
            - snapshot_id: UUID of snapshot
            - total_attachments: Total number of attachments in queue
            - downloaded: Number successfully downloaded
            - failed: Number that failed download
            - skipped: Number already completed (if resume=True)
            - total_bytes: Total bytes downloaded
            - duration: Total execution time in seconds
            - report_path: Path to generated report (if not dry_run)

        Raises:
            ValueError: If snapshot_id is invalid or no attachments found
        """
        self._logger.info(f"Starting download pass for snapshot: {snapshot_id}")
        if resume:
            self._logger.info("Resume mode enabled - skipping completed downloads")
        if dry_run:
            self._logger.info("Dry run mode - will preview queue without downloading")

        start_time = datetime.now(UTC)

        # Get filtered queue items
        queue_items = self._get_filtered_queue_items(
            snapshot_id=snapshot_id,
            entity_types=entity_types,
            resume=resume,
            filters=filters,
        )

        if not queue_items:
            self._logger.info("No attachments to download")
            return {
                "snapshot_id": snapshot_id,
                "total_attachments": 0,
                "downloaded": 0,
                "failed": 0,
                "skipped": 0,
                "total_bytes": 0,
                "duration": 0.0,
            }

        # Dry run - just show preview
        if dry_run:
            return self._preview_download_queue(queue_items, snapshot_id)

        # Process downloads with progress tracking
        download_results = self._process_downloads(
            queue_items=queue_items,
            output_dir=output_dir,
        )

        # Calculate duration
        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        # Collect failed items for report
        failed_items = []
        if download_results["failed"] > 0:
            failed_queue_items = self._repository.get_attachment_queue(snapshot_id, status="failed")
            failed_items = [
                {
                    "attachment_id": item.attachment_id,
                    "parent_type": item.parent_type,
                    "parent_id": item.parent_id,
                    "last_error": item.last_error,
                    "attempt_count": item.attempt_count,
                }
                for item in failed_queue_items
            ]

        # Generate download report
        report_generator = DownloadReportGenerator(output_dir=self._config_manager.get_reports_dir())
        markdown_path, json_path = report_generator.generate_report(
            snapshot_id=snapshot_id,
            total_attachments=len(queue_items),
            downloaded=download_results["downloaded"],
            failed=download_results["failed"],
            skipped=download_results.get("skipped", 0),
            total_bytes=download_results["total_bytes"],
            duration=duration,
            failed_items=failed_items,
        )

        results = {
            "snapshot_id": snapshot_id,
            "total_attachments": len(queue_items),
            "downloaded": download_results["downloaded"],
            "failed": download_results["failed"],
            "skipped": download_results.get("skipped", 0),
            "total_bytes": download_results["total_bytes"],
            "duration": duration,
            "report_markdown": markdown_path,
            "report_json": json_path,
        }

        self._logger.success(
            f"Download pass completed: {results['downloaded']} downloaded, "
            f"{results['failed']} failed, {results['total_bytes']:,} bytes "
            f"in {duration:.1f}s"
        )
        self._logger.info(f"Download report: {markdown_path}")

        return results

    def _get_filtered_queue_items(
        self,
        snapshot_id: str,
        entity_types: Optional[List[str]] = None,
        resume: bool = False,
        filters: Optional[DownloadFilters] = None,
    ) -> List[AttachmentQueueItem]:
        """Get attachment queue items with optional filtering.

        Args:
            snapshot_id: Map snapshot UUID
            entity_types: Optional filter for parent entity types
            resume: If True, only get pending/failed items (skip done)
            filters: Optional DownloadFilters for advanced filtering

        Returns:
            Filtered list of AttachmentQueueItem instances
        """
        if resume:
            # Resume mode: only pending and failed
            pending = self._repository.get_attachment_queue(snapshot_id, status="pending")
            failed = self._repository.get_attachment_queue(snapshot_id, status="failed")
            queue_items = pending + failed
        else:
            # Normal mode: only pending (don't retry failed from previous runs)
            queue_items = self._repository.get_attachment_queue(snapshot_id, status="pending")

        # Filter by entity type if specified (legacy parameter for backward compatibility)
        if entity_types:
            entity_types_lower = [et.lower() for et in entity_types]
            queue_items = [
                item
                for item in queue_items
                if item.parent_type.lower() in entity_types_lower
            ]

        # Apply advanced filters if provided
        if filters:
            queue_items = self._apply_filters(queue_items, filters)

        return queue_items

    def _apply_filters(
        self,
        queue_items: List[AttachmentQueueItem],
        filters: DownloadFilters,
    ) -> List[AttachmentQueueItem]:
        """Apply DownloadFilters to queue items.

        Filters items based on file type, size, and parent entity type.
        For file type and size filtering, we need to look up attachment metadata.

        Args:
            queue_items: List of queue items to filter
            filters: DownloadFilters with filter criteria

        Returns:
            Filtered list of AttachmentQueueItem instances
        """
        filtered_items = []

        for item in queue_items:
            # Filter by parent entity type (uses queue item data directly)
            if not filters.matches_parent_type(item.parent_type):
                continue

            # For file type and size filters, we need attachment metadata
            if filters.file_types or filters.min_size is not None or filters.max_size is not None:
                attachment = self._repository.get_attachment_by_id(item.attachment_id)
                if not attachment:
                    # Skip if attachment metadata not found
                    self._logger.debug(f"Skipping {item.attachment_id} - metadata not found")
                    continue

                # Filter by file type
                if not filters.matches_file_type(attachment.file_name):
                    continue

                # Filter by file size
                if not filters.matches_size(attachment.file_size):
                    continue

            # Passed all filters
            filtered_items.append(item)

        return filtered_items

    def _download_worker(
        self,
        queue_item: AttachmentQueueItem,
        base_download_path: str,
        display: MultiProgressDisplay,
        task_id: int,
    ) -> Dict[str, Any]:
        """Worker function for parallel downloads with progress tracking.

        Runs in thread pool. Downloads attachment and reports progress to MultiProgressDisplay.
        Does NOT update database - caller handles that.

        Args:
            queue_item: Queue item to download
            base_download_path: Base path for downloads
            display: MultiProgressDisplay instance for progress updates
            task_id: Task ID for this download in the progress display

        Returns:
            dict with:
            - queue_item: Original queue item
            - success: bool
            - attachment: Attachment object (if found)
            - download_result: Result dict from AttachmentDownloader
            - error: Exception or error message (if failed)
            - task_id: Progress task ID (for completion tracking)
        """
        try:
            # Get attachment metadata
            attachment = self._repository.get_attachment_by_id(queue_item.attachment_id)
            if not attachment:
                return {
                    "queue_item": queue_item,
                    "success": False,
                    "attachment": None,
                    "download_result": None,
                    "error": f"Attachment not found: {queue_item.attachment_id}",
                    "task_id": task_id,
                }

            # Create progress callback for this download
            def progress_callback(bytes_chunk: int):
                display.update(task_id, advance=bytes_chunk)

            # Create downloader (each thread gets own instance)
            downloader = AttachmentDownloader(
                repository=self._repository,
                logger=self._logger,
                base_download_path=base_download_path,
                progress_callback=progress_callback,
            )

            # Download file
            download_result = downloader.download_attachment(attachment)

            return {
                "queue_item": queue_item,
                "success": download_result["success"],
                "attachment": attachment,
                "download_result": download_result,
                "error": download_result.get("error_message") if not download_result["success"] else None,
                "task_id": task_id,
            }

        except Exception as e:
            self._logger.error(f"Worker exception for {queue_item.attachment_id}: {e}")
            return {
                "queue_item": queue_item,
                "success": False,
                "attachment": None,
                "download_result": None,
                "error": str(e),
                "task_id": task_id,
            }

    def _process_downloads(
        self,
        queue_items: List[AttachmentQueueItem],
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Process attachment downloads with parallel execution and multi-progress tracking.

        Uses ThreadPoolExecutor to download multiple attachments concurrently with
        individual progress bars for each active download plus aggregate statistics.
        Database writes are serialized in the main thread for thread-safety.

        Args:
            queue_items: List of queue items to download
            output_dir: Optional custom download directory

        Returns:
            Dictionary with download results:
            - downloaded: Number successfully downloaded
            - failed: Number that failed
            - total_bytes: Total bytes downloaded
        """
        # Get concurrency setting from config
        attachment_config = self._config_manager.get_attachment_config()
        max_workers = attachment_config.get("concurrent_downloads", 3)

        base_download_path = str(output_dir) if output_dir else "./attachments"

        # Calculate total bytes for overall progress
        total_bytes_to_download = sum(
            (self._repository.get_attachment_by_id(item.attachment_id).file_size or 0)
            for item in queue_items
            if self._repository.get_attachment_by_id(item.attachment_id)
        )

        # Track results
        downloaded_count = 0
        failed_count = 0
        total_bytes_downloaded = 0

        # Process downloads with MultiProgressDisplay
        with MultiProgressDisplay(
            console=self._console,
            max_workers=max_workers,
            description=f"Downloading {len(queue_items)} attachments",
            show_speed=True,
        ) as display:
            # Start overall progress tracking
            display.start_overall(
                total_items=len(queue_items),
                total_bytes=total_bytes_to_download,
            )

            # Submit all downloads to thread pool
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit jobs and create progress tasks
                futures = {}

                for item in queue_items:
                    # Get attachment for file size
                    attachment = self._repository.get_attachment_by_id(item.attachment_id)
                    if not attachment:
                        # Handle missing attachment - mark as failed immediately
                        item.status = "failed"
                        item.last_error = f"Attachment not found: {item.attachment_id}"
                        item.attempt_count += 1
                        item.updated_at = self._get_current_timestamp()
                        self._repository.update_attachment_queue_status(item)
                        failed_count += 1
                        display.log(f"✗ {item.attachment_id[:12]} - Attachment not found", level="error")
                        continue

                    file_size = attachment.file_size or 0
                    task_name = attachment.file_name or item.attachment_id[:12]

                    # Add task to display
                    task_id = display.add_task(task_name, total_bytes=file_size)

                    # Submit worker
                    future = executor.submit(
                        self._download_worker,
                        item,
                        base_download_path,
                        display,
                        task_id,
                    )
                    futures[future] = (item, task_id, task_name)

                # Process results as they complete
                for future in as_completed(futures):
                    item, task_id, task_name = futures[future]
                    result = future.result()
                    queue_item = result["queue_item"]

                    # Update database based on result (serialized in main thread)
                    queue_item.updated_at = self._get_current_timestamp()

                    if result["success"]:
                        # Update attachment with local file path
                        attachment = result["attachment"]
                        download_result = result["download_result"]

                        updated_attachment = Attachment(
                            id=attachment.id,
                            note_id=attachment.note_id,
                            file_name=attachment.file_name,
                            content_type=attachment.content_type,
                            original_url=attachment.original_url,
                            local_file_path=download_result["local_file_path"],
                            file_size=attachment.file_size,
                            created_at=attachment.created_at,
                        )
                        self._repository.save_attachments([updated_attachment])

                        queue_item.status = "done"
                        queue_item.last_error = None
                        downloaded_count += 1
                        total_bytes_downloaded += download_result.get("bytes_downloaded", 0)

                        # Log success
                        display.log(f"✓ {task_name} ({download_result.get('bytes_downloaded', 0):,} bytes)")
                    else:
                        queue_item.status = "failed"
                        queue_item.last_error = result["error"]
                        queue_item.attempt_count += 1
                        failed_count += 1

                        # Log failure
                        display.log(f"✗ {task_name} - {result['error']}", level="error")

                    # Update queue status
                    self._repository.update_attachment_queue_status(queue_item)

                    # Complete and hide this task
                    display.complete_task(task_id, task_name)

        return {
            "downloaded": downloaded_count,
            "failed": failed_count,
            "total_bytes": total_bytes_downloaded,
        }

    def _preview_download_queue(
        self,
        queue_items: List[AttachmentQueueItem],
        snapshot_id: str,
    ) -> Dict[str, Any]:
        """Preview download queue without downloading (dry run mode).

        Args:
            queue_items: List of queue items that would be downloaded
            snapshot_id: Map snapshot UUID

        Returns:
            Dictionary with preview information
        """
        # Group by parent entity type
        by_entity_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}

        for item in queue_items:
            by_entity_type[item.parent_type] = by_entity_type.get(item.parent_type, 0) + 1
            by_status[item.status] = by_status.get(item.status, 0) + 1

        self._logger.info("=" * 60)
        self._logger.info("DOWNLOAD QUEUE PREVIEW (DRY RUN)")
        self._logger.info("=" * 60)
        self._logger.info(f"Snapshot ID: {snapshot_id}")
        self._logger.info(f"Total attachments: {len(queue_items)}")
        self._logger.info("")
        self._logger.info("By Entity Type:")
        for entity_type, count in sorted(by_entity_type.items()):
            self._logger.info(f"  {entity_type}: {count}")
        self._logger.info("")
        self._logger.info("By Status:")
        for status, count in sorted(by_status.items()):
            self._logger.info(f"  {status}: {count}")
        self._logger.info("=" * 60)

        return {
            "snapshot_id": snapshot_id,
            "total_attachments": len(queue_items),
            "by_entity_type": by_entity_type,
            "by_status": by_status,
            "dry_run": True,
        }

    @staticmethod
    def _get_current_timestamp() -> str:
        """Get current UTC timestamp in ISO format.

        Returns:
            ISO 8601 formatted timestamp string
        """
        return datetime.now(UTC).isoformat()
