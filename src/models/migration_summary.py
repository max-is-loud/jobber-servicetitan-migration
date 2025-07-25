"""Migration summary data structure for reporting and logging."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=False)
class MigrationSummary:
    """
    Represents the results and status of a complete migration operation.

    Used by migration coordinators to structure migration results for CLI reporting
    and structured logging. Supports all entity types including Client, Invoice,
    Quote, Note, and Attachment with comprehensive metrics and error tracking.
    Includes skip tracking for resumable migrations.
    Not frozen to allow error collection during migration.
    """

    clients_processed: int  # Number of client records successfully processed
    invoices_processed: int  # Number of invoice records successfully processed
    quotes_processed: int  # Number of quote records successfully processed
    notes_processed: int  # Number of note records successfully processed
    note_references_collected: int  # Number of note references collected for deferred processing
    attachments_processed: int  # Number of attachment records successfully processed
    files_downloaded: int  # Number of attachment files successfully downloaded
    total_bytes_downloaded: int  # Total bytes of attachment files downloaded
    download_failures: int  # Number of attachment download failures
    start_time: str  # ISO format timestamp when migration started
    end_time: str  # ISO format timestamp when migration completed
    duration_seconds: float  # Total migration time in seconds
    errors: List[str]  # List of non-fatal errors encountered during processing

    # Skip tracking fields for resumable migrations
    clients_skipped: int = 0  # Number of client records skipped (already exist)
    invoices_skipped: int = 0  # Number of invoice records skipped (already exist)
    quotes_skipped: int = 0  # Number of quote records skipped (already exist)
    notes_skipped: int = 0  # Number of note records skipped (already exist)
    attachments_skipped: int = 0  # Number of attachment records skipped (already exist)

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

    def get_total_entities(self, include_skipped: bool = False) -> int:
        """Get total number of entities processed across all types.

        Args:
            include_skipped: Whether to include skipped entities in the count

        Returns:
            Total count of processed entities (and optionally skipped)
        """
        processed = (
            self.clients_processed
            + self.invoices_processed
            + self.quotes_processed
            + self.notes_processed
            + self.attachments_processed
        )

        if include_skipped:
            skipped = (
                self.clients_skipped
                + self.invoices_skipped
                + self.quotes_skipped
                + self.notes_skipped
                + self.attachments_skipped
            )
            return processed + skipped

        return processed

    def get_total_skipped(self) -> int:
        """Get total number of entities skipped across all types.

        Returns:
            Total count of skipped entities
        """
        return (
            self.clients_skipped
            + self.invoices_skipped
            + self.quotes_skipped
            + self.notes_skipped
            + self.attachments_skipped
        )

    def get_skip_percentage(self) -> float:
        """Calculate percentage of entities that were skipped.

        Returns:
            Skip percentage (0.0 to 100.0), or 0.0 if no entities processed
        """
        total_entities = self.get_total_entities(include_skipped=True)
        if total_entities == 0:
            return 0.0

        return (self.get_total_skipped() / total_entities) * 100.0

    def format_summary(self) -> str:
        """Format comprehensive migration summary string.

        Returns:
            Human-readable summary of all migration metrics including skip statistics
        """
        total_entities = self.get_total_entities()
        total_skipped = self.get_total_skipped()
        skip_percentage = self.get_skip_percentage()

        summary_lines = [
            f"Migration completed in {self.format_duration()}:",
            f"  • {self.clients_processed:,} clients processed",
            f"  • {self.invoices_processed:,} invoices processed",
            f"  • {self.quotes_processed:,} quotes processed",
            f"  • {self.notes_processed:,} notes processed",
            f"  • {self.note_references_collected:,} note references collected",
            f"  • {self.attachments_processed:,} attachments processed",
            f"  • {self.files_downloaded:,} files downloaded ({self.total_bytes_downloaded:,} bytes)",  # noqa: E501
            f"  • {total_entities:,} total entities processed",
        ]

        # Add skip statistics if any entities were skipped
        if total_skipped > 0:
            summary_lines.extend(
                [
                    "",  # Empty line for separation
                    "Skip Statistics:",
                    f"  • {self.clients_skipped:,} clients skipped",
                    f"  • {self.invoices_skipped:,} invoices skipped",
                    f"  • {self.quotes_skipped:,} quotes skipped",
                    f"  • {self.notes_skipped:,} notes skipped",
                    f"  • {self.attachments_skipped:,} attachments skipped",
                    f"  • {total_skipped:,} total entities skipped ({skip_percentage:.1f}%)",
                ]
            )

        if self.download_failures > 0:
            summary_lines.append(f"  • {self.download_failures} download failures")

        if self.errors:
            summary_lines.append(f"  • {len(self.errors)} non-fatal errors")

        return "\n".join(summary_lines)
