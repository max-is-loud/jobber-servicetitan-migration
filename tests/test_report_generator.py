"""Tests for MigrationReportGenerator."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.reports.report_generator import MigrationReportGenerator


class TestMigrationReportGeneratorInitialization:
    """Test MigrationReportGenerator initialization."""

    def test_init_with_default_migration_name(self):
        """Test initialization with default migration name."""
        generator = MigrationReportGenerator()
        assert generator.migration_name == "migration"
        assert generator.start_time is None
        assert generator.end_time is None
        assert generator.extractor_summaries == {}

    def test_init_with_custom_migration_name(self):
        """Test initialization with custom migration name."""
        generator = MigrationReportGenerator(migration_name="test_migration")
        assert generator.migration_name == "test_migration"

    def test_init_creates_empty_summaries_dict(self):
        """Test initialization creates empty summaries dictionary."""
        generator = MigrationReportGenerator()
        assert isinstance(generator.extractor_summaries, dict)
        assert len(generator.extractor_summaries) == 0


class TestAddExtractorSummary:
    """Test adding extractor summaries to report."""

    def test_add_single_extractor_summary(self):
        """Test adding a single extractor summary."""
        generator = MigrationReportGenerator()
        summary = {
            "total_entities": 100,
            "total_pages": 5,
            "error_count": 0,
            "duration_seconds": 45.2,
        }
        generator.add_extractor_summary("clients", summary)
        assert "clients" in generator.extractor_summaries
        assert generator.extractor_summaries["clients"] == summary

    def test_add_multiple_extractor_summaries(self):
        """Test adding multiple extractor summaries."""
        generator = MigrationReportGenerator()
        clients_summary = {"total_entities": 100, "total_pages": 5, "error_count": 0}
        invoices_summary = {"total_entities": 250, "total_pages": 13, "error_count": 2}

        generator.add_extractor_summary("clients", clients_summary)
        generator.add_extractor_summary("invoices", invoices_summary)

        assert len(generator.extractor_summaries) == 2
        assert generator.extractor_summaries["clients"] == clients_summary
        assert generator.extractor_summaries["invoices"] == invoices_summary

    def test_add_extractor_summary_overwrites_existing(self):
        """Test that adding summary for same entity type overwrites previous."""
        generator = MigrationReportGenerator()
        old_summary = {"total_entities": 50}
        new_summary = {"total_entities": 100}

        generator.add_extractor_summary("clients", old_summary)
        generator.add_extractor_summary("clients", new_summary)

        assert generator.extractor_summaries["clients"] == new_summary

    def test_add_extractor_summary_with_related_entities(self):
        """Test adding summary with related entities tracking."""
        generator = MigrationReportGenerator()
        summary = {
            "total_entities": 100,
            "total_pages": 5,
            "error_count": 0,
            "related_entities": {"notes": 450},
        }
        generator.add_extractor_summary("clients", summary)
        assert generator.extractor_summaries["clients"]["related_entities"]["notes"] == 450


class TestSetTiming:
    """Test setting migration timing information."""

    def test_set_timing_stores_start_and_end(self):
        """Test that set_timing stores both timestamps."""
        generator = MigrationReportGenerator()
        start = datetime(2025, 1, 1, 10, 0, 0)
        end = datetime(2025, 1, 1, 10, 15, 30)

        generator.set_timing(start, end)

        assert generator.start_time == start
        assert generator.end_time == end

    def test_set_timing_can_be_updated(self):
        """Test that timing can be updated after being set."""
        generator = MigrationReportGenerator()
        old_start = datetime(2025, 1, 1, 10, 0, 0)
        old_end = datetime(2025, 1, 1, 10, 15, 0)
        new_start = datetime(2025, 1, 1, 11, 0, 0)
        new_end = datetime(2025, 1, 1, 11, 20, 0)

        generator.set_timing(old_start, old_end)
        generator.set_timing(new_start, new_end)

        assert generator.start_time == new_start
        assert generator.end_time == new_end


class TestGenerateTextReport:
    """Test text report generation."""

    def test_generate_text_report_basic_structure(self):
        """Test that text report has basic structure."""
        generator = MigrationReportGenerator(migration_name="test")
        report = generator.generate_text_report()

        assert "MIGRATION SUMMARY REPORT: test" in report
        assert "OVERALL STATISTICS" in report
        assert "ENTITY BREAKDOWN" in report
        assert "=" * 80 in report
        assert "-" * 80 in report

    def test_generate_text_report_with_no_data(self):
        """Test text report generation with no data."""
        generator = MigrationReportGenerator()
        report = generator.generate_text_report()

        assert "Total Entities Extracted: 0" in report
        assert "Total Pages Fetched:      0" in report
        assert "Total Errors:             0" in report

    def test_generate_text_report_with_single_extractor(self):
        """Test text report with single extractor summary."""
        generator = MigrationReportGenerator()
        generator.add_extractor_summary("clients", {"total_entities": 150, "total_pages": 8, "error_count": 1})
        report = generator.generate_text_report()

        assert "Total Entities Extracted: 150" in report
        assert "Total Pages Fetched:      8" in report
        assert "Total Errors:             1" in report
        assert "CLIENTS:" in report
        assert "Extracted:     150" in report
        assert "Pages:         8" in report
        assert "Errors:        1" in report

    def test_generate_text_report_with_multiple_extractors(self):
        """Test text report with multiple extractor summaries."""
        generator = MigrationReportGenerator()
        generator.add_extractor_summary("clients", {"total_entities": 150, "total_pages": 8, "error_count": 1})
        generator.add_extractor_summary("invoices", {"total_entities": 500, "total_pages": 25, "error_count": 3})
        report = generator.generate_text_report()

        # Overall totals
        assert "Total Entities Extracted: 650" in report
        assert "Total Pages Fetched:      33" in report
        assert "Total Errors:             4" in report

        # Individual extractors
        assert "CLIENTS:" in report
        assert "INVOICES:" in report

    def test_generate_text_report_with_timing(self):
        """Test text report includes timing information."""
        generator = MigrationReportGenerator()
        start = datetime(2025, 1, 1, 10, 0, 0)
        end = datetime(2025, 1, 1, 10, 15, 45)
        generator.set_timing(start, end)

        report = generator.generate_text_report()

        assert "Start Time:  2025-01-01 10:00:00" in report
        assert "End Time:    2025-01-01 10:15:45" in report
        assert "Duration:" in report
        assert "15m 45s" in report

    def test_generate_text_report_with_duration_formatting(self):
        """Test various duration formatting scenarios."""
        generator = MigrationReportGenerator()
        generator.add_extractor_summary("clients", {"total_entities": 100, "duration_seconds": 3725})  # 1h 2m 5s
        report = generator.generate_text_report()

        assert "Duration:      1h 2m 5s" in report

    def test_generate_text_report_with_rate_calculation(self):
        """Test that rate is calculated correctly."""
        generator = MigrationReportGenerator()
        generator.add_extractor_summary("clients", {"total_entities": 100, "duration_seconds": 50.0})
        report = generator.generate_text_report()

        assert "Rate:" in report
        assert "2.00 entities/second" in report

    def test_generate_text_report_with_related_entities(self):
        """Test text report shows related entities."""
        generator = MigrationReportGenerator()
        generator.add_extractor_summary(
            "clients",
            {
                "total_entities": 100,
                "total_pages": 5,
                "error_count": 0,
                "related_entities": {"notes": 450, "attachments": 23},
            },
        )
        report = generator.generate_text_report()

        assert "Related Entities:" in report
        assert "notes: 450" in report
        assert "attachments: 23" in report

    def test_generate_text_report_formats_large_numbers(self):
        """Test that large numbers are formatted with commas."""
        generator = MigrationReportGenerator()
        generator.add_extractor_summary("clients", {"total_entities": 1234567, "total_pages": 6173, "error_count": 42})
        report = generator.generate_text_report()

        assert "1,234,567" in report
        assert "6,173" in report


class TestGenerateJsonReport:
    """Test JSON report generation."""

    def test_generate_json_report_valid_json(self):
        """Test that JSON report is valid JSON."""
        generator = MigrationReportGenerator()
        json_report = generator.generate_json_report()

        # Should not raise exception
        data = json.loads(json_report)
        assert isinstance(data, dict)

    def test_generate_json_report_basic_structure(self):
        """Test JSON report has expected structure."""
        generator = MigrationReportGenerator(migration_name="test_migration")
        json_report = generator.generate_json_report()
        data = json.loads(json_report)

        assert data["migration_name"] == "test_migration"
        assert "generated_at" in data
        assert "timing" in data
        assert "summary" in data
        assert "extractors" in data

    def test_generate_json_report_summary_structure(self):
        """Test JSON report summary has correct fields."""
        generator = MigrationReportGenerator()
        json_report = generator.generate_json_report()
        data = json.loads(json_report)

        assert "total_entities" in data["summary"]
        assert "total_pages" in data["summary"]
        assert "total_errors" in data["summary"]

    def test_generate_json_report_with_no_data(self):
        """Test JSON report with no extractor data."""
        generator = MigrationReportGenerator()
        json_report = generator.generate_json_report()
        data = json.loads(json_report)

        assert data["summary"]["total_entities"] == 0
        assert data["summary"]["total_pages"] == 0
        assert data["summary"]["total_errors"] == 0
        assert data["extractors"] == {}

    def test_generate_json_report_with_extractors(self):
        """Test JSON report includes extractor summaries."""
        generator = MigrationReportGenerator()
        clients_summary = {"total_entities": 150, "total_pages": 8, "error_count": 1}
        generator.add_extractor_summary("clients", clients_summary)

        json_report = generator.generate_json_report()
        data = json.loads(json_report)

        assert data["summary"]["total_entities"] == 150
        assert data["summary"]["total_pages"] == 8
        assert data["summary"]["total_errors"] == 1
        assert "clients" in data["extractors"]
        assert data["extractors"]["clients"] == clients_summary

    def test_generate_json_report_with_timing(self):
        """Test JSON report includes timing information."""
        generator = MigrationReportGenerator()
        start = datetime(2025, 1, 1, 10, 0, 0)
        end = datetime(2025, 1, 1, 10, 15, 45)
        generator.set_timing(start, end)

        json_report = generator.generate_json_report()
        data = json.loads(json_report)

        assert "start_time" in data["timing"]
        assert "end_time" in data["timing"]
        assert "duration_seconds" in data["timing"]
        assert "duration_formatted" in data["timing"]
        assert data["timing"]["duration_seconds"] == 945.0  # 15m 45s
        assert data["timing"]["duration_formatted"] == "15m 45s"

    def test_generate_json_report_timing_is_iso_format(self):
        """Test that timing uses ISO 8601 format."""
        generator = MigrationReportGenerator()
        start = datetime(2025, 1, 1, 10, 0, 0)
        end = datetime(2025, 1, 1, 10, 15, 45)
        generator.set_timing(start, end)

        json_report = generator.generate_json_report()
        data = json.loads(json_report)

        assert data["timing"]["start_time"] == "2025-01-01T10:00:00"
        assert data["timing"]["end_time"] == "2025-01-01T10:15:45"

    def test_generate_json_report_aggregates_multiple_extractors(self):
        """Test JSON report aggregates data from multiple extractors."""
        generator = MigrationReportGenerator()
        generator.add_extractor_summary("clients", {"total_entities": 150, "total_pages": 8, "error_count": 1})
        generator.add_extractor_summary("invoices", {"total_entities": 500, "total_pages": 25, "error_count": 3})

        json_report = generator.generate_json_report()
        data = json.loads(json_report)

        assert data["summary"]["total_entities"] == 650
        assert data["summary"]["total_pages"] == 33
        assert data["summary"]["total_errors"] == 4


class TestFormatDuration:
    """Test duration formatting utility."""

    def test_format_duration_seconds_only(self):
        """Test formatting duration with seconds only."""
        result = MigrationReportGenerator._format_duration(45)
        assert result == "45s"

    def test_format_duration_minutes_and_seconds(self):
        """Test formatting duration with minutes and seconds."""
        result = MigrationReportGenerator._format_duration(125)  # 2m 5s
        assert result == "2m 5s"

    def test_format_duration_hours_minutes_seconds(self):
        """Test formatting duration with hours, minutes, and seconds."""
        result = MigrationReportGenerator._format_duration(3725)  # 1h 2m 5s
        assert result == "1h 2m 5s"

    def test_format_duration_exact_minute(self):
        """Test formatting duration with exact minutes."""
        result = MigrationReportGenerator._format_duration(120)  # 2m 0s
        assert result == "2m 0s"

    def test_format_duration_exact_hour(self):
        """Test formatting duration with exact hours."""
        result = MigrationReportGenerator._format_duration(3600)  # 1h 0m 0s
        assert result == "1h 0s"

    def test_format_duration_zero_seconds(self):
        """Test formatting duration of zero."""
        result = MigrationReportGenerator._format_duration(0)
        assert result == "0s"

    def test_format_duration_fractional_seconds(self):
        """Test formatting duration with fractional seconds (should truncate)."""
        result = MigrationReportGenerator._format_duration(125.7)
        assert result == "2m 5s"


class TestSaveTextReport:
    """Test saving text reports to files."""

    def test_save_text_report_creates_file(self):
        """Test that save_text_report creates a file."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            generator.add_extractor_summary("clients", {"total_entities": 100, "total_pages": 5, "error_count": 0})

            output_path = Path(tmpdir) / "report.txt"
            generator.save_text_report(output_path)

            assert output_path.exists()
            assert output_path.is_file()

    def test_save_text_report_content(self):
        """Test that saved text report has correct content."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator(migration_name="test")
            generator.add_extractor_summary("clients", {"total_entities": 100, "total_pages": 5, "error_count": 0})

            output_path = Path(tmpdir) / "report.txt"
            generator.save_text_report(output_path)

            content = output_path.read_text()
            assert "MIGRATION SUMMARY REPORT: test" in content
            assert "Total Entities Extracted: 100" in content

    def test_save_text_report_creates_parent_directories(self):
        """Test that save_text_report creates parent directories if needed."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            output_path = Path(tmpdir) / "reports" / "2025" / "report.txt"

            generator.save_text_report(output_path)

            assert output_path.exists()
            assert output_path.parent.exists()


