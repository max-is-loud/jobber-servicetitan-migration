"""Unit tests for multi-pass migration domain models."""

import pytest
from src.models import (
    EntityInventory,
    MapSnapshot,
    ExtractQueueItem,
    AttachmentQueueItem,
)


class TestEntityInventory:
    """Test suite for EntityInventory model."""

    def test_entity_inventory_with_required_fields(self):
        """Test EntityInventory instantiation with required fields only."""
        inventory = EntityInventory(
            entity_type="clients",
            entity_id="client-123",
            discovered_at="2025-01-19T10:30:00Z",
            map_snapshot_id="snap-001",
        )

        assert inventory.entity_type == "clients"
        assert inventory.entity_id == "client-123"
        assert inventory.discovered_at == "2025-01-19T10:30:00Z"
        assert inventory.map_snapshot_id == "snap-001"
        assert inventory.updated_at is None
        assert inventory.estimated_relations_json == "{}"

    def test_entity_inventory_with_all_fields(self):
        """Test EntityInventory instantiation with all fields including optional."""
        inventory = EntityInventory(
            entity_type="invoices",
            entity_id="invoice-456",
            discovered_at="2025-01-19T10:30:00Z",
            map_snapshot_id="snap-001",
            updated_at="2025-01-19T09:00:00Z",
            estimated_relations_json='{"notes": 5, "attachments": 2}',
        )

        assert inventory.entity_type == "invoices"
        assert inventory.entity_id == "invoice-456"
        assert inventory.discovered_at == "2025-01-19T10:30:00Z"
        assert inventory.map_snapshot_id == "snap-001"
        assert inventory.updated_at == "2025-01-19T09:00:00Z"
        assert inventory.estimated_relations_json == '{"notes": 5, "attachments": 2}'

    def test_entity_inventory_default_estimated_relations_json(self):
        """Test EntityInventory has default empty JSON object for estimated_relations_json."""
        inventory = EntityInventory(
            entity_type="jobs",
            entity_id="job-789",
            discovered_at="2025-01-19T10:30:00Z",
            map_snapshot_id="snap-002",
        )

        assert inventory.estimated_relations_json == "{}"

    def test_entity_inventory_is_dataclass(self):
        """Test EntityInventory is a dataclass with proper attributes."""
        inventory = EntityInventory(
            entity_type="quotes",
            entity_id="quote-111",
            discovered_at="2025-01-19T10:30:00Z",
            map_snapshot_id="snap-003",
        )

        # Verify dataclass functionality
        assert hasattr(inventory, "__dataclass_fields__")
        assert "entity_type" in inventory.__dataclass_fields__
        assert "entity_id" in inventory.__dataclass_fields__


class TestMapSnapshot:
    """Test suite for MapSnapshot model."""

    def test_map_snapshot_with_required_fields(self):
        """Test MapSnapshot instantiation with required fields only."""
        snapshot = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
        )

        assert snapshot.id == "snap-001"
        assert snapshot.created_at == "2025-01-19T10:00:00Z"
        assert snapshot.pass1_cutoff == "2025-01-19T10:00:00Z"
        assert snapshot.label is None
        assert snapshot.entities_included == "[]"

    def test_map_snapshot_with_all_fields(self):
        """Test MapSnapshot instantiation with all fields including optional."""
        snapshot = MapSnapshot(
            id="snap-002",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
            label="2025-q1-migration",
            entities_included='["clients", "invoices", "jobs"]',
        )

        assert snapshot.id == "snap-002"
        assert snapshot.created_at == "2025-01-19T10:00:00Z"
        assert snapshot.pass1_cutoff == "2025-01-19T10:00:00Z"
        assert snapshot.label == "2025-q1-migration"
        assert snapshot.entities_included == '["clients", "invoices", "jobs"]'

    def test_map_snapshot_default_entities_included(self):
        """Test MapSnapshot has default empty JSON array for entities_included."""
        snapshot = MapSnapshot(
            id="snap-003",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
        )

        assert snapshot.entities_included == "[]"

    def test_map_snapshot_is_dataclass(self):
        """Test MapSnapshot is a dataclass with proper attributes."""
        snapshot = MapSnapshot(
            id="snap-004",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
        )

        # Verify dataclass functionality
        assert hasattr(snapshot, "__dataclass_fields__")
        assert "id" in snapshot.__dataclass_fields__
        assert "label" in snapshot.__dataclass_fields__


