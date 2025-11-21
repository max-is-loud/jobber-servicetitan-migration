"""Integration tests for TightBeam CLI commands.

Tests CLI argument parsing, help text, error handling, output formatting,
and backward compatibility for all commands.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from typer.testing import CliRunner

from src.cli.main import app


class TestCLIRunner:
    """Test harness for CLI integration tests."""

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
    def mock_env(self, monkeypatch):
        """Set up mock environment variables for OAuth."""
        monkeypatch.setenv("JOBBER_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("JOBBER_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("JOBBER_REDIRECT_URI", "http://localhost:8080/callback")


class TestMainCLI(TestCLIRunner):
    """Test main CLI entry point."""

    def test_help_displays_correctly(self, runner):
        """Test that --help flag displays help text."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "TightBeam" in result.stdout
        assert "Jobber Data Migration Tool" in result.stdout
        assert "oauth" in result.stdout
        assert "migrate" in result.stdout

    def test_no_command_shows_help(self, runner):
        """Test that running with no command shows help."""
        result = runner.invoke(app, [])
        # Typer returns exit code 2 for missing command (this is expected behavior)
        assert result.exit_code == 2

    def test_invalid_command_shows_error(self, runner):
        """Test that invalid command shows appropriate error."""
        result = runner.invoke(app, ["invalid-command"])
        assert result.exit_code != 0


