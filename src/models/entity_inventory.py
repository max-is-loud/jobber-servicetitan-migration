"""EntityInventory model for tracking discovered entities during map pass."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EntityInventory:
    """Entity inventory record for map mode discovery pass.

    Stores lightweight metadata about entities discovered during the map pass,
    including entity identifiers, timestamps, and estimated relationship counts.
    This enables targeted extraction planning and cost estimation before full
    data retrieval.

    The estimated_relations field stores counts as a JSON string for SQLite
    TEXT storage. Example format:
        '{"notes": 5, "attachments": 2, "line_items": 10}'

    This data is used to:
    - Estimate API costs for full extraction
    - Identify "heavy" entities with many relations
    - Plan pagination and concurrency strategies
    - Build extraction queues for the extract pass
    """

    entity_type: str  # Entity type name (e.g., "clients", "invoices")
    entity_id: str  # The unique identifier from Jobber API
    discovered_at: str  # ISO8601DateTime when discovered during map pass
    map_snapshot_id: str  # Foreign key to map_snapshot table
    updated_at: Optional[str] = None  # Last update timestamp from API (if available)
    estimated_relations_json: str = "{}"  # JSON string of relation counts
