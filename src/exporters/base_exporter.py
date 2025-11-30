"""Base exporter interface for database export functionality."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional


class BaseExporter(ABC):
    """
    Abstract base class for database exporters.

    Defines the common interface for exporting SQLite database tables
    to various formats (XLSX, CSV, etc.).
    """

    def __init__(self, db_path: Path, output_path: Path):
        """
        Initialize the exporter.

        Args:
            db_path: Path to the SQLite database file
            output_path: Path where export file(s) will be saved
        """
        self.db_path = db_path
        self.output_path = output_path

    @abstractmethod
    def export(
        self,
        tables: Optional[List[str]] = None,
        include_metadata: bool = True,
    ) -> Path:
        """
        Export database tables to the target format.

        Args:
            tables: List of table names to export. If None, exports all tables.
            include_metadata: Whether to include metadata about table relationships.

        Returns:
            Path to the exported file or directory

        Raises:
            FileNotFoundError: If database file doesn't exist
            ValueError: If specified tables don't exist in database
        """
        pass

    @abstractmethod
    def get_table_list(self) -> List[str]:
        """
        Get list of all tables in the database.

        Returns:
            List of table names, excluding system tables
        """
        pass

    def _validate_tables(self, requested_tables: Optional[List[str]]) -> List[str]:
        """
        Validate requested tables exist in database.

        Args:
            requested_tables: List of table names to validate, or None for all

        Returns:
            List of valid table names to export

        Raises:
            ValueError: If any requested table doesn't exist
        """
        available_tables = self.get_table_list()

        if requested_tables is None:
            return available_tables

        invalid_tables = set(requested_tables) - set(available_tables)
        if invalid_tables:
            raise ValueError(
                f"Tables not found in database: {', '.join(sorted(invalid_tables))}\n"
                f"Available tables: {', '.join(sorted(available_tables))}"
            )

        return requested_tables