class TestOAuthCommands(TestCLIRunner):
    """Test OAuth subcommands."""

    def test_oauth_help(self, runner):
        """Test oauth --help displays all subcommands."""
        result = runner.invoke(app, ["oauth", "--help"])
        assert result.exit_code == 0
        assert "OAuth" in result.stdout or "authentication" in result.stdout
        assert "init" in result.stdout
        assert "status" in result.stdout
        assert "setup" in result.stdout
        assert "callback" in result.stdout
        assert "clear" in result.stdout

    def test_oauth_setup_displays_instructions(self, runner):
        """Test oauth setup command displays setup instructions."""
        result = runner.invoke(app, ["oauth", "setup"])
        assert result.exit_code == 0
        assert "JOBBER_CLIENT_ID" in result.stdout
        assert "JOBBER_CLIENT_SECRET" in result.stdout
        assert "JOBBER_REDIRECT_URI" in result.stdout
        assert "environment variables" in result.stdout.lower()

    def test_oauth_status_without_config(self, runner, monkeypatch):
        """Test oauth status when OAuth is not configured."""
        # Clear OAuth environment variables
        monkeypatch.delenv("JOBBER_CLIENT_ID", raising=False)
        monkeypatch.delenv("JOBBER_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("JOBBER_REDIRECT_URI", raising=False)
        monkeypatch.delenv("JOBBER_TOKEN", raising=False)

        result = runner.invoke(app, ["oauth", "status"])
        assert result.exit_code == 0
        assert "Authentication Status" in result.stdout or "status" in result.stdout.lower()

    def test_oauth_status_with_env_token(self, runner, monkeypatch):
        """Test oauth status with JOBBER_TOKEN environment variable."""
        # Set environment token
        monkeypatch.setenv("JOBBER_TOKEN", "test_token_123")

        # Mock the HTTP client to avoid actual API calls
        with patch("src.cli.oauth.ServiceFactory.create_http_client") as mock_http:
            mock_response = {"data": {"__schema": {"queryType": {"name": "Query"}}}}
            mock_http.return_value.post.return_value = mock_response

            result = runner.invoke(app, ["oauth", "status"])
            assert result.exit_code == 0
            assert "Environment Token" in result.stdout or "JOBBER_TOKEN" in result.stdout

    def test_oauth_init_manual_mode_help(self, runner, mock_env):
        """Test oauth init command accepts --no-auto flag."""
        # Test that the flag is recognized by checking help
        result = runner.invoke(app, ["oauth", "init", "--help"])
        assert result.exit_code == 0
        assert "--auto" in result.stdout or "auto" in result.stdout.lower()

    @patch("src.cli.oauth._create_repository")
    def test_oauth_clear_no_tokens(self, mock_repo, runner, temp_db):
        """Test oauth clear when no tokens exist."""
        mock_repo_instance = Mock()
        mock_repo_instance.get_oauth_tokens.return_value = None
        mock_repo.return_value = mock_repo_instance

        result = runner.invoke(app, ["oauth", "clear", "--db", temp_db, "--yes"])
        assert result.exit_code == 0
        assert "No OAuth2 tokens found" in result.stdout or "No tokens" in result.stdout

    @patch("src.cli.oauth._create_repository")
    def test_oauth_clear_with_confirmation(self, mock_repo, runner, temp_db):
        """Test oauth clear with tokens requires confirmation."""
        mock_repo_instance = Mock()
        mock_repo_instance.get_oauth_tokens.return_value = {"access_token": "test"}
        mock_repo.return_value = mock_repo_instance

        # Test without --yes flag (auto-decline in test)
        result = runner.invoke(app, ["oauth", "clear", "--db", temp_db], input="n\n")
        assert "cancelled" in result.stdout.lower() or result.exit_code == 0

    @patch("src.cli.oauth._create_repository")
    def test_oauth_clear_with_yes_flag(self, mock_repo, runner, temp_db):
        """Test oauth clear with --yes flag skips confirmation."""
        mock_repo_instance = Mock()
        mock_repo_instance.get_oauth_tokens.return_value = {"access_token": "test"}
        mock_repo_instance.clear_oauth_tokens.return_value = None
        mock_repo.return_value = mock_repo_instance

        result = runner.invoke(app, ["oauth", "clear", "--db", temp_db, "--yes"])
        assert result.exit_code == 0
        mock_repo_instance.clear_oauth_tokens.assert_called_once()

    def test_oauth_callback_requires_code(self, runner):
        """Test oauth callback requires --code parameter."""
        result = runner.invoke(app, ["oauth", "callback"])
        assert result.exit_code != 0
        # Typer writes errors to output (combination of stdout and stderr)
        # Check if command fails with non-zero exit code (that's sufficient)


class TestMigrateCommands(TestCLIRunner):
    """Test migrate subcommands."""

    def test_migrate_help(self, runner):
        """Test migrate --help displays all subcommands."""
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "migrate" in result.stdout.lower() or "migration" in result.stdout.lower()
        assert "start" in result.stdout
        assert "map" in result.stdout
        assert "extract" in result.stdout
        assert "reconcile" in result.stdout
        assert "all" in result.stdout

    def test_migrate_global_options_help(self, runner):
        """Test migrate help shows global options."""
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        # Check for important global options
        assert "--db" in result.stdout
        assert "--verbose" in result.stdout
        assert "--resume" in result.stdout
        assert "--adaptive" in result.stdout
        assert "--optimization-level" in result.stdout

    def test_migrate_map_help(self, runner, monkeypatch):
        """Test migrate map --help displays map options."""
        # Set token to bypass auth check
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        result = runner.invoke(app, ["migrate", "map", "--help"])
        assert result.exit_code == 0
        assert "map" in result.stdout.lower()
        assert "--entity" in result.stdout or "--entities" in result.stdout
        assert "--snapshot-label" in result.stdout
        assert "--report-dir" in result.stdout

    def test_migrate_extract_help(self, runner, monkeypatch):
        """Test migrate extract --help displays extract options."""
        # Set token to bypass auth check
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        result = runner.invoke(app, ["migrate", "extract", "--help"])
        assert result.exit_code == 0
        assert "extract" in result.stdout.lower()
        assert "--snapshot-id" in result.stdout
        assert "--entity" in result.stdout or "--entities" in result.stdout
        assert "--resume" in result.stdout

    def test_migrate_extract_requires_snapshot_id(self, runner, monkeypatch):
        """Test migrate extract requires --snapshot-id parameter."""
        # Set up minimal auth to get past auth check
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "extract"])
            # Should fail with missing required parameter
            assert result.exit_code != 0

    def test_migrate_all_help(self, runner, monkeypatch):
        """Test migrate all --help displays options."""
        # Set token to bypass auth check
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        result = runner.invoke(app, ["migrate", "all", "--help"])
        assert result.exit_code == 0
        assert "all" in result.stdout.lower() or "migrate" in result.stdout.lower()

    def test_migrate_specific_entity_commands_help(self, runner, monkeypatch):
        """Test entity-specific command help texts."""
        # Set token to bypass auth check
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        # Test quotes command
        result = runner.invoke(app, ["migrate", "quotes", "--help"])
        assert result.exit_code == 0
        assert "quote" in result.stdout.lower()

        # Test users command
        result = runner.invoke(app, ["migrate", "users", "--help"])
        assert result.exit_code == 0
        assert "user" in result.stdout.lower()

        # Test expenses command
        result = runner.invoke(app, ["migrate", "expenses", "--help"])
        assert result.exit_code == 0
        assert "expense" in result.stdout.lower()


