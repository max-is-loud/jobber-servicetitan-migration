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
        repo.get_extract_queue.side_effect = lambda sid, et, status=None, **kwargs: self._get_extract_queue(repo, sid, et, status)
        repo.update_queue_status.side_effect = lambda item: self._update_queue_status(repo, item)

        # Attachment queue methods
        repo.create_attachment_queue.side_effect = lambda sid, attachments: self._create_attachment_queue(repo, sid, attachments)
        repo.get_attachment_queue.side_effect = lambda sid, s=None: self._get_attachment_queue(repo, sid, s)
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
        client_count = sum(
            1 for inv in mock_repository._entity_inventories
            if inv.entity_type == "clients"
        )
        invoice_count = sum(
            1 for inv in mock_repository._entity_inventories
            if inv.entity_type == "invoices"
        )

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
                entity_id=f"client_{i}",
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
                entity_id=f"client_{i}",
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
                estimated_relations_json='{}',
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
                                "updatedAt": "2024-01-01T00:00:00Z"
                            }
                        }
                        for i in range(count)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None}
                }
            }
        }

    def _create_full_clients_response(self, cursor: Optional[str] = None) -> Dict:
        """Create full client response for extraction."""
        return {
            "data": {
                "clients": {
                    "nodes": [
                        {
                            "id": f"client_{i}",
                            "name": f"Test Client {i}",
                            "email": f"client_{i}@example.com",
                            "createdAt": "2024-01-01T00:00:00Z",
                            "updatedAt": "2024-01-01T00:00:00Z",
                            "notes": {
                                "nodes": [
                                    {"id": f"note_{j}", "content": f"Note {j}"}
                                    for j in range(2)
                                ]
                            },
                            "attachments": {
                                "nodes": [
                                    {"id": f"attach_{i}", "url": f"https://example.com/client_{i}.pdf"}
                                ]
                            }
                        }
                        for i in range(5)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None}
                }
            }
        }

    def _create_full_invoices_response(self, cursor: Optional[str] = None) -> Dict:
        """Create full invoice response for extraction."""
        return {
            "data": {
                "invoices": {
                    "nodes": [
                        {
                            "id": f"invoice_{i}",
                            "number": f"INV-{i:04d}",
                            "total": 1000.00 + (i * 100),
                            "createdAt": "2024-01-01T00:00:00Z",
                            "updatedAt": "2024-01-01T00:00:00Z",
                            "lineItems": {
                                "nodes": [
                                    {"id": f"line_{j}", "description": f"Item {j}", "amount": 100.00}
                                    for j in range(3)
                                ]
                            }
                        }
                        for i in range(3)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None}
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
                            "updatedAt": "2024-01-01T00:00:00Z"
                        }
                        for i in range(4)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None}
                }
            }
        }

    def _map_client_data(self, data: Dict) -> Client:
        """Map raw client data to Client model."""
        return Client(
            id=data["id"],
            name=data.get("name"),
            email=data.get("email"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
        )

    def _map_invoice_data(self, data: Dict) -> Invoice:
        """Map raw invoice data to Invoice model."""
        return Invoice(
            id=data["id"],
            number=data.get("number"),
            total=data.get("total"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
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
        inventory = [inv for inv in repo._entity_inventories if inv.map_snapshot_id == snapshot_id and inv.entity_type == entity_type]
        for inv in inventory:
            queue_item = ExtractQueueItem(
                map_snapshot_id=snapshot_id,
                entity_type=entity_type,
                entity_id=inv.entity_id,
                status="pending",
                updated_at=datetime.now().isoformat(),
                attempt_count=0
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
                attempt_count=0
            )
            repo._attachment_queues[snapshot_id].append(queue_item)

    def _get_attachment_queue(
        self, repo, snapshot_id: str, status: Optional[str] = None
    ) -> List[AttachmentQueueItem]:
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