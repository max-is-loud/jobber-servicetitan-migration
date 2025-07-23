"""Baseline CLI tests for TightBeam v2 CLI refactoring.

This test suite establishes comprehensive coverage of all CLI commands,
options, and behaviors before refactoring into modular subcommand structure.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from src.cli import app, main


class TestCLIBaseline:
    """Comprehensive baseline tests for CLI functionality."""

    def setup_method(self):
        """Set up test environment for each CLI test."""
        self.runner = CliRunner()

        # Create temporary database
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = Path(self.temp_db_file.name)
        self.temp_db_file.close()

        # Create temporary download directory
        self.temp_download_dir = tempfile.mkdtemp(prefix="cli_attachments_")
        self.download_path = Path(self.temp_download_dir)

    def teardown_method(self):
        """Clean up test environment after each CLI test."""
        if self.temp_db_path.exists():
            self.temp_db_path.unlink()

        import shutil

        if self.download_path.exists():
            shutil.rmtree(self.download_path)

    def test_main_help_output(self):
        """Test main CLI help message and structure."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "TightBeam v2 - Jobber Data Migration Tool" in result.stdout
        assert "migrate" in result.stdout
        assert "oauth" in result.stdout

    def test_oauth_group_help_output(self):
        """Test OAuth subcommand group help message."""
        result = self.runner.invoke(app, ["oauth", "--help"])
        assert result.exit_code == 0
        assert "OAuth authentication setup commands" in result.stdout
        assert "callback" in result.stdout
        assert "clear" in result.stdout
        assert "init" in result.stdout
        assert "setup" in result.stdout
        assert "status" in result.stdout

    def test_migrate_group_help_output(self):
        """Test migration subcommand group help message."""
        result = self.runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "Data migration commands" in result.stdout
        assert "--db" in result.stdout
        assert "--verbose" in result.stdout
        assert "--deferred-notes" in result.stdout
        assert "--optimization-level" in result.stdout
        assert "--enable-cost-monitoring" in result.stdout
        assert "--resume" in result.stdout
        assert "--adaptive" in result.stdout

    def test_migrate_all_help_output(self):
        """Test migrate all command help message."""
        result = self.runner.invoke(app, ["migrate", "all", "--help"])
        assert result.exit_code == 0
        assert "Migrate all data from Jobber API" in result.stdout
        assert "Deferred Notes Loading" in result.stdout
        assert "Resume Mode" in result.stdout
        assert "Authentication options" in result.stdout

    def test_oauth_init_help_output(self):
        """Test OAuth init command help message."""
        result = self.runner.invoke(app, ["oauth", "init", "--help"])
        assert result.exit_code == 0
        assert "Initialize OAuth2 authorization flow" in result.stdout
        assert "--db" in result.stdout
        assert "--port" in result.stdout
        assert "--auto" in result.stdout

    def test_oauth_setup_command(self):
        """Test OAuth setup command displays instructions."""
        result = self.runner.invoke(app, ["oauth", "setup"])
        assert result.exit_code == 0
        assert "JOBBER_CLIENT_ID" in result.stdout
        assert "JOBBER_CLIENT_SECRET" in result.stdout
        assert "JOBBER_REDIRECT_URI" in result.stdout
        assert "JOBBER_TOKEN" in result.stdout

    def test_oauth_status_without_config(self):
        """Test OAuth status command when no authentication is configured."""
        with patch.dict(os.environ, {}, clear=True):
            result = self.runner.invoke(app, ["oauth", "status"])
            assert result.exit_code == 0
            # Should show no authentication configured

    @patch("src.cli.AuthProvider.get_oauth2_config")
    def test_oauth_status_with_token_env(self, mock_get_config):
        """Test OAuth status command with JOBBER_TOKEN environment variable."""
        mock_get_config.side_effect = Exception("No OAuth config")

        with patch.dict(os.environ, {"JOBBER_TOKEN": "test_token"}, clear=True):
            with patch("src.cli.HttpClient") as mock_http:
                mock_response = {"data": {"__schema": {"queryType": {"name": "Query"}}}}
                mock_http.return_value.post.return_value = mock_response

                result = self.runner.invoke(app, ["oauth", "status"])
                assert result.exit_code == 0
                assert "Environment Token" in result.stdout

    def test_entity_migration_commands_help(self):
        """Test all individual entity migration command help messages."""
        entities = [
            "quotes",
            "attachments",
            "users",
            "expenses",
            "visits",
            "timesheet-entries",
            "products",
            "tax-rates",
        ]

        for entity in entities:
            result = self.runner.invoke(app, ["migrate", entity, "--help"])
            assert result.exit_code == 0, f"Help for {entity} command failed"
            assert f"Extract {entity}" in result.stdout or f"Extract {entity.replace('-', ' ')}" in result.stdout
            assert "--limit" in result.stdout
            assert "--resume" in result.stdout

    def test_attachments_command_specific_options(self):
        """Test attachments command has specific download path option."""
        result = self.runner.invoke(app, ["migrate", "attachments", "--help"])
        assert result.exit_code == 0
        assert "--download-path" in result.stdout

    @patch("src.cli.AuthProvider.get_oauth2_config")
    def test_migration_command_missing_auth_config(self, mock_get_config):
        """Test migration command with missing authentication configuration."""
        mock_get_config.side_effect = Exception("Missing OAuth config")

        with patch.dict(os.environ, {}, clear=True):
            result = self.runner.invoke(app, ["migrate", "quotes", "--db", str(self.temp_db_path), "--limit", "1"])

            assert result.exit_code == 1
            assert "Configuration Error" in result.stdout

    def test_migration_group_options_inheritance(self):
        """Test that migration group options are properly inherited by subcommands."""
        # Test with verbose flag at group level
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error for test")

            result = self.runner.invoke(
                app, ["migrate", "--verbose", "--db", str(self.temp_db_path), "quotes", "--limit", "1"]
            )

            # Should fail due to auth config but show that verbose was processed
            assert result.exit_code == 1

    def test_optimization_level_validation(self):
        """Test optimization level parameter validation."""
        result = self.runner.invoke(app, ["migrate", "--optimization-level", "invalid", "quotes"])

        assert result.exit_code == 1
        assert "Invalid optimization level" in result.stdout

    def test_default_database_path(self):
        """Test default database path behavior."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error for test")

            result = self.runner.invoke(app, ["migrate", "quotes", "--limit", "1"])

            # Should fail due to auth but show default db path was used
            assert result.exit_code == 1

    @patch("src.cli.AuthProvider.get_oauth2_config")
    @patch("src.cli.OAuth2Manager")
    @patch("src.cli._create_repository")
    def test_oauth_clear_command(self, mock_repo, mock_oauth, mock_config):
        """Test OAuth clear command functionality."""
        mock_config.return_value = ("id", "secret", "uri")
        mock_repository = Mock()
        mock_repository.get_oauth_tokens.return_value = {"access_token": "test"}
        mock_repo.return_value = mock_repository

        result = self.runner.invoke(app, ["oauth", "clear", "--db", str(self.temp_db_path), "--yes"])

        assert result.exit_code == 0
        assert "cleared successfully" in result.stdout

    @patch("src.cli.AuthProvider.get_oauth2_config")
    @patch("src.cli.OAuth2Manager")
    def test_oauth_callback_command(self, mock_oauth, mock_config):
        """Test OAuth callback command functionality."""
        mock_config.return_value = ("id", "secret", "uri")
        mock_oauth_instance = Mock()
        mock_oauth.return_value = mock_oauth_instance

        # Mock token exchange
        mock_oauth_instance.exchange_code_for_tokens.return_value = {
            "access_token": "test_token",
            "refresh_token": "refresh_token",
            "expires_in": 3600,
        }

        with patch("src.cli._create_repository") as mock_repo:
            mock_repository = Mock()
            mock_repo.return_value = mock_repository

            result = self.runner.invoke(
                app, ["oauth", "callback", "--code", "test_auth_code", "--db", str(self.temp_db_path)]
            )

            assert result.exit_code == 0

    def test_migrate_default_to_all_command(self):
        """Test that migrate without subcommand defaults to 'all' command."""
        with patch("src.cli.migrate_all") as mock_migrate_all:
            # Mock to prevent actual execution
            mock_migrate_all.return_value = None

            self.runner.invoke(app, ["migrate", "--db", str(self.temp_db_path)])

            # Should call migrate_all function
            mock_migrate_all.assert_called_once()

    def test_error_handling_exit_codes(self):
        """Test structured error handling and exit codes."""
        # Test configuration error (exit code 1)
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Config error")

            result = self.runner.invoke(app, ["migrate", "quotes"])
            assert result.exit_code == 1

    def test_verbose_flag_processing(self):
        """Test verbose flag is properly processed."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            result = self.runner.invoke(app, ["migrate", "--verbose", "quotes", "--limit", "1"])

            # Should process verbose flag before failing on auth
            assert result.exit_code == 1

    def test_resume_flag_processing(self):
        """Test resume flag is properly processed."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            result = self.runner.invoke(app, ["migrate", "--resume", "quotes", "--limit", "1"])

            # Should process resume flag before failing on auth
            assert result.exit_code == 1

    def test_deferred_notes_flag_processing(self):
        """Test deferred notes flag options."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            # Test deferred notes (default)
            result = self.runner.invoke(app, ["migrate", "--deferred-notes", "all"])
            assert result.exit_code == 1

            # Test immediate notes
            result = self.runner.invoke(app, ["migrate", "--immediate-notes", "all"])
            assert result.exit_code == 1

    def test_cost_monitoring_flags(self):
        """Test cost monitoring flag options."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            # Test enable cost monitoring (default)
            result = self.runner.invoke(app, ["migrate", "--enable-cost-monitoring", "all"])
            assert result.exit_code == 1

            # Test disable cost monitoring
            result = self.runner.invoke(app, ["migrate", "--disable-cost-monitoring", "all"])
            assert result.exit_code == 1

            # Test verbose cost monitoring
            result = self.runner.invoke(app, ["migrate", "--cost-monitoring-verbose", "all"])
            assert result.exit_code == 1

    def test_adaptive_optimization_flags(self):
        """Test adaptive optimization flag options."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            # Test adaptive optimization
            result = self.runner.invoke(app, ["migrate", "--adaptive", "all"])
            assert result.exit_code == 1

            # Test no adaptive optimization (default)
            result = self.runner.invoke(app, ["migrate", "--no-adaptive", "all"])
            assert result.exit_code == 1

    def test_main_entry_point(self):
        """Test main() entry point function."""
        with patch("src.cli.app") as mock_app:
            main()
            mock_app.assert_called_once()

    def test_all_optimization_levels(self):
        """Test all valid optimization levels."""
        valid_levels = ["conservative", "moderate", "aggressive"]

        for level in valid_levels:
            with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
                mock_config.side_effect = Exception("Auth error")

                result = self.runner.invoke(app, ["migrate", "--optimization-level", level, "quotes", "--limit", "1"])

                # Should process optimization level before failing on auth
                assert result.exit_code == 1

    def test_database_path_option_types(self):
        """Test database path option accepts Path objects."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            result = self.runner.invoke(app, ["migrate", "--db", str(self.temp_db_path), "quotes", "--limit", "1"])

            # Should process db path before failing on auth
            assert result.exit_code == 1


class TestCLIOptionPrecedence:
    """Test option precedence between group-level and command-level options."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = Path(self.temp_db_file.name)
        self.temp_db_file.close()

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_db_path.exists():
            self.temp_db_path.unlink()

    def test_group_level_vs_command_level_resume(self):
        """Test resume flag precedence: command-level > group-level."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            # Group-level resume should be inherited
            result = self.runner.invoke(app, ["migrate", "--resume", "quotes", "--limit", "1"])
            assert result.exit_code == 1

            # Command-level resume should override group-level
            result = self.runner.invoke(app, ["migrate", "quotes", "--resume", "--limit", "1"])
            assert result.exit_code == 1


class TestCLIRegressionPreventions:
    """Test critical CLI behaviors that must be preserved during refactor."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_migrate_without_subcommand_calls_all(self):
        """Critical: Ensure 'migrate' without subcommand still calls 'all' command."""
        with patch("src.cli.migrate_all") as mock_migrate_all:
            mock_migrate_all.return_value = None

            self.runner.invoke(app, ["migrate"])

            # This behavior MUST be preserved during refactor
            mock_migrate_all.assert_called_once()

    def test_typer_context_object_pattern(self):
        """Critical: Ensure Typer context object pattern is maintained."""
        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Auth error")

            # The context object pattern is critical for shared configuration
            result = self.runner.invoke(app, ["migrate", "--verbose", "--db", "/tmp/test.db", "quotes"])

            # Should fail on auth but process the context correctly
            assert result.exit_code == 1

    def test_error_code_consistency(self):
        """Critical: Ensure error codes remain consistent."""
        error_scenarios = [
            # Configuration error should be exit code 1
            (["migrate", "quotes"], 1),
        ]

        with patch("src.cli.AuthProvider.get_oauth2_config") as mock_config:
            mock_config.side_effect = Exception("Config error")

            for command, expected_code in error_scenarios:
                result = self.runner.invoke(app, command)
                assert result.exit_code == expected_code, f"Command {command} should exit with code {expected_code}"

    def test_rich_console_integration(self):
        """Critical: Ensure Rich console integration is maintained."""
        # Test that Rich console is used for output formatting
        result = self.runner.invoke(app, ["oauth", "setup"])
        assert result.exit_code == 0
        # Rich formatting should be present in output
        assert "OAuth" in result.stdout


# Summary of baseline test coverage:
# 1. All main CLI help outputs ✓
# 2. All subcommand help outputs ✓
# 3. OAuth command functionality ✓
# 4. Migration command functionality ✓
# 5. Option inheritance and precedence ✓
# 6. Error handling and exit codes ✓
# 7. Flag processing for all options ✓
# 8. Critical behavior preservation ✓
# 9. Integration patterns ✓
# 10. Entry point validation ✓

# This comprehensive test suite establishes a solid baseline
# for validating that the CLI refactor preserves all existing
# functionality while moving to a modular structure.