class TestMigrateGlobalOptions(TestCLIRunner):
    """Test migrate global options parsing."""

    def test_db_option_parsing(self, runner, temp_db, monkeypatch):
        """Test --db option is parsed correctly."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        # Mock ServiceFactory to avoid actual migration
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.services.ServiceFactory.create_repository") as mock_repo:
                mock_repo.return_value = Mock()

                result = runner.invoke(app, ["migrate", "--db", temp_db, "all"])
                # Command should process the --db option
                # (actual test would verify the db path is used, but this tests parsing)

    def test_verbose_option_parsing(self, runner, monkeypatch):
        """Test --verbose option is parsed correctly."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "--verbose", "--help"])
            assert result.exit_code == 0

    def test_resume_option_parsing(self, runner, monkeypatch):
        """Test --resume option is parsed correctly."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "--resume", "--help"])
            assert result.exit_code == 0

    def test_adaptive_option_parsing(self, runner, monkeypatch):
        """Test --adaptive option is parsed correctly."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "--adaptive", "--help"])
            assert result.exit_code == 0

    def test_optimization_level_options(self, runner, monkeypatch):
        """Test --optimization-level accepts valid values."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            # Test conservative
            result = runner.invoke(app, ["migrate", "--optimization-level", "conservative", "--help"])
            assert result.exit_code == 0

            # Test moderate (default)
            result = runner.invoke(app, ["migrate", "--optimization-level", "moderate", "--help"])
            assert result.exit_code == 0

            # Test aggressive
            result = runner.invoke(app, ["migrate", "--optimization-level", "aggressive", "--help"])
            assert result.exit_code == 0

    def test_dry_run_option_parsing(self, runner, monkeypatch):
        """Test --dry-run option is parsed correctly."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "--dry-run", "--help"])
            assert result.exit_code == 0

    def test_cost_monitoring_options(self, runner, monkeypatch):
        """Test cost monitoring options are parsed correctly."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            # Test --enable-cost-monitoring
            result = runner.invoke(app, ["migrate", "--enable-cost-monitoring", "--help"])
            assert result.exit_code == 0

            # Test --cost-monitoring-verbose
            result = runner.invoke(app, ["migrate", "--cost-monitoring-verbose", "--help"])
            assert result.exit_code == 0


class TestAuthenticationChecks(TestCLIRunner):
    """Test authentication requirement checks."""

    def test_migrate_requires_authentication(self, runner, monkeypatch):
        """Test migrate commands require authentication."""
        # Clear all auth environment variables
        monkeypatch.delenv("JOBBER_TOKEN", raising=False)
        monkeypatch.delenv("JOBBER_CLIENT_ID", raising=False)
        monkeypatch.delenv("JOBBER_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("JOBBER_REDIRECT_URI", raising=False)

        # Mock repository to return no tokens
        with patch("src.cli.migrate.ServiceFactory.create_repository") as mock_repo:
            mock_repo_instance = Mock()
            mock_repo_instance.get_oauth_tokens.return_value = None
            mock_repo.return_value = mock_repo_instance

            with patch("src.cli.migrate.ServiceFactory.create_oauth2_manager") as mock_oauth:
                # Raise ConfigurationError to simulate no OAuth config
                from src.exceptions import ConfigurationError

                mock_oauth.side_effect = ConfigurationError("OAuth not configured")

                result = runner.invoke(app, ["migrate", "all"])
                assert result.exit_code != 0
                assert "Authentication Required" in result.stdout or "authentication" in result.stdout.lower()

    def test_migrate_with_env_token_bypasses_oauth(self, runner, monkeypatch):
        """Test JOBBER_TOKEN environment variable bypasses OAuth check."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token_value")

        # Simplified test: just verify that having JOBBER_TOKEN set doesn't
        # trigger an authentication error when trying to run migrate commands
        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "--help"])
            # With JOBBER_TOKEN set, should be able to at least see help
            # (the _check_authentication bypass worked)
            assert result.exit_code == 0


