"""Extract mode coordinator for queue-based entity hydration."""

from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeRemainingColumn

from ..clients import JobberClient
from ..config import ConfigManagerImpl
from ..extractors import (
    ClientsExtractor,
    ExpensesExtractor,
    InvoicesExtractor,
    JobsExtractor,
    ProductServicesExtractor,
    PropertiesExtractor,
    QuotesExtractor,
    RequestsExtractor,
    TaxRatesExtractor,
    TimesheetEntriesExtractor,
    UsersExtractor,
    VisitsExtractor,
)
from ..interfaces import Logger
from ..mappers import EntityMapper
from ..models import ExtractQueueItem, MapSnapshot
from ..repositories import Repository


class ExtractModeCoordinator:
    """
    Coordinator for extract mode hydration pass using map data.

    Loads entity inventory from map snapshot, creates extraction queues,
    processes entities with status tracking and retry capability,
    validates completeness against map totals.
    """

    # Map entity type names to extractor classes
    _EXTRACTOR_MAP = {
        "clients": ClientsExtractor,
        "invoices": InvoicesExtractor,
        "quotes": QuotesExtractor,
        "jobs": JobsExtractor,
        "properties": PropertiesExtractor,
        "requests": RequestsExtractor,
        "users": UsersExtractor,
        "expenses": ExpensesExtractor,
        "visits": VisitsExtractor,
        "timesheetEntries": TimesheetEntriesExtractor,
        "productsAndServices": ProductServicesExtractor,
        "taxRates": TaxRatesExtractor,
    }

    @classmethod
    def supported_entity_types(cls) -> List[str]:
        """Return supported entity types for extract mode."""
        return sorted(cls._EXTRACTOR_MAP.keys())

    def __init__(
        self,
        jobber_client: JobberClient,
        entity_mapper: EntityMapper,
        repository: Repository,
        logger: Logger,
        config_manager: Optional[ConfigManagerImpl] = None,
    ) -> None:
        """Initialize ExtractModeCoordinator.

        Args:
            jobber_client: Client for Jobber GraphQL API communication
            entity_mapper: Mapper for transforming API data to domain models
            repository: Repository for database operations
            logger: Logger for structured output
            config_manager: Optional config manager for pagination settings
        """
        self._jobber_client = jobber_client
        self._entity_mapper = entity_mapper
        self._repository = repository
        self._logger = logger
        self._config_manager = config_manager or ConfigManagerImpl()
        self._console = Console()

    def run_extract_pass(
        self,
        snapshot_id: str,
        entity_types: Optional[List[str]] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute extract mode hydration pass using map snapshot data.

        Args:
            snapshot_id: Map snapshot UUID to extract from
            entity_types: Optional list of entity types to extract (default: all from snapshot)
            resume: Whether to resume from existing queue state (default: False)

        Returns:
            Dictionary with extraction results:
            - snapshot_id: UUID of map snapshot used
            - entity_results: Dict mapping entity type to extraction results
            - totals: Aggregate statistics
            - duration: Total execution time in seconds
            - discrepancies: List of completeness check failures

        Raises:
            ValueError: If snapshot not found or invalid entity types provided
        """
        self._logger.info(f"Starting extract mode pass for snapshot: {snapshot_id}")

        # Load map snapshot
        snapshot = self._repository.get_map_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"Map snapshot not found: {snapshot_id}")

        # Determine entity types to extract
        import json

        snapshot_entity_types = json.loads(snapshot.entities_included)
        if entity_types is None:
            entity_types = snapshot_entity_types
        else:
            # Validate requested types are in snapshot
            invalid_types = set(entity_types) - set(snapshot_entity_types)
            if invalid_types:
                raise ValueError(
                    f"Entity types not in snapshot: {invalid_types}. " f"Available types: {snapshot_entity_types}"
                )

        self._logger.info(f"Extracting entity types: {entity_types}")

        # Create/resume extract queues
        if not resume:
            self._logger.info("Creating extract queues from entity inventory...")
            for entity_type in entity_types:
                self._repository.create_extract_queue(snapshot_id, entity_type)
        else:
            self._logger.info("Resuming from existing extract queues...")

        # Process queues
        start_time = datetime.now(UTC)
        entity_results = {}
        total_extracted = 0
        total_failed = 0

        for entity_type in entity_types:
            result = self._process_queue(snapshot_id, entity_type)
            entity_results[entity_type] = result
            total_extracted += result["extracted"]
            total_failed += result["failed"]

        # Process attachment queue after all entities extracted
        attachment_result = self._process_attachment_queue(snapshot_id)

        # Validate completeness (compare map totals vs extracted counts)
        discrepancies = self._validate_completeness(snapshot_id, entity_types, entity_results, attachment_result)

        # Calculate duration
        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        if discrepancies:
            self._logger.warning(
                f"Extract pass completed with {len(discrepancies)} discrepancy(ies): "
                f"{total_extracted} extracted, {total_failed} failed, "
                f"{attachment_result['downloaded']} attachments downloaded in {duration:.1f}s"
            )
        else:
            self._logger.success(
                f"Extract pass completed: {total_extracted} extracted, "
                f"{total_failed} failed, {attachment_result['downloaded']} attachments downloaded "
                f"in {duration:.1f}s"
            )

        return {
            "snapshot_id": snapshot_id,
            "entity_results": entity_results,
            "attachment_result": attachment_result,
            "discrepancies": discrepancies,
            "totals": {
                "total_extracted": total_extracted,
                "total_failed": total_failed,
                "entity_types_count": len(entity_types),
            },
            "duration": duration,
        }

    def _process_queue(
        self,
        snapshot_id: str,
        entity_type: str,
    ) -> Dict[str, Any]:
        """
        Process extraction queue for a single entity type.

        Args:
            snapshot_id: Map snapshot UUID
            entity_type: Entity type to process (e.g., "clients")

        Returns:
            Dictionary with processing results:
            - entity_type: Name of entity type processed
            - extracted: Number of entities successfully extracted
            - failed: Number of entities that failed extraction
            - skipped: Number of entities already done
        """
        self._logger.info(f"Processing extract queue for {entity_type}...")

        # Get queue items (pending + failed for retry)
        pending_items = self._repository.get_extract_queue(snapshot_id, entity_type, status="pending")
        failed_items = self._repository.get_extract_queue(snapshot_id, entity_type, status="failed")
        all_items = pending_items + failed_items

        if not all_items:
            self._logger.info(f"No items to process for {entity_type}")
            return {
                "entity_type": entity_type,
                "extracted": 0,
                "failed": 0,
                "skipped": 0,
            }

        # Create extractor with attachment queuing enabled
        extractor = self._create_extractor(entity_type, snapshot_id)

        # Process queue with Rich progress bar
        extracted_count = 0
        failed_count = 0
        skipped_count = 0

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeRemainingColumn(),
            console=self._console,
        ) as progress:
            task_id = progress.add_task(f"Extracting {entity_type}...", total=len(all_items))

            for item in all_items:
                try:
                    # Mark in progress
                    item.status = "in_progress"
                    item.updated_at = self._get_current_timestamp()
                    self._repository.update_queue_status(item)

                    # Extract single entity
                    result = extractor.extract_single(item.entity_id)

                    if result["success"]:
                        # Mark done
                        item.status = "done"
                        item.last_error = None
                        extracted_count += 1
                    else:
                        # Mark failed
                        item.status = "failed"
                        item.last_error = result.get("error", "Unknown error")
                        item.attempt_count += 1
                        failed_count += 1

                    item.updated_at = self._get_current_timestamp()
                    self._repository.update_queue_status(item)

                except Exception as e:
                    # Mark failed with exception info
                    self._logger.error(f"Failed to extract {entity_type} {item.entity_id}: {e}")
                    item.status = "failed"
                    item.last_error = str(e)
                    item.attempt_count += 1
                    item.updated_at = self._get_current_timestamp()
                    self._repository.update_queue_status(item)
                    failed_count += 1

                progress.update(task_id, advance=1)

        self._logger.success(
            f"Completed {entity_type}: {extracted_count} extracted, " f"{failed_count} failed, {skipped_count} skipped"
        )

        return {
            "entity_type": entity_type,
            "extracted": extracted_count,
            "failed": failed_count,
            "skipped": skipped_count,
        }

    def _process_attachment_queue(self, snapshot_id: str) -> Dict[str, Any]:
        """Process attachment download queue.

        Downloads all pending/failed attachments from the attachment queue,
        updates attachment metadata with local file paths, and tracks download status.
        Enables retry of failed downloads without re-fetching parent entities.

        Args:
            snapshot_id: Map snapshot UUID

        Returns:
            Dictionary with attachment processing results:
            - downloaded: Number of attachments successfully downloaded
            - failed: Number of attachments that failed download
            - skipped: Number of attachments already done
        """
        self._logger.info("Processing attachment download queue...")

        # Import AttachmentDownloader locally to avoid circular imports
        from ..extractors.attachment_downloader import AttachmentDownloader

        # Get pending and failed attachments for retry
        pending_attachments = self._repository.get_attachment_queue(snapshot_id, status="pending")
        failed_attachments = self._repository.get_attachment_queue(snapshot_id, status="failed")
        all_attachments = pending_attachments + failed_attachments

        if not all_attachments:
            self._logger.info("No attachments to download")
            return {"downloaded": 0, "failed": 0, "skipped": 0}

        # Initialize attachment downloader
        attachment_downloader = AttachmentDownloader(logger=self._logger)

        # Track results
        downloaded_count = 0
        failed_count = 0

        # Process attachments with Rich progress bar
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeRemainingColumn(),
            console=self._console,
        ) as progress:
            task_id = progress.add_task("Downloading attachments...", total=len(all_attachments))

            for queue_item in all_attachments:
                try:
                    # Mark in progress
                    queue_item.status = "in_progress"
                    queue_item.updated_at = self._get_current_timestamp()
                    self._repository.update_attachment_queue_status(queue_item)

                    # Get attachment metadata from repository
                    attachment = self._repository.get_attachment_by_id(queue_item.attachment_id)

                    if not attachment:
                        # Attachment not found in database
                        queue_item.status = "failed"
                        queue_item.last_error = f"Attachment not found: {queue_item.attachment_id}"
                        queue_item.attempt_count += 1
                        queue_item.updated_at = self._get_current_timestamp()
                        self._repository.update_attachment_queue_status(queue_item)
                        failed_count += 1
                        progress.update(task_id, advance=1)
                        continue

                    # Download attachment file
                    download_result = attachment_downloader.download_attachment(attachment)

                    if download_result["success"]:
                        # Update attachment metadata with downloaded file path
                        from ..models import Attachment

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

                        # Mark done
                        queue_item.status = "done"
                        queue_item.last_error = None
                        downloaded_count += 1
                    else:
                        # Download failed
                        queue_item.status = "failed"
                        queue_item.last_error = download_result.get("error_message", "Unknown error")
                        queue_item.attempt_count += 1
                        failed_count += 1

                    queue_item.updated_at = self._get_current_timestamp()
                    self._repository.update_attachment_queue_status(queue_item)

                except Exception as e:
                    # Mark failed with exception info
                    self._logger.error(f"Failed to download attachment {queue_item.attachment_id}: {e}")
                    queue_item.status = "failed"
                    queue_item.last_error = str(e)
                    queue_item.attempt_count += 1
                    queue_item.updated_at = self._get_current_timestamp()
                    self._repository.update_attachment_queue_status(queue_item)
                    failed_count += 1

                progress.update(task_id, advance=1)

        self._logger.success(f"Attachment processing completed: {downloaded_count} downloaded, {failed_count} failed")

        return {
            "downloaded": downloaded_count,
            "failed": failed_count,
            "skipped": 0,
        }

    def _validate_completeness(
        self,
        snapshot_id: str,
        entity_types: List[str],
        entity_results: Dict[str, Any],
        attachment_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Validate extraction completeness against map snapshot totals.

        Compares expected entity counts from map snapshot with actual extracted counts.
        Checks for missing entities, failed extractions, and attachment download issues.
        Returns list of discrepancies for reporting.

        Args:
            snapshot_id: Map snapshot UUID
            entity_types: List of entity types that were extracted
            entity_results: Extraction results per entity type
            attachment_result: Attachment download results

        Returns:
            List of discrepancy dictionaries with:
            - type: Type of discrepancy (entity_count, failed_entities, failed_attachments)
            - entity_type: Entity type affected (if applicable)
            - expected: Expected count from map
            - actual: Actual extracted/done count
            - difference: Expected - actual
            - severity: "error" or "warning"
            - message: Human-readable description
        """
        self._logger.info("Validating extraction completeness...")

        discrepancies = []

        # Validate per-type entity counts
        for entity_type in entity_types:
            # Get expected count from entity inventory (map snapshot)
            inventory = self._repository.get_entity_inventory(snapshot_id, entity_type)
            expected_count = len(inventory)

            # Get actual extracted count
            result = entity_results.get(entity_type, {})
            extracted_count = result.get("extracted", 0)
            failed_count = result.get("failed", 0)

            # Check if extracted + failed = expected (all items were attempted)
            total_attempted = extracted_count + failed_count

            if total_attempted < expected_count:
                # Some entities weren't even attempted (queue incomplete)
                discrepancies.append(
                    {
                        "type": "entity_count_mismatch",
                        "entity_type": entity_type,
                        "expected": expected_count,
                        "actual": total_attempted,
                        "difference": expected_count - total_attempted,
                        "severity": "error",
                        "message": f"{entity_type}: {expected_count - total_attempted} entities not attempted "
                        f"(expected {expected_count}, attempted {total_attempted})",
                    }
                )

            # Check for failed extractions
            if failed_count > 0:
                discrepancies.append(
                    {
                        "type": "failed_entities",
                        "entity_type": entity_type,
                        "expected": expected_count,
                        "actual": extracted_count,
                        "difference": failed_count,
                        "severity": "warning" if failed_count < expected_count * 0.1 else "error",  # <10% = warning
                        "message": f"{entity_type}: {failed_count} entities failed extraction "
                        f"({extracted_count}/{expected_count} successful)",
                    }
                )

        # Validate attachment downloads
        attachment_failed = attachment_result.get("failed", 0)
        if attachment_failed > 0:
            attachment_total = (
                attachment_result.get("downloaded", 0)
                + attachment_result.get("failed", 0)
                + attachment_result.get("skipped", 0)
            )
            discrepancies.append(
                {
                    "type": "failed_attachments",
                    "entity_type": None,
                    "expected": attachment_total,
                    "actual": attachment_result.get("downloaded", 0),
                    "difference": attachment_failed,
                    "severity": "warning" if attachment_failed < attachment_total * 0.1 else "error",
                    "message": f"Attachments: {attachment_failed} failed download "
                    f"({attachment_result.get('downloaded', 0)}/{attachment_total} successful)",
                }
            )

        # Log summary
        if discrepancies:
            self._logger.warning(f"Found {len(discrepancies)} completeness discrepancy(ies)")
            for disc in discrepancies:
                log_method = self._logger.error if disc["severity"] == "error" else self._logger.warning
                log_method(f"  [{disc['severity'].upper()}] {disc['message']}")
        else:
            self._logger.success("Completeness validation passed: all entities and attachments accounted for")

        return discrepancies

    def _create_extractor(self, entity_type: str, snapshot_id: str):
        """Create extractor instance for the specified entity type.

        Args:
            entity_type: Name of entity type (e.g., "clients")
            snapshot_id: Map snapshot UUID for attachment queuing

        Returns:
            Initialized extractor instance with attachment queuing enabled
        """
        extractor_class = self._EXTRACTOR_MAP.get(entity_type)
        if not extractor_class:
            raise ValueError(f"No extractor found for entity type: {entity_type}")

        return extractor_class(
            jobber_client=self._jobber_client,
            entity_mapper=self._entity_mapper,
            repository=self._repository,
            logger=self._logger,
            config_manager=self._config_manager,
            skip_existing_entities=False,  # Extract mode doesn't skip
            # Note: Attachment queuing is available but disabled by default
            # to maintain backward compatibility. Pass queue_attachments=True
            # and map_snapshot_id to enable it when needed.
        )

    def get_queue_status(
        self,
        snapshot_id: str,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get current status of extract queues.

        Args:
            snapshot_id: Map snapshot UUID
            entity_type: Optional entity type to filter by

        Returns:
            Dictionary with queue status by entity type
        """
        snapshot = self._repository.get_map_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"Map snapshot not found: {snapshot_id}")

        import json

        entity_types = [entity_type] if entity_type else json.loads(snapshot.entities_included)

        status_by_type = {}

        for et in entity_types:
            pending = len(self._repository.get_extract_queue(snapshot_id, et, status="pending"))
            in_progress = len(self._repository.get_extract_queue(snapshot_id, et, status="in_progress"))
            done = len(self._repository.get_extract_queue(snapshot_id, et, status="done"))
            failed = len(self._repository.get_extract_queue(snapshot_id, et, status="failed"))

            status_by_type[et] = {
                "pending": pending,
                "in_progress": in_progress,
                "done": done,
                "failed": failed,
                "total": pending + in_progress + done + failed,
            }

        return status_by_type

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format.

        Returns:
            ISO8601 formatted timestamp string
        """
        return datetime.now(UTC).isoformat()
