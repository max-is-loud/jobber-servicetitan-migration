"""CLI tests for 'migrate download' command.

Tests the download command CLI interface including argument parsing,
validation, error handling, and integration with DownloadModeCoordinator.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app


class TestDownloadCommand:
    """Test suite for 'migrate download' CLI command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    def mock_auth_env(self, monkeypatch):
        """Set up mock authentication environment."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

    # ==================== Help and Basic Usage ====================

    def test_download_command_help(self, runner, mock_auth_env):
        """Test 'migrate download --help' displays command help."""
        result = runner.invoke(app, ["migrate", "download", "--help"])
        assert result.exit_code == 0
        assert "download" in result.stdout.lower()
        assert "--snapshot-id" in result.stdout
        assert "--resume" in result.stdout
        assert "--entity" in result.stdout
        assert "--file-type" in result.stdout
        assert "--min-size" in result.stdout
        assert "--max-size" in result.stdout
        assert "--output-dir" in result.stdout
        assert "--dry-run" in result.stdout

    def test_download_command_in_migrate_help(self, runner):
        """Test that 'download' appears in 'migrate --help'."""
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "download" in result.stdout.lower()

    # ==================== Required Parameters ====================

    def test_download_requires_snapshot_id(self, runner, mock_auth_env):
        """Test that download command requires --snapshot-id parameter."""
        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "download"])
            # Should fail with missing required parameter
            assert result.exit_code != 0

    def test_download_with_snapshot_id(self, runner, mock_auth_env, temp_db):
        """Test download command with valid snapshot-id."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    mock_coordinator.run_download_pass.return_value = {
                        "snapshot_id": "test_snapshot",
                        "total_attachments": 10,
                        "downloaded": 10,
                        "failed": 0,
                        "total_bytes": 10240,
                        "duration": 5.5,
                        "report_markdown": "/tmp/report.md",
                        "report_json": "/tmp/report.json",
                    }

                    result = runner.invoke(
                        app,
                        ["migrate", "download", "--snapshot-id", "test_snapshot", "--db", temp_db],
                    )

                    assert result.exit_code == 0
                    mock_coordinator.run_download_pass.assert_called_once()

    # ==================== Resume Flag ====================

    def test_download_with_resume_flag(self, runner, mock_auth_env, temp_db):
        """Test download command with --resume flag."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    mock_coordinator.run_download_pass.return_value = {
                        "snapshot_id": "test_snapshot",
                        "total_attachments": 5,
                        "downloaded": 3,
                        "failed": 0,
                        "skipped": 2,
                        "total_bytes": 5120,
                        "duration": 2.5,
                        "report_markdown": "/tmp/resume_report.md",
                        "report_json": "/tmp/resume_report.json",
                    }

                    result = runner.invoke(
                        app,
                        [
                            "migrate",
                            "download",
                            "--snapshot-id",
                            "test_snapshot",
                            "--resume",
                            "--db",
                            temp_db,
                        ],
                    )

                    assert result.exit_code == 0
                    # Verify resume=True was passed
                    call_kwargs = mock_coordinator.run_download_pass.call_args[1]
                    assert call_kwargs["resume"] is True

    # ==================== Filter Options ====================

    def test_download_with_entity_filter(self, runner, mock_auth_env, temp_db):
        """Test download command with --entity filter."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    mock_coordinator.run_download_pass.return_value = {
                        "snapshot_id": "test_snapshot",
                        "total_attachments": 3,
                        "downloaded": 3,
                        "failed": 0,
                        "total_bytes": 3072,
                        "duration": 1.5,
                        "report_markdown": "/tmp/filtered_report.md",
                        "report_json": "/tmp/filtered_report.json",
                    }

                    result = runner.invoke(
                        app,
                        [
                            "migrate",
                            "download",
                            "--snapshot-id",
                            "test_snapshot",
                            "--entity",
                            "clients",
                            "--entity",
                            "invoices",
                            "--db",
                            temp_db,
                        ],
                    )

                    assert result.exit_code == 0
                    # Verify entity_types filter was passed
                    call_kwargs = mock_coordinator.run_download_pass.call_args[1]
                    assert call_kwargs["entity_types"] == ["clients", "invoices"]

    def test_download_with_file_type_filter(self, runner, mock_auth_env, temp_db):
        """Test download command with --file-type filter."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    with patch("src.models.download_filters.DownloadFilters") as mock_filters_class:
                        # Setup mocks
                        mock_repo = Mock()
                        mock_repo_factory.return_value = mock_repo

                        mock_coordinator = Mock()
                        mock_coordinator_class.return_value = mock_coordinator
                        mock_coordinator.run_download_pass.return_value = {
                            "snapshot_id": "test_snapshot",
                            "total_attachments": 5,
                            "downloaded": 5,
                            "failed": 0,
                            "total_bytes": 5120,
                            "duration": 2.0,
                            "report_markdown": "/tmp/pdf_report.md",
                            "report_json": "/tmp/pdf_report.json",
                        }

                        result = runner.invoke(
                            app,
                            [
                                "migrate",
                                "download",
                                "--snapshot-id",
                                "test_snapshot",
                                "--file-type",
                                "pdf",
                                "--file-type",
                                "jpg",
                                "--db",
                                temp_db,
                            ],
                        )

                        assert result.exit_code == 0
                        # Verify DownloadFilters was created with file types
                        mock_filters_class.assert_called_once()
                        call_kwargs = mock_filters_class.call_args[1]
                        assert call_kwargs["file_types"] == ["pdf", "jpg"]

    def test_download_with_size_filters(self, runner, mock_auth_env, temp_db):
        """Test download command with --min-size and --max-size filters."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    with patch("src.models.download_filters.DownloadFilters") as mock_filters_class:
                        # Setup mocks
                        mock_repo = Mock()
                        mock_repo_factory.return_value = mock_repo

                        mock_coordinator = Mock()
                        mock_coordinator_class.return_value = mock_coordinator
                        mock_coordinator.run_download_pass.return_value = {
                            "snapshot_id": "test_snapshot",
                            "total_attachments": 2,
                            "downloaded": 2,
                            "failed": 0,
                            "total_bytes": 3072,
                            "duration": 1.0,
                            "report_markdown": "/tmp/size_report.md",
                            "report_json": "/tmp/size_report.json",
                        }

                        result = runner.invoke(
                            app,
                            [
                                "migrate",
                                "download",
                                "--snapshot-id",
                                "test_snapshot",
                                "--min-size",
                                "1KB",
                                "--max-size",
                                "1MB",
                                "--db",
                                temp_db,
                            ],
                        )

                        assert result.exit_code == 0
                        # Verify DownloadFilters was created with size limits
                        mock_filters_class.assert_called_once()
                        call_kwargs = mock_filters_class.call_args[1]
                        assert call_kwargs["min_size"] == 1024  # 1KB
                        assert call_kwargs["max_size"] == 1048576  # 1MB

    def test_download_with_combined_filters(self, runner, mock_auth_env, temp_db):
        """Test download command with multiple filter types combined."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    with patch("src.models.download_filters.DownloadFilters") as mock_filters_class:
                        # Setup mocks
                        mock_repo = Mock()
                        mock_repo_factory.return_value = mock_repo

                        mock_coordinator = Mock()
                        mock_coordinator_class.return_value = mock_coordinator
                        mock_coordinator.run_download_pass.return_value = {
                            "snapshot_id": "test_snapshot",
                            "total_attachments": 1,
                            "downloaded": 1,
                            "failed": 0,
                            "total_bytes": 2048,
                            "duration": 0.5,
                            "report_markdown": "/tmp/combined_report.md",
                            "report_json": "/tmp/combined_report.json",
                        }

                        result = runner.invoke(
                            app,
                            [
                                "migrate",
                                "download",
                                "--snapshot-id",
                                "test_snapshot",
                                "--entity",
                                "invoices",
                                "--file-type",
                                "pdf",
                                "--max-size",
                                "5MB",
                                "--db",
                                temp_db,
                            ],
                        )

                        assert result.exit_code == 0
                        # Verify all filters were passed
                        call_kwargs = mock_coordinator.run_download_pass.call_args[1]
                        assert call_kwargs["entity_types"] == ["invoices"]

                        filter_kwargs = mock_filters_class.call_args[1]
                        assert filter_kwargs["file_types"] == ["pdf"]
                        assert filter_kwargs["max_size"] == 5242880  # 5MB

    # ==================== Dry Run Mode ====================

    def test_download_dry_run_mode(self, runner, mock_auth_env, temp_db):
        """Test download command with --dry-run flag."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    mock_coordinator.run_download_pass.return_value = {
                        "snapshot_id": "test_snapshot",
                        "total_attachments": 15,
                        "by_entity_type": {"clients": 5, "invoices": 10},
                        "by_status": {"pending": 15},
                        "dry_run": True,
                    }

                    result = runner.invoke(
                        app,
                        [
                            "migrate",
                            "download",
                            "--snapshot-id",
                            "test_snapshot",
                            "--dry-run",
                            "--db",
                            temp_db,
                        ],
                    )

                    assert result.exit_code == 0
                    # Verify dry_run=True was passed
                    call_kwargs = mock_coordinator.run_download_pass.call_args[1]
                    assert call_kwargs["dry_run"] is True

                    # Check output mentions preview
                    assert "preview" in result.stdout.lower() or "dry run" in result.stdout.lower()

    # ==================== Custom Output Directory ====================

    def test_download_custom_output_directory(self, runner, mock_auth_env, temp_db):
        """Test download command with --output-dir option."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    mock_coordinator.run_download_pass.return_value = {
                        "snapshot_id": "test_snapshot",
                        "total_attachments": 5,
                        "downloaded": 5,
                        "failed": 0,
                        "total_bytes": 10240,
                        "duration": 2.0,
                        "report_markdown": "/custom/reports/report.md",
                        "report_json": "/custom/reports/report.json",
                    }

                    custom_dir = "/custom/downloads"
                    result = runner.invoke(
                        app,
                        [
                            "migrate",
                            "download",
                            "--snapshot-id",
                            "test_snapshot",
                            "--output-dir",
                            custom_dir,
                            "--db",
                            temp_db,
                        ],
                    )

                    assert result.exit_code == 0
                    # Verify custom output_dir was passed
                    call_kwargs = mock_coordinator.run_download_pass.call_args[1]
                    assert str(call_kwargs["output_dir"]) == custom_dir

    # ==================== Error Handling ====================

    def test_download_invalid_snapshot_id(self, runner, mock_auth_env, temp_db):
        """Test download command with non-existent snapshot ID."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    # Simulate coordinator raising ValueError for invalid snapshot
                    mock_coordinator.run_download_pass.side_effect = ValueError(
                        "Invalid snapshot ID: nonexistent_snapshot"
                    )

                    result = runner.invoke(
                        app,
                        [
                            "migrate",
                            "download",
                            "--snapshot-id",
                            "nonexistent_snapshot",
                            "--db",
                            temp_db,
                        ],
                    )

                    # Should handle error gracefully
                    assert result.exit_code != 0

    def test_download_with_failures_shows_report(self, runner, mock_auth_env, temp_db):
        """Test that download command displays report path when failures occur."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    mock_coordinator.run_download_pass.return_value = {
                        "snapshot_id": "test_snapshot",
                        "total_attachments": 10,
                        "downloaded": 7,
                        "failed": 3,
                        "total_bytes": 7168,
                        "duration": 3.5,
                        "report_markdown": "/tmp/failure_report.md",
                        "report_json": "/tmp/failure_report.json",
                    }

                    result = runner.invoke(
                        app,
                        ["migrate", "download", "--snapshot-id", "test_snapshot", "--db", temp_db],
                    )

                    assert result.exit_code == 0
                    # Check that failures are mentioned
                    assert "3" in result.stdout and "failed" in result.stdout.lower()
                    # Check that report path is shown
                    assert "report" in result.stdout.lower()

    def test_download_empty_queue(self, runner, mock_auth_env, temp_db):
        """Test download command when attachment queue is empty."""
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo_factory:
                with patch("src.coordinators.download_mode_coordinator.DownloadModeCoordinator") as mock_coordinator_class:
                    # Setup mocks
                    mock_repo = Mock()
                    mock_repo_factory.return_value = mock_repo

                    mock_coordinator = Mock()
                    mock_coordinator_class.return_value = mock_coordinator
                    mock_coordinator.run_download_pass.return_value = {
                        "snapshot_id": "test_snapshot",
                        "total_attachments": 0,
                        "downloaded": 0,
                        "failed": 0,
                        "total_bytes": 0,
                        "duration": 0.0,
                    }

                    result = runner.invoke(
                        app,
                        ["migrate", "download", "--snapshot-id", "test_snapshot", "--db", temp_db],
                    )

                    assert result.exit_code == 0
                    # Should mention no attachments
                    assert "0" in result.stdout or "no" in result.stdout.lower()

    # ==================== Authentication ====================

    def test_download_requires_authentication(self, runner, temp_db, monkeypatch):
        """Test that download command requires authentication."""
        # Clear auth environment
        monkeypatch.delenv("JOBBER_TOKEN", raising=False)

        with patch("src.cli.migrate._check_authentication") as mock_auth_check:
            mock_auth_check.side_effect = SystemExit(1)

            result = runner.invoke(
                app,
                ["migrate", "download", "--snapshot-id", "test_snapshot", "--db", temp_db],
            )

            # Should fail due to authentication check
            assert result.exit_code != 0
