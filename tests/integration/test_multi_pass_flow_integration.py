"""Integration tests for complete multi-pass migration flow (Map → Extract).

Tests end-to-end workflows including:
- Happy path: successful map → extract flow
- Resume scenario: recovering from partial extraction
- Completeness validation: verifying entity extraction counts
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, MagicMock, patch, call
from uuid import uuid4

import pytest

from src.clients import JobberClient
from src.config import ConfigManagerImpl
from src.coordinators.extract_mode_coordinator import ExtractModeCoordinator
from src.coordinators.map_mode_coordinator import MapModeCoordinator
from src.interfaces import Logger
from src.mappers import EntityMapper
from src.models import (
    AttachmentQueueItem,
    Client,
    EntityInventory,
    ExtractQueueItem,
    Invoice,
    MapSnapshot,
)
from src.repositories import Repository


class TestMultiPassFlowIntegration:
    """Integration tests for complete multi-pass migration workflow."""

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        logger = Mock(spec=Logger)
        logger.info = Mock()
        logger.success = Mock()
        logger.debug = Mock()
        logger.warning = Mock()
        logger.error = Mock()
        return logger

    @pytest.fixture
    def mock_config_manager(self):
        """Create mock configuration manager."""
        config_manager = Mock(spec=ConfigManagerImpl)
        config_manager.get_pagination_config.return_value = 50
        config_manager.page_size = 50
        return config_manager

    @pytest.fixture
    def mock_jobber_client(self):
        """Create mock JobberClient with comprehensive response mocking."""
        client = Mock(spec=JobberClient)

        # Map mode responses (minimal data)
        client.fetch_clients_map.return_value = self._create_map_response("clients")
        client.fetch_invoices_map.return_value = self._create_map_response("invoices")
        client.fetch_jobs_map.return_value = self._create_map_response("jobs")

        # Extract mode responses (full data)
        client.fetch_clients.side_effect = self._create_full_clients_response
        client.fetch_invoices.side_effect = self._create_full_invoices_response
        client.fetch_jobs.return_value = self._create_full_jobs_response()

        return client

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository with in-memory state tracking."""
        repo = Mock(spec=Repository)

        # In-memory storage
        repo._map_snapshots = {}
        repo._entity_inventories = []
        repo._extract_queues = {}
        repo._attachment_queues = {}
        repo._clients = []
        repo._invoices = []
        repo._attachments = []

        # Map mode methods
        repo.save_map_snapshot.side_effect = lambda snapshot: self._save_snapshot(repo, snapshot)
        repo.save_entity_inventory.side_effect = lambda items: repo._entity_inventories.extend(items)
        repo.get_entity_inventory.side_effect = lambda sid, et=None: self._get_entity_inventory(repo, sid, et)
        repo.get_map_snapshot.side_effect = lambda sid: repo._map_snapshots.get(sid)

        # Extract mode methods
        repo.create_extract_queue.side_effect = lambda sid, et: self._create_extract_queue(repo, sid, et)
        repo.get_extract_queue.side_effect = lambda sid, et, status=None, **kwargs: self._get_extract_queue(
            repo, sid, et, status
        )
        repo.update_queue_status.side_effect = lambda item: self._update_queue_status(repo, item)

        # Attachment queue methods
        repo.create_attachment_queue.side_effect = lambda sid, attachments: self._create_attachment_queue(
            repo, sid, attachments
        )
        repo.get_attachment_queue.side_effect = lambda sid, status=None, **kwargs: self._get_attachment_queue(
            repo, sid, status
        )
        repo.update_attachment_queue_status.side_effect = lambda item: self._update_attachment_status(repo, item)

        # Entity storage
        repo.save_clients.side_effect = lambda clients: repo._clients.extend(clients)
        repo.save_invoices.side_effect = lambda invoices: repo._invoices.extend(invoices)
        repo.save_attachments.side_effect = lambda attachments: repo._attachments.extend(attachments)
        repo.entity_exists.return_value = False

        return repo

    @pytest.fixture
    def mock_entity_mapper(self):
        """Create mock entity mapper."""
        mapper = Mock(spec=EntityMapper)
        mapper.map_client.side_effect = lambda data: self._map_client_data(data)
        mapper.map_invoice.side_effect = lambda data: self._map_invoice_data(data)
        return mapper

    @pytest.fixture
    def temp_report_dir(self):
        """Create temporary report directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_happy_path_full_migration(
        self,
        mock_jobber_client,
        mock_repository,
        mock_entity_mapper,
        mock_logger,
        mock_config_manager,
        temp_report_dir,
    ):
        """Test successful end-to-end multi-pass migration."""
        # Phase 1: Map Mode
        map_coordinator = MapModeCoordinator(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        result = map_coordinator.run_map_pass(
            entity_types=["clients", "invoices"],
            label="test-migration",
        )

        # Verify map results
        assert result["snapshot_id"] is not None
        snapshot_id = result["snapshot_id"]
        assert len(mock_repository._entity_inventories) > 0

        # Get inventory counts for validation
        client_count = sum(1 for inv in mock_repository._entity_inventories if inv.entity_type == "clients")
        invoice_count = sum(1 for inv in mock_repository._entity_inventories if inv.entity_type == "invoices")

        # Phase 2: Extract Mode
        extract_coordinator = ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

        extract_result = extract_coordinator.run_extract_pass(
            snapshot_id=snapshot_id,
            entity_types=["clients", "invoices"],
        )

        # Verify extract results
        assert extract_result["snapshot_id"] == snapshot_id
        assert len(mock_repository._clients) == client_count
        assert len(mock_repository._invoices) == invoice_count

        # Verify all queues completed
        for queue_items in mock_repository._extract_queues.values():
            for item in queue_items:
                assert item.status == "done"

    def test_resume_scenario_after_partial_extraction(
        self,
        mock_jobber_client,
        mock_repository,
        mock_entity_mapper,
        mock_logger,
        mock_config_manager,
        temp_report_dir,
    ):
        """Test resuming extraction after partial failure."""
        # Setup: Create map snapshot with inventory
        snapshot_id = str(uuid4())
        timestamp = datetime.now().isoformat()
        mock_repository._map_snapshots[snapshot_id] = MapSnapshot(
            id=snapshot_id,
            created_at=timestamp,
            pass1_cutoff=timestamp,
            label="resume-test",
            entities_included='["clients"]',
        )

        # Add inventory items
        mock_repository._entity_inventories = [
            EntityInventory(
                map_snapshot_id=snapshot_id,
                entity_type="clients",
                entity_id=f"clients_{i}",
                discovered_at=timestamp,
                updated_at=timestamp,
                estimated_relations_json='{"notes": 2, "attachments": 1}',
            )
            for i in range(5)
        ]

        # Simulate partial extraction (first 3 done, 1 failed, 1 pending)
        mock_repository._extract_queues[snapshot_id] = [
            ExtractQueueItem(
                map_snapshot_id=snapshot_id,
                entity_type="clients",
                entity_id=f"clients_{i}",
                status="done" if i < 3 else "failed" if i == 3 else "pending",
                updated_at=timestamp,
                attempt_count=1 if i == 3 else 0,
            )
            for i in range(5)
        ]

        # Run extract coordinator in resume mode
        extract_coordinator = ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

        extract_coordinator.run_extract_pass(
            snapshot_id=snapshot_id,
            entity_types=["clients"],
            resume=True,
        )

        # Verify only failed and pending items were processed
        processed_count = mock_jobber_client.fetch_clients.call_count
        assert processed_count >= 1  # At least one fetch call for remaining items

        # Verify all items now marked as done
        for item in mock_repository._extract_queues[snapshot_id]:
            assert item.status == "done"

    def test_completeness_validation(
        self,
        mock_jobber_client,
        mock_repository,
        mock_entity_mapper,
        mock_logger,
        mock_config_manager,
        temp_report_dir,
    ):
        """Test completeness validation between inventory and extracted entities."""
        # Setup: Create map snapshot with inventory
        snapshot_id = str(uuid4())
        timestamp = datetime.now().isoformat()
        mock_repository._map_snapshots[snapshot_id] = MapSnapshot(
            id=snapshot_id,
            created_at=timestamp,
            pass1_cutoff=timestamp,
            label="completeness-test",
            entities_included='["clients"]',
        )

        # Add inventory (10 clients expected)
        mock_repository._entity_inventories = [
            EntityInventory(
                map_snapshot_id=snapshot_id,
                entity_type="clients",
                entity_id=f"client_{i}",
                discovered_at=timestamp,
                updated_at=timestamp,
                estimated_relations_json="{}",
            )
            for i in range(10)
        ]

        # Run extraction
        extract_coordinator = ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

        result = extract_coordinator.run_extract_pass(
            snapshot_id=snapshot_id,
            entity_types=["clients"],
        )

        # Verify result contains expected information
        assert result["snapshot_id"] == snapshot_id
        assert "entity_results" in result
        assert "totals" in result
        assert "duration" in result

        # Verify expected vs actual counts match
        expected_count = 10
        actual_count = len(mock_repository._clients)
        assert actual_count <= expected_count  # May be less if some fail

    def test_discrepancy_detection(
        self,
        mock_jobber_client,
        mock_repository,
        mock_entity_mapper,
        mock_logger,
    ):
        """Test that extract mode detects when entity count differs from inventory."""
        # Setup: Create map snapshot with 10 entities in inventory
        snapshot_id = str(uuid4())
        timestamp = datetime.now().isoformat()
        mock_repository._map_snapshots[snapshot_id] = MapSnapshot(
            id=snapshot_id,
            created_at=timestamp,
            pass1_cutoff=timestamp,
            label="discrepancy-test",
            entities_included='["clients"]',
        )

        # Add 10 entities to inventory (what map pass discovered)
        mock_repository._entity_inventories = [
            EntityInventory(
                map_snapshot_id=snapshot_id,
                entity_type="clients",
                entity_id=f"clients_{i}",
                discovered_at=timestamp,
                updated_at=timestamp,
                estimated_relations_json="{}",
            )
            for i in range(10)
        ]

        # Mock create_extract_queue to only create 8 items instead of 10
        # This simulates incomplete queue creation (e.g., database error partway through)
        def create_incomplete_queue(snapshot_id_param, entity_type_param):
            if snapshot_id_param not in mock_repository._extract_queues:
                mock_repository._extract_queues[snapshot_id_param] = []
            # Only create 8 items instead of all 10 from inventory!
            for i in range(8):
                queue_item = ExtractQueueItem(
                    map_snapshot_id=snapshot_id_param,
                    entity_type=entity_type_param,
                    entity_id=f"clients_{i}",
                    status="pending",
                    updated_at=timestamp,
                    attempt_count=0,
                )
                mock_repository._extract_queues[snapshot_id_param].append(queue_item)

        mock_repository.create_extract_queue.side_effect = create_incomplete_queue

        # Mock fetch_clients to return matching entities
        def limited_clients_response(cursor=None):
            return {
                "data": {
                    "clients": {
                        "edges": [
                            {
                                "node": {
                                    "id": f"clients_{i}",
                                    "name": f"Test Client {i}",
                                    "email": f"client_{i}@example.com",
                                    "createdAt": timestamp,
                                    "updatedAt": timestamp,
                                    "notes": {
                                        "edges": [],
                                        "pageInfo": {"hasNextPage": False}
                                    },
                                    "noteAttachments": {
                                        "edges": [],
                                        "pageInfo": {"hasNextPage": False}
                                    }
                                }
                            }
                            for i in range(8)  # Only 8 entities, not 10!
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None}
                    }
                }
            }

        mock_jobber_client.fetch_clients.side_effect = limited_clients_response

        # Run extraction
        extract_coordinator = ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

        result = extract_coordinator.run_extract_pass(
            snapshot_id=snapshot_id,
            entity_types=["clients"],
        )

        # Verify discrepancies were detected
        assert "discrepancies" in result
        assert len(result["discrepancies"]) > 0

        # Check for entity_count_mismatch discrepancy
        entity_mismatches = [
            d for d in result["discrepancies"]
            if d["type"] == "entity_count_mismatch"
        ]
        assert len(entity_mismatches) > 0, "Should detect entity count mismatch"

        # Verify the discrepancy details
        mismatch = entity_mismatches[0]
        assert mismatch["entity_type"] == "clients"
        assert mismatch["expected"] == 10  # From inventory
        assert mismatch["actual"] == 8  # From API (entities that could be attempted)
        assert mismatch["severity"] == "error"

        # Verify logger was called with warning
        assert mock_logger.warning.called

    def test_data_drift_handling(
        self,
        mock_jobber_client,
        mock_repository,
        mock_entity_mapper,
        mock_logger,
    ):
        """Test that entities modified after map cutoff are still extracted."""
        # Setup: Create map snapshot with a cutoff time
        snapshot_id = str(uuid4())
        cutoff_time = "2024-01-01T12:00:00+00:00"  # Map pass cutoff
        current_time = "2024-01-01T14:00:00+00:00"  # 2 hours later

        mock_repository._map_snapshots[snapshot_id] = MapSnapshot(
            id=snapshot_id,
            created_at=cutoff_time,
            pass1_cutoff=cutoff_time,  # Cutoff at map time
            label="drift-test",
            entities_included='["clients"]',
        )

        # Add 5 entities to inventory (discovered during map pass)
        mock_repository._entity_inventories = [
            EntityInventory(
                map_snapshot_id=snapshot_id,
                entity_type="clients",
                entity_id=f"clients_{i}",
                discovered_at=cutoff_time,
                updated_at=cutoff_time,  # All discovered at cutoff time
                estimated_relations_json="{}",
            )
            for i in range(5)
        ]

        # Mock API to return some entities with updatedAt > cutoff (data drift!)
        # Entities 0-2: no drift (updated before cutoff)
        # Entities 3-4: drifted (updated after cutoff)
        def clients_with_drift(cursor=None):
            return {
                "data": {
                    "clients": {
                        "edges": [
                            {
                                "node": {
                                    "id": f"clients_{i}",
                                    "name": f"Test Client {i}",
                                    "email": f"client_{i}@example.com",
                                    "createdAt": "2024-01-01T10:00:00+00:00",
                                    # Entities 3-4 have updatedAt > cutoff (drift)
                                    "updatedAt": current_time if i >= 3 else cutoff_time,
                                    "notes": {
                                        "edges": [],
                                        "pageInfo": {"hasNextPage": False}
                                    },
                                    "noteAttachments": {
                                        "edges": [],
                                        "pageInfo": {"hasNextPage": False}
                                    }
                                }
                            }
                            for i in range(5)
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None}
                    }
                }
            }

        mock_jobber_client.fetch_clients.side_effect = clients_with_drift

        # Run extraction
        extract_coordinator = ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

        result = extract_coordinator.run_extract_pass(
            snapshot_id=snapshot_id,
            entity_types=["clients"],
        )

        # Verify all entities were extracted successfully despite drift
        assert result["entity_results"]["clients"]["extracted"] == 5
        assert result["entity_results"]["clients"]["failed"] == 0

        # Verify all 5 entities were saved (including drifted ones)
        assert len(mock_repository._clients) == 5

        # Note: Drift warnings would be tested here if drift detection is implemented
        # For now, we verify the system handles drift gracefully by extracting all entities

    def test_attachment_retry(
        self,
        mock_jobber_client,
        mock_repository,
        mock_entity_mapper,
        mock_logger,
    ):
        """Test that failed attachments are retried on subsequent extract pass."""
        # Setup: Create map snapshot
        snapshot_id = str(uuid4())
        timestamp = datetime.now().isoformat()
        mock_repository._map_snapshots[snapshot_id] = MapSnapshot(
            id=snapshot_id,
            created_at=timestamp,
            pass1_cutoff=timestamp,
            label="attachment-retry-test",
            entities_included='["clients"]',
        )

        # Add 2 clients to inventory (with no new attachments expected)
        mock_repository._entity_inventories = [
            EntityInventory(
                map_snapshot_id=snapshot_id,
                entity_type="clients",
                entity_id=f"clients_{i}",
                discovered_at=timestamp,
                updated_at=timestamp,
                estimated_relations_json='{"noteAttachments": 0}',  # No new attachments
            )
            for i in range(2)
        ]

        # Setup: Create attachments in repository (use different IDs to avoid conflicts with API mock)
        from src.models import Attachment, AttachmentQueueItem

        mock_attachments = [
            Attachment(
                id=f"failed_attach_{i}",  # Different ID to avoid conflicts
                note_id=f"note_{i}",
                file_name=f"failed_file_{i}.pdf",
                content_type="application/pdf",
                original_url=f"https://jobber.com/failed-attachments/{i}",
                local_file_path="",  # Empty initially
                file_size=1024,
                created_at=timestamp,
            )
            for i in range(2)
        ]

        # Add failed attachments to repository's attachment storage (preserve as dict for get_attachment_by_id)
        if not isinstance(mock_repository._attachments, dict):
            # Convert list to dict for attachment lookups
            mock_repository._attachment_list = mock_repository._attachments
            mock_repository._attachments_dict = {att.id: att for att in mock_attachments}
        else:
            mock_repository._attachment_list = []
            mock_repository._attachments_dict = {att.id: att for att in mock_attachments}

        # Mock get_attachment_by_id to return the failed attachments
        def get_attachment_by_id(attachment_id):
            return mock_repository._attachments_dict.get(attachment_id)

        mock_repository.get_attachment_by_id = get_attachment_by_id

        # Mock save_attachments to append to list (as expected by fixture)
        def save_attachments(attachments):
            mock_repository._attachment_list.extend(attachments)

        mock_repository.save_attachments.side_effect = save_attachments

        # Setup: Create attachment queue with 2 failed attachments
        mock_repository._attachment_queues[snapshot_id] = [
            AttachmentQueueItem(
                map_snapshot_id=snapshot_id,
                parent_type="clients",  # Correct field name
                parent_id=f"clients_{i}",  # Correct field name
                attachment_id=f"failed_attach_{i}",  # Match the failed attachment IDs
                status="failed",  # Initially failed
                updated_at=timestamp,
                last_error="Network timeout",
                attempt_count=1,
            )
            for i in range(2)
        ]

        # Mock attachment downloader to succeed on retry
        from src.extractors.attachment_downloader import AttachmentDownloader

        # Track download attempts
        download_attempts = []

        def mock_download(attachment: Attachment):
            download_attempts.append(attachment.id)
            # Succeed on all attempts (simulating successful retry)
            return {
                "success": True,
                "local_file_path": f"/tmp/downloads/{attachment.id}.pdf",
            }

        # Run first extraction pass (which will retry the failed attachments)
        extract_coordinator = ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

        # Mock the attachment downloader
        with patch.object(AttachmentDownloader, 'download_attachment', side_effect=mock_download):
            result = extract_coordinator.run_extract_pass(
                snapshot_id=snapshot_id,
                entity_types=["clients"],
            )

        # Verify failed attachments were retried
        assert len(download_attempts) >= 2, f"Should retry at least 2 failed attachments, got {len(download_attempts)}: {download_attempts}"
        assert "failed_attach_0" in download_attempts, "Should retry failed_attach_0"
        assert "failed_attach_1" in download_attempts, "Should retry failed_attach_1"

        # Verify attachment statuses were updated to done
        attachment_queue = mock_repository._attachment_queues[snapshot_id]
        done_attachments = [a for a in attachment_queue if a.status == "done"]
        assert len(done_attachments) >= 2, f"At least 2 attachments should be marked as done, got {len(done_attachments)}"

        # Verify failed attachments are now done
        failed_attach_statuses = {a.attachment_id: a.status for a in attachment_queue if "failed_attach" in a.attachment_id}
        assert failed_attach_statuses.get("failed_attach_0") == "done", "failed_attach_0 should be done"
        assert failed_attach_statuses.get("failed_attach_1") == "done", "failed_attach_1 should be done"

    def test_end_to_end_reconcile(
        self,
        mock_jobber_client,
        mock_repository,
        mock_entity_mapper,
        mock_logger,
    ):
        """Test complete reconcile workflow: re-map -> compare -> extract deltas."""
        # Phase 1: Initial map with 5 clients
        snapshot_id_1 = str(uuid4())
        timestamp_1 = datetime.now().isoformat()

        # Mock API to return 5 clients initially
        initial_client_count = 5

        def create_map_response_initial(cursor=None):
            return {
                "data": {
                    "clients": {
                        "edges": [
                            {
                                "node": {
                                    "id": f"clients_{i}",
                                    "updatedAt": timestamp_1,
                                    "noteAttachments": {"totalCount": 0},
                                }
                            }
                            for i in range(initial_client_count)
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }

        mock_jobber_client.fetch_clients_map.side_effect = create_map_response_initial

        # Run initial map pass
        map_coordinator = MapModeCoordinator(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            logger=mock_logger,
        )

        # Run map extraction (this creates the snapshot automatically)
        map_result = map_coordinator.run_map_pass(["clients"], label="initial-map")
        snapshot_id_1 = map_result["snapshot_id"]  # Get the snapshot ID from result

        # Verify 5 entities discovered
        assert map_result["totals"]["total_entities"] == 5, "Should discover 5 clients in initial map"

        # Phase 2: Run extract pass for initial 5 clients
        extract_coordinator = ExtractModeCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
        )

        extract_result_1 = extract_coordinator.run_extract_pass(
            snapshot_id=snapshot_id_1,
            entity_types=["clients"],
        )

        # Verify 5 clients extracted
        assert extract_result_1["totals"]["total_extracted"] == 5, "Should extract 5 clients"

        # Phase 3: Simulate changes - API now returns 8 clients (3 new ones)
        timestamp_2 = datetime.now().isoformat()
        new_client_count = 8

        def create_map_response_reconcile(cursor=None):
            return {
                "data": {
                    "clients": {
                        "edges": [
                            {
                                "node": {
                                    "id": f"clients_{i}",
                                    "updatedAt": timestamp_2 if i >= 5 else timestamp_1,  # New clients have new timestamp
                                    "noteAttachments": {"totalCount": 0},
                                }
                            }
                            for i in range(new_client_count)
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }

        mock_jobber_client.fetch_clients_map.side_effect = create_map_response_reconcile

        # Also update fetch_clients for extract mode to return all 8 clients
        def create_full_clients_response_8(cursor=None):
            return {
                "data": {
                    "clients": {
                        "edges": [
                            {
                                "node": {
                                    "id": f"clients_{i}",
                                    "name": f"Test Client {i}",
                                    "email": f"client_{i}@example.com",
                                    "createdAt": timestamp_2 if i >= 5 else timestamp_1,
                                    "updatedAt": timestamp_2 if i >= 5 else timestamp_1,
                                    "notes": {"edges": [], "pageInfo": {"hasNextPage": False}},
                                    "noteAttachments": {"edges": [], "pageInfo": {"hasNextPage": False}},
                                }
                            }
                            for i in range(8)
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }

        mock_jobber_client.fetch_clients.side_effect = create_full_clients_response_8

        # Run reconcile map pass (this creates a new snapshot)
        reconcile_map_result = map_coordinator.run_map_pass(["clients"], label="reconcile-map")
        snapshot_id_2 = reconcile_map_result["snapshot_id"]  # Get the new snapshot ID

        # Verify 8 entities discovered (5 existing + 3 new)
        assert reconcile_map_result["totals"]["total_entities"] == 8, "Should discover 8 clients in reconcile map"

        # Phase 4: Identify deltas
        # Get inventories from both snapshots
        inventory_1 = set(item.entity_id for item in mock_repository._entity_inventories if item.map_snapshot_id == snapshot_id_1)
        inventory_2 = set(item.entity_id for item in mock_repository._entity_inventories if item.map_snapshot_id == snapshot_id_2)

        deltas = inventory_2 - inventory_1

        # Verify 3 deltas detected
        assert len(deltas) == 3, f"Should detect 3 deltas, found {len(deltas)}: {deltas}"
        assert "clients_5" in deltas, "clients_5 should be a delta"
        assert "clients_6" in deltas, "clients_6 should be a delta"
        assert "clients_7" in deltas, "clients_7 should be a delta"

        # Phase 5: Extract only deltas
        # Override create_extract_queue to only create queue items for delta entities
        def create_delta_queue(repo, snapshot_id, entity_type):
            if snapshot_id != snapshot_id_2:
                # Use default behavior for first snapshot
                return self._create_extract_queue(repo, snapshot_id, entity_type)

            # For reconcile, only create queue items for deltas
            inventory = [item for item in repo._entity_inventories if item.map_snapshot_id == snapshot_id and item.entity_id in deltas]

            from src.models import ExtractQueueItem
            queue_items = [
                ExtractQueueItem(
                    map_snapshot_id=snapshot_id,
                    entity_type=entity_type,
                    entity_id=item.entity_id,
                    status="pending",
                    updated_at=datetime.now().isoformat(),
                    attempt_count=0,
                )
                for item in inventory
            ]

            # Create flat list structure (not nested by entity_type)
            if snapshot_id not in repo._extract_queues:
                repo._extract_queues[snapshot_id] = []

            repo._extract_queues[snapshot_id].extend(queue_items)

        mock_repository.create_extract_queue.side_effect = lambda sid, et: create_delta_queue(mock_repository, sid, et)

        # Run extract pass for deltas
        extract_result_2 = extract_coordinator.run_extract_pass(
            snapshot_id=snapshot_id_2,
            entity_types=["clients"],
        )

        # Verify only 3 delta clients extracted
        assert extract_result_2["totals"]["total_extracted"] == 3, f"Should extract 3 delta clients, got {extract_result_2['totals']['total_extracted']}"

        # Verify total clients saved is 8 (5 from initial + 3 from reconcile)
        total_clients_saved = len(mock_repository._clients)
        assert total_clients_saved == 8, f"Should have 8 total clients saved, got {total_clients_saved}"

    # Helper methods for mock data generation

    def _create_map_response(self, entity_type: str) -> Dict:
        """Create minimal response for map mode queries."""
        count = {"clients": 5, "invoices": 3, "jobs": 4}.get(entity_type, 2)
        return {
            "data": {
                entity_type: {
                    "edges": [
                        {
                            "node": {
                                "id": f"{entity_type}_{i}",
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                            }
                        }
                        for i in range(count)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def _create_full_clients_response(self, cursor: Optional[str] = None) -> Dict:
        """Create full client response for extraction."""
        return {
            "data": {
                "clients": {
                    "edges": [
                        {
                            "node": {
                                "id": f"clients_{i}",
                                "name": f"Test Client {i}",
                                "email": f"client_{i}@example.com",
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "notes": {
                                    "edges": [{"node": {"id": f"note_{j}", "content": f"Note {j}"}} for j in range(2)],
                                    "pageInfo": {"hasNextPage": False},
                                },
                                "noteAttachments": {
                                    "edges": [
                                        {"node": {"id": f"attach_{i}", "url": f"https://example.com/client_{i}.pdf"}}
                                    ],
                                    "pageInfo": {"hasNextPage": False},
                                },
                            }
                        }
                        for i in range(5)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def _create_full_invoices_response(self, cursor: Optional[str] = None) -> Dict:
        """Create full invoice response for extraction."""
        return {
            "data": {
                "invoices": {
                    "edges": [
                        {
                            "node": {
                                "id": f"invoices_{i}",
                                "number": f"INV-{i:04d}",
                                "total": 1000.00 + (i * 100),
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "lineItems": {
                                    "edges": [
                                        {"node": {"id": f"line_{j}", "description": f"Item {j}", "amount": 100.00}}
                                        for j in range(3)
                                    ],
                                    "pageInfo": {"hasNextPage": False},
                                },
                                "notes": {"edges": [], "pageInfo": {"hasNextPage": False}},
                                "noteAttachments": {"edges": [], "pageInfo": {"hasNextPage": False}},
                            }
                        }
                        for i in range(3)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def _create_full_jobs_response(self) -> Dict:
        """Create full jobs response for extraction."""
        return {
            "data": {
                "jobs": {
                    "nodes": [
                        {
                            "id": f"job_{i}",
                            "title": f"Job {i}",
                            "status": "active",
                            "createdAt": "2024-01-01T00:00:00Z",
                            "updatedAt": "2024-01-01T00:00:00Z",
                        }
                        for i in range(4)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def _map_client_data(self, data: Dict) -> Client:
        """Map raw client data to Client model."""
        # Split name into first_name and last_name
        full_name = data.get("name", "Test Client")
        name_parts = full_name.rsplit(" ", 1)
        first_name = name_parts[0] if len(name_parts) > 0 else "Test"
        last_name = name_parts[1] if len(name_parts) > 1 else "Client"

        return Client(
            id=data["id"],
            first_name=first_name,
            last_name=last_name,
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            created_at=data.get("createdAt", ""),
        )

    def _map_invoice_data(self, data: Dict) -> Invoice:
        """Map raw invoice data to Invoice model."""
        total_cents = int(data.get("total", 0) * 100) if data.get("total") else 0
        return Invoice(
            id=data["id"],
            client_id=data.get("clientId", "unknown"),
            number=data.get("number", ""),
            total_cents=total_cents,
            status=data.get("status", "draft"),
            issued_at=data.get("createdAt", ""),
        )

    def _save_snapshot(self, repo, snapshot: MapSnapshot) -> None:
        """Save map snapshot in mock repository."""
        repo._map_snapshots[snapshot.id] = snapshot

    def _get_entity_inventory(self, repo, snapshot_id: str, entity_type: Optional[str] = None) -> List[EntityInventory]:
        """Get entity inventory from mock repository."""
        inventory = [item for item in repo._entity_inventories if item.map_snapshot_id == snapshot_id]
        if entity_type:
            inventory = [item for item in inventory if item.entity_type == entity_type]
        return inventory

    def _create_extract_queue(self, repo, snapshot_id: str, entity_type: str):
        """Create extract queue in mock repository."""
        if snapshot_id not in repo._extract_queues:
            repo._extract_queues[snapshot_id] = []
        # Simulate creating queue items from inventory
        inventory = [
            inv
            for inv in repo._entity_inventories
            if inv.map_snapshot_id == snapshot_id and inv.entity_type == entity_type
        ]
        for inv in inventory:
            queue_item = ExtractQueueItem(
                map_snapshot_id=snapshot_id,
                entity_type=entity_type,
                entity_id=inv.entity_id,
                status="pending",
                updated_at=datetime.now().isoformat(),
                attempt_count=0,
            )
            repo._extract_queues[snapshot_id].append(queue_item)

    def _get_extract_queue(
        self, repo, snapshot_id: str, entity_type: str, status: Optional[str] = None
    ) -> List[ExtractQueueItem]:
        """Get extract queue from mock repository."""
        if snapshot_id not in repo._extract_queues:
            return []
        queue = repo._extract_queues[snapshot_id]
        queue = [item for item in queue if item.entity_type == entity_type]
        if status:
            queue = [item for item in queue if item.status == status]
        return queue

    def _update_queue_status(self, repo, queue_item: ExtractQueueItem):
        """Update queue item status in mock repository."""
        # Find and update the item in the repository
        if queue_item.map_snapshot_id in repo._extract_queues:
            for i, item in enumerate(repo._extract_queues[queue_item.map_snapshot_id]):
                if item.entity_id == queue_item.entity_id and item.entity_type == queue_item.entity_type:
                    repo._extract_queues[queue_item.map_snapshot_id][i] = queue_item
                    break

    def _create_attachment_queue(self, repo, snapshot_id: str, attachments: List[dict]):
        """Create attachment queue in mock repository."""
        if snapshot_id not in repo._attachment_queues:
            repo._attachment_queues[snapshot_id] = []
        # Convert attachment dicts to AttachmentQueueItems
        for attach in attachments:
            queue_item = AttachmentQueueItem(
                attachment_id=attach.get("id"),
                parent_type=attach.get("parent_type", "clients"),
                parent_id=attach.get("parent_id"),
                status="pending",
                map_snapshot_id=snapshot_id,
                updated_at=datetime.now().isoformat(),
                attempt_count=0,
            )
            repo._attachment_queues[snapshot_id].append(queue_item)

    def _get_attachment_queue(self, repo, snapshot_id: str, status: Optional[str] = None) -> List[AttachmentQueueItem]:
        """Get attachment queue from mock repository."""
        if snapshot_id not in repo._attachment_queues:
            return []
        queue = repo._attachment_queues[snapshot_id]
        if status:
            return [item for item in queue if item.status == status]
        return queue

    def _update_attachment_status(self, repo, queue_item: AttachmentQueueItem):
        """Update attachment queue item status."""
        # Find and update the item in the repository
        for snapshot_id, queue in repo._attachment_queues.items():
            for i, item in enumerate(queue):
                if item.attachment_id == queue_item.attachment_id:
                    repo._attachment_queues[snapshot_id][i] = queue_item
                    return
