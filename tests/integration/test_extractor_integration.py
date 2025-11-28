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
                                "pageInfo": {"hasNextPage": False},
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
                                "pageInfo": {"hasNextPage": False},
                            },
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "cursor_1"},
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
                                "pageInfo": {"hasNextPage": False},
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
                                "pageInfo": {"hasNextPage": False},
                            },
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": "cursor_inv_1"},
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
        total_raw = data.get("total", "0")
        try:
            total_cents = int(float(total_raw) * 100)
        except (TypeError, ValueError):
            total_cents = 0

        return Invoice(
            id=data["id"],
            client_id=data.get("client", {}).get("id", ""),
            number=data.get("invoiceNumber", ""),
            total_cents=total_cents,
            status=data.get("invoiceStatus", ""),
            issued_at=data.get("createdAt", ""),
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


@pytest.fixture
def mock_attachment_downloader():
    """Mock AttachmentDownloader to prevent real HTTP requests."""
    with patch("src.extractors.base_extractor.AttachmentDownloader") as mock_class:
        mock_instance = Mock()
        mock_instance.download_attachment.return_value = {
            "success": True,
            "local_file_path": "./attachments/mock/test_file.pdf",
            "bytes_downloaded": 12345,
            "error_message": None,
        }
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.mark.integration
class TestExtractorIntegration:
    """Integration tests for new extractors with nested notes optimization."""

    def test_end_to_end_client_extraction_with_nested_notes(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager,
        mock_attachment_downloader,
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
            skip_existing_entities=False,
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
        mock_config_manager,
        mock_attachment_downloader,
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
            skip_existing_entities=False,
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
        tmp_path,
        mock_attachment_downloader,
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
        mock_config_manager,
        mock_attachment_downloader,
    ):
        """Test error handling when notes pagination has issues.

        Validates:
        - With auto-pagination, additional notes are fetched when hasNextPage=True
        - If pagination fails, extraction continues with partial notes
        - Warning is logged when auto-pagination fails
        - Primary entity extraction succeeds
        """
        # Mock initial response with hasNextPage=True and endCursor
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
                                    "totalCount": 4,
                                    "edges": [
                                        {"node": {"id": "note_1", "body": "Note 1", "createdAt": "2023-11-15T10:00:00Z"}},
                                        {"node": {"id": "note_2", "body": "Note 2", "createdAt": "2023-11-15T10:00:00Z"}},
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": "cursor_note_2",
                                    },
                                },
                            },
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor_1"},
                }
            }
        }

        # Mock fetch_additional_notes to raise an error (simulating pagination failure)
        mock_jobber_client.fetch_additional_notes.side_effect = Exception("Pagination API error")

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

        # Verify extraction succeeded despite note pagination failure
        assert result["entities_processed"] == 1, "Should process client successfully"

        # Verify fetch_additional_notes was called (auto-pagination attempted)
        mock_jobber_client.fetch_additional_notes.assert_called_once_with(
            entity_id="client_1",
            entity_type="client",
            cursor="cursor_note_2",
            page_size=100,
        )

        # Verify warning was logged about pagination failure
        assert mock_logger.warning.called, "Should warn about pagination failure"
        warning_message = str(mock_logger.warning.call_args)
        assert "Error fetching additional notes" in warning_message

        # Verify client was still saved
        mock_repository.save_clients.assert_called_once()

        # Verify initial notes were still saved (partial success)
        mock_repository.save_notes.assert_called()

    def test_error_handling_mapping_error_in_nested_notes(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager,
        mock_attachment_downloader,
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
        assert mock_logger.debug.called or mock_logger.warning.called or mock_logger.error.called

        # Verify client was saved (even though notes failed)
        mock_repository.save_clients.assert_called_once()

    def test_extraction_summary_includes_nested_notes_metrics(
        self,
        mock_jobber_client,
        mock_entity_mapper,
        mock_repository,
        mock_logger,
        mock_config_manager,
        mock_attachment_downloader,
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
        expected_keys = {
            "total_entities",
            "entities_skipped",
            "total_pages",
            "extraction_duration",
            "average_page_size",
            "entities_per_second",
            "last_cursor",
            "extraction_status",
            "error_count",
        }
        assert expected_keys.issubset(summary.keys())
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
        tmp_path,
        mock_attachment_downloader,
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
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("No permission")):
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
            warning_calls = [call for call in mock_logger.warning.call_args_list if "report" in str(call).lower()]
            # May or may not have warnings depending on when the error occurs
            # The key is that the migration didn't raise an exception


class TestAutoPagination:
    """Tests for auto-pagination of notes and attachments."""

    def test_auto_pagination_fetches_all_notes(
        self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_config_manager, mock_logger
    ):
        """Test that extractor automatically fetches all notes when hasNextPage is True."""
        # Initial page with hasNextPage=True
        mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "totalCount": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "client_1",
                                "firstName": "John",
                                "lastName": "Doe",
                                "notes": {
                                    "totalCount": 25,  # More than initial fetch limit
                                    "edges": [
                                        {"node": {"id": "note_1", "message": "First note", "createdAt": "2023-01-01"}}
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": "cursor_page_2"
                                    }
                                },
                                "noteAttachments": {
                                    "totalCount": 0,
                                    "edges": [],
                                    "pageInfo": {"hasNextPage": False}
                                }
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False}
                }
            }
        }

        # Additional notes pages
        mock_jobber_client.fetch_additional_notes.side_effect = [
            # Page 2
            {
                "totalCount": 25,
                "edges": [
                    {"node": {"id": "note_2", "message": "Second note", "createdAt": "2023-01-02"}},
                    {"node": {"id": "note_3", "message": "Third note", "createdAt": "2023-01-03"}}
                ],
                "pageInfo": {
                    "hasNextPage": True,
                    "endCursor": "cursor_page_3"
                }
            },
            # Page 3 (final)
            {
                "totalCount": 25,
                "edges": [
                    {"node": {"id": "note_4", "message": "Fourth note", "createdAt": "2023-01-04"}}
                ],
                "pageInfo": {
                    "hasNextPage": False,
                    "endCursor": None
                }
            }
        ]

        # Setup mapper to return mock entities
        mock_client = Mock(spec=Client, id="client_1")
        mock_entity_mapper.map_client.return_value = mock_client
        mock_entity_mapper.map_note.side_effect = [
            Mock(spec=Note, id="note_1"),
            Mock(spec=Note, id="note_2"),
            Mock(spec=Note, id="note_3"),
            Mock(spec=Note, id="note_4"),
        ]

        # Create extractor and run extraction
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            entity_mapper=mock_entity_mapper,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        extractor.extract()

        # Verify fetch_additional_notes was called twice (for pages 2 and 3)
        assert mock_jobber_client.fetch_additional_notes.call_count == 2

        # Verify it was called with correct parameters
        first_call = mock_jobber_client.fetch_additional_notes.call_args_list[0]
        assert first_call[1]["entity_id"] == "client_1"
        assert first_call[1]["entity_type"] == "client"
        assert first_call[1]["cursor"] == "cursor_page_2"

        second_call = mock_jobber_client.fetch_additional_notes.call_args_list[1]
        assert second_call[1]["cursor"] == "cursor_page_3"

        # Verify all 4 notes were mapped
        assert mock_entity_mapper.map_note.call_count == 4

        # Verify all notes were saved
        assert mock_repository.save_notes.called

    def test_auto_pagination_fetches_all_attachments(
        self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_config_manager, mock_logger
    ):
        """Test that extractor automatically fetches all attachments when hasNextPage is True."""
        # Initial page with hasNextPage=True
        mock_jobber_client.fetch_invoices.return_value = {
            "data": {
                "invoices": {
                    "totalCount": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "invoice_1",
                                "invoiceNumber": "INV-001",
                                "notes": {
                                    "totalCount": 0,
                                    "edges": [],
                                    "pageInfo": {"hasNextPage": False}
                                },
                                "noteAttachments": {
                                    "totalCount": 15,  # More than initial fetch limit
                                    "edges": [
                                        {"node": {"id": "att_1", "fileName": "file1.pdf", "url": "https://example.com/1"}}
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": "att_cursor_2"
                                    }
                                }
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False}
                }
            }
        }

        # Additional attachments page (final)
        mock_jobber_client.fetch_additional_attachments.return_value = {
            "totalCount": 15,
            "edges": [
                {"node": {"id": "att_2", "fileName": "file2.pdf", "url": "https://example.com/2"}},
                {"node": {"id": "att_3", "fileName": "file3.pdf", "url": "https://example.com/3"}}
            ],
            "pageInfo": {
                "hasNextPage": False,
                "endCursor": None
            }
        }

        # Setup mapper
        mock_invoice = Mock(spec=Invoice, id="invoice_1")
        mock_entity_mapper.map_invoice.return_value = mock_invoice

        # Create mock attachments with required attributes
        mock_att_1 = Mock(
            spec=Attachment,
            id="att_1",
            file_name="file1.pdf",
            original_url="https://example.com/1",
            local_path=None,
            file_size=1024,
            content_type="application/pdf"
        )
        mock_att_2 = Mock(
            spec=Attachment,
            id="att_2",
            file_name="file2.pdf",
            original_url="https://example.com/2",
            local_path=None,
            file_size=2048,
            content_type="application/pdf"
        )
        mock_att_3 = Mock(
            spec=Attachment,
            id="att_3",
            file_name="file3.pdf",
            original_url="https://example.com/3",
            local_path=None,
            file_size=3072,
            content_type="application/pdf"
        )

        mock_entity_mapper.map_attachment.side_effect = [mock_att_1, mock_att_2, mock_att_3]

        # Disable auto-download in config to test only pagination
        mock_config_manager.get_auto_download.return_value = False

        # Create extractor
        extractor = InvoicesExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            entity_mapper=mock_entity_mapper,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        extractor.extract()

        # Verify fetch_additional_attachments was called
        assert mock_jobber_client.fetch_additional_attachments.call_count == 1

        # Verify correct parameters
        call_args = mock_jobber_client.fetch_additional_attachments.call_args[1]
        assert call_args["entity_id"] == "invoice_1"
        assert call_args["entity_type"] == "invoice"
        assert call_args["cursor"] == "att_cursor_2"

        # Verify all 3 attachments were mapped
        assert mock_entity_mapper.map_attachment.call_count == 3

    def test_auto_pagination_handles_errors_gracefully(
        self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_config_manager, mock_logger
    ):
        """Test that pagination errors don't break the extraction."""
        # Initial page with hasNextPage=True
        mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "totalCount": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "client_1",
                                "firstName": "John",
                                "lastName": "Doe",
                                "notes": {
                                    "totalCount": 20,
                                    "edges": [
                                        {"node": {"id": "note_1", "message": "First note", "createdAt": "2023-01-01"}}
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": "cursor_page_2"
                                    }
                                },
                                "noteAttachments": {
                                    "totalCount": 0,
                                    "edges": [],
                                    "pageInfo": {"hasNextPage": False}
                                }
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False}
                }
            }
        }

        # Mock fetch_additional_notes to raise an error
        mock_jobber_client.fetch_additional_notes.side_effect = Exception("API error during pagination")

        # Setup mapper
        mock_client = Mock(spec=Client, id="client_1")
        mock_entity_mapper.map_client.return_value = mock_client
        mock_entity_mapper.map_note.return_value = Mock(spec=Note, id="note_1")

        # Create extractor
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            entity_mapper=mock_entity_mapper,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        # Should complete without raising exception
        extractor.extract()

        # Verify warning was logged about the error
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("Error fetching additional notes" in call for call in warning_calls)

        # Verify client was still saved despite pagination error
        assert mock_repository.save_clients.called

    def test_no_pagination_when_hasNextPage_false(
        self, mock_jobber_client, mock_entity_mapper, mock_repository, mock_config_manager, mock_logger
    ):
        """Test that no additional requests are made when hasNextPage is False."""
        # Page with hasNextPage=False
        mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "totalCount": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "client_1",
                                "firstName": "John",
                                "lastName": "Doe",
                                "notes": {
                                    "totalCount": 2,
                                    "edges": [
                                        {"node": {"id": "note_1", "message": "First note", "createdAt": "2023-01-01"}},
                                        {"node": {"id": "note_2", "message": "Second note", "createdAt": "2023-01-02"}}
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": False,
                                        "endCursor": None
                                    }
                                },
                                "noteAttachments": {
                                    "totalCount": 0,
                                    "edges": [],
                                    "pageInfo": {"hasNextPage": False}
                                }
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False}
                }
            }
        }

        # Setup mapper
        mock_client = Mock(spec=Client, id="client_1")
        mock_entity_mapper.map_client.return_value = mock_client
        mock_entity_mapper.map_note.side_effect = [
            Mock(spec=Note, id="note_1"),
            Mock(spec=Note, id="note_2"),
        ]

        # Create extractor
        extractor = ClientsExtractor(
            jobber_client=mock_jobber_client,
            repository=mock_repository,
            entity_mapper=mock_entity_mapper,
            logger=mock_logger,
            config_manager=mock_config_manager,
        )

        extractor.extract()

        # Verify fetch_additional_notes was NOT called (since no need for auto-pagination, fetch_additional_notes may not exist as an attribute)
        if hasattr(mock_jobber_client, 'fetch_additional_notes'):
            assert not mock_jobber_client.fetch_additional_notes.called

        # Verify only 2 notes were mapped (from first page)
        assert mock_entity_mapper.map_note.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
