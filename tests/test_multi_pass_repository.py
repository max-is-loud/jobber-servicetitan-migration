"""Unit tests for multi-pass migration repository methods."""

import sqlite3
import pytest
from src.repositories.repository import Repository
from src.exceptions import RepositoryError
from src.models import (
    EntityInventory,
    MapSnapshot,
    ExtractQueueItem,
    AttachmentQueueItem,
)


class TestMultiPassSchemaInitialization:
    """Test suite for multi-pass migration schema creation."""

    def test_init_schema_creates_multi_pass_tables(self):
        """Test init_schema creates all multi-pass migration tables."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        cursor = conn.cursor()

        # Verify all multi-pass tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            "map_snapshot",
            "entity_inventory",
            "relation_inventory",
            "extract_queue",
            "attachment_queue",
        }

        assert expected_tables.issubset(tables)

        cursor.close()
        conn.close()

    def test_map_snapshot_table_has_correct_columns(self):
        """Test map_snapshot table has all required columns."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(map_snapshot)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {"id", "label", "created_at", "entities_included", "pass1_cutoff"}
        assert expected_columns == columns

        cursor.close()
        conn.close()

    def test_entity_inventory_table_has_composite_primary_key(self):
        """Test entity_inventory has composite primary key (entity_type, entity_id, map_snapshot_id)."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        cursor = conn.cursor()

        # Insert first record
        cursor.execute(
            """INSERT INTO entity_inventory
               (entity_type, entity_id, discovered_at, map_snapshot_id)
               VALUES ('clients', 'c1', '2025-01-19T10:00:00Z', 'snap1')"""
        )

        # Should succeed - different snapshot
        cursor.execute(
            """INSERT INTO entity_inventory
               (entity_type, entity_id, discovered_at, map_snapshot_id)
               VALUES ('clients', 'c1', '2025-01-19T10:00:00Z', 'snap2')"""
        )

        # Should fail - duplicate composite key
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """INSERT INTO entity_inventory
                   (entity_type, entity_id, discovered_at, map_snapshot_id)
                   VALUES ('clients', 'c1', '2025-01-19T10:00:00Z', 'snap1')"""
            )

        cursor.close()
        conn.close()

    def test_extract_queue_table_has_foreign_key_cascade_delete(self):
        """Test extract_queue foreign key constraint with CASCADE delete."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        cursor = conn.cursor()

        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys = ON")

        # Insert snapshot
        cursor.execute(
            """INSERT INTO map_snapshot (id, created_at, pass1_cutoff)
               VALUES ('snap1', '2025-01-19T10:00:00Z', '2025-01-19T10:00:00Z')"""
        )

        # Insert queue item
        cursor.execute(
            """INSERT INTO extract_queue
               (entity_type, entity_id, status, map_snapshot_id, updated_at)
               VALUES ('clients', 'c1', 'pending', 'snap1', '2025-01-19T10:00:00Z')"""
        )

        conn.commit()

        # Verify queue item exists
        cursor.execute("SELECT COUNT(*) FROM extract_queue WHERE map_snapshot_id = 'snap1'")
        assert cursor.fetchone()[0] == 1

        # Delete snapshot - should cascade delete queue item
        cursor.execute("DELETE FROM map_snapshot WHERE id = 'snap1'")
        conn.commit()

        # Verify queue item was deleted
        cursor.execute("SELECT COUNT(*) FROM extract_queue WHERE map_snapshot_id = 'snap1'")
        assert cursor.fetchone()[0] == 0

        cursor.close()
        conn.close()

    def test_multi_pass_indexes_created(self):
        """Test all multi-pass migration indexes are created."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        cursor = conn.cursor()

        # Get all indexes
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = {row[0] for row in cursor.fetchall()}

        expected_indexes = {
            "idx_entity_inventory_snapshot",
            "idx_entity_inventory_type",
            "idx_relation_inventory_snapshot",
            "idx_extract_queue_snapshot",
            "idx_extract_queue_status",
            "idx_attachment_queue_snapshot",
            "idx_attachment_queue_status",
        }

        assert expected_indexes.issubset(indexes)

        cursor.close()
        conn.close()


class TestMapSnapshotRepository:
    """Test suite for MapSnapshot repository methods."""

    def test_save_map_snapshot(self):
        """Test saving a map snapshot."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        snapshot = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
            label="test-snapshot",
            entities_included='["clients", "invoices"]',
        )

        repo.save_map_snapshot(snapshot)

        # Verify saved
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM map_snapshot WHERE id = ?", ("snap-001",))
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "snap-001"
        assert row[1] == "test-snapshot"

        cursor.close()
        conn.close()

    def test_save_map_snapshot_upsert_behavior(self):
        """Test saving same snapshot twice (INSERT OR REPLACE)."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        snapshot1 = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
            label="first-label",
        )

        repo.save_map_snapshot(snapshot1)

        # Update with same ID
        snapshot2 = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T11:00:00Z",
            pass1_cutoff="2025-01-19T11:00:00Z",
            label="updated-label",
        )

        repo.save_map_snapshot(snapshot2)

        # Should only have one record with updated values
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM map_snapshot")
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT label FROM map_snapshot WHERE id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == "updated-label"

        cursor.close()
        conn.close()

    def test_get_map_snapshot_by_id(self):
        """Test retrieving map snapshot by ID."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        snapshot = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
            label="test-snapshot",
            entities_included='["clients"]',
        )

        repo.save_map_snapshot(snapshot)

        # Retrieve by ID
        retrieved = repo.get_map_snapshot("snap-001")

        assert retrieved is not None
        assert retrieved.id == "snap-001"
        assert retrieved.label == "test-snapshot"
        assert retrieved.entities_included == '["clients"]'

        conn.close()

    def test_get_map_snapshot_by_label(self):
        """Test retrieving map snapshot by label."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        snapshot = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
            label="test-snapshot",
        )

        repo.save_map_snapshot(snapshot)

        # Retrieve by label
        retrieved = repo.get_map_snapshot("test-snapshot")

        assert retrieved is not None
        assert retrieved.id == "snap-001"
        assert retrieved.label == "test-snapshot"

        conn.close()

    def test_get_map_snapshot_not_found(self):
        """Test retrieving non-existent snapshot returns None."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        result = repo.get_map_snapshot("non-existent")

        assert result is None

        conn.close()

    def test_list_map_snapshots(self):
        """Test listing all map snapshots ordered by created_at DESC."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Insert multiple snapshots
        snapshots = [
            MapSnapshot(
                id="snap-001",
                created_at="2025-01-19T10:00:00Z",
                pass1_cutoff="2025-01-19T10:00:00Z",
                label="first",
            ),
            MapSnapshot(
                id="snap-002",
                created_at="2025-01-19T12:00:00Z",
                pass1_cutoff="2025-01-19T12:00:00Z",
                label="second",
            ),
            MapSnapshot(
                id="snap-003",
                created_at="2025-01-19T11:00:00Z",
                pass1_cutoff="2025-01-19T11:00:00Z",
                label="third",
            ),
        ]

        for snapshot in snapshots:
            repo.save_map_snapshot(snapshot)

        # List all
        results = repo.list_map_snapshots()

        assert len(results) == 3
        # Should be ordered by created_at DESC
        assert results[0].id == "snap-002"  # 12:00:00
        assert results[1].id == "snap-003"  # 11:00:00
        assert results[2].id == "snap-001"  # 10:00:00

        conn.close()

    def test_list_map_snapshots_empty(self):
        """Test listing snapshots when none exist."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        results = repo.list_map_snapshots()

        assert results == []

        conn.close()


