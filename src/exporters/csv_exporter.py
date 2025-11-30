"""CSV exporter for database export functionality."""

import csv
import sqlite3
from pathlib import Path
from typing import Callable, List, Optional

import pandas as pd

from .base_exporter import BaseExporter


class CsvExporter(BaseExporter):
    """
    Export SQLite database tables to separate CSV files.

    Creates a directory containing individual CSV files for each table.
    Optionally includes a README.txt file documenting table relationships
    and structure for non-technical users.
    """

    # System tables to exclude from export
    SYSTEM_TABLES = {"sqlite_sequence", "sqlite_stat1"}

    # Table relationships documentation
    TABLE_RELATIONSHIPS = {
        "invoices": {"client_id": "clients.id"},
        "quotes": {"client_id": "clients.id", "property_id": "properties.id"},
        "jobs": {
            "client_id": "clients.id",
            "property_id": "properties.id",
            "quote_id": "quotes.id",
        },
        "properties": {"client_id": "clients.id"},
        "notes": {},  # entity_type and entity_id are polymorphic
        "attachments": {"note_id": "notes.id"},
        "visits": {"job_id": "jobs.id"},
        "expenses": {"job_id": "jobs.id"},
        "timesheet_entries": {"visit_id": "visits.id", "user_id": "users.id"},
        "requests": {"client_id": "clients.id", "property_id": "properties.id"},
        "note_references": {"note_id": "notes.id"},
    }

    def export(
        self,
        tables: Optional[List[str]] = None,
        include_metadata: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Path:
        """
        Export database tables to separate CSV files.

        Args:
            tables: List of table names to export. If None, exports all tables.
            include_metadata: Whether to include README.txt with relationships.
            progress_callback: Optional callback function(table_name, current, total)
                called after each table export for progress tracking.

        Returns:
            Path to the export directory containing CSV files

        Raises:
            FileNotFoundError: If database file doesn't exist
            ValueError: If specified tables don't exist in database
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        # Validate and get list of tables to export
        tables_to_export = self._validate_tables(tables)

        # Ensure output path is a directory
        if self.output_path.suffix:
            # If a file path was given, use its parent and create a subdirectory
            export_dir = self.output_path.parent / self.output_path.stem
        else:
            export_dir = self.output_path

        # Create export directory
        export_dir.mkdir(parents=True, exist_ok=True)

        # Connect to database
        conn = sqlite3.connect(str(self.db_path))

        try:
            # Export each table to a separate CSV file
            total_tables = len(tables_to_export)
            for idx, table_name in enumerate(sorted(tables_to_export), start=1):
                self._export_table(conn, table_name, export_dir)
                if progress_callback:
                    progress_callback(table_name, idx, total_tables)

            # Add README if requested
            if include_metadata:
                self._create_readme(export_dir, tables_to_export)

        finally:
            conn.close()

        return export_dir

    def get_table_list(self) -> List[str]:
        """
        Get list of all non-system tables in the database.

        Returns:
            List of table names, excluding system tables
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
            all_tables = [row[0] for row in cursor.fetchall()]
            return [t for t in all_tables if t not in self.SYSTEM_TABLES]
        finally:
            conn.close()

    def _export_table(
        self, conn: sqlite3.Connection, table_name: str, export_dir: Path
    ) -> None:
        """
        Export a single table to CSV file.

        Args:
            conn: Database connection
            table_name: Name of the table to export
            export_dir: Directory where CSV file will be saved
        """
        # Read table data
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

        # Create CSV file path
        csv_file = export_dir / f"{table_name}.csv"

        # Export to CSV
        df.to_csv(csv_file, index=False, quoting=csv.QUOTE_NONNUMERIC)

    def _create_readme(self, export_dir: Path, exported_tables: List[str]) -> None:
        """
        Create README.txt file documenting export structure.

        Args:
            export_dir: Directory where README will be saved
            exported_tables: List of tables that were exported
        """
        readme_path = export_dir / "README.txt"

        with open(readme_path, "w", encoding="utf-8") as f:
            # Header
            f.write("=" * 70 + "\n")
            f.write("TightBeam Database Export - CSV Format\n")
            f.write("=" * 70 + "\n\n")

            # Overview
            f.write("OVERVIEW\n")
            f.write("-" * 70 + "\n")
            f.write(f"This directory contains {len(exported_tables)} CSV files,\n")
            f.write("one for each database table.\n\n")

            # File listing
            f.write("EXPORTED FILES\n")
            f.write("-" * 70 + "\n")
            for table in sorted(exported_tables):
                f.write(f"  • {table}.csv\n")
            f.write("\n")

            # Table relationships
            f.write("TABLE RELATIONSHIPS (Foreign Keys)\n")
            f.write("-" * 70 + "\n")
            f.write(
                "The following tables are related through foreign key references:\n\n"
            )

            for table in sorted(exported_tables):
                if table in self.TABLE_RELATIONSHIPS:
                    relationships = self.TABLE_RELATIONSHIPS[table]
                    if relationships:
                        f.write(f"{table}:\n")
                        for fk_column, ref_table in relationships.items():
                            f.write(f"  • {fk_column} → {ref_table}\n")
                        f.write("\n")

            # Special notes
            f.write("SPECIAL NOTES\n")
            f.write("-" * 70 + "\n\n")

            f.write("JSON Fields:\n")
            f.write(
                "  Some columns contain JSON data (e.g., additional_emails,\n"
                "  line_items). These are stored as text strings and can be\n"
                "  parsed as JSON if needed.\n\n"
            )

            f.write("Attachments:\n")
            f.write(
                "  The 'attachments.csv' file includes a 'local_file_path' column\n"
                "  pointing to downloaded files. These paths are relative to where\n"
                "  the TightBeam tool was run.\n\n"
            )

            f.write("Polymorphic Relations:\n")
            f.write(
                "  The 'notes.csv' table uses 'entity_type' + 'entity_id' to link\n"
                "  to various entities (clients, jobs, etc.). Match entity_type to\n"
                "  the corresponding CSV file and entity_id to the 'id' column.\n\n"
            )

            # Import notes
            f.write("IMPORTING TO OTHER PLATFORMS\n")
            f.write("-" * 70 + "\n")
            f.write(
                "When importing these CSV files to other platforms, please note:\n\n"
            )
            f.write(
                "  • Import order matters due to foreign key relationships.\n"
                "    Import parent tables (e.g., clients) before child tables\n"
                "    (e.g., invoices).\n\n"
            )
            f.write(
                "  • Some web forms may not support JSON fields. You may need\n"
                "    to extract or simplify these fields before import.\n\n"
            )
            f.write(
                "  • ID columns should be preserved to maintain relationships\n"
                "    between tables.\n\n"
            )

            # Footer
            f.write("=" * 70 + "\n")
            f.write("For more information, visit: https://github.com/maxjmohr/tightbeam-v2\n")
            f.write("=" * 70 + "\n")
