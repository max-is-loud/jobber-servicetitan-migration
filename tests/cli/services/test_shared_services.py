"""Unit tests for SharedServices database path resolution."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli.services.shared import SharedServices


class TestResolveDbPath:
    """Test SharedServices.resolve_db_path() with various scenarios."""

    def test_explicit_parameter_takes_highest_priority(self, monkeypatch):
        """Test that explicit db parameter overrides everything."""
        monkeypatch.setenv("TIGHTBEAM_DB", "/env/var/path.db")
        explicit_path = Path("/explicit/path.db")

        result = SharedServices.resolve_db_path(explicit_path)

        assert result == explicit_path

    def test_environment_variable_used_when_no_explicit_param(self, monkeypatch):
        """Test that TIGHTBEAM_DB env var is used when db param is None."""
        test_env_path = "/environment/database.db"
        monkeypatch.setenv("TIGHTBEAM_DB", test_env_path)

        result = SharedServices.resolve_db_path(None)

        assert result == Path(test_env_path)

    def test_config_file_used_when_no_env_var(self, monkeypatch):
        """Test that config file value is used when env var is not set."""
        # Ensure env var is not set
        monkeypatch.delenv("TIGHTBEAM_DB", raising=False)

        # Mock ConfigManagerImpl to return specific path
        mock_config = MagicMock()
        mock_config.get_database_config.return_value = {"default_path": "config_database.sqlite"}

        with patch("src.config.ConfigManagerImpl", return_value=mock_config):
            result = SharedServices.resolve_db_path(None)

        assert result == Path("config_database.sqlite")

    def test_default_fallback_when_config_fails(self, monkeypatch):
        """Test that DEFAULT_DB_PATH is used when config loading fails."""
        # Ensure env var is not set
        monkeypatch.delenv("TIGHTBEAM_DB", raising=False)

        # Mock ConfigManagerImpl to raise exception
        with patch("src.config.ConfigManagerImpl", side_effect=Exception("Config error")):
            result = SharedServices.resolve_db_path(None)

        assert result == SharedServices.DEFAULT_DB_PATH

    def test_default_fallback_when_no_config_no_env(self, monkeypatch):
        """Test that DEFAULT_DB_PATH is used when nothing is configured."""
        # Ensure env var is not set
        monkeypatch.delenv("TIGHTBEAM_DB", raising=False)

        # Mock ConfigManagerImpl to raise ImportError (module not found)
        with patch("src.config.ConfigManagerImpl", side_effect=ImportError("No module")):
            result = SharedServices.resolve_db_path(None)

        assert result == SharedServices.DEFAULT_DB_PATH

    def test_precedence_explicit_over_env_over_config(self, monkeypatch):
        """Test full precedence chain: explicit > env > config > default."""
        # Setup all sources
        explicit_path = Path("/explicit/test.db")
        monkeypatch.setenv("TIGHTBEAM_DB", "/env/test.db")

        mock_config = MagicMock()
        mock_config.get_database_config.return_value = {"default_path": "config_test.db"}

        with patch("src.config.ConfigManagerImpl", return_value=mock_config):
            # Test 1: Explicit parameter wins
            result = SharedServices.resolve_db_path(explicit_path)
            assert result == explicit_path

            # Test 2: Without explicit, env var wins
            result = SharedServices.resolve_db_path(None)
            assert result == Path("/env/test.db")

            # Test 3: Without explicit or env, config wins
            monkeypatch.delenv("TIGHTBEAM_DB")
            result = SharedServices.resolve_db_path(None)
            assert result == Path("config_test.db")

    def test_empty_string_env_var_treated_as_not_set(self, monkeypatch):
        """Test that empty string in TIGHTBEAM_DB falls through to config/default."""
        monkeypatch.setenv("TIGHTBEAM_DB", "")

        mock_config = MagicMock()
        mock_config.get_database_config.return_value = {"default_path": "config_fallback.db"}

        with patch("src.config.ConfigManagerImpl", return_value=mock_config):
            result = SharedServices.resolve_db_path(None)

        # Empty string should be falsy, so should fall through to config
        assert result == Path("config_fallback.db")

    def test_relative_path_preserved(self, monkeypatch):
        """Test that relative paths are preserved as Path objects."""
        relative_path = "relative/path/to/db.sqlite"
        monkeypatch.setenv("TIGHTBEAM_DB", relative_path)

        result = SharedServices.resolve_db_path(None)

        assert result == Path(relative_path)
        assert not result.is_absolute()

    def test_absolute_path_preserved(self, monkeypatch):
        """Test that absolute paths are preserved as Path objects."""
        absolute_path = "/absolute/path/to/db.sqlite"
        monkeypatch.setenv("TIGHTBEAM_DB", absolute_path)

        result = SharedServices.resolve_db_path(None)

        assert result == Path(absolute_path)

    def test_default_db_path_is_tightbeam_sqlite(self):
        """Test that the default database path constant is correct."""
        assert SharedServices.DEFAULT_DB_PATH == Path("tightbeam.sqlite")

    def test_get_default_db_path_returns_constant(self):
        """Test that get_default_db_path() returns DEFAULT_DB_PATH."""
        result = SharedServices.get_default_db_path()
        assert result == SharedServices.DEFAULT_DB_PATH
        assert result == Path("tightbeam.sqlite")
