"""Unit tests for configuration models validation."""

import pytest
from src.config.config_models import AttachmentConfig


class TestAttachmentConfig:
    """Test AttachmentConfig dataclass validation."""

    def test_valid_default_values(self):
        """Test AttachmentConfig with default values."""
        config = AttachmentConfig(auto_download=False)

        assert config.auto_download is False
        assert config.concurrent_downloads == 3
        assert config.max_concurrent_downloads == 50
        assert config.chunk_size == 65536
        assert config.http_pool_connections == 50
        assert config.http_pool_maxsize == 50

    def test_valid_custom_concurrent_downloads(self):
        """Test AttachmentConfig with valid custom concurrent_downloads values."""
        # Test minimum value
        config = AttachmentConfig(auto_download=True, concurrent_downloads=1)
        assert config.concurrent_downloads == 1

        # Test middle value
        config = AttachmentConfig(auto_download=True, concurrent_downloads=25)
        assert config.concurrent_downloads == 25

        # Test maximum value (default max)
        config = AttachmentConfig(auto_download=True, concurrent_downloads=50)
        assert config.concurrent_downloads == 50

    def test_valid_custom_max_concurrent_downloads(self):
        """Test AttachmentConfig with custom max_concurrent_downloads."""
        config = AttachmentConfig(
            auto_download=True,
            concurrent_downloads=5,
            max_concurrent_downloads=20
        )
        assert config.max_concurrent_downloads == 20
        assert config.concurrent_downloads == 5

    def test_invalid_concurrent_downloads_zero(self):
        """Test that concurrent_downloads=0 raises ValueError."""
        with pytest.raises(ValueError, match="concurrent_downloads must be between 1 and"):
            AttachmentConfig(auto_download=True, concurrent_downloads=0)

    def test_invalid_concurrent_downloads_negative(self):
        """Test that negative concurrent_downloads raises ValueError."""
        with pytest.raises(ValueError, match="concurrent_downloads must be between 1 and"):
            AttachmentConfig(auto_download=True, concurrent_downloads=-1)

    def test_invalid_concurrent_downloads_exceeds_max(self):
        """Test that concurrent_downloads > max_concurrent_downloads raises ValueError."""
        with pytest.raises(ValueError, match="concurrent_downloads must be between 1 and 50"):
            AttachmentConfig(auto_download=True, concurrent_downloads=51)

    def test_invalid_concurrent_downloads_type_string(self):
        """Test that concurrent_downloads with string type raises ValueError."""
        with pytest.raises(ValueError, match="concurrent_downloads must be an integer"):
            AttachmentConfig(auto_download=True, concurrent_downloads="three")

    def test_invalid_concurrent_downloads_type_float(self):
        """Test that concurrent_downloads with float type raises ValueError."""
        with pytest.raises(ValueError, match="concurrent_downloads must be an integer"):
            AttachmentConfig(auto_download=True, concurrent_downloads=3.5)

    def test_invalid_max_concurrent_downloads_zero(self):
        """Test that max_concurrent_downloads=0 raises ValueError."""
        with pytest.raises(ValueError, match="max_concurrent_downloads must be at least 1"):
            AttachmentConfig(
                auto_download=True,
                concurrent_downloads=1,
                max_concurrent_downloads=0
            )

    def test_invalid_max_concurrent_downloads_negative(self):
        """Test that negative max_concurrent_downloads raises ValueError."""
        with pytest.raises(ValueError, match="max_concurrent_downloads must be at least 1"):
            AttachmentConfig(
                auto_download=True,
                concurrent_downloads=1,
                max_concurrent_downloads=-5
            )

    def test_invalid_max_concurrent_downloads_type(self):
        """Test that max_concurrent_downloads with wrong type raises ValueError."""
        with pytest.raises(ValueError, match="max_concurrent_downloads must be an integer"):
            AttachmentConfig(
                auto_download=True,
                concurrent_downloads=3,
                max_concurrent_downloads="ten"
            )

    def test_auto_download_type_validation(self):
        """Test that auto_download validates boolean type."""
        with pytest.raises(ValueError, match="auto_download must be a boolean"):
            AttachmentConfig(auto_download="false")

    def test_concurrent_downloads_respects_custom_max(self):
        """Test that validation uses custom max_concurrent_downloads."""
        # This should work
        config = AttachmentConfig(
            auto_download=True,
            concurrent_downloads=15,
            max_concurrent_downloads=20
        )
        assert config.concurrent_downloads == 15

        # This should fail
        with pytest.raises(ValueError, match="concurrent_downloads must be between 1 and 5"):
            AttachmentConfig(
                auto_download=True,
                concurrent_downloads=10,
                max_concurrent_downloads=5
            )
