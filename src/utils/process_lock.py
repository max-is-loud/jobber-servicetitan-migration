"""Process lock utility to prevent concurrent migrations."""

import os
import signal
from pathlib import Path
from typing import Optional


class ProcessLockError(Exception):
    """Raised when a process lock cannot be acquired."""
    pass


class ProcessLock:
    """File-based process lock to prevent concurrent execution.

    Uses PID file locking to ensure only one migration process runs at a time.
    Automatically cleans up stale locks from crashed processes.
    """

    def __init__(self, lock_file: Path, process_name: str = "migration"):
        """Initialize process lock.

        Args:
            lock_file: Path to the lock file (e.g., /tmp/tightbeam_migration.lock)
            process_name: Descriptive name for error messages
        """
        self.lock_file = lock_file
        self.process_name = process_name
        self._acquired = False

    def acquire(self) -> None:
        """Acquire the process lock.

        Raises:
            ProcessLockError: If another process holds the lock
        """
        # Check if lock file exists
        if self.lock_file.exists():
            # Read existing PID
            try:
                existing_pid = int(self.lock_file.read_text().strip())

                # Check if process is still running
                if self._is_process_running(existing_pid):
                    raise ProcessLockError(
                        f"Another {self.process_name} process is already running (PID: {existing_pid}). "
                        f"Please wait for it to complete or stop it before starting a new {self.process_name}."
                    )
                else:
                    # Stale lock file - process has crashed or been killed
                    # Remove it and continue
                    self.lock_file.unlink()
            except (ValueError, FileNotFoundError):
                # Invalid or deleted lock file - safe to proceed
                pass

        # Ensure parent directory exists
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Write our PID to the lock file
        self.lock_file.write_text(str(os.getpid()))
        self._acquired = True

    def release(self) -> None:
        """Release the process lock."""
        if self._acquired and self.lock_file.exists():
            try:
                # Only remove if it contains our PID (prevent race conditions)
                if int(self.lock_file.read_text().strip()) == os.getpid():
                    self.lock_file.unlink()
            except (ValueError, FileNotFoundError):
                pass
            self._acquired = False

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        try:
            # Send signal 0 to check if process exists (doesn't actually send a signal)
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            # Process doesn't exist
            return False
        except PermissionError:
            # Process exists but we don't have permission to signal it
            # This means it's running
            return True

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False
