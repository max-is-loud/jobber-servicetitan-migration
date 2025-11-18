"""Migration report generator for creating extraction summaries.

Generates comprehensive migration reports in text and JSON formats,
aggregating data from extractor summaries to provide insights into
migration performance, API costs, and success rates.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class MigrationReportGenerator:
    """Generates migration summary reports in multiple formats.

    Creates detailed reports from extractor summaries, including:
    - Entity counts and success rates
    - Timing and performance metrics
    - API cost tracking (GraphQL query costs)
    - Rate limiting statistics
    - Error summaries

    Supports both human-readable text format and structured JSON format
    for programmatic consumption and historical tracking.
    """

    def __init__(self, migration_name: str = "migration"):
        """Initialize report generator.

        Args:
            migration_name: Name/identifier for this migration
        """
        self.migration_name = migration_name
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.extractor_summaries: dict[str, dict[str, Any]] = {}

    def add_extractor_summary(
        self, entity_type: str, summary: dict[str, Any]
    ) -> None:
        """Add an extractor summary to the report.

        Args:
            entity_type: Type of entity (e.g., "clients", "invoices")
            summary: Extractor summary dictionary containing metrics
        """
        self.extractor_summaries[entity_type] = summary

    def set_timing(self, start_time: datetime, end_time: datetime) -> None:
        """Set migration timing information.

        Args:
            start_time: Migration start timestamp
            end_time: Migration end timestamp
        """
        self.start_time = start_time
        self.end_time = end_time

    def generate_text_report(self) -> str:
        """Generate human-readable text report.

        Returns:
            Formatted text report string
        """
        lines = []
        lines.append("=" * 80)
        lines.append(f"MIGRATION SUMMARY REPORT: {self.migration_name}")
        lines.append("=" * 80)
        lines.append("")

        # Timing information
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            lines.append(f"Start Time:  {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"End Time:    {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"Duration:    {self._format_duration(duration.total_seconds())}")
            lines.append("")

        # Overall statistics
        total_entities = sum(
            summary.get("total_extracted", 0)
            for summary in self.extractor_summaries.values()
        )
        total_pages = sum(
            summary.get("pages_fetched", 0)
            for summary in self.extractor_summaries.values()
        )
        total_errors = sum(
            summary.get("errors", 0) for summary in self.extractor_summaries.values()
        )

        lines.append("OVERALL STATISTICS")
        lines.append("-" * 80)
        lines.append(f"Total Entities Extracted: {total_entities:,}")
        lines.append(f"Total Pages Fetched:      {total_pages:,}")
        lines.append(f"Total Errors:             {total_errors:,}")
        lines.append("")

        # Per-entity summaries
        lines.append("ENTITY BREAKDOWN")
        lines.append("-" * 80)
        for entity_type, summary in sorted(self.extractor_summaries.items()):
            lines.append(f"\n{entity_type.upper()}:")
            lines.append(f"  Extracted:     {summary.get('total_extracted', 0):,}")
            lines.append(f"  Pages:         {summary.get('pages_fetched', 0):,}")
            lines.append(f"  Errors:        {summary.get('errors', 0):,}")

            # Related entities (like notes)
            related = summary.get("related_entities", {})
            if related:
                lines.append("  Related Entities:")
                for rel_type, count in related.items():
                    lines.append(f"    {rel_type}: {count:,}")

            # Timing
            if "duration_seconds" in summary:
                duration_str = self._format_duration(summary["duration_seconds"])
                lines.append(f"  Duration:      {duration_str}")

                # Calculate rate
                if summary["duration_seconds"] > 0:
                    rate = summary.get("total_extracted", 0) / summary["duration_seconds"]
                    lines.append(f"  Rate:          {rate:.2f} entities/second")

        lines.append("")
        lines.append("=" * 80)
        return "\n".join(lines)

    def generate_json_report(self) -> str:
        """Generate structured JSON report.

        Returns:
            JSON string with complete migration data
        """
        report_data = {
            "migration_name": self.migration_name,
            "generated_at": datetime.now().isoformat(),
            "timing": {},
            "summary": {
                "total_entities": 0,
                "total_pages": 0,
                "total_errors": 0,
            },
            "extractors": self.extractor_summaries,
        }

        # Add timing if available
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            report_data["timing"] = {
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
                "duration_seconds": duration,
                "duration_formatted": self._format_duration(duration),
            }

        # Calculate summary statistics
        for summary in self.extractor_summaries.values():
            report_data["summary"]["total_entities"] += summary.get(
                "total_extracted", 0
            )
            report_data["summary"]["total_pages"] += summary.get("pages_fetched", 0)
            report_data["summary"]["total_errors"] += summary.get("errors", 0)

        return json.dumps(report_data, indent=2)

    def save_text_report(self, output_path: Path) -> None:
        """Save text report to file.

        Args:
            output_path: Path where text report will be saved
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.generate_text_report())

    def save_json_report(self, output_path: Path) -> None:
        """Save JSON report to file.

        Args:
            output_path: Path where JSON report will be saved
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.generate_json_report())

    def save_reports(self, base_path: Path, include_timestamp: bool = True) -> tuple[Path, Path]:
        """Save both text and JSON reports.

        Args:
            base_path: Base directory for reports
            include_timestamp: Whether to include timestamp in filenames

        Returns:
            Tuple of (text_report_path, json_report_path)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") if include_timestamp else ""

        if timestamp:
            text_filename = f"migration_report_{timestamp}.txt"
            json_filename = f"migration_report_{timestamp}.json"
        else:
            text_filename = "migration_report.txt"
            json_filename = "migration_report.json"

        text_path = base_path / text_filename
        json_path = base_path / json_filename

        self.save_text_report(text_path)
        self.save_json_report(json_path)

        return text_path, json_path

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted string (e.g., "2h 34m 56s")
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")

        return " ".join(parts)
