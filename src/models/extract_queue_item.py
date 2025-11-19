"""ExtractQueueItem model for tracking entity extraction status."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractQueueItem:
    """Extract queue item for tracking per-entity extraction status.

    Represents a single entity queued for extraction during the extract pass.
    Enables:
    - Per-entity status tracking (pending/in_progress/done/failed)
    - Resumable extraction (skip done, retry failed)
    - Error tracking with detailed messages
    - Retry attempt counting
    - Targeted re-extraction without full pipeline restart

    Status flow:
        pending → in_progress → done (success)
                              → failed (error, can retry)

    Queue items are created from entity_inventory records during extract pass
    initialization and updated as extraction progresses.
    """

    entity_type: str  # Entity type name (e.g., "clients", "invoices")
    entity_id: str  # The unique identifier to extract
    status: str  # Queue status: pending, in_progress, done, failed
    map_snapshot_id: str  # Foreign key to map_snapshot table
    updated_at: str  # ISO8601DateTime of last status update
    last_error: Optional[str] = None  # Error message from last failed attempt
    attempt_count: int = 0  # Number of extraction attempts made