class TestEntityInventoryRepository:
    """Test suite for EntityInventory repository methods."""

    def test_save_entity_inventory_batch(self):
        """Test batch saving entity inventory records."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="c2",
                discovered_at="2025-01-19T10:01:00Z",
                map_snapshot_id="snap-001",
                updated_at="2025-01-18T15:00:00Z",
                estimated_relations_json='{"notes": 3}',
            ),
            EntityInventory(
                entity_type="invoices",
                entity_id="i1",
                discovered_at="2025-01-19T10:02:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)

        # Verify all saved
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entity_inventory WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 3

        cursor.close()
        conn.close()

    def test_save_entity_inventory_empty_list(self):
        """Test saving empty list returns without error."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Should not raise error
        repo.save_entity_inventory([])

        conn.close()

    def test_get_entity_inventory_all(self):
        """Test retrieving all entity inventory for a snapshot."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
            EntityInventory(
                entity_type="invoices",
                entity_id="i1",
                discovered_at="2025-01-19T10:01:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)

        # Get all inventory
        results = repo.get_entity_inventory("snap-001")

        assert len(results) == 2
        assert results[0].entity_type == "clients"
        assert results[1].entity_type == "invoices"

        conn.close()

    def test_get_entity_inventory_filtered_by_type(self):
        """Test retrieving entity inventory filtered by entity type."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="c2",
                discovered_at="2025-01-19T10:01:00Z",
                map_snapshot_id="snap-001",
            ),
            EntityInventory(
                entity_type="invoices",
                entity_id="i1",
                discovered_at="2025-01-19T10:02:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)

        # Get only clients
        results = repo.get_entity_inventory("snap-001", entity_type="clients")

        assert len(results) == 2
        assert all(r.entity_type == "clients" for r in results)

        conn.close()

    def test_get_entity_inventory_empty(self):
        """Test retrieving inventory when none exists."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        results = repo.get_entity_inventory("non-existent")

        assert results == []

        conn.close()


class TestRelationInventoryRepository:
    """Test suite for relation_inventory repository methods."""

    def test_save_relation_inventory_batch(self):
        """Test batch saving relation inventory records."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        inventory = [
            {
                "parent_type": "clients",
                "parent_id": "c1",
                "relation_type": "notes",
                "count": 5,
                "cursor_hint": "cursor-abc",
                "map_snapshot_id": "snap-001",
            },
            {
                "parent_type": "clients",
                "parent_id": "c1",
                "relation_type": "invoices",
                "count": 10,
                "cursor_hint": None,
                "map_snapshot_id": "snap-001",
            },
        ]

        repo.save_relation_inventory(inventory)

        # Verify saved
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM relation_inventory WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 2

        cursor.close()
        conn.close()

    def test_save_relation_inventory_empty_list(self):
        """Test saving empty list returns without error."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Should not raise error
        repo.save_relation_inventory([])

        conn.close()


class TestExtractQueueRepository:
    """Test suite for ExtractQueue repository methods."""

    def test_create_extract_queue_from_inventory(self):
        """Test creating extract queue from entity inventory."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Create inventory
        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="c2",
                discovered_at="2025-01-19T10:01:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)

        # Create queue from inventory
        repo.create_extract_queue("snap-001", "clients")

        # Verify queue created
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM extract_queue WHERE map_snapshot_id = ? AND entity_type = ?",
            ("snap-001", "clients"),
        )
        assert cursor.fetchone()[0] == 2

        # Verify status is 'pending'
        cursor.execute(
            "SELECT status FROM extract_queue WHERE map_snapshot_id = ? AND entity_type = ?",
            ("snap-001", "clients"),
        )
        statuses = [row[0] for row in cursor.fetchall()]
        assert all(status == "pending" for status in statuses)

        cursor.close()
        conn.close()

    def test_create_extract_queue_insert_or_ignore(self):
        """Test creating queue twice uses INSERT OR IGNORE (no duplicates)."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Create inventory
        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)

        # Create queue twice
        repo.create_extract_queue("snap-001", "clients")
        repo.create_extract_queue("snap-001", "clients")

        # Should only have one record
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM extract_queue WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 1

        cursor.close()
        conn.close()

    def test_get_extract_queue_all(self):
        """Test retrieving all extract queue items for a snapshot and entity type."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Create inventory and queue
        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="c2",
                discovered_at="2025-01-19T10:01:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)
        repo.create_extract_queue("snap-001", "clients")

        # Get all queue items
        results = repo.get_extract_queue("snap-001", "clients")

        assert len(results) == 2
        assert results[0].entity_type == "clients"
        assert results[0].status == "pending"

        conn.close()

    def test_get_extract_queue_filtered_by_status(self):
        """Test retrieving extract queue items filtered by status."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Create inventory and queue
        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="c2",
                discovered_at="2025-01-19T10:01:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)
        repo.create_extract_queue("snap-001", "clients")

        # Update one to 'done'
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE extract_queue SET status = 'done'
               WHERE entity_id = 'c1' AND map_snapshot_id = 'snap-001'"""
        )
        conn.commit()

        # Get only pending items
        results = repo.get_extract_queue("snap-001", "clients", status="pending")

        assert len(results) == 1
        assert results[0].entity_id == "c2"
        assert results[0].status == "pending"

        cursor.close()
        conn.close()

    def test_update_queue_status(self):
        """Test updating extract queue item status."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Create inventory and queue
        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)
        repo.create_extract_queue("snap-001", "clients")

        # Get queue item
        items = repo.get_extract_queue("snap-001", "clients")
        item = items[0]

        # Update to in_progress
        item.status = "in_progress"
        item.attempt_count = 1
        repo.update_queue_status(item)

        # Verify updated
        updated_items = repo.get_extract_queue("snap-001", "clients")
        assert updated_items[0].status == "in_progress"
        assert updated_items[0].attempt_count == 1

        conn.close()

    def test_update_queue_status_with_error(self):
        """Test updating queue status with error information."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Create inventory and queue
        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        repo.save_entity_inventory(inventory)
        repo.create_extract_queue("snap-001", "clients")

        # Get queue item
        items = repo.get_extract_queue("snap-001", "clients")
        item = items[0]

        # Update to failed with error
        item.status = "failed"
        item.last_error = "Connection timeout"
        item.attempt_count = 3
        repo.update_queue_status(item)

        # Verify updated
        updated_items = repo.get_extract_queue("snap-001", "clients")
        assert updated_items[0].status == "failed"
        assert updated_items[0].last_error == "Connection timeout"
        assert updated_items[0].attempt_count == 3

        conn.close()


