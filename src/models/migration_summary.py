"""Migration summary data structure for reporting and logging."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=False)
class MigrationSummary:
    """
    Represents the results and status of a migration operation.

    Used by MigrationCoordinator to structure migration results for CLI reporting
    and structured logging. Not frozen to allow error collection during migration.
    """

    clients_processed: int  # Number of client records successfully processed
    invoices_processed: int  # Number of invoice records successfully processed
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