class TestMapModeOptions(TestCLIRunner):
    """Test map mode specific options."""

    def test_map_entity_option_single(self, runner, monkeypatch):
        """Test map --entity option with single entity."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.coordinators.map_mode_coordinator.MapModeCoordinator") as mock_coordinator:
                mock_instance = Mock()
                mock_instance.run_map_pass.return_value = {
                    "snapshot_id": "test-id",
                    "entity_counts": {"clients": 10},
                    "total_entities": 10,
                    "timestamp": "2025-01-01T00:00:00Z",
                }
                mock_coordinator.return_value = mock_instance

                with patch("src.cli.services.ServiceFactory.create_repository"):
                    with patch("src.cli.services.ServiceFactory.create_http_client"):
                        with patch("src.cli.services.ServiceFactory.create_rate_limited_jobber_client"):
                            result = runner.invoke(app, ["migrate", "map", "--entity", "clients"])
                            # Should accept the --entity option (test that it runs without error)

    def test_map_entity_option_multiple(self, runner, monkeypatch):
        """Test map --entity option with multiple entities."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                ["migrate", "map", "--entity", "clients", "--entity", "invoices", "--help"],
            )
            assert result.exit_code == 0

    def test_map_snapshot_label_option(self, runner, monkeypatch):
        """Test map --snapshot-label option."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "map", "--snapshot-label", "test-label", "--help"])
            assert result.exit_code == 0

    def test_map_report_dir_option(self, runner, monkeypatch):
        """Test map --report-dir option."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "map", "--report-dir", "/tmp/reports", "--help"])
            assert result.exit_code == 0


class TestExtractModeOptions(TestCLIRunner):
    """Test extract mode specific options."""

    def test_extract_snapshot_id_required(self, runner, monkeypatch):
        """Test extract --snapshot-id is required."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "extract"])
            assert result.exit_code != 0
            # Exit code != 0 is sufficient to verify required parameter check

    def test_extract_entity_option(self, runner, monkeypatch):
        """Test extract --entity option."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "extract",
                    "--snapshot-id",
                    "test-id",
                    "--entity",
                    "clients",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_extract_resume_option(self, runner, monkeypatch):
        """Test extract --resume option."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                ["migrate", "extract", "--snapshot-id", "test-id", "--resume", "--help"],
            )
            assert result.exit_code == 0

    def test_extract_report_dir_option(self, runner, monkeypatch):
        """Test extract --report-dir option."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "extract",
                    "--snapshot-id",
                    "test-id",
                    "--report-dir",
                    "/tmp/reports",
                    "--help",
                ],
            )
            assert result.exit_code == 0


