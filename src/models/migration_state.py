"""MigrationState model for tracking cursor positions per entity type."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MigrationState:
    """Migration state for tracking cursor positions and sync progress during resume operations.

    Tracks the last processed cursor position, total records fetched, and sync status
    for each entity type to enable resumption from the last checkpoint during migrations.

    This supports Phase 7's resumable extraction pattern where large migrations can be
    interrupted and resumed without re-processing already extracted data.
    """

    entity_type: str
    last_cursor: Optional[str]
    updated_at: str
    total_fetched: int = 0
    sync_status: str = "pending"  # pending, in_progress, completed, error
    last_sync_at: Optional[str] = None
