"""AttachmentQueueItem model for tracking attachment download status."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AttachmentQueueItem:
    """Attachment queue item for tracking binary download status.

    Represents a single attachment queued for download during the extract pass.
    Decouples attachment downloads from parent entity extraction, enabling:
    - Isolated retry of failed downloads without re-fetching parent entities
    - Per-attachment status tracking (pending/in_progress/done/failed)
    - Batch download processing after entity extraction
    - Error tracking with detailed messages
    - Retry attempt counting

    Status flow:
        pending → in_progress → done (download success)
                              → failed (download error, can retry)

    Queue items are created during entity extraction when attachments are
    discovered, then processed in a separate download pass. This prevents
    attachment download failures from blocking entity extraction.
    """

    attachment_id: str  # The unique identifier of the attachment
    parent_type: str  # Type of parent entity (e.g., "clients", "invoices")
    parent_id: str  # ID of parent entity this attachment belongs to
    status: str  # Queue status: pending, in_progress, done, failed
    map_snapshot_id: str  # Foreign key to map_snapshot table
    updated_at: str  # ISO8601DateTime of last status update
    last_error: Optional[str] = None  # Error message from last failed download
    attempt_count: int = 0  # Number of download attempts made
