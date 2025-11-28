"""Unit tests for MapReportGenerator."""

import json
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open
import pytest
from datetime import datetime

from src.reports.map_report_generator import MapReportGenerator


class TestMapReportGenerator:
    """Test suite for MapReportGenerator."""

    @pytest.fixture
    def temp_output_dir(self, tmp_path):
        """Create temporary output directory."""
        return tmp_path

    @pytest.fixture
    def report_generator(self, temp_output_dir):
        """Create MapReportGenerator instance."""
        return MapReportGenerator(output_dir=temp_output_dir)

    @pytest.fixture
    def sample_entity_results(self):
        """Create sample entity results for testing."""
        return {
            "clients": {"total_entities": 150, "total_pages": 3, "entity_type": "clients"},
            "invoices": {"total_entities": 200, "total_pages": 4, "entity_type": "invoices"},
            "quotes": {"total_entities": 75, "total_pages": 2, "entity_type": "quotes"},
        }

    @pytest.fixture
    def sample_totals(self):
        """Create sample totals for testing."""
        return {"total_entities": 425, "entity_types_count": 3}

    @pytest.fixture
    def sample_hotspots(self):
        """Create sample hotspots for testing."""
        return {
            "clients": [
                {
                    "entity_id": "client_1",
                    "entity_type": "clients",
                    "total_relations": 100,
                    "relations": {"notes": 60, "attachments": 40},
                },
                {
                    "entity_id": "client_2",
                    "entity_type": "clients",
                    "total_relations": 75,
                    "relations": {"notes": 50, "attachments": 25},
                },
            ],
            "invoices": [
                {
                    "entity_id": "invoice_1",
                    "entity_type": "invoices",
                    "total_relations": 50,
                    "relations": {"notes": 30, "attachments": 20},
                }
            ],
        }

    @pytest.fixture
    def sample_density_stats(self):
        """Create sample density statistics for testing."""
        return {
            "clients": {
                "total_entities": 150,
                "avg_relations": 12.5,
                "max_relations": 100,
                "entities_with_relations": 120,
            },
            "invoices": {
                "total_entities": 200,
                "avg_relations": 8.3,
                "max_relations": 50,
                "entities_with_relations": 180,
            },
        }

    def test_report_generator_initialization(self, temp_output_dir):
        """Test MapReportGenerator initializes with output directory."""
        generator = MapReportGenerator(output_dir=temp_output_dir)
        assert generator._output_dir == temp_output_dir

    def test_report_generator_default_output_dir(self):
        """Test MapReportGenerator uses current directory as default."""
        generator = MapReportGenerator()
        assert generator._output_dir == Path(".")

    def test_generate_report_creates_files(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test generate_report creates both Markdown and JSON files."""
        markdown_path, json_path = report_generator.generate_report(
            snapshot_id="snap_123",
            label="test-report",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
        )

        assert Path(markdown_path).exists()
        assert Path(json_path).exists()
        assert markdown_path.endswith(".md")
        assert json_path.endswith(".json")

    def test_generate_report_filenames_include_label_and_timestamp(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test generated report filenames include label and timestamp."""
        markdown_path, json_path = report_generator.generate_report(
            snapshot_id="snap_123",
            label="my-test-label",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=30.0,
        )

        assert "my-test-label" in markdown_path
        assert "my-test-label" in json_path

    def test_markdown_report_contains_summary_section(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test Markdown report contains summary statistics section."""
        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="summary-test",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
        )

        content = Path(markdown_path).read_text()

        assert "Summary Statistics" in content
        assert "Total Entities Discovered" in content
        assert "425" in content
        assert "Entity Types Extracted" in content
        assert "3" in content

    def test_markdown_report_contains_entity_breakdown_table(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test Markdown report contains entity type breakdown table."""
        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="breakdown-test",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
        )

        content = Path(markdown_path).read_text()

        assert "Entity Type Breakdown" in content
        assert "| Entity Type | Count | Pages | Avg/Page |" in content
        assert "clients" in content
        assert "150" in content
        assert "invoices" in content
        assert "200" in content

    def test_markdown_report_contains_density_analysis(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals, sample_density_stats
    ):
        """Test Markdown report contains density analysis when provided."""
        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="density-test",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
            density_stats_by_type=sample_density_stats,
        )

        content = Path(markdown_path).read_text()

        assert "Density Analysis" in content
        assert "Avg Relations" in content
        assert "Max Relations" in content
        assert "12.5" in content  # clients avg
        assert "100" in content  # clients max

    def test_markdown_report_contains_hotspots_section(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals, sample_hotspots
    ):
        """Test Markdown report contains hotspots section when provided."""
        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="hotspots-test",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
            hotspots_by_type=sample_hotspots,
        )

        content = Path(markdown_path).read_text()

        assert "Hotspot Entities" in content
        assert "client_1" in content
        assert "100" in content  # total relations
        assert "notes: 60" in content

    def test_markdown_report_contains_recommendations(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test Markdown report contains recommendations section."""
        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="recommendations-test",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
        )

        content = Path(markdown_path).read_text()

        assert "Extraction Recommendations" in content

    def test_json_report_structure(self, report_generator, temp_output_dir, sample_entity_results, sample_totals):
        """Test JSON report has correct structure."""
        _, json_path = report_generator.generate_report(
            snapshot_id="snap_123",
            label="json-test",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
        )

        with open(json_path, "r") as f:
            report_data = json.load(f)

        assert "snapshot_id" in report_data
        assert "label" in report_data
        assert "generated_at" in report_data
        assert "duration_seconds" in report_data
        assert "summary" in report_data
        assert "entity_results" in report_data
        assert "density_stats" in report_data
        assert "hotspots" in report_data

        assert report_data["snapshot_id"] == "snap_123"
        assert report_data["label"] == "json-test"
        assert report_data["duration_seconds"] == 45.5

    def test_recommendations_for_large_entity_count(self, report_generator, temp_output_dir, sample_totals):
        """Test recommendations identify large entity counts."""
        large_entity_results = {
            "clients": {"total_entities": 15000, "total_pages": 300, "entity_type": "clients"},
        }

        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="large-entities",
            entity_results=large_entity_results,
            totals={"total_entities": 15000, "entity_types_count": 1},
            duration=120.0,
        )

        content = Path(markdown_path).read_text()

        assert "Large entity count" in content or "15,000" in content
        assert "pagination" in content.lower() or "rate limit" in content.lower()

    def test_recommendations_for_high_relation_density(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test recommendations identify high relation density."""
        high_density_stats = {
            "clients": {
                "total_entities": 100,
                "avg_relations": 25.5,  # High average
                "max_relations": 200,
                "entities_with_relations": 95,
            }
        }

        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="high-density",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
            density_stats_by_type=high_density_stats,
        )

        content = Path(markdown_path).read_text()

        assert "High average relations" in content or "25.5" in content

    def test_recommendations_for_hotspot_entities(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test recommendations identify hotspot entities with many relations."""
        extreme_hotspots = {
            "clients": [
                {
                    "entity_id": "client_extreme",
                    "entity_type": "clients",
                    "total_relations": 150,
                    "relations": {"notes": 100, "attachments": 50},
                }
            ]
        }

        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="extreme-hotspots",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
            hotspots_by_type=extreme_hotspots,
        )

        content = Path(markdown_path).read_text()

        assert ">100 related items" in content or "150 relations" in content

    def test_recommendations_default_message(self, report_generator, temp_output_dir, sample_totals):
        """Test default recommendation when no special conditions detected."""
        normal_results = {
            "clients": {"total_entities": 50, "total_pages": 1, "entity_type": "clients"},
        }

        normal_density = {
            "clients": {
                "total_entities": 50,
                "avg_relations": 5.0,
                "max_relations": 15,
                "entities_with_relations": 40,
            }
        }

        normal_hotspots = {
            "clients": [
                {
                    "entity_id": "client_1",
                    "entity_type": "clients",
                    "total_relations": 15,
                    "relations": {"notes": 10, "attachments": 5},
                }
            ]
        }

        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_123",
            label="normal",
            entity_results=normal_results,
            totals={"total_entities": 50, "entity_types_count": 1},
            duration=10.0,
            density_stats_by_type=normal_density,
            hotspots_by_type=normal_hotspots,
        )

        content = Path(markdown_path).read_text()

        assert "No special considerations" in content or "standard extraction" in content.lower()

    def test_markdown_report_header_contains_metadata(
        self, report_generator, temp_output_dir, sample_entity_results, sample_totals
    ):
        """Test Markdown report header contains snapshot metadata."""
        markdown_path, _ = report_generator.generate_report(
            snapshot_id="snap_abc123",
            label="metadata-test",
            entity_results=sample_entity_results,
            totals=sample_totals,
            duration=45.5,
        )

        content = Path(markdown_path).read_text()

        assert "Map Pass Report: metadata-test" in content
        assert "snap_abc123" in content
        assert "45.5s" in content
