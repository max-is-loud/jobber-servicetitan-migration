"""Simplified integration tests for MaxExtractCoordinator.

Tests Phase 7 key behaviors without complex mocking.
"""

import pytest
from unittest.mock import Mock, patch

from src.coordinators.max_extract_coordinator import MaxExtractCoordinator


@pytest.mark.integration
class TestMaxExtractCoordinatorSimple:
    """Simplified integration tests for MaxExtractCoordinator."""

    def test_entity_order_constant_is_valid(self):
        """Test that ENTITY_ORDER is defined and contains expected entities."""
        order = MaxExtractCoordinator.ENTITY_ORDER

        # Verify basic structure
        assert isinstance(order, list)
        assert len(order) == 13  # All 13 entity types

        # Verify all expected entities present
        expected_entities = {
            "users",
            "clients",
            "properties",
            "requests",
            "quotes",
            "jobs",
            "visits",
            "invoices",
            "expenses",
            "timesheet_entries",
            "product_services",
            "tax_rates",
            "notes",
        }
        assert set(order) == expected_entities

    def test_entity_order_respects_user_dependencies(self):
        """Test users come before entities that reference them."""
        order = MaxExtractCoordinator.ENTITY_ORDER

        users_idx = order.index("users")
        # Entities that reference users must come after
        assert users_idx < order.index("visits")
        assert users_idx < order.index("timesheet_entries")

    def test_entity_order_respects_client_dependencies(self):
        """Test clients come before entities that reference them."""
        order = MaxExtractCoordinator.ENTITY_ORDER

        clients_idx = order.index("clients")
        # Entities that reference clients must come after
        assert clients_idx < order.index("properties")
        assert clients_idx < order.index("jobs")
        assert clients_idx < order.index("quotes")
        assert clients_idx < order.index("invoices")
        assert clients_idx < order.index("requests")
        assert clients_idx < order.index("visits")

    def test_entity_order_respects_job_dependencies(self):
        """Test jobs come before entities that reference them."""
        order = MaxExtractCoordinator.ENTITY_ORDER

        jobs_idx = order.index("jobs")
        # Entities that reference jobs must come after
        assert jobs_idx < order.index("visits")
        assert jobs_idx < order.index("expenses")
        assert jobs_idx < order.index("invoices")

    def test_entity_order_places_notes_last(self):
        """Test notes come after parent entities (polymorphic references)."""
        order = MaxExtractCoordinator.ENTITY_ORDER

        notes_idx = order.index("notes")
        # Notes reference multiple entity types, should be last or near-last
        assert notes_idx > order.index("clients")
        assert notes_idx > order.index("jobs")
        assert notes_idx > order.index("quotes")
        assert notes_idx > order.index("invoices")
        assert notes_idx > order.index("requests")

    @patch("src.coordinators.max_extract_coordinator.UsersExtractor")
    @patch("src.coordinators.max_extract_coordinator.ClientsExtractor")
    def test_build_extractors_creates_all_types(
        self, mock_clients_cls, mock_users_cls, mocker
    ):
        """Test _build_extractors creates all 13 extractor types."""
        # Mock all extractor classes
        extractor_classes = [
            "UsersExtractor",
            "ClientsExtractor",
            "PropertiesExtractor",
            "RequestsExtractor",
            "QuotesExtractor",
            "JobsExtractor",
            "VisitsExtractor",
            "InvoicesExtractor",
            "ExpensesExtractor",
            "TimesheetEntriesExtractor",
            "ProductServicesExtractor",
            "TaxRatesExtractor",
            "NotesExtractor",
        ]

        # Patch all extractor imports
        mocks = {}
        for extractor_cls in extractor_classes:
            mock = mocker.patch(
                f"src.coordinators.max_extract_coordinator.{extractor_cls}"
            )
            mock.return_value = Mock()
            mocks[extractor_cls] = mock

        # Create coordinator with mocked dependencies
        mock_client = Mock()
        mock_repo = Mock()
        mock_logger = Mock()
        mock_mapper = Mock()

        coordinator = MaxExtractCoordinator(
            jobber_client=mock_client,
            repository=mock_repo,
            logger=mock_logger,
            entity_mapper=mock_mapper,
        )

        # Verify all extractors were created
        assert len(coordinator._extractors) == 13
        assert all(
            entity_type in coordinator._extractors
            for entity_type in MaxExtractCoordinator.ENTITY_ORDER
        )

    def test_extract_all_validates_entity_names(self, mocker):
        """Test that invalid entity names are filtered with warning."""
        # Mock all extractors
        mocker.patch.object(
            MaxExtractCoordinator,
            "_build_extractors",
            return_value={
                "users": Mock(extract_all=Mock(return_value=[])),
                "clients": Mock(extract_all=Mock(return_value=[])),
            },
        )

        mock_logger = Mock()
        coordinator = MaxExtractCoordinator(
            jobber_client=Mock(),
            repository=Mock(),
            logger=mock_logger,
            entity_mapper=Mock(),
        )

        # Request mix of valid and invalid entities
        summary = coordinator.extract_all(
            entities=["users", "invalid_entity", "clients", "another_bad_one"],
            resume=False,
        )

        # Verify only valid entities processed
        assert "users" in summary["results"]
        assert "clients" in summary["results"]
        assert "invalid_entity" not in summary["results"]
        assert "another_bad_one" not in summary["results"]

        # Verify warning logged
        assert mock_logger.warning.called
        warning_msg = str(mock_logger.warning.call_args)
        assert "invalid_entity" in warning_msg or "another_bad_one" in warning_msg

    def test_extract_all_maintains_dependency_order(self, mocker):
        """Test that dependency order is maintained for requested subset."""
        # Track extraction order
        extraction_order = []

        def make_tracker(entity_type):
            def tracked_extract(resume=False):
                extraction_order.append(entity_type)
                return []

            return Mock(extract_all=tracked_extract)

        # Mock extractors for dependency chain
        mocker.patch.object(
            MaxExtractCoordinator,
            "_build_extractors",
            return_value={
                "users": make_tracker("users"),
                "clients": make_tracker("clients"),
                "properties": make_tracker("properties"),
                "jobs": make_tracker("jobs"),
            },
        )

        coordinator = MaxExtractCoordinator(
            jobber_client=Mock(),
            repository=Mock(),
            logger=Mock(),
            entity_mapper=Mock(),
        )

        # Request entities out of order
        summary = coordinator.extract_all(
            entities=["jobs", "clients", "users", "properties"],
            resume=False,
        )

        # Verify dependency order was maintained
        assert extraction_order.index("users") < extraction_order.index("clients")
        assert extraction_order.index("clients") < extraction_order.index("properties")
        assert extraction_order.index("properties") < extraction_order.index("jobs")

    def test_extract_all_passes_resume_flag(self, mocker):
        """Test that resume parameter is passed to extractors."""
        # Track resume parameter
        resume_calls = []

        def tracked_extract(resume=False):
            resume_calls.append(resume)
            return []

        mocker.patch.object(
            MaxExtractCoordinator,
            "_build_extractors",
            return_value={"users": Mock(extract_all=tracked_extract)},
        )

        coordinator = MaxExtractCoordinator(
            jobber_client=Mock(),
            repository=Mock(),
            logger=Mock(),
            entity_mapper=Mock(),
        )

        # Test with resume=True
        coordinator.extract_all(entities=["users"], resume=True)
        assert resume_calls[-1] is True

        # Test with resume=False
        coordinator.extract_all(entities=["users"], resume=False)
        assert resume_calls[-1] is False

    def test_extract_all_handles_extractor_errors(self, mocker):
        """Test extraction continues despite individual extractor failures."""
        mocker.patch.object(
            MaxExtractCoordinator,
            "_build_extractors",
            return_value={
                "users": Mock(extract_all=Mock(return_value=[Mock()])),
                "clients": Mock(extract_all=Mock(side_effect=Exception("API Error"))),
                "properties": Mock(extract_all=Mock(return_value=[Mock(), Mock()])),
            },
        )

        coordinator = MaxExtractCoordinator(
            jobber_client=Mock(),
            repository=Mock(),
            logger=Mock(),
            entity_mapper=Mock(),
        )

        summary = coordinator.extract_all(
            entities=["users", "clients", "properties"], resume=False
        )

        # Verify users and properties succeeded
        assert summary["results"]["users"] == 1
        assert summary["results"]["properties"] == 2

        # Verify clients failed but didn't crash
        assert summary["results"]["clients"] == 0

        # Verify error recorded
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["entity_type"] == "clients"
        assert "API Error" in summary["errors"][0]["error"]

    def test_extract_all_returns_summary_structure(self, mocker):
        """Test that extract_all returns properly structured summary."""
        mocker.patch.object(
            MaxExtractCoordinator,
            "_build_extractors",
            return_value={
                "users": Mock(extract_all=Mock(return_value=[Mock()] * 5)),
                "clients": Mock(extract_all=Mock(return_value=[Mock()] * 3)),
            },
        )

        coordinator = MaxExtractCoordinator(
            jobber_client=Mock(),
            repository=Mock(),
            logger=Mock(),
            entity_mapper=Mock(),
        )

        summary = coordinator.extract_all(entities=["users", "clients"], resume=False)

        # Verify structure
        assert "total_entities" in summary
        assert "results" in summary
        assert "errors" in summary

        # Verify counts
        assert summary["total_entities"] == 8
        assert summary["results"]["users"] == 5
        assert summary["results"]["clients"] == 3
        assert len(summary["errors"]) == 0
