"""MigrationState model for tracking cursor positions per entity type."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MigrationState:
    """Migration state for tracking cursor positions during resume operations.

    Tracks the last processed cursor position for each entity type to enable
    resumption from the last processed position during migrations.
    """

    entity_type: str
    last_cursor: Optional[str]
    updated_at: str
