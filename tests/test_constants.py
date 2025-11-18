"""Tests for application constants."""

import pytest


class TestConstants:
    """Test cases for src/constants.py."""

    def test_app_version_is_read_from_package_metadata(self):
        """Test that APP_VERSION is correctly read from package metadata."""
        from src.constants import APP_VERSION

        # When package is installed, version should match pyproject.toml
        # When not installed (e.g., tests without editable install), fallback to "0.0.0-dev"
        assert isinstance(APP_VERSION, str)
        assert len(APP_VERSION) > 0
        # Version should be either from package metadata (e.g., "0.1.3") or fallback
        assert APP_VERSION == "0.1.3" or APP_VERSION == "0.0.0-dev"

    def test_version_display_includes_version(self):
        """Test that VERSION_DISPLAY includes the version."""
        from src.constants import VERSION_DISPLAY, APP_VERSION

        assert APP_VERSION in VERSION_DISPLAY
        assert "TightBeam" in VERSION_DISPLAY

    def test_all_required_constants_defined(self):
        """Test that all required constants are defined."""
        from src import constants

        # Application metadata
        assert hasattr(constants, "APP_NAME")
        assert hasattr(constants, "APP_VERSION")
        assert hasattr(constants, "APP_DESCRIPTION")

        # Verify they have expected types
        assert isinstance(constants.APP_NAME, str)
        assert isinstance(constants.APP_VERSION, str)
        assert isinstance(constants.APP_DESCRIPTION, str)