class TestAttachmentQueueRepository:
    """Test suite for AttachmentQueue repository methods."""

    def test_create_attachment_queue(self):
        """Test creating attachment download queue."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        attachments = [
            {
                "attachment_id": "att-1",
                "parent_type": "clients",
                "parent_id": "c1",
            },
            {
                "attachment_id": "att-2",
                "parent_type": "invoices",
                "parent_id": "i1",
            },
        ]

        repo.create_attachment_queue("snap-001", attachments)

        # Verify queue created
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM attachment_queue WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 2

        # Verify status is 'pending'
        cursor.execute("SELECT status FROM attachment_queue WHERE map_snapshot_id = ?", ("snap-001",))
        statuses = [row[0] for row in cursor.fetchall()]
        assert all(status == "pending" for status in statuses)

        cursor.close()
        conn.close()

    def test_create_attachment_queue_empty_list(self):
        """Test creating attachment queue with empty list returns without error."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Should not raise error
        repo.create_attachment_queue("snap-001", [])

        conn.close()

    def test_create_attachment_queue_insert_or_ignore(self):
        """Test creating attachment queue twice uses INSERT OR IGNORE."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        attachments = [
            {
                "attachment_id": "att-1",
                "parent_type": "clients",
                "parent_id": "c1",
            },
        ]

        # Create queue twice
        repo.create_attachment_queue("snap-001", attachments)
        repo.create_attachment_queue("snap-001", attachments)

        # Should only have one record
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM attachment_queue WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 1

        cursor.close()
        conn.close()

    def test_get_attachment_queue_all(self):
        """Test retrieving all attachment queue items for a snapshot."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        attachments = [
            {
                "attachment_id": "att-1",
                "parent_type": "clients",
                "parent_id": "c1",
            },
            {
                "attachment_id": "att-2",
                "parent_type": "invoices",
                "parent_id": "i1",
            },
        ]

        repo.create_attachment_queue("snap-001", attachments)

        # Get all queue items
        results = repo.get_attachment_queue("snap-001")

        assert len(results) == 2
        assert results[0].attachment_id == "att-1"
        assert results[0].status == "pending"

        conn.close()

    def test_get_attachment_queue_filtered_by_status(self):
        """Test retrieving attachment queue items filtered by status."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        attachments = [
            {
                "attachment_id": "att-1",
                "parent_type": "clients",
                "parent_id": "c1",
            },
            {
                "attachment_id": "att-2",
                "parent_type": "invoices",
                "parent_id": "i1",
            },
        ]

        repo.create_attachment_queue("snap-001", attachments)

        # Update one to 'done'
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE attachment_queue SET status = 'done'
               WHERE attachment_id = 'att-1' AND map_snapshot_id = 'snap-001'"""
        )
        conn.commit()

        # Get only pending items
        results = repo.get_attachment_queue("snap-001", status="pending")

        assert len(results) == 1
        assert results[0].attachment_id == "att-2"
        assert results[0].status == "pending"

        cursor.close()
        conn.close()

    def test_update_attachment_queue_status(self):
        """Test updating attachment queue item status."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        attachments = [
            {
                "attachment_id": "att-1",
                "parent_type": "clients",
                "parent_id": "c1",
            },
        ]

        repo.create_attachment_queue("snap-001", attachments)

        # Get queue item
        items = repo.get_attachment_queue("snap-001")
        item = items[0]

        # Update to in_progress
        item.status = "in_progress"
        item.attempt_count = 1
        repo.update_attachment_queue_status(item)

        # Verify updated
        updated_items = repo.get_attachment_queue("snap-001")
        assert updated_items[0].status == "in_progress"
        assert updated_items[0].attempt_count == 1

        conn.close()

    def test_update_attachment_queue_status_with_error(self):
        """Test updating attachment queue status with error information."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        attachments = [
            {
                "attachment_id": "att-1",
                "parent_type": "clients",
                "parent_id": "c1",
            },
        ]

        repo.create_attachment_queue("snap-001", attachments)

        # Get queue item
        items = repo.get_attachment_queue("snap-001")
        item = items[0]

        # Update to failed with error
        item.status = "failed"
        item.last_error = "File not found: 404"
        item.attempt_count = 2
        repo.update_attachment_queue_status(item)

        # Verify updated
        updated_items = repo.get_attachment_queue("snap-001")
        assert updated_items[0].status == "failed"
        assert updated_items[0].last_error == "File not found: 404"
        assert updated_items[0].attempt_count == 2

        conn.close()


