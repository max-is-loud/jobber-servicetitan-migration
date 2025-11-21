"""Pytest configuration for integration tests.

Provides common fixtures and setup for Enhanced Jobber Data Coverage
integration testing.
"""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def integration_test_env():
    """Create isolated test environment for integration tests."""
    # Set test environment variables
    os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
    os.environ["JOBBER_CLIENT_SECRET"] = "test_client_secret"
    os.environ["JOBBER_REDIRECT_URI"] = "http://localhost:8080/callback"
    os.environ["JOBBER_TOKEN"] = "test_token"

    yield

    # Cleanup environment
    test_vars = [
        "JOBBER_CLIENT_ID",
        "JOBBER_CLIENT_SECRET",
        "JOBBER_REDIRECT_URI",
        "JOBBER_TOKEN",
    ]
    for var in test_vars:
        if var in os.environ:
            del os.environ[var]


@pytest.fixture
def temp_database():
    """Create temporary database for testing."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_path = Path(temp_file.name)
    temp_file.close()

    yield temp_path

    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_download_dir():
    """Create temporary download directory for attachment testing."""
    temp_dir = tempfile.mkdtemp(prefix="test_attachments_")
    temp_path = Path(temp_dir)

    yield temp_path

    import shutil

    if temp_path.exists():
        shutil.rmtree(temp_path)


# Integration test markers


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "prd_validation: mark test as PRD validation test")
    config.addinivalue_line("markers", "cli_test: mark test as CLI integration test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
