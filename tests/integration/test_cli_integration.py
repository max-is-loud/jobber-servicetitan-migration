"""CLI integration tests for Enhanced Jobber Data Coverage commands.

Tests all CLI commands including migrate, fetch-quotes, fetch-notes, and
fetch-attachments to ensure complete command-line interface functionality.
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.cli import _execute_entity_extraction
from src.repositories import Repository


class TestCLIIntegration:
    """Integration tests for CLI command functionality."""

    def setup_method(self):
        """Set up test environment for each CLI test."""
        # Create temporary database
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = Path(self.temp_db_file.name)
        self.temp_db_file.close()

        # Create temporary download directory
        self.temp_download_dir = tempfile.mkdtemp(prefix="cli_attachments_")
        self.download_path = Path(self.temp_download_dir)

        # Sample test data for CLI responses
        self.sample_quote_response = {
            "data": {
                "quotes": {
                    "edges": [
                        {
                            "node": {
                                "id": "quote_cli_123",
                                "client": {"id": "client_456"},
                                "quoteNumber": "CLI-Q-001",
                                "title": "CLI Test Quote",
                                "amounts": {"total": 150.00, "subtotal": 135.00},
                                "message": "CLI test quote message",
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

        self.sample_note_response = {
            "data": {
                "nodes": {
                    "edges": [
                        {
                            "node": {
                                "id": "note_cli_789",
                                "message": "CLI test note content",
                                "client": {"id": "client_456"},
                                "entity": {"id": "client_456"},
                                "createdAt": "2023-01-01T10:00:00Z",
                                "updatedAt": "2023-01-01T11:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

        self.sample_attachment_response = {
            "data": {
                "attachments": {
                    "edges": [
                        {
                            "node": {
                                "id": "attachment_cli_101",
                                "note": {"id": "note_cli_789"},
                                "fileName": "cli_test_file.pdf",
                                "contentType": "application/pdf",
                                "downloadUrl": "https://example.com/files/cli_test_file.pdf",
                                "fileSize": 2048,
                                "createdAt": "2023-01-01T10:00:00Z",
                            }
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    def teardown_method(self):
        """Clean up test environment after each CLI test."""
        if self.temp_db_path.exists():
            self.temp_db_path.unlink()

        import shutil

        if self.download_path.exists():
            shutil.rmtree(self.download_path)

    @patch("src.cli.AuthProvider")
    @patch("src.cli.OAuth2Manager")
    @patch("src.cli.JobberClient")
    @patch("src.cli.RateLimitedHttpClient")
    def test_fetch_quotes_command(
        self,
        mock_rate_limited_client,
        mock_jobber_client,
        mock_oauth_manager,
        mock_auth_provider,
    ):
        """Test fetch-quotes CLI command functionality."""
        # Setup mocks
        mock_jobber_instance = Mock()
        mock_jobber_instance.fetch_quotes.return_value = self.sample_quote_response
        mock_jobber_client.return_value = mock_jobber_instance

        # Mock authentication components
        mock_auth_provider.get_oauth2_config.return_value = (
            "client_id",
            "client_secret",
            "redirect_uri",
        )

        # Test the CLI execution function directly
        with patch("sys.exit") as mock_exit:
            _execute_entity_extraction(
                entity_type="quotes", db=self.temp_db_path, verbose=True, page_limit=1
            )

            # Verify successful exit
            mock_exit.assert_called_with(0)

        # Validate data was persisted
        connection = sqlite3.Connection(str(self.temp_db_path))
        repository = Repository(connection)
        quotes = repository.get_all_quotes()

        assert len(quotes) == 1
        assert quotes[0].id == "quote_cli_123"
        assert quotes[0].quote_number == "CLI-Q-001"
        assert quotes[0].title == "CLI Test Quote"

        connection.close()

    @patch("src.cli.AuthProvider")
    @patch("src.cli.OAuth2Manager")
    @patch("src.cli.JobberClient")
    @patch("src.cli.RateLimitedHttpClient")
    def test_fetch_notes_command(
        self,
        mock_rate_limited_client,
        mock_jobber_client,
        mock_oauth_manager,
        mock_auth_provider,
    ):
        """Test fetch-notes CLI command functionality."""
        # Setup mocks
        mock_jobber_instance = Mock()
        mock_jobber_instance.fetch_notes.return_value = self.sample_note_response
        mock_jobber_client.return_value = mock_jobber_instance

        # Mock authentication components
        mock_auth_provider.get_oauth2_config.return_value = (
            "client_id",
            "client_secret",
            "redirect_uri",
        )

        # Test the CLI execution function
        with patch("sys.exit") as mock_exit:
            _execute_entity_extraction(
                entity_type="notes", db=self.temp_db_path, verbose=True, page_limit=1
            )

            # Verify successful exit
            mock_exit.assert_called_with(0)

        # Validate data was persisted
        connection = sqlite3.Connection(str(self.temp_db_path))
        repository = Repository(connection)
        notes = repository.get_all_notes()

        assert len(notes) == 1
        assert notes[0].id == "note_cli_789"
        assert notes[0].message == "CLI test note content"

        connection.close()

    @patch("src.cli.AuthProvider")
    @patch("src.cli.OAuth2Manager")
    @patch("src.cli.JobberClient")
    @patch("src.cli.RateLimitedHttpClient")
    @patch("requests.Session.get")
    def test_fetch_attachments_command(
        self,
        mock_requests_get,
        mock_rate_limited_client,
        mock_jobber_client,
        mock_oauth_manager,
        mock_auth_provider,
    ):
        """Test fetch-attachments CLI command with file downloads."""
        # Setup mocks
        mock_jobber_instance = Mock()
        mock_jobber_instance.fetch_attachments.return_value = (
            self.sample_attachment_response
        )
        mock_jobber_client.return_value = mock_jobber_instance

        # Mock authentication components
        mock_auth_provider.get_oauth2_config.return_value = (
            "client_id",
            "client_secret",
            "redirect_uri",
        )

        # Mock file download
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"CLI test file content"]
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        # Test the CLI execution function
        with patch("sys.exit") as mock_exit:
            _execute_entity_extraction(
                entity_type="attachments",
                db=self.temp_db_path,
                verbose=True,
                page_limit=1,
                download_path=str(self.download_path),
            )

            # Verify successful exit
            mock_exit.assert_called_with(0)

        # Validate data was persisted
        connection = sqlite3.Connection(str(self.temp_db_path))
        repository = Repository(connection)
        attachments = repository.get_all_attachments()

        assert len(attachments) == 1
        assert attachments[0].id == "attachment_cli_101"
        assert attachments[0].file_name == "cli_test_file.pdf"

        # Validate file was downloaded
        expected_file = self.download_path / "note_cli_789" / "cli_test_file.pdf"
        assert expected_file.exists()
        assert expected_file.read_bytes() == b"CLI test file content"

        connection.close()

    @patch("src.cli.AuthProvider")
    def test_cli_error_handling(self, mock_auth_provider):
        """Test CLI error handling for configuration errors."""
        # Mock authentication failure
        mock_auth_provider.get_oauth2_config.side_effect = Exception(
            "Auth config error"
        )

        # Test configuration error handling
        with patch("sys.exit") as mock_exit:
            with patch("typer.echo") as mock_echo:
                _execute_entity_extraction(
                    entity_type="quotes", db=self.temp_db_path, verbose=True
                )

                # Verify error exit code
                mock_exit.assert_called_with(1)

                # Verify error message was displayed
                error_calls = [
                    call
                    for call in mock_echo.call_args_list
                    if "Configuration Error" in str(call)
                ]
                assert len(error_calls) > 0

    def test_cli_parameter_validation(self):
        """Test CLI parameter validation and edge cases."""
        # Test with invalid entity type
        with pytest.raises(ValueError, match="Unsupported entity type"):
            _execute_entity_extraction(
                entity_type="invalid_type", db=self.temp_db_path, verbose=False
            )

        # Test with non-existent download path for attachments
        non_existent_path = "/non/existent/path"

        with patch("src.cli.AuthProvider") as mock_auth_provider:
            mock_auth_provider.get_oauth2_config.return_value = (
                "client_id",
                "client_secret",
                "redirect_uri",
            )

            with patch("src.cli.JobberClient") as mock_jobber_client:
                mock_jobber_instance = Mock()
                mock_jobber_instance.fetch_attachments.return_value = (
                    self.sample_attachment_response
                )
                mock_jobber_client.return_value = mock_jobber_instance

                with patch("sys.exit") as mock_exit:
                    # Should still work - AttachmentDownloader creates directories
                    _execute_entity_extraction(
                        entity_type="attachments",
                        db=self.temp_db_path,
                        verbose=False,
                        download_path=non_existent_path,
                    )

                    # Should complete successfully
                    mock_exit.assert_called_with(0)

    @patch("src.cli.AuthProvider")
    @patch("src.cli.OAuth2Manager")
    @patch("src.cli.JobberClient")
    @patch("src.cli.RateLimitedHttpClient")
    def test_cli_progress_reporting(
        self,
        mock_rate_limited_client,
        mock_jobber_client,
        mock_oauth_manager,
        mock_auth_provider,
    ):
        """Test CLI progress reporting and verbose output."""
        # Setup mocks with multiple pages for progress testing
        page1_response = {
            "data": {
                "quotes": {
                    "edges": [
                        {
                            "node": {
                                **self.sample_quote_response["data"]["quotes"]["edges"][
                                    0
                                ]["node"],
                                "id": f"quote_{i}",
                            }
                        }
                        for i in range(3)
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                }
            }
        }

        page2_response = {
            "data": {
                "quotes": {
                    "edges": [
                        {
                            "node": {
                                **self.sample_quote_response["data"]["quotes"]["edges"][
                                    0
                                ]["node"],
                                "id": f"quote_{i}",
                            }
                        }
                        for i in range(3, 5)
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor2"},
                }
            }
        }

        mock_jobber_instance = Mock()
        mock_jobber_instance.fetch_quotes.side_effect = [page1_response, page2_response]
        mock_jobber_client.return_value = mock_jobber_instance

        # Mock authentication
        mock_auth_provider.get_oauth2_config.return_value = (
            "client_id",
            "client_secret",
            "redirect_uri",
        )

        # Capture logger output
        with patch("src.cli.ConsoleLogger") as mock_logger_class:
            mock_logger = Mock()
            mock_logger_class.return_value = mock_logger

            with patch("sys.exit"):
                _execute_entity_extraction(
                    entity_type="quotes",
                    db=self.temp_db_path,
                    verbose=True,
                    page_limit=2,
                )

            # Verify progress logging was called
            logger_calls = mock_logger.info.call_args_list
            progress_calls = [
                call
                for call in logger_calls
                if "quotes extraction" in str(call).lower()
            ]
            assert len(progress_calls) > 0

            # Verify summary logging
            summary_calls = [
                call for call in logger_calls if "completed" in str(call).lower()
            ]
            assert len(summary_calls) > 0
