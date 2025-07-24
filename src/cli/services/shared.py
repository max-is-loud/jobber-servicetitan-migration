"""Shared services and utilities for CLI commands.

This module provides centralized access to commonly used services
across all CLI commands to eliminate duplication.
"""

from pathlib import Path
from typing import ClassVar, Optional

from rich.console import Console


class SharedServices:
    """Centralized access to shared services used across CLI commands.

    This class provides a singleton-like access pattern to commonly used
    services like console output, configuration, and common constants.
    """

    # Shared console instance for all CLI output
    _console: ClassVar[Optional[Console]] = None

    # Default database path
    DEFAULT_DB_PATH: ClassVar[Path] = Path("tightbeam.sqlite")

    @classmethod
    def get_console(cls) -> Console:
        """Get the shared Rich console instance.

        Returns:
            Console: Shared Rich console for enhanced output
        """
        if cls._console is None:
            cls._console = Console()
        return cls._console

    @classmethod
    def get_default_db_path(cls) -> Path:
        """Get the default database path.

        Returns:
            Path: Default SQLite database path
        """
        return cls.DEFAULT_DB_PATH

    @classmethod
    def resolve_db_path(cls, db: Optional[Path] = None) -> Path:
        """Resolve database path with fallback to default.

        Args:
            db: Optional database path

        Returns:
            Path: Resolved database path
        """
        return db or cls.DEFAULT_DB_PATH
