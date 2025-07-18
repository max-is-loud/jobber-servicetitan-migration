"""Migration summary data structure for reporting and logging."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=False)
class MigrationSummary:
    """
    Represents the results and status of a complete migration operation.

    Used by MigrationCoordinator to structure migration results for CLI reporting
    and structured logging. Supports all entity types including Client, Invoice,
    Quote, Note, and Attachment with comprehensive metrics and error tracking.
    Not frozen to allow error collection during migration.
    """

    clients_processed: int  # Number of client records successfully processed
    invoices_processed: int  # Number of invoice records successfully processed
    quotes_processed: int  # Number of quote records successfully processed
    notes_processed: int  # Number of note records successfully processed
    attachments_processed: int  # Number of attachment records successfully processed
    files_downloaded: int  # Number of attachment files successfully downloaded
    total_bytes_downloaded: int  # Total bytes of attachment files downloaded
    download_failures: int  # Number of attachment download failures
    start_time: str  # ISO format timestamp when migration started
    end_time: str  # ISO format timestamp when migration completed
    duration_seconds: float  # Total migration time in seconds
    errors: List[str]  # List of non-fatal errors encountered during processing

    def format_duration(self) -> str:
        """Format duration_seconds into human-readable time string.

        Returns:
            Human-readable duration string (e.g., "2.3 seconds", "1m 23.5s")
        """
        if self.duration_seconds < 60:
            return f"{self.duration_seconds:.1f} seconds"

        minutes = int(self.duration_seconds // 60)
        seconds = self.duration_seconds % 60
        return f"{minutes}m {seconds:.1f}s"

    def add_error(self, error: str) -> None:
        """Add a non-fatal error to the error list.

        Args:
            error: Error message to track
        """
        self.errors.append(error)

    def get_total_entities(self) -> int:
        """Get total number of entities processed across all types.

        Returns:
            Total count of all processed entities
        """
        return (
            self.clients_processed
            + self.invoices_processed
            + self.quotes_processed
            + self.notes_processed
            + self.attachments_processed
        )

    def format_summary(self) -> str:
        """Format comprehensive migration summary string.

        Returns:
            Human-readable summary of all migration metrics
        """
        total_entities = self.get_total_entities()
        summary_lines = [
            f"Migration completed in {self.format_duration()}:",
            f"  • {self.clients_processed:,} clients processed",
            f"  • {self.invoices_processed:,} invoices processed",
            f"  • {self.quotes_processed:,} quotes processed",
            f"  • {self.notes_processed:,} notes processed",
            f"  • {self.attachments_processed:,} attachments processed",
            f"  • {self.files_downloaded:,} files downloaded ({self.total_bytes_downloaded:,} bytes)",  # noqa: E501
            f"  • {total_entities:,} total entities processed",
        ]

        if self.download_failures > 0:
            summary_lines.append(f"  • {self.download_failures} download failures")

        if self.errors:
            summary_lines.append(f"  • {len(self.errors)} non-fatal errors")

        return "\n".join(summary_lines)