class TestMultiPassErrorHandling:
    """Test suite for error handling in multi-pass repository methods."""

    def test_save_map_snapshot_raises_repository_error_on_sqlite_error(self):
        """Test save_map_snapshot raises RepositoryError on database error."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Close connection to force error
        conn.close()

        snapshot = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
        )

        with pytest.raises(RepositoryError) as exc_info:
            repo.save_map_snapshot(snapshot)

        assert "Failed to save map snapshot" in str(exc_info.value)

    def test_get_map_snapshot_raises_repository_error_on_sqlite_error(self):
        """Test get_map_snapshot raises RepositoryError on database error."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Close connection to force error
        conn.close()

        with pytest.raises(RepositoryError) as exc_info:
            repo.get_map_snapshot("snap-001")

        assert "Failed to get map snapshot" in str(exc_info.value)

    def test_save_entity_inventory_raises_repository_error_on_sqlite_error(self):
        """Test save_entity_inventory raises RepositoryError on database error."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Close connection to force error
        conn.close()

        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
        ]

        with pytest.raises(RepositoryError) as exc_info:
            repo.save_entity_inventory(inventory)

        assert "Failed to save entity inventory batch" in str(exc_info.value)

    def test_create_extract_queue_raises_repository_error_on_sqlite_error(self):
        """Test create_extract_queue raises RepositoryError on database error."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Close connection to force error
        conn.close()

        with pytest.raises(RepositoryError) as exc_info:
            repo.create_extract_queue("snap-001", "clients")

        assert "Failed to create extract queue" in str(exc_info.value)