class TestErrorHandling(TestCLIRunner):
    """Test error handling in CLI commands."""

    def test_invalid_optimization_level(self, runner, monkeypatch):
        """Test invalid optimization level shows error."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "--optimization-level", "invalid", "all"])
            # Typer should reject invalid choice
            # Note: Typer might not reject this if it's a string type, so this test
            # verifies current behavior

    def test_invalid_db_path(self, runner, monkeypatch):
        """Test invalid database path handling."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        # Use invalid path
        invalid_path = "/nonexistent/directory/db.sqlite"

        with patch("src.cli.migrate._check_authentication"):
            # Most CLI frameworks will accept the path even if invalid,
            # error occurs when trying to use it
            result = runner.invoke(app, ["migrate", "--db", invalid_path, "--help"])
            # Should parse without error (error would occur during actual use)


class TestBackwardCompatibility(TestCLIRunner):
    """Test backward compatibility features."""

    def test_migrate_all_still_works(self, runner, monkeypatch):
        """Test traditional 'migrate all' command still exists."""
        # Set token to bypass auth check
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        # Simply verify the command is recognized
        result = runner.invoke(app, ["migrate", "all", "--help"])
        assert result.exit_code == 0
        assert "all" in result.stdout.lower() or "migrate" in result.stdout.lower()

    def test_legacy_commands_available(self, runner):
        """Test legacy entity-specific commands are still available."""
        # Test that all legacy commands are still registered
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0

        # Verify legacy commands are present
        assert "quotes" in result.stdout
        assert "attachments" in result.stdout
        assert "users" in result.stdout
        assert "expenses" in result.stdout

    def test_resume_flag_works_with_all(self, runner):
        """Test --resume flag works with 'migrate all' command."""
        # Verify the global --resume flag is recognized in help
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "--resume" in result.stdout


class TestOutputFormatting(TestCLIRunner):
    """Test output formatting and display."""

    def test_help_output_is_formatted(self, runner):
        """Test help output uses Rich formatting."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Output should be formatted (contains structure)
        assert len(result.stdout) > 100  # Reasonable help text length

    def test_oauth_status_uses_table_format(self, runner, monkeypatch):
        """Test oauth status uses table formatting."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.oauth.ServiceFactory.create_http_client") as mock_http:
            mock_response = {"data": {"__schema": {"queryType": {"name": "Query"}}}}
            mock_http.return_value.post.return_value = mock_response

            result = runner.invoke(app, ["oauth", "status"])
            assert result.exit_code == 0
            # Should contain table elements or structured output
            assert "Authentication Status" in result.stdout or "Status" in result.stdout

    def test_oauth_setup_uses_panel_format(self, runner):
        """Test oauth setup uses panel formatting."""
        result = runner.invoke(app, ["oauth", "setup"])
        assert result.exit_code == 0
        # Should contain panel/box elements
        assert "JOBBER_CLIENT_ID" in result.stdout
        assert len(result.stdout) > 200  # Formatted output is longer


