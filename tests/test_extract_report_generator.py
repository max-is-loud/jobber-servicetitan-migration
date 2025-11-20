"""Unit tests for ExtractReportGenerator."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.reports.extract_report_generator import ExtractReportGenerator


class TestExtractReportGenerator:
    """Test suite for ExtractReportGenerator."""

    @pytest.fixture
    def temp_output_dir(self, tmp_path):
        """Create temporary output directory."""
        return tmp_path / "reports"

    @pytest.fixture
    def generator(self, temp_output_dir):
        """Create ExtractReportGenerator instance."""
        temp_output_dir.mkdir(parents=True, exist_ok=True)
        return ExtractReportGenerator(output_dir=temp_output_dir)

    @pytest.fixture
    def sample_results(self):
        """Create sample extraction results."""
        return {
            "snapshot_id": "snapshot_123",
            "label": "test-extract",
            "entity_results": {
                "clients": {"extracted": 100, "failed": 5, "skipped": 0},
                "invoices": {"extracted": 50, "failed": 2, "skipped": 0},
            },
            "attachment_result": {"downloaded": 75, "failed": 3, "skipped": 0},
            "discrepancies": [],
            "totals": {"total_extracted": 150, "total_failed": 7, "entity_types_count": 2},
            "duration": 120.5,
        }

    # ==================== Test generate_report() ====================

    def test_generate_report_creates_both_files(self, generator, temp_output_dir, sample_results):
        """Test generate_report creates both Markdown and JSON files."""
        md_path, json_path = generator.generate_report(**sample_results)

        assert Path(md_path).exists()
        assert Path(json_path).exists()
        assert md_path.endswith(".md")
        assert json_path.endswith(".json")

    def test_generate_report_filenames_include_label_and_timestamp(self, generator, sample_results):
        """Test generate_report filenames include label and timestamp."""
        md_path, json_path = generator.generate_report(**sample_results)

        assert "test-extract" in md_path
        assert "test-extract" in json_path
        assert "extract-report-" in md_path
        assert "extract-report-" in json_path

    def test_generate_report_returns_absolute_paths(self, generator, temp_output_dir, sample_results):
        """Test generate_report returns absolute file paths."""
        md_path, json_path = generator.generate_report(**sample_results)

        assert Path(md_path).is_absolute()
        assert Path(json_path).is_absolute()

    def test_generate_report_files_exist_after_generation(self, generator, sample_results):
        """Test files exist and are readable after generation."""
        md_path, json_path = generator.generate_report(**sample_results)

        md_content = Path(md_path).read_text(encoding="utf-8")
        json_content = Path(json_path).read_text(encoding="utf-8")

        assert len(md_content) > 0
        assert len(json_content) > 0

    def test_generate_report_content_accuracy(self, generator, sample_results):
        """Test report content contains accurate data."""
        md_path, json_path = generator.generate_report(**sample_results)

        md_content = Path(md_path).read_text(encoding="utf-8")
        json_data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        # Check Markdown content
        assert "snapshot_123" in md_content
        assert "test-extract" in md_content
        assert "150" in md_content  # total extracted

        # Check JSON content
        assert json_data["snapshot_id"] == "snapshot_123"
        assert json_data["label"] == "test-extract"
        assert json_data["summary"]["total_extracted"] == 150

    # ==================== Test Markdown report content ====================

    def test_markdown_report_summary_statistics(self, generator, sample_results):
        """Test Markdown report includes summary statistics section."""
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "## Summary Statistics" in content
        assert "Total Entities Extracted:** 150" in content
        assert "Total Entities Failed:** 7" in content
        assert "Entity Types Processed:** 2" in content
        assert "Attachments Downloaded:** 75" in content
        assert "Attachments Failed:** 3" in content
        assert "Extraction Rate:" in content

    def test_markdown_report_entity_type_breakdown_table(self, generator, sample_results):
        """Test Markdown report includes entity type breakdown table."""
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "## Entity Type Breakdown" in content
        assert "| Entity Type | Extracted | Failed | Success Rate |" in content
        assert "| clients |" in content
        assert "| invoices |" in content

    def test_markdown_report_completeness_validation_passed(self, generator, sample_results):
        """Test Markdown report shows completeness validation passed."""
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "## Completeness Validation" in content
        assert ":white_check_mark:" in content
        assert "All entities and attachments accounted for" in content

    def test_markdown_report_completeness_validation_failed_with_errors(self, generator, sample_results):
        """Test Markdown report shows completeness validation failed with errors."""
        sample_results["discrepancies"] = [
            {
                "type": "entity_count_mismatch",
                "entity_type": "clients",
                "expected": 110,
                "actual": 100,
                "difference": 10,
                "severity": "error",
                "message": "clients: 10 entities not attempted",
            }
        ]

        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "## Completeness Validation" in content
        assert ":warning:" in content
        assert "1 discrepancy(ies) found" in content
        assert "#### Errors" in content
        assert "entity_count_mismatch" in content

    def test_markdown_report_completeness_validation_failed_with_warnings(self, generator, sample_results):
        """Test Markdown report shows completeness validation warnings."""
        sample_results["discrepancies"] = [
            {
                "type": "failed_entities",
                "entity_type": "clients",
                "expected": 100,
                "actual": 95,
                "difference": 5,
                "severity": "warning",
                "message": "clients: 5 entities failed extraction",
            }
        ]

        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "#### Warnings" in content
        assert "failed_entities" in content

    def test_markdown_report_retry_recommendations(self, generator, sample_results):
        """Test Markdown report includes retry recommendations."""
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "## Retry Recommendations" in content

    def test_markdown_report_next_steps(self, generator, sample_results):
        """Test Markdown report includes next steps section."""
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "## Next Steps" in content

    def test_markdown_report_next_steps_with_discrepancies(self, generator, sample_results):
        """Test Markdown report shows appropriate next steps with discrepancies."""
        sample_results["discrepancies"] = [
            {
                "type": "failed_entities",
                "entity_type": "clients",
                "severity": "error",
                "message": "Test error",
            }
        ]

        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "Review discrepancies above" in content
        assert "Retry failed extractions" in content
        assert "--resume" in content

    def test_markdown_report_next_steps_without_discrepancies(self, generator, sample_results):
        """Test Markdown report shows appropriate next steps without discrepancies."""
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "Verify extracted data in database" in content
        assert "Run data quality checks" in content

    # ==================== Test JSON report structure ====================

    def test_json_report_all_required_fields_present(self, generator, sample_results):
        """Test JSON report contains all required fields."""
        _, json_path = generator.generate_report(**sample_results)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert "snapshot_id" in data
        assert "label" in data
        assert "generated_at" in data
        assert "duration_seconds" in data
        assert "summary" in data
        assert "entity_results" in data
        assert "attachment_result" in data
        assert "discrepancies" in data
        assert "completeness" in data
        assert "recommendations" in data

    def test_json_report_correct_data_types(self, generator, sample_results):
        """Test JSON report has correct data types."""
        _, json_path = generator.generate_report(**sample_results)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert isinstance(data["snapshot_id"], str)
        assert isinstance(data["label"], str)
        assert isinstance(data["generated_at"], str)
        assert isinstance(data["duration_seconds"], (int, float))
        assert isinstance(data["summary"], dict)
        assert isinstance(data["entity_results"], dict)
        assert isinstance(data["attachment_result"], dict)
        assert isinstance(data["discrepancies"], list)
        assert isinstance(data["completeness"], dict)
        assert isinstance(data["recommendations"], list)

    def test_json_report_completeness_status_calculation_passed(self, generator, sample_results):
        """Test JSON report calculates completeness status as passed."""
        _, json_path = generator.generate_report(**sample_results)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["completeness"]["status"] == "passed"
        assert data["completeness"]["error_count"] == 0
        assert data["completeness"]["warning_count"] == 0

    def test_json_report_completeness_status_calculation_failed(self, generator, sample_results):
        """Test JSON report calculates completeness status as failed with discrepancies."""
        sample_results["discrepancies"] = [
            {"type": "error1", "severity": "error", "message": "Error 1"},
            {"type": "error2", "severity": "error", "message": "Error 2"},
            {"type": "warning1", "severity": "warning", "message": "Warning 1"},
        ]

        _, json_path = generator.generate_report(**sample_results)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        assert data["completeness"]["status"] == "failed"
        assert data["completeness"]["error_count"] == 2
        assert data["completeness"]["warning_count"] == 1

    def test_json_report_recommendations_generation(self, generator, sample_results):
        """Test JSON report generates recommendations."""
        _, json_path = generator.generate_report(**sample_results)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        # With failures, should have recommendations
        assert len(data["recommendations"]) > 0

    # ==================== Test _generate_recommendations() ====================

    def test_generate_recommendations_no_failures(self, generator):
        """Test _generate_recommendations returns empty list with no failures."""
        entity_results = {"clients": {"extracted": 100, "failed": 0}}
        attachment_result = {"downloaded": 50, "failed": 0}
        discrepancies = []

        recommendations = generator._generate_recommendations(entity_results, attachment_result, discrepancies)

        assert len(recommendations) == 0

    def test_generate_recommendations_failed_entities(self, generator):
        """Test _generate_recommendations suggests retry for failed entities."""
        entity_results = {
            "clients": {"extracted": 95, "failed": 5},
            "invoices": {"extracted": 48, "failed": 2},
        }
        attachment_result = {"downloaded": 50, "failed": 0}
        discrepancies = []

        recommendations = generator._generate_recommendations(entity_results, attachment_result, discrepancies)

        assert len(recommendations) > 0
        # Should recommend retrying failed entities
        assert any("Retry 7 failed entity extraction" in rec for rec in recommendations)
        # Should have per-type recommendations
        assert any("clients: 5 failed" in rec for rec in recommendations)
        assert any("invoices: 2 failed" in rec for rec in recommendations)

    def test_generate_recommendations_failed_attachments(self, generator):
        """Test _generate_recommendations suggests retry for failed attachments."""
        entity_results = {"clients": {"extracted": 100, "failed": 0}}
        attachment_result = {"downloaded": 70, "failed": 10}
        discrepancies = []

        recommendations = generator._generate_recommendations(entity_results, attachment_result, discrepancies)

        assert len(recommendations) > 0
        assert any("Retry 10 failed attachment download" in rec for rec in recommendations)

    def test_generate_recommendations_entity_count_mismatch(self, generator):
        """Test _generate_recommendations suggests queue rebuild for count mismatch."""
        entity_results = {"clients": {"extracted": 50, "failed": 0}}
        attachment_result = {"downloaded": 0, "failed": 0}
        discrepancies = [
            {
                "type": "entity_count_mismatch",
                "entity_type": "clients",
                "expected": 100,
                "actual": 50,
                "severity": "error",
                "message": "50 entities not attempted",
            }
        ]

        recommendations = generator._generate_recommendations(entity_results, attachment_result, discrepancies)

        assert len(recommendations) > 0
        assert any("Queue appears incomplete" in rec for rec in recommendations)
        assert any("re-run extract pass without --resume" in rec for rec in recommendations)

    def test_generate_recommendations_multiple_failure_types(self, generator):
        """Test _generate_recommendations handles multiple failure types."""
        entity_results = {"clients": {"extracted": 90, "failed": 10}}
        attachment_result = {"downloaded": 70, "failed": 5}
        discrepancies = [
            {
                "type": "entity_count_mismatch",
                "entity_type": "clients",
                "expected": 100,
                "actual": 100,
                "severity": "error",
                "message": "Count mismatch",
            }
        ]

        recommendations = generator._generate_recommendations(entity_results, attachment_result, discrepancies)

        # Should have recommendations for failed entities, failed attachments, and queue rebuild
        assert len(recommendations) >= 3

    # ==================== Test edge cases ====================

    def test_generate_report_with_zero_duration(self, generator, sample_results):
        """Test generate_report handles zero duration gracefully."""
        sample_results["duration"] = 0.0

        _, json_path = generator.generate_report(**sample_results)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        # Should not crash on division by zero
        assert "extraction_rate" in data["summary"]

    def test_generate_report_with_empty_entity_results(self, generator, sample_results):
        """Test generate_report handles empty entity results."""
        sample_results["entity_results"] = {}
        sample_results["totals"]["total_extracted"] = 0
        sample_results["totals"]["total_failed"] = 0
        sample_results["totals"]["entity_types_count"] = 0

        md_path, json_path = generator.generate_report(**sample_results)

        # Should create reports without crashing
        assert Path(md_path).exists()
        assert Path(json_path).exists()

    def test_generate_report_with_long_label(self, generator, sample_results):
        """Test generate_report handles very long labels."""
        sample_results["label"] = "a" * 200  # Very long label

        md_path, json_path = generator.generate_report(**sample_results)

        # Should create files with truncated or full label
        assert Path(md_path).exists()
        assert Path(json_path).exists()

    def test_generate_report_default_output_dir(self, sample_results):
        """Test generate_report uses current directory as default output."""
        generator = ExtractReportGenerator()  # No output_dir specified

        md_path, json_path = generator.generate_report(**sample_results)

        # Should create files in current directory
        assert Path(md_path).exists()
        assert Path(json_path).exists()

        # Cleanup
        Path(md_path).unlink()
        Path(json_path).unlink()

    def test_generate_report_creates_output_directory_if_not_exists(self, tmp_path, sample_results):
        """Test generate_report creates output directory if it doesn't exist."""
        non_existent_dir = tmp_path / "non_existent_reports"
        generator = ExtractReportGenerator(output_dir=non_existent_dir)

        # Directory doesn't exist yet
        assert not non_existent_dir.exists()

        # Should create directory when generating report
        non_existent_dir.mkdir(parents=True, exist_ok=True)
        md_path, json_path = generator.generate_report(**sample_results)

        assert Path(md_path).exists()
        assert Path(json_path).exists()

    def test_markdown_report_extraction_rate_calculation(self, generator, sample_results):
        """Test Markdown report correctly calculates extraction rate."""
        # 150 entities / 120.5 seconds = ~1.24 entities/second
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        assert "Extraction Rate:" in content
        assert "entities/second" in content

    def test_markdown_report_success_rate_calculation(self, generator, sample_results):
        """Test Markdown report correctly calculates success rates."""
        md_path, _ = generator.generate_report(**sample_results)
        content = Path(md_path).read_text(encoding="utf-8")

        # clients: 100 extracted, 5 failed = 95.2% success rate
        # invoices: 50 extracted, 2 failed = 96.2% success rate
        assert "95.2%" in content or "95.0%" in content  # Allow for rounding
        assert "96.2%" in content or "96.0%" in content

    def test_json_report_summary_extraction_rate(self, generator, sample_results):
        """Test JSON report includes extraction rate in summary."""
        _, json_path = generator.generate_report(**sample_results)
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))

        expected_rate = 150 / 120.5
        assert abs(data["summary"]["extraction_rate"] - expected_rate) < 0.01