class TestMultiPassIntegrationScenarios:
    """Test suite for complete multi-pass workflow scenarios."""

    def test_complete_map_to_extract_workflow(self):
        """Test complete workflow from map snapshot to extract queue."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Step 1: Create map snapshot
        snapshot = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
            label="test-migration",
            entities_included='["clients", "invoices"]',
        )
        repo.save_map_snapshot(snapshot)

        # Step 2: Save entity inventory from map pass
        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
                estimated_relations_json='{"notes": 5}',
            ),
            EntityInventory(
                entity_type="clients",
                entity_id="c2",
                discovered_at="2025-01-19T10:01:00Z",
                map_snapshot_id="snap-001",
            ),
        ]
        repo.save_entity_inventory(inventory)

        # Step 3: Create extract queue from inventory
        repo.create_extract_queue("snap-001", "clients")

        # Step 4: Process queue (update statuses)
        queue_items = repo.get_extract_queue("snap-001", "clients", status="pending")
        assert len(queue_items) == 2

        # Mark first as in_progress
        queue_items[0].status = "in_progress"
        repo.update_queue_status(queue_items[0])

        # Mark second as done
        queue_items[1].status = "done"
        repo.update_queue_status(queue_items[1])

        # Step 5: Verify final state
        pending = repo.get_extract_queue("snap-001", "clients", status="pending")
        in_progress = repo.get_extract_queue("snap-001", "clients", status="in_progress")
        done = repo.get_extract_queue("snap-001", "clients", status="done")

        assert len(pending) == 0
        assert len(in_progress) == 1
        assert len(done) == 1

        conn.close()

    def test_cascade_delete_on_snapshot_removal(self):
        """Test CASCADE delete removes all related records when snapshot is deleted."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        # Enable foreign keys
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Create complete workflow
        snapshot = MapSnapshot(
            id="snap-001",
            created_at="2025-01-19T10:00:00Z",
            pass1_cutoff="2025-01-19T10:00:00Z",
        )
        repo.save_map_snapshot(snapshot)

        inventory = [
            EntityInventory(
                entity_type="clients",
                entity_id="c1",
                discovered_at="2025-01-19T10:00:00Z",
                map_snapshot_id="snap-001",
            ),
        ]
        repo.save_entity_inventory(inventory)

        repo.create_extract_queue("snap-001", "clients")

        attachments = [
            {
                "attachment_id": "att-1",
                "parent_type": "clients",
                "parent_id": "c1",
            },
        ]
        repo.create_attachment_queue("snap-001", attachments)

        # Verify records exist
        cursor.execute("SELECT COUNT(*) FROM entity_inventory WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT COUNT(*) FROM extract_queue WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT COUNT(*) FROM attachment_queue WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 1

        # Delete snapshot
        cursor.execute("DELETE FROM map_snapshot WHERE id = ?", ("snap-001",))
        conn.commit()

        # Verify all related records deleted via CASCADE
        cursor.execute("SELECT COUNT(*) FROM entity_inventory WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 0

        cursor.execute("SELECT COUNT(*) FROM extract_queue WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 0

        cursor.execute("SELECT COUNT(*) FROM attachment_queue WHERE map_snapshot_id = ?", ("snap-001",))
        assert cursor.fetchone()[0] == 0

        cursor.close()
        conn.close()