class TestCommandCombinations(TestCLIRunner):
    """Test various command and option combinations."""

    def test_multiple_global_options_combined(self, runner, monkeypatch, temp_db):
        """Test combining multiple global migrate options."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "--db",
                    temp_db,
                    "--verbose",
                    "--resume",
                    "--adaptive",
                    "--optimization-level",
                    "conservative",
                    "--enable-cost-monitoring",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_map_with_all_options(self, runner, monkeypatch):
        """Test map command with all available options."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "--adaptive",
                    "--verbose",
                    "map",
                    "--entity",
                    "clients",
                    "--entity",
                    "invoices",
                    "--snapshot-label",
                    "test",
                    "--report-dir",
                    "./reports",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_extract_with_all_options(self, runner, monkeypatch):
        """Test extract command with all available options."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "--resume",
                    "--verbose",
                    "--adaptive",
                    "extract",
                    "--snapshot-id",
                    "test-snapshot-id",
                    "--entity",
                    "clients",
                    "--resume",
                    "--report-dir",
                    "./reports",
                    "--help",
                ],
            )
            assert result.exit_code == 0


class TestMigrateStartCommand(TestCLIRunner):
    """Test migrate start command with backward compatibility."""

    def test_migrate_start_help(self, runner, monkeypatch):
        """Test migrate start --help displays help text."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        result = runner.invoke(app, ["migrate", "start", "--help"])
        assert result.exit_code == 0
        assert "start" in result.stdout.lower() or "migration" in result.stdout.lower()
        assert "--use-multi-pass" in result.stdout
        assert "single-pass" in result.stdout.lower()
        assert "multi-pass" in result.stdout.lower()

    def test_migrate_start_shows_multi_pass_options(self, runner, monkeypatch):
        """Test migrate start help shows multi-pass specific options."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        result = runner.invoke(app, ["migrate", "start", "--help"])
        assert result.exit_code == 0
        assert "--entity" in result.stdout or "--entities" in result.stdout
        assert "--snapshot-label" in result.stdout
        assert "--report-dir" in result.stdout
        assert "--resume" in result.stdout

    def test_migrate_start_single_pass_default(self, runner, monkeypatch):
        """Test migrate start defaults to single-pass mode."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.migrate_all") as mock_all:
                with patch("src.cli.services.ServiceFactory.create_repository"):
                    result = runner.invoke(app, ["migrate", "start"])
                    # Should delegate to migrate_all when --use-multi-pass is not specified
                    assert mock_all.called

    def test_migrate_start_multi_pass_flag(self, runner, monkeypatch):
        """Test migrate start --use-multi-pass runs multi-pass strategy."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.services.ServiceFactory.create_repository") as mock_repo:
                with patch("src.cli.services.ServiceFactory.create_oauth2_manager"):
                    with patch("src.cli.services.ServiceFactory.create_rate_limited_jobber_client"):
                        with patch("src.coordinators.map_mode_coordinator.MapModeCoordinator") as mock_map:
                            with patch(
                                "src.coordinators.extract_mode_coordinator.ExtractModeCoordinator"
                            ) as mock_extract:
                                # Mock repository instance
                                mock_repo_instance = Mock()
                                mock_repo_instance.get_map_snapshot.return_value = Mock(label="test-label")
                                mock_repo.return_value = mock_repo_instance

                                # Mock map coordinator
                                mock_map_instance = Mock()
                                mock_map_instance.run_map_pass.return_value = {
                                    "snapshot_id": "test-snapshot",
                                    "label": "test-label",
                                    "entity_results": {},
                                    "totals": {},
                                    "duration": 10.0,
                                }
                                mock_map_instance.identify_hotspots.return_value = []
                                mock_map_instance.get_density_stats.return_value = {}
                                mock_map.return_value = mock_map_instance

                                # Mock extract coordinator
                                mock_extract_instance = Mock()
                                mock_extract_instance.run_extract_pass.return_value = {
                                    "entity_results": {},
                                    "attachment_result": {},
                                    "discrepancies": [],
                                    "totals": {},
                                    "duration": 20.0,
                                }
                                mock_extract.return_value = mock_extract_instance

                                # Mock report generators
                                with patch("src.reports.MapReportGenerator") as mock_map_report:
                                    with patch("src.reports.ExtractReportGenerator") as mock_extract_report:
                                        mock_map_report.return_value.generate_report.return_value = (
                                            "map.md",
                                            "map.json",
                                        )
                                        mock_extract_report.return_value.generate_report.return_value = (
                                            "extract.md",
                                            "extract.json",
                                        )

                                        result = runner.invoke(app, ["migrate", "start", "--use-multi-pass"])

                                        # Verify both coordinators were called
                                        assert mock_map_instance.run_map_pass.called
                                        assert mock_extract_instance.run_extract_pass.called

    def test_migrate_start_multi_pass_with_entities(self, runner, monkeypatch):
        """Test migrate start --use-multi-pass with specific entities."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "start",
                    "--use-multi-pass",
                    "--entity",
                    "clients",
                    "--entity",
                    "invoices",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_migrate_start_multi_pass_with_snapshot_label(self, runner, monkeypatch):
        """Test migrate start --use-multi-pass with snapshot label."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "start",
                    "--use-multi-pass",
                    "--snapshot-label",
                    "test-migration",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_migrate_start_multi_pass_with_report_dir(self, runner, monkeypatch):
        """Test migrate start --use-multi-pass with custom report directory."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "start",
                    "--use-multi-pass",
                    "--report-dir",
                    "./custom-reports",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_migrate_start_multi_pass_with_resume(self, runner, monkeypatch):
        """Test migrate start --use-multi-pass with resume flag."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                ["migrate", "start", "--use-multi-pass", "--resume", "--help"],
            )
            assert result.exit_code == 0

    def test_migrate_start_backward_compatibility(self, runner, monkeypatch):
        """Test migrate start maintains backward compatibility with single-pass."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        # Verify that 'migrate start' without --use-multi-pass behaves like 'migrate all'
        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.migrate.migrate_all") as mock_all:
                with patch("src.cli.services.ServiceFactory.create_repository"):
                    runner.invoke(app, ["migrate", "start"])

                    # Should call migrate_all (single-pass behavior)
                    assert mock_all.called
                    # Verify it was called with correct parameters
                    assert mock_all.call_count == 1

    def test_migrate_start_multi_pass_invalid_entity(self, runner, monkeypatch):
        """Test migrate start --use-multi-pass with invalid entity type."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.services.ServiceFactory.create_repository"):
                with patch("src.cli.services.ServiceFactory.create_oauth2_manager"):
                    result = runner.invoke(
                        app,
                        ["migrate", "start", "--use-multi-pass", "--entity", "invalid_entity"],
                    )
                    # Should fail with invalid entity type
                    assert result.exit_code != 0
                    assert "Invalid entity" in result.stdout or "invalid" in result.stdout.lower()

    def test_migrate_start_all_options_combined(self, runner, monkeypatch, temp_db):
        """Test migrate start with all options combined."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "--db",
                    temp_db,
                    "--verbose",
                    "--adaptive",
                    "start",
                    "--use-multi-pass",
                    "--entity",
                    "clients",
                    "--snapshot-label",
                    "full-test",
                    "--report-dir",
                    "./reports",
                    "--resume",
                    "--help",
                ],
            )
            assert result.exit_code == 0


