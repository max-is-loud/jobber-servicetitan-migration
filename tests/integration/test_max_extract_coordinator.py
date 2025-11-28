"""Integration tests for MaxExtractCoordinator.

Tests Phase 7 orchestration of multi-entity extraction with:
1. Full extraction pipeline (all entities in dependency order)
2. Selective entity extraction
3. Resume from checkpoint functionality
4. Entity dependency ordering
5. Error handling and recovery
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

import pytest

from src.coordinators.max_extract_coordinator import MaxExtractCoordinator
from src.clients import JobberClient
from src.mappers import EntityMapper
from src.repositories import Repository
from src.interfaces import Logger
from src.models import (
    Client,
    User,
    Property,
    Job,
    Quote,
    Request,
    Invoice,
    Visit,
    Expense,
    TimeSheetEntry,
    ProductService,
    TaxRate,
    Note,
)


@pytest.fixture
def db_connection():
    """Create SQLite connection for testing."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def mock_jobber_client():
    """Create mock JobberClient with responses for all entity types."""
    client = MagicMock(spec=JobberClient)

    # Mock users response
    client.fetch_users.return_value = {
        "data": {
            "users": {
                "edges": [
                    {
                        "cursor": "user_cursor_1",
                        "node": {
                            "id": "user_1",
                            "firstName": "Alice",
                            "lastName": "Admin",
                            "email": "alice@company.com",
                            "role": "admin",
                            "createdAt": "2023-01-01T00:00:00Z",
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "user_cursor_1"},
            }
        },
        "extensions": {"cost": {"actualCost": 10}},
    }

    # Mock clients response
    client.fetch_clients.return_value = {
        "data": {
            "clients": {
                "edges": [
                    {
                        "cursor": "client_cursor_1",
                        "node": {
                            "id": "client_1",
                            "firstName": "John",
                            "lastName": "Doe",
                            "email": "john@example.com",
                            "createdAt": "2023-01-15T00:00:00Z",
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "client_cursor_1"},
            }
        },
        "extensions": {"cost": {"actualCost": 10}},
    }

    # Mock properties response
    client.fetch_properties.return_value = {
        "data": {
            "properties": {
                "edges": [
                    {
                        "cursor": "property_cursor_1",
                        "node": {
                            "id": "property_1",
                            "client": {"id": "client_1"},
                            "name": "Main Office",
                            "address": {"line1": "123 Main St"},
                            "createdAt": "2023-01-20T00:00:00Z",
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "property_cursor_1"},
            }
        },
        "extensions": {"cost": {"actualCost": 10}},
    }

    # Mock quotes response
    client.fetch_quotes.return_value = {
        "data": {
            "quotes": {
                "edges": [
                    {
                        "cursor": "quote_cursor_1",
                        "node": {
                            "id": "quote_1",
                            "client": {"id": "client_1"},
                            "quoteNumber": "Q-001",
                            "title": "Office Cleaning",
                            "createdAt": "2023-02-01T00:00:00Z",
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "quote_cursor_1"},
            }
        },
        "extensions": {"cost": {"actualCost": 10}},
    }

    # Mock jobs response
    client.fetch_jobs.return_value = {
        "data": {
            "jobs": {
                "edges": [
                    {
                        "cursor": "job_cursor_1",
                        "node": {
                            "id": "job_1",
                            "client": {"id": "client_1"},
                            "property": {"id": "property_1"},
                            "jobNumber": "J-001",
                            "title": "Monthly Cleaning",
                            "createdAt": "2023-02-15T00:00:00Z",
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "job_cursor_1"},
            }
        },
        "extensions": {"cost": {"actualCost": 10}},
    }

    # Mock invoices response
    client.fetch_invoices.return_value = {
        "data": {
            "invoices": {
                "edges": [
                    {
                        "cursor": "invoice_cursor_1",
                        "node": {
                            "id": "invoice_1",
                            "client": {"id": "client_1"},
                            "job": {"id": "job_1"},
                            "invoiceNumber": "INV-001",
                            "createdAt": "2023-03-01T00:00:00Z",
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "invoice_cursor_1"},
            }
        },
        "extensions": {"cost": {"actualCost": 10}},
    }

    # Mock other entity types with empty responses
    empty_response = lambda name: {
        "data": {
            name: {
                "edges": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        },
        "extensions": {"cost": {"actualCost": 5}},
    }

    client.fetch_requests.return_value = empty_response("requests")
    client.fetch_visits.return_value = empty_response("visits")
    client.fetch_expenses.return_value = empty_response("expenses")
    client.fetch_timesheet_entries.return_value = empty_response("timesheetEntries")
    client.fetch_products_services.return_value = empty_response("productsAndServices")
    client.fetch_tax_rates.return_value = empty_response("taxRates")

    return client


@pytest.fixture
def mock_entity_mapper():
    """Create mock EntityMapper."""
    # Use MagicMock without spec for flexible mocking
    # Return values aren't needed since we're mocking at extractor level
    return MagicMock()


@pytest.fixture
def mock_logger():
    """Create mock Logger."""
    return MagicMock(spec=Logger)


@pytest.fixture
def real_repository(db_connection):
    """Create real Repository with in-memory database."""
    repo = Repository(db_connection)
    repo.init_schema()
    return repo


@pytest.mark.integration
class TestMaxExtractCoordinator:
    """Integration tests for MaxExtractCoordinator."""

    def test_init_builds_all_extractors(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that coordinator initializes with all 14 extractors."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Verify all 14 entity types have extractors
        assert len(coordinator._extractors) == 14
        assert "users" in coordinator._extractors
        assert "clients" in coordinator._extractors
        assert "properties" in coordinator._extractors
        assert "requests" in coordinator._extractors
        assert "quotes" in coordinator._extractors
        assert "jobs" in coordinator._extractors
        assert "visits" in coordinator._extractors
        assert "invoices" in coordinator._extractors
        assert "expenses" in coordinator._extractors
        assert "timesheet_entries" in coordinator._extractors
        assert "product_services" in coordinator._extractors
        assert "tax_rates" in coordinator._extractors
        assert "notes" in coordinator._extractors

    def test_entity_order_respects_dependencies(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that ENTITY_ORDER follows dependency constraints."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        order = coordinator.ENTITY_ORDER

        # Users must come before entities that reference them
        users_idx = order.index("users")
        assert users_idx < order.index("clients")  # clients reference users
        assert users_idx < order.index("visits")  # visits reference users
        assert users_idx < order.index("timesheet_entries")  # timesheet_entries reference users

        # Clients must come before entities that reference them
        clients_idx = order.index("clients")
        assert clients_idx < order.index("properties")  # properties reference clients
        assert clients_idx < order.index("jobs")  # jobs reference clients
        assert clients_idx < order.index("quotes")  # quotes reference clients
        assert clients_idx < order.index("invoices")  # invoices reference clients

        # Properties must come before jobs
        properties_idx = order.index("properties")
        assert properties_idx < order.index("jobs")  # jobs reference properties

        # Jobs must come before dependent entities
        jobs_idx = order.index("jobs")
        assert jobs_idx < order.index("visits")  # visits reference jobs
        assert jobs_idx < order.index("expenses")  # expenses reference jobs
        assert jobs_idx < order.index("invoices")  # invoices reference jobs

        # Notes should come after parent entities
        notes_idx = order.index("notes")
        assert notes_idx > clients_idx
        assert notes_idx > jobs_idx
        assert notes_idx > order.index("quotes")
        assert notes_idx > order.index("invoices")

    def test_extract_all_entities_success(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test successful extraction of all entities in dependency order."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Execute full extraction
        summary = coordinator.extract_all(resume=False)

        # Verify summary structure
        assert "total_entities" in summary
        assert "results" in summary
        assert "errors" in summary

        # Verify no errors
        assert len(summary["errors"]) == 0

        # Verify results for each entity type
        assert "users" in summary["results"]
        assert "clients" in summary["results"]
        assert "properties" in summary["results"]

        # Verify total count
        assert summary["total_entities"] >= 0

    def test_extract_selective_entities(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test selective entity extraction (only specified types)."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Extract only users and clients
        summary = coordinator.extract_all(entities=["users", "clients"], resume=False)

        # Verify only requested entities in results
        assert len(summary["results"]) == 2
        assert "users" in summary["results"]
        assert "clients" in summary["results"]
        assert "properties" not in summary["results"]
        assert "jobs" not in summary["results"]

    def test_extract_maintains_dependency_order_with_subset(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that dependency order is maintained even for entity subset."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Request entities out of dependency order
        requested = ["jobs", "clients", "users", "properties"]

        # Track extraction order
        extraction_order = []

        # Patch extractors to track call order
        for entity_type in requested:
            original_extract = coordinator._extractors[entity_type].extract_all

            def make_tracker(etype):
                def tracked_extract(resume=False):
                    extraction_order.append(etype)
                    return []

                return tracked_extract

            coordinator._extractors[entity_type].extract_all = make_tracker(entity_type)

        # Execute
        summary = coordinator.extract_all(entities=requested, resume=False)

        # Verify dependency order was maintained
        assert extraction_order.index("users") < extraction_order.index("clients")
        assert extraction_order.index("clients") < extraction_order.index("properties")
        assert extraction_order.index("properties") < extraction_order.index("jobs")

    def test_extract_with_resume_flag(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that resume flag is passed to extractors."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Patch one extractor to verify resume parameter
        resume_called_with = []
        original_extract = coordinator._extractors["users"].extract_all

        def tracked_extract(resume=False):
            resume_called_with.append(resume)
            return []

        coordinator._extractors["users"].extract_all = tracked_extract

        # Execute with resume=True
        coordinator.extract_all(entities=["users"], resume=True)

        # Verify resume was passed correctly
        assert len(resume_called_with) == 1
        assert resume_called_with[0] is True

    def test_extract_handles_extractor_errors_gracefully(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that extraction continues despite individual extractor failures."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Make clients extractor fail
        coordinator._extractors["clients"].extract_all = Mock(
            side_effect=Exception("API Error")
        )

        # Execute extraction
        summary = coordinator.extract_all(entities=["users", "clients", "properties"], resume=False)

        # Verify users and properties succeeded, clients failed
        assert "users" in summary["results"]
        assert "clients" in summary["results"]
        assert summary["results"]["clients"] == 0  # Failed extraction

        # Verify error was recorded
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["entity_type"] == "clients"
        assert "API Error" in summary["errors"][0]["error"]

    def test_extract_validates_entity_names(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that invalid entity names are filtered out with warning."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Request valid and invalid entities
        summary = coordinator.extract_all(
            entities=["users", "invalid_entity", "clients"], resume=False
        )

        # Verify only valid entities were processed
        assert "users" in summary["results"]
        assert "clients" in summary["results"]
        assert "invalid_entity" not in summary["results"]

        # Verify warning was logged
        mock_logger.warning.assert_called()
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("invalid_entity" in str(call) for call in warning_calls)

    def test_extract_summary_statistics(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that summary contains accurate statistics."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Mock extractors to return known counts
        coordinator._extractors["users"].extract_all = Mock(return_value=[Mock()] * 5)
        coordinator._extractors["clients"].extract_all = Mock(return_value=[Mock()] * 10)

        # Execute
        summary = coordinator.extract_all(entities=["users", "clients"], resume=False)

        # Verify statistics
        assert summary["results"]["users"] == 5
        assert summary["results"]["clients"] == 10
        assert summary["total_entities"] == 15
        assert len(summary["errors"]) == 0

    def test_extract_logs_progress(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that coordinator logs extraction progress."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Execute
        summary = coordinator.extract_all(entities=["users", "clients"], resume=False)

        # Verify progress logging
        info_calls = [str(call) for call in mock_logger.info.call_args_list]

        # Should log start message
        assert any("Starting max extraction" in str(call) for call in info_calls)

        # Should log per-entity extraction
        assert any("Extracting: users" in str(call) for call in info_calls)
        assert any("Extracting: clients" in str(call) for call in info_calls)

        # Should log completion
        assert any("Completed users" in str(call) for call in info_calls)
        assert any("Completed clients" in str(call) for call in info_calls)

        # Should log summary
        assert any("Extraction Summary" in str(call) for call in info_calls)

    def test_extract_empty_entity_list_extracts_all(
        self, mock_jobber_client, real_repository, mock_logger, mock_entity_mapper
    ):
        """Test that None/empty entities list extracts all entity types."""
        coordinator = MaxExtractCoordinator(
            jobber_client=mock_jobber_client,
            repository=real_repository,
            logger=mock_logger,
            entity_mapper=mock_entity_mapper,
        )

        # Execute with entities=None (default)
        summary = coordinator.extract_all(entities=None, resume=False)

        # Verify all 14 entity types were processed
        assert len(summary["results"]) == 14
        assert all(
            entity in summary["results"] for entity in coordinator.ENTITY_ORDER
        )
