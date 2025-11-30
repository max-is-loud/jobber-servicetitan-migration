"""Unit tests for database exporters."""

import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.exporters import CsvExporter, XlsxExporter


@pytest.fixture
def sample_db():
    """Create a temporary test database with sample data."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create sample tables
    cursor.execute(
        """
        CREATE TABLE clients (
            id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            email TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE invoices (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            total_cents INTEGER,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    """
    )

    # Insert sample data
    cursor.execute(
        "INSERT INTO clients VALUES ('c1', 'John', 'Doe', 'john@example.com')"
    )
    cursor.execute(
        "INSERT INTO clients VALUES ('c2', 'Jane', 'Smith', 'jane@example.com')"
    )
    cursor.execute("INSERT INTO invoices VALUES ('i1', 'c1', 10000)")
    cursor.execute("INSERT INTO invoices VALUES ('i2', 'c2', 20000)")

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink()


class TestXlsxExporter:
    """Test cases for XLSX exporter."""

    def test_export_all_tables(self, sample_db):
        """Test exporting all tables to XLSX."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            output_path = Path(f.name)

        try:
            exporter = XlsxExporter(sample_db, output_path)
            result = exporter.export()

            assert result.exists()
            assert result.suffix == ".xlsx"

            # Verify exported data
            df_clients = pd.read_excel(result, sheet_name="clients")
            df_invoices = pd.read_excel(result, sheet_name="invoices")

            assert len(df_clients) == 2
            assert len(df_invoices) == 2
            assert "first_name" in df_clients.columns
            assert "total_cents" in df_invoices.columns

            # Verify metadata sheet exists
            xl_file = pd.ExcelFile(result)
            assert "README" in xl_file.sheet_names

        finally:
            if output_path.exists():
                output_path.unlink()

    def test_export_specific_tables(self, sample_db):
        """Test exporting specific tables to XLSX."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            output_path = Path(f.name)

        try:
            exporter = XlsxExporter(sample_db, output_path)
            result = exporter.export(tables=["clients"])

            xl_file = pd.ExcelFile(result)
            assert "clients" in xl_file.sheet_names
            assert "invoices" not in xl_file.sheet_names

        finally:
            if output_path.exists():
                output_path.unlink()

    def test_export_without_metadata(self, sample_db):
        """Test exporting without metadata sheet."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            output_path = Path(f.name)

        try:
            exporter = XlsxExporter(sample_db, output_path)
            result = exporter.export(include_metadata=False)

            xl_file = pd.ExcelFile(result)
            assert "README" not in xl_file.sheet_names

        finally:
            if output_path.exists():
                output_path.unlink()

    def test_get_table_list(self, sample_db):
        """Test getting list of tables."""
        exporter = XlsxExporter(sample_db, Path("dummy.xlsx"))
        tables = exporter.get_table_list()

        assert "clients" in tables
        assert "invoices" in tables
        assert "sqlite_sequence" not in tables

    def test_invalid_table_name(self, sample_db):
        """Test error handling for invalid table names."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            output_path = Path(f.name)

        try:
            exporter = XlsxExporter(sample_db, output_path)

            with pytest.raises(ValueError, match="Tables not found"):
                exporter.export(tables=["nonexistent_table"])

        finally:
            if output_path.exists():
                output_path.unlink()

    def test_missing_database(self):
        """Test error handling for missing database."""
        exporter = XlsxExporter(Path("nonexistent.db"), Path("output.xlsx"))

        with pytest.raises(FileNotFoundError):
            exporter.export()

    def test_progress_callback(self, sample_db):
        """Test progress callback functionality."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            output_path = Path(f.name)

        try:
            exporter = XlsxExporter(sample_db, output_path)
            progress_calls = []

            def callback(table_name: str, current: int, total: int):
                progress_calls.append((table_name, current, total))

            exporter.export(progress_callback=callback)

            # Should have been called for each table
            assert len(progress_calls) == 2
            assert progress_calls[0][1] == 1  # First table, current = 1
            assert progress_calls[1][1] == 2  # Second table, current = 2
            assert all(call[2] == 2 for call in progress_calls)  # total = 2

        finally:
            if output_path.exists():
                output_path.unlink()


class TestCsvExporter:
    """Test cases for CSV exporter."""

    def test_export_all_tables(self, sample_db):
        """Test exporting all tables to CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export"

            exporter = CsvExporter(sample_db, output_path)
            result = exporter.export()

            assert result.exists()
            assert result.is_dir()

            # Check CSV files exist
            clients_csv = result / "clients.csv"
            invoices_csv = result / "invoices.csv"
            readme = result / "README.txt"

            assert clients_csv.exists()
            assert invoices_csv.exists()
            assert readme.exists()

            # Verify exported data
            df_clients = pd.read_csv(clients_csv)
            df_invoices = pd.read_csv(invoices_csv)

            assert len(df_clients) == 2
            assert len(df_invoices) == 2

    def test_export_specific_tables(self, sample_db):
        """Test exporting specific tables to CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export"

            exporter = CsvExporter(sample_db, output_path)
            result = exporter.export(tables=["clients"])

            assert (result / "clients.csv").exists()
            assert not (result / "invoices.csv").exists()

    def test_export_without_metadata(self, sample_db):
        """Test exporting without README."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export"

            exporter = CsvExporter(sample_db, output_path)
            result = exporter.export(include_metadata=False)

            assert not (result / "README.txt").exists()

    def test_get_table_list(self, sample_db):
        """Test getting list of tables."""
        exporter = CsvExporter(sample_db, Path("dummy"))
        tables = exporter.get_table_list()

        assert "clients" in tables
        assert "invoices" in tables

    def test_invalid_table_name(self, sample_db):
        """Test error handling for invalid table names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export"

            exporter = CsvExporter(sample_db, output_path)

            with pytest.raises(ValueError, match="Tables not found"):
                exporter.export(tables=["nonexistent_table"])

    def test_missing_database(self):
        """Test error handling for missing database."""
        exporter = CsvExporter(Path("nonexistent.db"), Path("output"))

        with pytest.raises(FileNotFoundError):
            exporter.export()

    def test_progress_callback(self, sample_db):
        """Test progress callback functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export"

            exporter = CsvExporter(sample_db, output_path)
            progress_calls = []

            def callback(table_name: str, current: int, total: int):
                progress_calls.append((table_name, current, total))

            exporter.export(progress_callback=callback)

            # Should have been called for each table
            assert len(progress_calls) == 2
            assert progress_calls[0][1] == 1
            assert progress_calls[1][1] == 2
            assert all(call[2] == 2 for call in progress_calls)