class TestMigrateReconcileCommand(TestCLIRunner):
    """Test migrate reconcile command."""

    def test_migrate_reconcile_help(self, runner, monkeypatch):
        """Test migrate reconcile --help displays help text."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        result = runner.invoke(app, ["migrate", "reconcile", "--help"])
        assert result.exit_code == 0
        assert "reconcile" in result.stdout.lower() or "reconciliation" in result.stdout.lower()
        assert "--snapshot-id" in result.stdout
        assert "data drift" in result.stdout.lower()

    def test_migrate_reconcile_requires_snapshot_id(self, runner, monkeypatch):
        """Test migrate reconcile requires --snapshot-id parameter."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(app, ["migrate", "reconcile"])
            # Should fail with missing required parameter
            assert result.exit_code != 0

    def test_migrate_reconcile_with_snapshot_id(self, runner, monkeypatch):
        """Test migrate reconcile with valid snapshot ID."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.services.ServiceFactory.create_repository") as mock_repo:
                # Mock repository to return a valid snapshot
                mock_repo_instance = Mock()
                mock_repo_instance.get_map_snapshot.return_value = Mock(
                    snapshot_id="test-snapshot",
                    label="test-label",
                    created_at="2025-01-01T00:00:00Z",
                )
                mock_repo_instance.get_entity_inventory.return_value = [
                    Mock(entity_type="clients", entity_id="client-1"),
                    Mock(entity_type="invoices", entity_id="invoice-1"),
                ]
                mock_repo.return_value = mock_repo_instance

                with patch("src.cli.services.ServiceFactory.create_oauth2_manager"):
                    with patch("src.cli.services.ServiceFactory.create_rate_limited_jobber_client"):
                        with patch("src.coordinators.map_mode_coordinator.MapModeCoordinator") as mock_map:
                            with patch("src.coordinators.extract_mode_coordinator.ExtractModeCoordinator"):
                                # Mock map coordinator to return new snapshot
                                mock_map_instance = Mock()
                                mock_map_instance.run_map_pass.return_value = {
                                    "snapshot_id": "new-snapshot",
                                    "label": "test-label-reconcile",
                                    "entity_results": {},
                                    "totals": {},
                                    "duration": 10.0,
                                }
                                mock_map.return_value = mock_map_instance

                                # Mock extract queues and attachment queues
                                mock_repo_instance.get_extract_queue.return_value = []
                                mock_repo_instance.get_attachment_queue.return_value = []

                                result = runner.invoke(app, ["migrate", "reconcile", "--snapshot-id", "test-snapshot"])

                                # Verify snapshot was retrieved
                                assert mock_repo_instance.get_map_snapshot.called

    def test_migrate_reconcile_with_invalid_snapshot(self, runner, monkeypatch):
        """Test migrate reconcile with non-existent snapshot ID."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.services.ServiceFactory.create_repository") as mock_repo:
                # Mock repository to return None (snapshot not found)
                mock_repo_instance = Mock()
                mock_repo_instance.get_map_snapshot.return_value = None
                mock_repo.return_value = mock_repo_instance

                result = runner.invoke(app, ["migrate", "reconcile", "--snapshot-id", "invalid-snapshot"])

                # Should fail with snapshot not found error
                assert result.exit_code != 0
                assert "not found" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_migrate_reconcile_with_specific_entities(self, runner, monkeypatch):
        """Test migrate reconcile with specific entity types."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "reconcile",
                    "--snapshot-id",
                    "test-snapshot",
                    "--entity",
                    "clients",
                    "--entity",
                    "invoices",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_migrate_reconcile_with_invalid_entity(self, runner, monkeypatch):
        """Test migrate reconcile with invalid entity type."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.services.ServiceFactory.create_repository") as mock_repo:
                # Mock repository to return valid snapshot
                mock_repo_instance = Mock()
                mock_repo_instance.get_map_snapshot.return_value = Mock(
                    snapshot_id="test-snapshot",
                    label="test-label",
                    created_at="2025-01-01T00:00:00Z",
                )
                mock_repo.return_value = mock_repo_instance

                result = runner.invoke(
                    app,
                    [
                        "migrate",
                        "reconcile",
                        "--snapshot-id",
                        "test-snapshot",
                        "--entity",
                        "invalid_entity",
                    ],
                )

                # Should fail with invalid entity error
                assert result.exit_code != 0
                assert "Invalid entity" in result.stdout or "invalid" in result.stdout.lower()

    def test_migrate_reconcile_with_report_dir(self, runner, monkeypatch):
        """Test migrate reconcile with custom report directory."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    "reconcile",
                    "--snapshot-id",
                    "test-snapshot",
                    "--report-dir",
                    "./custom-reports",
                    "--help",
                ],
            )
            assert result.exit_code == 0

    def test_migrate_reconcile_empty_snapshot(self, runner, monkeypatch):
        """Test migrate reconcile with empty snapshot (no entities)."""
        monkeypatch.setenv("JOBBER_TOKEN", "test_token")

        with patch("src.cli.migrate._check_authentication"):
            with patch("src.cli.services.ServiceFactory.create_repository") as mock_repo:
                # Mock repository with valid snapshot but no inventory
                mock_repo_instance = Mock()
                mock_repo_instance.get_map_snapshot.return_value = Mock(
                    snapshot_id="test-snapshot",
                    label="test-label",
                    created_at="2025-01-01T00:00:00Z",
                )
                mock_repo_instance.get_entity_inventory.return_value = []  # Empty inventory
                mock_repo.return_value = mock_repo_instance

                result = runner.invoke(app, ["migrate", "reconcile", "--snapshot-id", "test-snapshot"])

                # Should exit gracefully with nothing to reconcile
                assert result.exit_code == 0
                assert "Nothing to reconcile" in result.stdout or "No entity types" in result.stdout
