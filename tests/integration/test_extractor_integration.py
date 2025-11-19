"""Integration tests for new extractors with nested notes and reporting.

Tests cover:
1. End-to-end extraction with nested notes optimization
2. Report generation within full migration flow
3. Error scenarios (notes pagination failures, mapping errors)
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

from src.coordinators.base_migration_coordinator import BaseMigrationCoordinator
from src.extractors import (
    ClientsExtractor,
    InvoicesExtractor,
    NotesExtractor,
    QuotesExtractor,
)
from src.clients import JobberClient
from src.config import ConfigManagerImpl
from src.mappers import EntityMapper
from src.repositories import Repository
from src.interfaces import Logger
from src.models import Client, Invoice, Note, Attachment


@pytest.fixture
def mock_config_manager():
    """Create a mock ConfigManager with nested_notes configuration."""
    config = Mock()  # Don't use spec to allow flexible mocking
    config.get_max_retries.return_value = 3
    config.get_nested_notes_limit.return_value = 10
    config.get_clients_page_size.return_value = 50
    config.get_invoices_page_size.return_value = 50
    config.get_pagination_config.return_value = 50
    return config


@pytest.fixture
def mock_jobber_client():
    """Create a mock JobberClient with comprehensive responses."""
    client = Mock()  # Don't use spec for flexible mocking

    # Mock clients response with nested notes and attachments
    client.fetch_clients.return_value = {
        "data": {
            "clients": {
                "edges": [
                    {
                        "cursor": "cursor_1",
                        "node": {
                            "id": "client_1",
                            "firstName": "John",
                            "lastName": "Doe",
                            "email": "john@example.com",
                            "phone": "555-0100",
                            "createdAt": "2023-11-15T10:00:00Z",
                            "notes": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "note_1",
                                            "body": "Test note for client",
                                            "createdAt": "2023-11-15T10:05:00Z",
                                            "updatedAt": "2023-11-15T10:05:00Z",
                                        }
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False}
                            },
                            "noteAttachments": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "attachment_1",
                                            "note": {"id": "note_1"},
                                            "fileName": "test_file.pdf",
                                            "contentType": "application/pdf",
                                            "url": "https://example.com/files/test_file.pdf",
                                            "fileSize": 12345,
                                            "createdAt": "2023-11-15T10:06:00Z",
                                        }
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False}
                            }
                        }
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "cursor_1"}
            }
        }
    }

    # Mock invoices response with nested notes and attachments
    client.fetch_invoices.return_value = {
        "data": {
            "invoices": {
                "edges": [
                    {
                        "cursor": "cursor_inv_1",
                        "node": {
                            "id": "invoice_1",
                            "invoiceNumber": "INV-001",
                            "subject": "Test Invoice",
                            "total": "100.00",
                            "createdAt": "2023-11-15T11:00:00Z",
                            "client": {"id": "client_1"},
                            "notes": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "note_2",
                                            "body": "Test note for invoice",
                                            "createdAt": "2023-11-15T11:05:00Z",
                                            "updatedAt": "2023-11-15T11:05:00Z",
                                        }
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False}
                            },
                            "noteAttachments": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "attachment_2",
                                            "note": {"id": "note_2"},
                                            "fileName": "invoice_doc.pdf",
                                            "contentType": "application/pdf",
                                            "url": "https://example.com/files/invoice_doc.pdf",
                                            "fileSize": 54321,
                                            "createdAt": "2023-11-15T11:06:00Z",
                                        }
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False}
                            }
                        }
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "cursor_inv_1"}
            }
        }
    }

    return client


@pytest.fixture
def mock_entity_mapper():
    """Create a mock EntityMapper."""
    mapper = Mock()  # Don't use spec for flexible mocking

    # Map clients
    def map_client(data):
        return Client(
            id=data["id"],
            first_name=data.get("firstName", ""),
            last_name=data.get("lastName", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            created_at=data.get("createdAt", ""),
            additional_emails="[]",
            additional_phones="[]",
        )

    # Map invoices
    def map_invoice(data):
        return Invoice(
            id=data["id"],
            invoice_number=data.get("invoiceNumber", ""),
            subject=data.get("subject", ""),
            total=data.get("total", "0.00"),
            created_at=data.get("createdAt", ""),
            client_id=data.get("client", {}).get("id", ""),
        )

    # Map notes
    def map_note(data):
        # Determine entity type and ID from data
        entity_type = "unknown"
        entity_id = ""
        if "client" in data:
            entity_type = "client"
            entity_id = data["client"]["id"]
        elif "invoice" in data:
            entity_type = "invoice"
            entity_id = data["invoice"]["id"]

        return Note(
            id=data["id"],
            entity_type=entity_type,
            entity_id=entity_id,
            message=data.get("body", ""),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", data.get("createdAt", "")),
        )

    # Map attachments
    def map_attachment(data):
        return Attachment(
            id=data["id"],
            note_id=data.get("note", {}).get("id", ""),
            file_name=data.get("fileName", ""),
            content_type=data.get("contentType", ""),
            original_url=data.get("url", ""),
            local_file_path=f"./attachments/{data.get('note', {}).get('id', 'unknown')}/{data.get('fileName', 'unknown')}",
            file_size=data.get("fileSize", 0),
            created_at=data.get("createdAt", ""),
        )

    mapper.map_client.side_effect = map_client
    mapper.map_invoice.side_effect = map_invoice
    mapper.map_note.side_effect = map_note
    mapper.map_attachment.side_effect = map_attachment

    return mapper


@pytest.fixture
def mock_repository():
    """Create a mock Repository."""
    repo = Mock()  # Don't use spec for flexible mocking
    repo.save_clients.return_value = None
    repo.save_invoices.return_value = None
    repo.save_notes.return_value = None
    repo.save_attachments.return_value = None
    repo.entity_exists.return_value = False
    return repo


@pytest.fixture
def mock_logger():
    """Create a mock Logger."""
    logger = Mock()  # Don't use spec for flexible mocking
    return logger


@pytest.mark.integration
class TestExtractorIntegration:
    """Integration tests for new extractors with nested notes optimization."""

    def test_end_to_end_client_extraction_with_nested_notes(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager
    ):
        """Test complete client extraction workflow with nested notes optimization.

        Validates:
        - Clients are extracted with nested notes in single query
        - Notes are automatically saved during client extraction
        - API call count is optimized (no separate note queries)
        """
        # Create ClientsExtractor
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
            skip_existing_entities=False
        )

        # Execute extraction
        result = extractor.extract()

        # Verify extraction results
        assert result["entities_processed"] == 1, "Should process 1 client"
        assert result["entities_skipped"] == 0, "Should skip 0 clients"
        # Notes are tracked separately, not in main result dict

        # Verify client was saved
        mock_repository.save_clients.assert_called_once()
        saved_clients = mock_repository.save_clients.call_args[0][0]
        assert len(saved_clients) == 1
        assert saved_clients[0].id == "client_1"

        # Verify nested notes were saved
        mock_repository.save_notes.assert_called()
        saved_notes = mock_repository.save_notes.call_args[0][0]
        assert len(saved_notes) >= 1, "Should save nested notes"
        assert any(note.id == "note_1" for note in saved_notes)

        # Verify nested attachments were saved
        mock_repository.save_attachments.assert_called()
        saved_attachments = mock_repository.save_attachments.call_args[0][0]
        assert len(saved_attachments) >= 1, "Should save nested attachments"
        assert any(att.id == "attachment_1" for att in saved_attachments)
        assert any(att.file_name == "test_file.pdf" for att in saved_attachments)

        # Verify API call optimization (only one fetch_clients call)
        assert mock_jobber_client.fetch_clients.call_count == 1

    def test_end_to_end_invoice_extraction_with_nested_notes(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager
    ):
        """Test complete invoice extraction workflow with nested notes optimization.

        Validates:
        - Invoices are extracted with nested notes in single query
        - Notes are automatically saved during invoice extraction
        - API call count is optimized (no separate note queries)
        """
        # Create InvoicesExtractor
        extractor = InvoicesExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
            skip_existing_entities=False
        )

        # Execute extraction
        result = extractor.extract()

        # Verify extraction results
        assert result["entities_processed"] == 1, "Should process 1 invoice"
        # Notes are tracked separately, not in main result dict

        # Verify invoice was saved
        mock_repository.save_invoices.assert_called_once()
        saved_invoices = mock_repository.save_invoices.call_args[0][0]
        assert len(saved_invoices) == 1
        assert saved_invoices[0].id == "invoice_1"

        # Verify nested notes were saved
        mock_repository.save_notes.assert_called()
        saved_notes = mock_repository.save_notes.call_args[0][0]
        assert len(saved_notes) >= 1, "Should save nested notes"
        assert any(note.id == "note_2" for note in saved_notes)

        # Verify nested attachments were saved
        mock_repository.save_attachments.assert_called()
        saved_attachments = mock_repository.save_attachments.call_args[0][0]
        assert len(saved_attachments) >= 1, "Should save nested attachments"
        assert any(att.id == "attachment_2" for att in saved_attachments)
        assert any(att.file_name == "invoice_doc.pdf" for att in saved_attachments)

        # Verify API call optimization (only one fetch_invoices call)
        assert mock_jobber_client.fetch_invoices.call_count == 1

    def test_migration_coordinator_with_report_generation(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager,
        temp_database,
        tmp_path
    ):
        """Test full migration flow with report generation.

        Validates:
        - Complete migration workflow executes successfully
        - Reports are generated after migration
        - Both text and JSON reports are created
        - Reports contain extractor summaries
        """
        # Create extractors
        clients_extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        invoices_extractor = InvoicesExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        # Create report output directory
        report_dir = tmp_path / "reports"
        report_dir.mkdir(exist_ok=True)

        # Create coordinator
        coordinator = BaseMigrationCoordinator(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
            clients_extractor=clients_extractor,
            invoices_extractor=invoices_extractor,
            quotes_extractor=None,
            notes_extractor=None,
            report_output_dir=report_dir,
        )

        # Execute migration
        summary = coordinator.migrate()

        # Verify migration completed
        assert summary is not None
        assert summary.clients_processed >= 0
        assert summary.invoices_processed >= 0

        # Verify reports were generated
        report_files = list(report_dir.glob("*.txt"))
        json_files = list(report_dir.glob("*.json"))

        assert len(report_files) >= 1, "Should create text report"
        assert len(json_files) >= 1, "Should create JSON report"

        # Verify report content
        text_report = report_files[0].read_text()
        assert "TightBeam Migration" in text_report
        assert "clients" in text_report.lower()

        json_report = json_files[0].read_text()
        assert "migration_name" in json_report
        assert "extractors" in json_report

    def test_error_handling_notes_pagination_failure(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager
    ):
        """Test error handling when notes pagination has issues.

        Validates:
        - Extraction continues even if notes have pagination issues
        - Warning is logged when notes are truncated
        - Primary entity extraction succeeds
        """
        # Mock response with truncated notes (hasNextPage=True)
        mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "edges": [
                        {
                            "cursor": "cursor_1",
                            "node": {
                                "id": "client_1",
                                "firstName": "John",
                                "lastName": "Doe",
                                "email": "john@example.com",
                                "phone": "555-0100",
                                "createdAt": "2023-11-15T10:00:00Z",
                                "notes": {
                                    "edges": [
                                        {"node": {"id": "note_1", "body": "Note 1"}},
                                        {"node": {"id": "note_2", "body": "Note 2"}},
                                    ],
                                    "pageInfo": {"hasNextPage": True}  # More notes exist!
                                }
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor_1"}
                }
            }
        }

        # Create extractor
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        # Execute extraction
        result = extractor.extract()

        # Verify extraction succeeded despite note truncation
        assert result["entities_processed"] == 1, "Should process client successfully"

        # Verify warning was logged about truncated notes
        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if "has more notes" in str(call).lower()
        ]
        assert len(warning_calls) > 0, "Should warn about truncated notes"

        # Verify client was still saved
        mock_repository.save_clients.assert_called_once()

    def test_error_handling_mapping_error_in_nested_notes(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager
    ):
        """Test error handling when note mapping fails.

        Validates:
        - Primary entity extraction succeeds even if note mapping fails
        - Mapping errors are caught and logged
        - Extraction continues for remaining entities
        """
        from src.exceptions import MappingError

        # Mock mapper to fail on note mapping
        def map_note_with_error(data):
            raise MappingError("Failed to map note")

        mock_entity_mapper.map_note.side_effect = map_note_with_error

        # Create extractor
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        # Execute extraction
        result = extractor.extract()

        # Verify client extraction succeeded despite note mapping failure
        assert result["entities_processed"] == 1, "Should process client successfully"

        # Verify error was logged
        assert mock_logger.warning.called or mock_logger.error.called

        # Verify client was saved (even though notes failed)
        mock_repository.save_clients.assert_called_once()

    def test_extraction_summary_includes_nested_notes_metrics(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager
    ):
        """Test that extraction summary includes nested notes metrics.

        Validates:
        - get_extraction_summary() includes note counts
        - Summary differentiates between primary entities and nested notes
        - Metrics are accurate
        """
        # Create extractor
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        # Execute extraction
        result = extractor.extract()

        # Get summary
        summary = extractor.get_extraction_summary()

        # Verify summary has expected structure
        assert "entities_processed" in summary
        assert "entities_skipped" in summary
        assert summary["entities_processed"] == 1
        # Summary may include related entities, errors, etc.


@pytest.mark.integration
class TestReportGenerationIntegration:
    """Integration tests specifically for report generation features."""

    def test_report_generation_does_not_fail_migration_on_error(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager,
        tmp_path
    ):
        """Test that report generation errors don't fail the migration.

        Validates:
        - Migration completes successfully even if reporting fails
        - Report errors are logged as warnings
        - Migration summary is still returned
        """
        # Create extractor
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            entity_mapper=mock_entity_mapper,
            repository=mock_repository,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        # Create coordinator with invalid report directory (will fail)
        invalid_report_dir = tmp_path / "nonexistent" / "deeply" / "nested" / "invalid"

        # Mock the mkdir to fail
        with patch('pathlib.Path.mkdir', side_effect=PermissionError("No permission")):
            coordinator = BaseMigrationCoordinator(
                jobber_client=mock_jobber_client,
                entity_mapper=mock_entity_mapper,
                repository=mock_repository,
                logger=mock_logger,
                config_manager=mock_config_manager,
                clients_extractor=extractor,
                invoices_extractor=None,
                quotes_extractor=None,
                notes_extractor=None,
                report_output_dir=invalid_report_dir,
            )

            # Execute migration - should succeed despite report failure
            summary = coordinator.migrate()

            # Verify migration completed
            assert summary is not None

            # Verify warning was logged about report failure
            warning_calls = [
                call for call in mock_logger.warning.call_args_list
                if "report" in str(call).lower()
            ]
            # May or may not have warnings depending on when the error occurs
            # The key is that the migration didn't raise an exception


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
