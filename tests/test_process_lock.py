"""Tests for process lock utility."""

import os
import tempfile
from pathlib import Path

import pytest

from src.utils import ProcessLock, ProcessLockError


class TestProcessLock:
    """Test suite for ProcessLock class."""

    def test_acquire_and_release_lock(self):
        """Test basic lock acquisition and release."""
        lock_file = Path(tempfile.gettempdir()) / "test_lock.lock"

        # Clean up any existing lock
        if lock_file.exists():
            lock_file.unlink()

        lock = ProcessLock(lock_file, "test")

        # Should be able to acquire lock
        lock.acquire()
        assert lock_file.exists()
        assert int(lock_file.read_text().strip()) == os.getpid()

        # Release lock
        lock.release()
        assert not lock_file.exists()

    def test_concurrent_lock_raises_error(self):
        """Test that concurrent lock acquisition raises error."""
        lock_file = Path(tempfile.gettempdir()) / "test_lock_concurrent.lock"

        # Clean up any existing lock
        if lock_file.exists():
            lock_file.unlink()

        # Acquire first lock
        lock1 = ProcessLock(lock_file, "test")
        lock1.acquire()

        # Try to acquire second lock - should fail
        lock2 = ProcessLock(lock_file, "test")
        with pytest.raises(ProcessLockError, match="Another test process is already running"):
            lock2.acquire()

        # Clean up
        lock1.release()

    def test_stale_lock_is_removed(self):
        """Test that stale locks from non-existent processes are removed."""
        lock_file = Path(tempfile.gettempdir()) / "test_lock_stale.lock"

        # Create a stale lock with a non-existent PID
        lock_file.write_text("999999")

        # Should be able to acquire lock (stale lock removed)
        lock = ProcessLock(lock_file, "test")
        lock.acquire()
        assert lock_file.exists()
        assert int(lock_file.read_text().strip()) == os.getpid()

        # Clean up
        lock.release()

    def test_context_manager(self):
        """Test ProcessLock as context manager."""
        lock_file = Path(tempfile.gettempdir()) / "test_lock_context.lock"

        # Clean up any existing lock
        if lock_file.exists():
            lock_file.unlink()

        # Use as context manager
        with ProcessLock(lock_file, "test"):
            assert lock_file.exists()
            assert int(lock_file.read_text().strip()) == os.getpid()

        # Should be released after context
        assert not lock_file.exists()

    def test_release_without_acquire(self):
        """Test that release without acquire doesn't raise error."""
        lock_file = Path(tempfile.gettempdir()) / "test_lock_no_acquire.lock"

        lock = ProcessLock(lock_file, "test")
        lock.release()  # Should not raise error
