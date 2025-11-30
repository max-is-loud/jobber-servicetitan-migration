"""XLSX exporter for database export functionality."""

import sqlite3
from pathlib import Path
from typing import Callable, List, Optional

import pandas as pd

from .base_exporter import BaseExporter


class XlsxExporter(BaseExporter):
    """
    Export SQLite database tables to multi-sheet XLSX workbook.

    Creates a single Excel file with each database table as a separate sheet.
    Optionally includes a metadata sheet documenting table relationships and
    foreign keys for non-technical users.
    """

    # System tables to exclude from export
    SYSTEM_TABLES = {
        "sqlite_sequence",  # SQLite internal
        "sqlite_stat1",  # SQLite internal
        "oauth_tokens",  # Sensitive OAuth credentials
        "graphql_costs",  # Internal API cost tracking
        "migration_state",  # Internal migration metadata
        "note_references",  # Internal deferred processing metadata
    }

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
        Export database tables to XLSX workbook.

        Args:
            tables: List of table names to export. If None, exports all tables.
            include_metadata: Whether to include metadata sheet with relationships.
            progress_callback: Optional callback function(table_name, current, total)
                called after each table export for progress tracking.

        Returns:
            Path to the exported XLSX file

        Raises:
            FileNotFoundError: If database file doesn't exist
            ValueError: If specified tables don't exist in database
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        # Validate and get list of tables to export
        tables_to_export = self._validate_tables(tables)

        # Ensure output path has .xlsx extension
        if self.output_path.suffix != ".xlsx":
            output_file = self.output_path.with_suffix(".xlsx")
        else:
            output_file = self.output_path

        # Create parent directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        conn = sqlite3.connect(str(self.db_path))

        try:
            # Create Excel writer with xlsxwriter engine
            # Disable string conversion to prevent URL hyperlink warnings when exceeding Excel's 65k limit
            with pd.ExcelWriter(
                output_file,
                engine="xlsxwriter",
                engine_kwargs={"options": {"strings_to_urls": False}},
            ) as writer:
                # Export each table as a separate sheet
                total_tables = len(tables_to_export)
                for idx, table_name in enumerate(sorted(tables_to_export), start=1):
                    self._export_table(conn, table_name, writer)
                    if progress_callback:
                        progress_callback(table_name, idx, total_tables)

                # Add metadata sheet if requested
                if include_metadata:
                    self._add_metadata_sheet(writer, tables_to_export)

        finally:
            conn.close()

        return output_file

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
        self, conn: sqlite3.Connection, table_name: str, writer: pd.ExcelWriter
    ) -> None:
        """
        Export a single table to Excel sheet.

        Args:
            conn: Database connection
            table_name: Name of the table to export
            writer: Pandas Excel writer object
        """
        # Read table data
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

        # Excel sheet names are limited to 31 characters
        sheet_name = table_name[:31]

        # Write to Excel with formatting
        df.to_excel(writer, sheet_name=sheet_name, index=False, freeze_panes=(1, 0))

        # Get workbook and worksheet objects for formatting
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # Add header format
        header_format = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#4472C4",
                "font_color": "white",
                "border": 1,
            }
        )

        # Apply header format
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Auto-adjust column widths
        for idx, col in enumerate(df.columns):
            # Get max length of column content
            max_length = max(
                df[col].astype(str).apply(len).max(),
                len(str(col)),
            )
            # Set column width (with some padding)
            worksheet.set_column(idx, idx, min(max_length + 2, 50))

    def _add_metadata_sheet(
        self, writer: pd.ExcelWriter, exported_tables: List[str]
    ) -> None:
        """
        Add metadata sheet documenting table relationships.

        Args:
            writer: Pandas Excel writer object
            exported_tables: List of tables that were exported
        """
        # Build metadata content
        metadata_rows = []

        # Add overview section
        metadata_rows.append(["TightBeam Database Export - Metadata"])
        metadata_rows.append([])
        metadata_rows.append(["Exported Tables:", len(exported_tables)])
        metadata_rows.append(["Tables:", ", ".join(sorted(exported_tables))])
        metadata_rows.append([])

        # Add relationships section
        metadata_rows.append(["Table Relationships (Foreign Keys)"])
        metadata_rows.append(["Source Table", "Foreign Key Column", "References"])
        metadata_rows.append([])

        for table in sorted(exported_tables):
            if table in self.TABLE_RELATIONSHIPS:
                relationships = self.TABLE_RELATIONSHIPS[table]
                if relationships:
                    for fk_column, ref_table in relationships.items():
                        metadata_rows.append([table, fk_column, ref_table])

        # Add special notes section
        metadata_rows.append([])
        metadata_rows.append(["Special Notes"])
        metadata_rows.append([])
        metadata_rows.append(
            [
                "JSON Fields",
                "Some columns contain JSON data (e.g., additional_emails, line_items)",
            ]
        )
        metadata_rows.append(
            [
                "Attachments",
                "The 'attachments' table includes local_file_path pointing to downloaded files",
            ]
        )
        metadata_rows.append(
            [
                "Polymorphic Relations",
                "The 'notes' table uses entity_type + entity_id to link to various entities",
            ]
        )

        # Create DataFrame and export
        metadata_df = pd.DataFrame(metadata_rows)
        metadata_df.to_excel(writer, sheet_name="README", index=False, header=False)

        # Get workbook and worksheet for formatting
        workbook = writer.book
        worksheet = writer.sheets["README"]

        # Format title
        title_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 14,
                "bg_color": "#44546A",
                "font_color": "white",
            }
        )
        worksheet.set_row(0, 20, title_format)

        # Format section headers
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9E1F2"})
        for row_num, row in enumerate(metadata_rows):
            if row and (
                row[0] in ["Table Relationships (Foreign Keys)", "Special Notes"]
            ):
                worksheet.set_row(row_num, None, header_format)

        # Format table headers
        table_header_format = workbook.add_format(
            {"bold": True, "bg_color": "#E7E6E6", "border": 1}
        )
        for row_num, row in enumerate(metadata_rows):
            if row and row[0] in ["Source Table", "JSON Fields"]:
                for col_num in range(len(row)):
                    worksheet.write(row_num, col_num, row[col_num], table_header_format)

        # Auto-adjust column widths
        worksheet.set_column(0, 0, 30)
        worksheet.set_column(1, 1, 40)
        worksheet.set_column(2, 2, 40)
