"""MapSnapshot model for tracking map pass execution metadata."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MapSnapshot:
    """Map snapshot record for tracking discovery pass execution.

    Represents a complete map pass execution with metadata about what was
    discovered, when it was discovered, and what entities were included.
    Snapshots enable:
    - Multiple extract passes from the same map data
    - Comparison of different map passes over time
    - Resumable extraction with known entity counts
    - Data drift detection (entities updated after pass1_cutoff)

    The entities_included field stores entity types as a JSON string:
        '["clients", "invoices", "quotes", "jobs"]'

    Labels provide human-friendly identifiers for snapshots, e.g.:
        - "2025-01-migration"
        - "pre-cleanup-snapshot"
        - "quarterly-backup"
    """

    id: str  # Unique snapshot identifier (UUID)
    created_at: str  # ISO8601DateTime when snapshot was created
    pass1_cutoff: str  # ISO8601DateTime marking snapshot cutoff time
    label: Optional[str] = None  # Human-friendly label for this snapshot
    entities_included: str = "[]"  # JSON array of entity types included
