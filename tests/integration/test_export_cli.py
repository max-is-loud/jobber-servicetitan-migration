"""Integration tests for export CLI commands."""

import tempfile
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()


def test_export_xlsx_command():
    """Test XLSX export command integration."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        output_path = Path(f.name)

    try:
        result = runner.invoke(
            app,
            [
                "export",
                "xlsx",
                "--db",
                "tightbeam.sqlite",
                "--output",
                str(output_path),
                "--tables",
                "clients",
            ],
        )

        assert result.exit_code == 0
        assert "Export complete" in result.stdout
        assert output_path.exists()

        # Verify exported data
        df = pd.read_excel(output_path, sheet_name="clients")
        assert len(df) > 0  # Should have client data

    finally:
        if output_path.exists():
            output_path.unlink()


def test_export_csv_command():
    """Test CSV export command integration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_export"

        result = runner.invoke(
            app,
            [
                "export",
                "csv",
                "--db",
                "tightbeam.sqlite",
                "--output",
                str(output_path),
                "--tables",
                "clients",
            ],
        )

        assert result.exit_code == 0
        assert "Export complete" in result.stdout
        assert output_path.exists()
        assert (output_path / "clients.csv").exists()
        assert (output_path / "README.txt").exists()


def test_export_help_command():
    """Test export help displays correctly."""
    result = runner.invoke(app, ["export", "--help"])

    assert result.exit_code == 0
    assert "Export database to XLSX or CSV formats" in result.stdout
    assert "xlsx" in result.stdout
    assert "csv" in result.stdout
    assert "all" in result.stdout


def test_export_xlsx_help():
    """Test XLSX export help."""
    result = runner.invoke(app, ["export", "xlsx", "--help"])

    assert result.exit_code == 0
    assert "Export database to XLSX (Excel) format" in result.stdout
    assert "--output" in result.stdout
    assert "--tables" in result.stdout
    assert "--no-metadata" in result.stdout
