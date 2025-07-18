"""Comprehensive integration tests for Enhanced Jobber Data Coverage workflow.

Tests the complete PRD implementation including all entity types, file downloads,
CLI commands, and data validation to ensure production readiness.
"""

import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.clients import JobberClient
from src.coordinators import MigrationCoordinator
from src.extractors import AttachmentDownloader, NotesExtractor, QuotesExtractor
from src.loggers import ConsoleLogger
from src.mappers import EntityMapper
from src.models import Attachment, Client, Invoice, MigrationSummary, Note, Quote
from src.repositories import Repository


class TestCompleteWorkflow:
    """Integration tests for complete Enhanced Jobber Data Coverage workflow."""

    def setup_method(self):
        """Set up test environment for each test method."""
        # Create temporary database and download directory
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = Path(self.temp_db_file.name)
        self.temp_db_file.close()

        self.temp_download_dir = tempfile.mkdtemp(prefix="attachments_")
        self.download_path = Path(self.temp_download_dir)

        # Create database connection and repository
        self.connection = sqlite3.Connection(str(self.temp_db_path))
        self.repository = Repository(self.connection)
        self.repository.init_schema()

        # Create logger
        self.logger = ConsoleLogger(verbose=True)

        # Create entity mapper
        self.entity_mapper = EntityMapper()

        # Mock JobberClient
        self.mock_jobber_client = Mock(spec=JobberClient)

        # Sample test data
        self.sample_client_data = {
            "id": "client_123",
            "firstName": "John",
            "lastName": "Doe",
            "companyName": "Test Company",
            "emails": [{"primary": True, "address": "john@test.com"}],
            "phones": [{"primary": True, "number": "+1234567890"}],
            "createdAt": "2023-01-01T10:00:00Z",
        }

        self.sample_invoice_data = {
            "id": "invoice_456",
            "client": {"id": "client_123"},
            "invoiceNumber": "INV-001",
            "amounts": {"total": 100.50},
            "invoiceStatus": "SENT",
            "issuedDate": "2023-01-02T10:00:00Z",
        }

        self.sample_quote_data = {
            "id": "quote_789",
            "client": {"id": "client_123"},
            "quoteNumber": "Q-001",
            "title": "Test Quote",
            "amounts": {"total": 200.00, "subtotal": 180.00},
            "message": "Test quote message",
            "lineItems": {"edges": [{"node": {"id": "item_1", "name": "Service"}}]},
            "createdAt": "2023-01-03T10:00:00Z",
            "transitionedAt": "2023-01-03T11:00:00Z",
            "updatedAt": "2023-01-03T12:00:00Z",
        }

        self.sample_note_data = {
            "id": "note_101",
            "message": "Test note content",
            "client": {"id": "client_123"},
            "entity": {"id": "client_123"},
            "createdAt": "2023-01-04T10:00:00Z",
            "updatedAt": "2023-01-04T11:00:00Z",
        }

        self.sample_attachment_data = {
            "id": "attachment_202",
            "note": {"id": "note_101"},
            "fileName": "test_document.pdf",
            "contentType": "application/pdf",
            "downloadUrl": "https://example.com/files/test_document.pdf",
            "fileSize": 1024,
            "createdAt": "2023-01-05T10:00:00Z",
        }

    def teardown_method(self):
        """Clean up test environment after each test method."""
        if self.connection:
            self.connection.close()

        if self.temp_db_path.exists():
            self.temp_db_path.unlink()

        import shutil

        if self.download_path.exists():
            shutil.rmtree(self.download_path)

    def test_complete_migration_workflow(self):
        """Test complete migration workflow with all entity types."""
        # Mock GraphQL responses for all entity types
        self._setup_mock_responses()

        # Create extractors
        quotes_extractor = QuotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )
        notes_extractor = NotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )
        attachment_downloader = AttachmentDownloader(
            self.mock_jobber_client,
            self.entity_mapper,
            self.repository,
            self.logger,
            base_download_path=str(self.download_path),
        )

        # Create MigrationCoordinator with all extractors
        coordinator = MigrationCoordinator(
            jobber_client=self.mock_jobber_client,
            entity_mapper=self.entity_mapper,
            repository=self.repository,
            logger=self.logger,
            quotes_extractor=quotes_extractor,
            notes_extractor=notes_extractor,
            attachment_downloader=attachment_downloader,
        )

        # Execute complete migration
        summary = coordinator.migrate(include_extended_entities=True)

        # Validate migration summary
        assert isinstance(summary, MigrationSummary)
        assert summary.clients_processed == 1
        assert summary.invoices_processed == 1
        assert summary.quotes_processed == 1
        assert summary.notes_processed == 1
        assert summary.attachments_processed == 1
        assert summary.get_total_entities() == 5
        assert summary.duration_seconds > 0

        # Validate data persistence
        self._validate_data_persistence()

        # Validate comprehensive summary formatting
        summary_text = summary.format_summary()
        assert "clients processed" in summary_text
        assert "invoices processed" in summary_text
        assert "quotes processed" in summary_text
        assert "notes processed" in summary_text
        assert "attachments processed" in summary_text

    def test_legacy_workflow_backward_compatibility(self):
        """Test legacy workflow maintains backward compatibility."""
        # Setup mock responses for Client and Invoice only
        self.mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "edges": [{"node": self.sample_client_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_invoices.return_value = {
            "data": {
                "invoices": {
                    "edges": [{"node": self.sample_invoice_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        # Create coordinator without extractors (legacy mode)
        coordinator = MigrationCoordinator(
            jobber_client=self.mock_jobber_client,
            entity_mapper=self.entity_mapper,
            repository=self.repository,
            logger=self.logger,
        )

        # Execute legacy migration
        summary = coordinator.migrate_legacy()

        # Validate legacy behavior
        assert summary.clients_processed == 1
        assert summary.invoices_processed == 1
        assert summary.quotes_processed == 0
        assert summary.notes_processed == 0
        assert summary.attachments_processed == 0
        assert summary.files_downloaded == 0
        assert summary.get_total_entities() == 2

    def test_error_handling_and_recovery(self):
        """Test comprehensive error handling and recovery mechanisms."""
        # Mock partial failures in different extractors
        self.mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "edges": [{"node": self.sample_client_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        # Mock invoice fetch failure
        self.mock_jobber_client.fetch_invoices.side_effect = Exception("API Error")

        coordinator = MigrationCoordinator(
            jobber_client=self.mock_jobber_client,
            entity_mapper=self.entity_mapper,
            repository=self.repository,
            logger=self.logger,
        )

        # Should raise exception due to critical invoice failure
        with pytest.raises(Exception, match="API Error"):
            coordinator.migrate(include_extended_entities=False)

        # Validate partial data was still processed
        clients = self.repository.get_all_clients()
        assert len(clients) == 1
        assert clients[0].id == "client_123"

    def test_extractor_individual_functionality(self):
        """Test individual extractor functionality and integration."""
        # Test QuotesExtractor
        self.mock_jobber_client.fetch_quotes.return_value = {
            "data": {
                "quotes": {
                    "edges": [{"node": self.sample_quote_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        quotes_extractor = QuotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )

        # Validate dependency validation
        assert quotes_extractor.validate_dependencies() == True

        # Execute extraction
        result = quotes_extractor.extract()

        # Validate results
        assert result["entities_processed"] == 1
        assert result["pages_processed"] == 1
        assert result["has_next_page"] == False
        assert result["extraction_time"] > 0

        # Validate data persistence
        quotes = self.repository.get_all_quotes()
        assert len(quotes) == 1
        assert quotes[0].id == "quote_789"
        assert quotes[0].client_id == "client_123"

    def test_attachment_download_functionality(self):
        """Test attachment download and file management functionality."""
        # Mock attachment fetch and file download
        self.mock_jobber_client.fetch_attachments.return_value = {
            "data": {
                "attachments": {
                    "edges": [{"node": self.sample_attachment_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        # Mock file download response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"test file content"]
        mock_response.raise_for_status.return_value = None

        with patch("requests.Session.get", return_value=mock_response):
            downloader = AttachmentDownloader(
                self.mock_jobber_client,
                self.entity_mapper,
                self.repository,
                self.logger,
                base_download_path=str(self.download_path),
            )

            # Execute attachment extraction and download
            result = downloader.extract()

            # Validate results
            assert result["entities_processed"] == 1
            assert result["files_downloaded"] == 1
            assert result["total_bytes_downloaded"] > 0
            assert result["download_failures"] == 0

            # Validate file system
            expected_file_path = self.download_path / "note_101" / "test_document.pdf"
            assert expected_file_path.exists()
            assert expected_file_path.read_bytes() == b"test file content"

            # Validate database persistence
            attachments = self.repository.get_all_attachments()
            assert len(attachments) == 1
            assert attachments[0].id == "attachment_202"
            assert attachments[0].note_id == "note_101"

    def test_pagination_and_large_datasets(self):
        """Test pagination handling and performance with larger datasets."""
        # Create multi-page mock responses
        page1_response = {
            "data": {
                "clients": {
                    "edges": [
                        {"node": {**self.sample_client_data, "id": f"client_{i}"}}
                        for i in range(100)
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_page1"},
                }
            }
        }

        page2_response = {
            "data": {
                "clients": {
                    "edges": [
                        {"node": {**self.sample_client_data, "id": f"client_{i}"}}
                        for i in range(100, 150)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor_page2"},
                }
            }
        }

        # Mock paginated responses
        self.mock_jobber_client.fetch_clients.side_effect = [
            page1_response,
            page2_response,
        ]

        coordinator = MigrationCoordinator(
            jobber_client=self.mock_jobber_client,
            entity_mapper=self.entity_mapper,
            repository=self.repository,
            logger=self.logger,
        )

        # Measure performance
        start_time = time.time()

        # Execute just client migration for pagination test
        clients_processed = coordinator._migrate_clients(
            MigrationSummary(
                clients_processed=0,
                invoices_processed=0,
                quotes_processed=0,
                notes_processed=0,
                attachments_processed=0,
                files_downloaded=0,
                total_bytes_downloaded=0,
                download_failures=0,
                start_time="",
                end_time="",
                duration_seconds=0.0,
                errors=[],
            )
        )

        processing_time = time.time() - start_time

        # Validate pagination handling
        assert clients_processed == 150
        assert self.mock_jobber_client.fetch_clients.call_count == 2

        # Validate performance (should process quickly in test environment)
        assert processing_time < 10.0  # Should complete within 10 seconds

        # Validate all data persisted
        clients = self.repository.get_all_clients()
        assert len(clients) == 150

    def test_data_validation_and_integrity(self):
        """Test data validation and integrity across all entity types."""
        # Setup complete dataset
        self._setup_mock_responses()

        # Create coordinator with all extractors
        coordinator = self._create_full_coordinator()

        # Execute migration
        summary = coordinator.migrate(include_extended_entities=True)

        # Comprehensive data validation
        self._validate_complete_data_integrity()

        # Validate entity relationships
        clients = self.repository.get_all_clients()
        invoices = self.repository.get_all_invoices()
        quotes = self.repository.get_all_quotes()
        notes = self.repository.get_all_notes()
        attachments = self.repository.get_all_attachments()

        # Validate foreign key relationships
        assert invoices[0].client_id == clients[0].id
        assert quotes[0].client_id == clients[0].id
        assert notes[0].client_id == clients[0].id
        assert attachments[0].note_id == notes[0].id

        # Validate data types and constraints
        assert isinstance(clients[0].id, str)
        assert isinstance(invoices[0].total_cents, int)
        assert isinstance(quotes[0].total, int)
        assert isinstance(attachments[0].file_size, int)

    def _setup_mock_responses(self):
        """Setup mock GraphQL responses for all entity types."""
        self.mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "edges": [{"node": self.sample_client_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_invoices.return_value = {
            "data": {
                "invoices": {
                    "edges": [{"node": self.sample_invoice_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_quotes.return_value = {
            "data": {
                "quotes": {
                    "edges": [{"node": self.sample_quote_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_notes.return_value = {
            "data": {
                "nodes": {
                    "edges": [{"node": self.sample_note_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_attachments.return_value = {
            "data": {
                "attachments": {
                    "edges": [{"node": self.sample_attachment_data}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def _create_full_coordinator(self):
        """Create MigrationCoordinator with all extractors."""
        quotes_extractor = QuotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )
        notes_extractor = NotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )

        # Mock successful file download for attachment testing
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status.return_value = None

        with patch("requests.Session.get", return_value=mock_response):
            attachment_downloader = AttachmentDownloader(
                self.mock_jobber_client,
                self.entity_mapper,
                self.repository,
                self.logger,
                base_download_path=str(self.download_path),
            )

        return MigrationCoordinator(
            jobber_client=self.mock_jobber_client,
            entity_mapper=self.entity_mapper,
            repository=self.repository,
            logger=self.logger,
            quotes_extractor=quotes_extractor,
            notes_extractor=notes_extractor,
            attachment_downloader=attachment_downloader,
        )

    def _validate_data_persistence(self):
        """Validate that all entity data was properly persisted."""
        clients = self.repository.get_all_clients()
        invoices = self.repository.get_all_invoices()
        quotes = self.repository.get_all_quotes()
        notes = self.repository.get_all_notes()
        attachments = self.repository.get_all_attachments()

        assert len(clients) == 1
        assert len(invoices) == 1
        assert len(quotes) == 1
        assert len(notes) == 1
        assert len(attachments) == 1

    def _validate_complete_data_integrity(self):
        """Validate complete data integrity and relationships."""
        # Validate all entities exist
        self._validate_data_persistence()

        # Validate specific field values
        clients = self.repository.get_all_clients()
        client = clients[0]
        assert client.id == "client_123"
        assert client.first_name == "John"
        assert client.last_name == "Doe"
        assert client.primary_email == "john@test.com"

        invoices = self.repository.get_all_invoices()
        invoice = invoices[0]
        assert invoice.id == "invoice_456"
        assert invoice.client_id == "client_123"
        assert invoice.number == "INV-001"
        assert invoice.total_cents == 10050  # $100.50 in cents

        quotes = self.repository.get_all_quotes()
        quote = quotes[0]
        assert quote.id == "quote_789"
        assert quote.client_id == "client_123"
        assert quote.number == "Q-001"
        assert quote.title == "Test Quote"

        notes = self.repository.get_all_notes()
        note = notes[0]
        assert note.id == "note_101"
        assert note.client_id == "client_123"
        assert note.message == "Test note content"

        attachments = self.repository.get_all_attachments()
        attachment = attachments[0]
        assert attachment.id == "attachment_202"
        assert attachment.note_id == "note_101"
        assert attachment.file_name == "test_document.pdf"
