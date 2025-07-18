"""PRD validation tests for Enhanced Jobber Data Coverage implementation.

Comprehensive tests validating that the implementation meets all PRD requirements
including data coverage, performance benchmarks, and production readiness criteria.
"""

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.clients import JobberClient
from src.coordinators import MigrationCoordinator
from src.extractors import AttachmentDownloader, NotesExtractor, QuotesExtractor
from src.loggers import ConsoleLogger
from src.mappers import EntityMapper
from src.models import MigrationSummary
from src.repositories import Repository


class TestPRDValidation:
    """PRD validation tests ensuring complete requirements compliance."""

    def setup_method(self):
        """Set up comprehensive test environment for PRD validation."""
        # Create temporary database and files
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = Path(self.temp_db_file.name)
        self.temp_db_file.close()

        self.temp_download_dir = tempfile.mkdtemp(prefix="prd_attachments_")
        self.download_path = Path(self.temp_download_dir)

        # Create test environment
        self.connection = sqlite3.Connection(str(self.temp_db_path))
        self.repository = Repository(self.connection)
        self.repository.init_schema()
        self.logger = ConsoleLogger(verbose=True)
        self.entity_mapper = EntityMapper()

        # Mock JobberClient for PRD validation
        self.mock_jobber_client = Mock(spec=JobberClient)

    def teardown_method(self):
        """Clean up PRD test environment."""
        if self.connection:
            self.connection.close()
        if self.temp_db_path.exists():
            self.temp_db_path.unlink()
        import shutil

        if self.download_path.exists():
            shutil.rmtree(self.download_path)

    def test_prd_day_1_3_basic_entity_coverage(self):
        """Test PRD Day 1-3: Basic entity coverage with Client and Invoice."""
        # Mock basic entity responses
        self.mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "edges": [
                        {
                            "node": {
                                "id": "client_prd_1",
                                "firstName": "Alice",
                                "lastName": "Johnson",
                                "companyName": "PRD Test Corp",
                                "emails": [
                                    {"primary": True, "address": "alice@prdtest.com"}
                                ],
                                "phones": [{"primary": True, "number": "+1555123456"}],
                                "createdAt": "2023-01-01T10:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_invoices.return_value = {
            "data": {
                "invoices": {
                    "edges": [
                        {
                            "node": {
                                "id": "invoice_prd_1",
                                "client": {"id": "client_prd_1"},
                                "invoiceNumber": "PRD-INV-001",
                                "amounts": {"total": 500.00},
                                "invoiceStatus": "SENT",
                                "issuedDate": "2023-01-02T10:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        # Create basic coordinator (legacy mode)
        coordinator = MigrationCoordinator(
            jobber_client=self.mock_jobber_client,
            entity_mapper=self.entity_mapper,
            repository=self.repository,
            logger=self.logger,
        )

        # Execute basic migration
        summary = coordinator.migrate_legacy()

        # PRD Day 1-3 validation
        assert summary.clients_processed >= 1, "PRD Day 1: Client extraction failed"
        assert summary.invoices_processed >= 1, "PRD Day 3: Invoice extraction failed"
        assert (
            len(summary.errors) == 0
        ), "PRD Day 1-3: No errors allowed in basic workflow"

        # Validate data quality
        clients = self.repository.get_all_clients()
        invoices = self.repository.get_all_invoices()

        assert len(clients) == 1
        assert len(invoices) == 1
        assert clients[0].id == "client_prd_1"
        assert invoices[0].client_id == clients[0].id

        print("✅ PRD Day 1-3: Basic entity coverage validated")

    def test_prd_day_5_quote_note_integration(self):
        """Test PRD Day 5: Quote and Note entity integration."""
        # Mock extended entity responses
        self._setup_extended_mock_responses()

        # Create extractors for quotes and notes
        quotes_extractor = QuotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )
        notes_extractor = NotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )

        # Create coordinator with extended extractors
        coordinator = MigrationCoordinator(
            jobber_client=self.mock_jobber_client,
            entity_mapper=self.entity_mapper,
            repository=self.repository,
            logger=self.logger,
            quotes_extractor=quotes_extractor,
            notes_extractor=notes_extractor,
        )

        # Execute migration with extended entities
        summary = coordinator.migrate(include_extended_entities=True)

        # PRD Day 5 validation
        assert summary.quotes_processed >= 1, "PRD Day 5: Quote extraction failed"
        assert summary.notes_processed >= 1, "PRD Day 5: Note extraction failed"
        assert (
            summary.get_total_entities() >= 4
        ), "PRD Day 5: Insufficient entity coverage"

        # Validate entity relationships
        quotes = self.repository.get_all_quotes()
        notes = self.repository.get_all_notes()
        clients = self.repository.get_all_clients()

        assert len(quotes) >= 1
        assert len(notes) >= 1
        assert quotes[0].client_id in [c.id for c in clients]
        assert notes[0].client_id in [c.id for c in clients]

        print("✅ PRD Day 5: Quote and Note integration validated")

    def test_prd_day_5_attachment_file_management(self):
        """Test PRD Day 5: Attachment file downloads and management."""
        # Setup attachment mock responses
        self._setup_attachment_mock_responses()

        # Mock file download
        mock_response = Mock()
        mock_response.iter_content.return_value = [
            b"PRD test file content for validation"
        ]
        mock_response.raise_for_status.return_value = None

        with patch("requests.Session.get", return_value=mock_response):
            attachment_downloader = AttachmentDownloader(
                self.mock_jobber_client,
                self.entity_mapper,
                self.repository,
                self.logger,
                base_download_path=str(self.download_path),
            )

            # Execute attachment extraction
            result = attachment_downloader.extract()

            # PRD Day 5 attachment validation
            assert (
                result["entities_processed"] >= 1
            ), "PRD Day 5: Attachment extraction failed"
            assert result["files_downloaded"] >= 1, "PRD Day 5: File download failed"
            assert (
                result["total_bytes_downloaded"] > 0
            ), "PRD Day 5: No bytes downloaded"
            assert (
                result["download_failures"] == 0
            ), "PRD Day 5: Download failures not allowed"

            # Validate file organization
            attachments = self.repository.get_all_attachments()
            assert len(attachments) >= 1

            # Validate file system organization (./attachments/{note_id}/{filename})
            note_id = attachments[0].note_id
            filename = attachments[0].file_name
            expected_file = self.download_path / note_id / filename

            assert (
                expected_file.exists()
            ), "PRD Day 5: File not downloaded to expected location"
            assert expected_file.read_bytes() == b"PRD test file content for validation"

        print("✅ PRD Day 5: Attachment file management validated")

    def test_prd_day_10_cli_interface_coverage(self):
        """Test PRD Day 10: Complete CLI interface coverage."""
        from src.cli import _execute_entity_extraction

        # Test all entity-specific CLI commands exist and function
        entity_types = ["quotes", "notes", "attachments"]

        for entity_type in entity_types:
            # Mock appropriate responses
            self._setup_cli_mock_responses(entity_type)

            with patch("src.cli.AuthProvider") as mock_auth:
                mock_auth.get_oauth2_config.return_value = (
                    "client_id",
                    "client_secret",
                    "redirect_uri",
                )

                with patch(
                    "src.cli.JobberClient", return_value=self.mock_jobber_client
                ):
                    with patch("src.cli.RateLimitedHttpClient"):
                        with patch("sys.exit") as mock_exit:
                            if entity_type == "attachments":
                                with patch("requests.Session.get") as mock_get:
                                    mock_response = Mock()
                                    mock_response.iter_content.return_value = [b"test"]
                                    mock_response.raise_for_status.return_value = None
                                    mock_get.return_value = mock_response

                                    _execute_entity_extraction(
                                        entity_type=entity_type,
                                        db=self.temp_db_path,
                                        verbose=False,
                                        page_limit=1,
                                    )
                            else:
                                _execute_entity_extraction(
                                    entity_type=entity_type,
                                    db=self.temp_db_path,
                                    verbose=False,
                                    page_limit=1,
                                )

                            # Verify successful execution
                            mock_exit.assert_called_with(0)

        print("✅ PRD Day 10: CLI interface coverage validated")

    def test_prd_day_12_unified_workflow_orchestration(self):
        """Test PRD Day 12: Complete unified workflow orchestration."""
        # Setup comprehensive mock responses
        self._setup_comprehensive_mock_responses()

        # Create complete coordinator with all extractors
        coordinator = self._create_complete_coordinator()

        # Execute complete unified workflow
        start_time = time.time()
        summary = coordinator.migrate(include_extended_entities=True)
        execution_time = time.time() - start_time

        # PRD Day 12 validation - unified workflow
        assert summary.clients_processed >= 1, "PRD Day 12: Client processing failed"
        assert summary.invoices_processed >= 1, "PRD Day 12: Invoice processing failed"
        assert summary.quotes_processed >= 1, "PRD Day 12: Quote processing failed"
        assert summary.notes_processed >= 1, "PRD Day 12: Note processing failed"
        assert (
            summary.attachments_processed >= 1
        ), "PRD Day 12: Attachment processing failed"
        assert summary.files_downloaded >= 1, "PRD Day 12: File download failed"

        # Validate complete entity coverage
        total_entities = summary.get_total_entities()
        assert (
            total_entities >= 5
        ), f"PRD Day 12: Insufficient entities processed: {total_entities}"

        # Validate comprehensive summary formatting
        summary_text = summary.format_summary()
        required_terms = [
            "clients",
            "invoices",
            "quotes",
            "notes",
            "attachments",
            "files downloaded",
        ]
        for term in required_terms:
            assert term in summary_text, f"PRD Day 12: Summary missing {term}"

        # Performance validation (should complete within reasonable time)
        assert execution_time < 5.0, f"PRD Day 12: Workflow too slow: {execution_time}s"

        print("✅ PRD Day 12: Unified workflow orchestration validated")

    def test_prd_day_13_production_readiness(self):
        """Test PRD Day 13: Production readiness and data validation."""
        # Setup production-like test environment
        self._setup_production_like_environment()

        # Create production-ready coordinator
        coordinator = self._create_complete_coordinator()

        # Execute production workflow simulation
        summary = coordinator.migrate(include_extended_entities=True)

        # PRD Day 13 production readiness validation

        # 1. Data integrity validation
        self._validate_production_data_integrity()

        # 2. Error handling robustness
        assert (
            len(summary.errors) == 0
        ), "PRD Day 13: Production workflow must be error-free"

        # 3. Performance benchmarks
        assert (
            summary.duration_seconds < 10.0
        ), "PRD Day 13: Production performance requirements not met"

        # 4. Complete entity coverage
        assert (
            summary.get_total_entities() >= 5
        ), "PRD Day 13: Incomplete entity coverage"

        # 5. File management validation
        assert (
            summary.files_downloaded > 0
        ), "PRD Day 13: File download functionality missing"
        assert (
            summary.download_failures == 0
        ), "PRD Day 13: Download failures in production"

        # 6. Database schema validation
        self._validate_database_schema_compliance()

        # 7. Comprehensive summary reporting
        summary_text = summary.format_summary()
        assert len(summary_text) > 100, "PRD Day 13: Insufficient summary detail"

        print("✅ PRD Day 13: Production readiness validated")

    def test_prd_success_criteria_compliance(self):
        """Test complete PRD success criteria compliance."""
        # Execute comprehensive test covering all PRD requirements
        self._setup_comprehensive_mock_responses()
        coordinator = self._create_complete_coordinator()

        # Measure complete workflow
        start_time = time.time()
        summary = coordinator.migrate(include_extended_entities=True)
        total_time = time.time() - start_time

        # PRD Success Criteria Validation
        success_criteria = {
            "Entity Coverage": summary.get_total_entities() >= 5,
            "Client Processing": summary.clients_processed >= 1,
            "Invoice Processing": summary.invoices_processed >= 1,
            "Quote Processing": summary.quotes_processed >= 1,
            "Note Processing": summary.notes_processed >= 1,
            "Attachment Processing": summary.attachments_processed >= 1,
            "File Downloads": summary.files_downloaded >= 1,
            "Error-Free Execution": len(summary.errors) == 0,
            "Performance Target": total_time < 10.0,
            "Data Integrity": self._check_data_relationships(),
            "Schema Compliance": self._check_schema_compliance(),
        }

        # Report success criteria results
        print("\n🎯 PRD Success Criteria Results:")
        all_passed = True
        for criterion, passed in success_criteria.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {criterion}: {status}")
            if not passed:
                all_passed = False

        assert all_passed, "PRD Success Criteria not fully met"
        print("\n🚀 All PRD Success Criteria PASSED - Production Ready!")

    def _setup_extended_mock_responses(self):
        """Setup mock responses for extended entities (quotes, notes)."""
        self.mock_jobber_client.fetch_clients.return_value = {
            "data": {
                "clients": {
                    "edges": [
                        {
                            "node": {
                                "id": "client_ext_1",
                                "firstName": "Extended",
                                "lastName": "Test",
                                "companyName": "Ext Corp",
                                "emails": [
                                    {"primary": True, "address": "ext@test.com"}
                                ],
                                "phones": [{"primary": True, "number": "+1555000001"}],
                                "createdAt": "2023-01-01T10:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_invoices.return_value = {
            "data": {
                "invoices": {
                    "edges": [
                        {
                            "node": {
                                "id": "invoice_ext_1",
                                "client": {"id": "client_ext_1"},
                                "invoiceNumber": "EXT-INV-001",
                                "amounts": {"total": 300.00},
                                "invoiceStatus": "SENT",
                                "issuedDate": "2023-01-02T10:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_quotes.return_value = {
            "data": {
                "quotes": {
                    "edges": [
                        {
                            "node": {
                                "id": "quote_ext_1",
                                "client": {"id": "client_ext_1"},
                                "quoteNumber": "EXT-Q-001",
                                "title": "Extended Quote",
                                "amounts": {"total": 400.00, "subtotal": 360.00},
                                "message": "Extended test quote",
                                "lineItems": {"edges": []},
                                "createdAt": "2023-01-03T10:00:00Z",
                                "transitionedAt": "2023-01-03T11:00:00Z",
                                "updatedAt": "2023-01-03T12:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.mock_jobber_client.fetch_notes.return_value = {
            "data": {
                "nodes": {
                    "edges": [
                        {
                            "node": {
                                "id": "note_ext_1",
                                "message": "Extended note content",
                                "client": {"id": "client_ext_1"},
                                "entity": {"id": "client_ext_1"},
                                "createdAt": "2023-01-04T10:00:00Z",
                                "updatedAt": "2023-01-04T11:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def _setup_attachment_mock_responses(self):
        """Setup mock responses for attachment testing."""
        # Include basic entities plus attachments
        self._setup_extended_mock_responses()

        self.mock_jobber_client.fetch_attachments.return_value = {
            "data": {
                "attachments": {
                    "edges": [
                        {
                            "node": {
                                "id": "attachment_prd_1",
                                "note": {"id": "note_ext_1"},
                                "fileName": "prd_test_document.pdf",
                                "contentType": "application/pdf",
                                "downloadUrl": "https://example.com/files/prd_test_document.pdf",
                                "fileSize": 4096,
                                "createdAt": "2023-01-05T10:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def _setup_cli_mock_responses(self, entity_type):
        """Setup mock responses for CLI testing."""
        if entity_type == "quotes":
            self.mock_jobber_client.fetch_quotes.return_value = {
                "data": {
                    "quotes": {
                        "edges": [
                            {
                                "node": {
                                    "id": "quote_cli_test",
                                    "client": {"id": "client_123"},
                                    "quoteNumber": "CLI-Q-001",
                                    "title": "CLI Quote",
                                    "amounts": {"total": 100.00, "subtotal": 90.00},
                                    "message": "CLI test",
                                    "lineItems": {"edges": []},
                                    "createdAt": "2023-01-01T10:00:00Z",
                                    "transitionedAt": "2023-01-01T11:00:00Z",
                                    "updatedAt": "2023-01-01T12:00:00Z",
                                }
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        elif entity_type == "notes":
            self.mock_jobber_client.fetch_notes.return_value = {
                "data": {
                    "nodes": {
                        "edges": [
                            {
                                "node": {
                                    "id": "note_cli_test",
                                    "message": "CLI note test",
                                    "client": {"id": "client_123"},
                                    "entity": {"id": "client_123"},
                                    "createdAt": "2023-01-01T10:00:00Z",
                                    "updatedAt": "2023-01-01T11:00:00Z",
                                }
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        elif entity_type == "attachments":
            self.mock_jobber_client.fetch_attachments.return_value = {
                "data": {
                    "attachments": {
                        "edges": [
                            {
                                "node": {
                                    "id": "attachment_cli_test",
                                    "note": {"id": "note_123"},
                                    "fileName": "cli_test.pdf",
                                    "contentType": "application/pdf",
                                    "downloadUrl": "https://example.com/cli_test.pdf",
                                    "fileSize": 1024,
                                    "createdAt": "2023-01-01T10:00:00Z",
                                }
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }

    def _setup_comprehensive_mock_responses(self):
        """Setup comprehensive mock responses for all entities."""
        self._setup_extended_mock_responses()
        self._setup_attachment_mock_responses()

    def _setup_production_like_environment(self):
        """Setup production-like test environment."""
        self._setup_comprehensive_mock_responses()

    def _create_complete_coordinator(self):
        """Create coordinator with all extractors for complete testing."""
        quotes_extractor = QuotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )
        notes_extractor = NotesExtractor(
            self.mock_jobber_client, self.entity_mapper, self.repository, self.logger
        )

        # Mock file download for attachment testing
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"Production test file content"]
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

    def _validate_production_data_integrity(self):
        """Validate production-level data integrity."""
        clients = self.repository.get_all_clients()
        invoices = self.repository.get_all_invoices()
        quotes = self.repository.get_all_quotes()
        notes = self.repository.get_all_notes()
        attachments = self.repository.get_all_attachments()

        # Validate counts
        assert len(clients) >= 1, "Production: No clients found"
        assert len(invoices) >= 1, "Production: No invoices found"
        assert len(quotes) >= 1, "Production: No quotes found"
        assert len(notes) >= 1, "Production: No notes found"
        assert len(attachments) >= 1, "Production: No attachments found"

        # Validate relationships
        client_ids = {c.id for c in clients}
        note_ids = {n.id for n in notes}

        for invoice in invoices:
            assert (
                invoice.client_id in client_ids
            ), f"Production: Orphaned invoice {invoice.id}"

        for quote in quotes:
            assert (
                quote.client_id in client_ids
            ), f"Production: Orphaned quote {quote.id}"

        for note in notes:
            assert note.client_id in client_ids, f"Production: Orphaned note {note.id}"

        for attachment in attachments:
            assert (
                attachment.note_id in note_ids
            ), f"Production: Orphaned attachment {attachment.id}"

    def _validate_database_schema_compliance(self):
        """Validate database schema meets PRD requirements."""
        cursor = self.connection.cursor()

        # Check all required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {
            "clients",
            "invoices",
            "quotes",
            "notes",
            "attachments",
            "oauth_tokens",
        }
        for table in required_tables:
            assert table in tables, f"Production: Missing required table {table}"

        # Validate table schemas have required columns
        for table in ["clients", "invoices", "quotes", "notes", "attachments"]:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in cursor.fetchall()}
            assert "id" in columns, f"Production: Table {table} missing id column"

    def _check_data_relationships(self):
        """Check data relationships are properly maintained."""
        try:
            self._validate_production_data_integrity()
            return True
        except AssertionError:
            return False

    def _check_schema_compliance(self):
        """Check schema compliance with PRD requirements."""
        try:
            self._validate_database_schema_compliance()
            return True
        except AssertionError:
            return False