class TestExtractQueueItem:
    """Test suite for ExtractQueueItem model."""

    def test_extract_queue_item_with_required_fields(self):
        """Test ExtractQueueItem instantiation with required fields only."""
        queue_item = ExtractQueueItem(
            entity_type="clients",
            entity_id="client-123",
            status="pending",
            map_snapshot_id="snap-001",
            updated_at="2025-01-19T10:30:00Z",
        )

        assert queue_item.entity_type == "clients"
        assert queue_item.entity_id == "client-123"
        assert queue_item.status == "pending"
        assert queue_item.map_snapshot_id == "snap-001"
        assert queue_item.updated_at == "2025-01-19T10:30:00Z"
        assert queue_item.last_error is None
        assert queue_item.attempt_count == 0

    def test_extract_queue_item_with_all_fields(self):
        """Test ExtractQueueItem instantiation with all fields including optional."""
        queue_item = ExtractQueueItem(
            entity_type="invoices",
            entity_id="invoice-456",
            status="failed",
            map_snapshot_id="snap-002",
            updated_at="2025-01-19T10:35:00Z",
            last_error="Connection timeout after 30s",
            attempt_count=3,
        )

        assert queue_item.entity_type == "invoices"
        assert queue_item.entity_id == "invoice-456"
        assert queue_item.status == "failed"
        assert queue_item.map_snapshot_id == "snap-002"
        assert queue_item.updated_at == "2025-01-19T10:35:00Z"
        assert queue_item.last_error == "Connection timeout after 30s"
        assert queue_item.attempt_count == 3

    def test_extract_queue_item_default_attempt_count(self):
        """Test ExtractQueueItem has default attempt_count of 0."""
        queue_item = ExtractQueueItem(
            entity_type="jobs",
            entity_id="job-789",
            status="pending",
            map_snapshot_id="snap-003",
            updated_at="2025-01-19T10:30:00Z",
        )

        assert queue_item.attempt_count == 0

    def test_extract_queue_item_status_values(self):
        """Test ExtractQueueItem with different status values."""
        statuses = ["pending", "in_progress", "done", "failed"]

        for status in statuses:
            queue_item = ExtractQueueItem(
                entity_type="quotes",
                entity_id="quote-999",
                status=status,
                map_snapshot_id="snap-004",
                updated_at="2025-01-19T10:30:00Z",
            )
            assert queue_item.status == status

    def test_extract_queue_item_is_dataclass(self):
        """Test ExtractQueueItem is a dataclass with proper attributes."""
        queue_item = ExtractQueueItem(
            entity_type="clients",
            entity_id="client-999",
            status="pending",
            map_snapshot_id="snap-005",
            updated_at="2025-01-19T10:30:00Z",
        )

        # Verify dataclass functionality
        assert hasattr(queue_item, "__dataclass_fields__")
        assert "status" in queue_item.__dataclass_fields__
        assert "attempt_count" in queue_item.__dataclass_fields__


class TestAttachmentQueueItem:
    """Test suite for AttachmentQueueItem model."""

    def test_attachment_queue_item_with_required_fields(self):
        """Test AttachmentQueueItem instantiation with required fields only."""
        queue_item = AttachmentQueueItem(
            attachment_id="att-123",
            parent_type="clients",
            parent_id="client-456",
            status="pending",
            map_snapshot_id="snap-001",
            updated_at="2025-01-19T10:30:00Z",
        )

        assert queue_item.attachment_id == "att-123"
        assert queue_item.parent_type == "clients"
        assert queue_item.parent_id == "client-456"
        assert queue_item.status == "pending"
        assert queue_item.map_snapshot_id == "snap-001"
        assert queue_item.updated_at == "2025-01-19T10:30:00Z"
        assert queue_item.last_error is None
        assert queue_item.attempt_count == 0

    def test_attachment_queue_item_with_all_fields(self):
        """Test AttachmentQueueItem instantiation with all fields including optional."""
        queue_item = AttachmentQueueItem(
            attachment_id="att-456",
            parent_type="invoices",
            parent_id="invoice-789",
            status="failed",
            map_snapshot_id="snap-002",
            updated_at="2025-01-19T10:35:00Z",
            last_error="File not found: 404",
            attempt_count=2,
        )

        assert queue_item.attachment_id == "att-456"
        assert queue_item.parent_type == "invoices"
        assert queue_item.parent_id == "invoice-789"
        assert queue_item.status == "failed"
        assert queue_item.map_snapshot_id == "snap-002"
        assert queue_item.updated_at == "2025-01-19T10:35:00Z"
        assert queue_item.last_error == "File not found: 404"
        assert queue_item.attempt_count == 2

    def test_attachment_queue_item_default_attempt_count(self):
        """Test AttachmentQueueItem has default attempt_count of 0."""
        queue_item = AttachmentQueueItem(
            attachment_id="att-789",
            parent_type="jobs",
            parent_id="job-111",
            status="pending",
            map_snapshot_id="snap-003",
            updated_at="2025-01-19T10:30:00Z",
        )

        assert queue_item.attempt_count == 0

    def test_attachment_queue_item_status_values(self):
        """Test AttachmentQueueItem with different status values."""
        statuses = ["pending", "in_progress", "done", "failed"]

        for status in statuses:
            queue_item = AttachmentQueueItem(
                attachment_id="att-999",
                parent_type="quotes",
                parent_id="quote-888",
                status=status,
                map_snapshot_id="snap-004",
                updated_at="2025-01-19T10:30:00Z",
            )
            assert queue_item.status == status

    def test_attachment_queue_item_is_dataclass(self):
        """Test AttachmentQueueItem is a dataclass with proper attributes."""
        queue_item = AttachmentQueueItem(
            attachment_id="att-111",
            parent_type="clients",
            parent_id="client-222",
            status="pending",
            map_snapshot_id="snap-005",
            updated_at="2025-01-19T10:30:00Z",
        )

        # Verify dataclass functionality
        assert hasattr(queue_item, "__dataclass_fields__")
        assert "attachment_id" in queue_item.__dataclass_fields__
        assert "parent_type" in queue_item.__dataclass_fields__