class TestSaveJsonReport:
    """Test saving JSON reports to files."""

    def test_save_json_report_creates_file(self):
        """Test that save_json_report creates a file."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            generator.add_extractor_summary("clients", {"total_entities": 100, "total_pages": 5, "error_count": 0})

            output_path = Path(tmpdir) / "report.json"
            generator.save_json_report(output_path)

            assert output_path.exists()
            assert output_path.is_file()

    def test_save_json_report_content(self):
        """Test that saved JSON report has valid JSON content."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator(migration_name="test")
            generator.add_extractor_summary("clients", {"total_entities": 100, "total_pages": 5, "error_count": 0})

            output_path = Path(tmpdir) / "report.json"
            generator.save_json_report(output_path)

            content = output_path.read_text()
            data = json.loads(content)
            assert data["migration_name"] == "test"
            assert data["summary"]["total_entities"] == 100

    def test_save_json_report_creates_parent_directories(self):
        """Test that save_json_report creates parent directories if needed."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            output_path = Path(tmpdir) / "reports" / "2025" / "report.json"

            generator.save_json_report(output_path)

            assert output_path.exists()
            assert output_path.parent.exists()


class TestSaveReports:
    """Test saving both text and JSON reports together."""

    def test_save_reports_creates_both_files(self):
        """Test that save_reports creates both text and JSON files."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            generator.add_extractor_summary("clients", {"total_entities": 100, "total_pages": 5, "error_count": 0})

            base_path = Path(tmpdir)
            text_path, json_path = generator.save_reports(base_path, include_timestamp=False)

            assert text_path.exists()
            assert json_path.exists()
            assert text_path.name == "migration_report.txt"
            assert json_path.name == "migration_report.json"

    def test_save_reports_with_timestamp(self):
        """Test that save_reports includes timestamp when requested."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            base_path = Path(tmpdir)
            text_path, json_path = generator.save_reports(base_path, include_timestamp=True)

            assert text_path.exists()
            assert json_path.exists()
            assert "migration_report_" in text_path.name
            assert ".txt" in text_path.name
            assert "migration_report_" in json_path.name
            assert ".json" in json_path.name

    def test_save_reports_without_timestamp(self):
        """Test that save_reports uses simple names without timestamp."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            base_path = Path(tmpdir)
            text_path, json_path = generator.save_reports(base_path, include_timestamp=False)

            assert text_path.name == "migration_report.txt"
            assert json_path.name == "migration_report.json"

    def test_save_reports_returns_correct_paths(self):
        """Test that save_reports returns the correct file paths."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            base_path = Path(tmpdir)
            text_path, json_path = generator.save_reports(base_path, include_timestamp=False)

            assert text_path == base_path / "migration_report.txt"
            assert json_path == base_path / "migration_report.json"

    def test_save_reports_creates_base_directory(self):
        """Test that save_reports creates base directory if needed."""
        with TemporaryDirectory() as tmpdir:
            generator = MigrationReportGenerator()
            base_path = Path(tmpdir) / "reports"
            generator.save_reports(base_path, include_timestamp=False)

            assert base_path.exists()
            assert base_path.is_dir()


class TestReportGeneratorIntegration:
    """Integration tests for complete report generation workflow."""

    def test_complete_migration_report_workflow(self):
        """Test complete workflow with multiple extractors and timing."""
        generator = MigrationReportGenerator(migration_name="production_migration")

        # Set timing
        start = datetime(2025, 1, 15, 14, 30, 0)
        end = datetime(2025, 1, 15, 15, 45, 30)
        generator.set_timing(start, end)

        # Add multiple extractor summaries
        generator.add_extractor_summary(
            "clients",
            {
                "total_entities": 1523,
                "total_pages": 16,
                "error_count": 2,
                "duration_seconds": 245.5,
                "related_entities": {"notes": 4231},
            },
        )
        generator.add_extractor_summary(
            "invoices",
            {
                "total_entities": 8945,
                "total_pages": 90,
                "error_count": 5,
                "duration_seconds": 1823.2,
            },
        )
        generator.add_extractor_summary(
            "quotes",
            {
                "total_entities": 3421,
                "total_pages": 35,
                "error_count": 1,
                "duration_seconds": 892.1,
            },
        )

        # Generate both reports
        with TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            text_path, json_path = generator.save_reports(base_path, include_timestamp=False)

            # Verify text report
            text_content = text_path.read_text()
            assert "production_migration" in text_content
            assert "Total Entities Extracted: 13,889" in text_content
            assert "Total Pages Fetched:      141" in text_content
            assert "Total Errors:             8" in text_content
            assert "CLIENTS:" in text_content
            assert "INVOICES:" in text_content
            assert "QUOTES:" in text_content
            assert "notes: 4,231" in text_content

            # Verify JSON report
            json_content = json_path.read_text()
            data = json.loads(json_content)
            assert data["migration_name"] == "production_migration"
            assert data["summary"]["total_entities"] == 13889
            assert data["summary"]["total_pages"] == 141
            assert data["summary"]["total_errors"] == 8
            assert len(data["extractors"]) == 3
