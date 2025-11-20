"""Extract report generator for extract mode hydration results."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ExtractReportGenerator:
    """
    Generator for extract mode hydration reports.

    Creates detailed Markdown and JSON reports with summary statistics,
    completeness validation results, discrepancy analysis, and retry
    recommendations for failed extractions and downloads.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        """Initialize ExtractReportGenerator.

        Args:
            output_dir: Optional directory for report output (default: current directory)
        """
        self._output_dir = output_dir or Path(".")

    def generate_report(
        self,
        snapshot_id: str,
        label: str,
        entity_results: dict[str, Any],
        attachment_result: dict[str, Any],
        discrepancies: list[dict[str, Any]],
        totals: dict[str, Any],
        duration: float,
    ) -> tuple[str, str]:
        """
        Generate comprehensive extract pass report in Markdown and JSON formats.

        Args:
            snapshot_id: Map snapshot UUID
            label: Snapshot label
            entity_results: Dict mapping entity type to extraction results
            attachment_result: Attachment download results
            discrepancies: List of completeness validation discrepancies
            totals: Dict with aggregate statistics
            duration: Total execution time in seconds

        Returns:
            Tuple of (markdown_path, json_path) for generated reports
        """
        # Generate report content
        markdown_content = self._generate_markdown_report(
            snapshot_id=snapshot_id,
            label=label,
            entity_results=entity_results,
            attachment_result=attachment_result,
            discrepancies=discrepancies,
            totals=totals,
            duration=duration,
        )

        json_content = self._generate_json_report(
            snapshot_id=snapshot_id,
            label=label,
            entity_results=entity_results,
            attachment_result=attachment_result,
            discrepancies=discrepancies,
            totals=totals,
            duration=duration,
        )

        # Write reports to files
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        markdown_filename = f"extract-report-{label}-{timestamp}.md"
        json_filename = f"extract-report-{label}-{timestamp}.json"

        markdown_path = self._output_dir / markdown_filename
        json_path = self._output_dir / json_filename

        markdown_path.write_text(markdown_content, encoding="utf-8")
        json_path.write_text(json_content, encoding="utf-8")

        return str(markdown_path), str(json_path)

    def _generate_markdown_report(
        self,
        snapshot_id: str,
        label: str,
        entity_results: dict[str, Any],
        attachment_result: dict[str, Any],
        discrepancies: list[dict[str, Any]],
        totals: dict[str, Any],
        duration: float,
    ) -> str:
        """Generate Markdown format report."""
        lines = [
            f"# Extract Pass Report: {label}",
            "",
            f"**Snapshot ID:** `{snapshot_id}`  ",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Duration:** {duration:.1f}s  ",
            "",
        ]

        # Summary Statistics
        lines.extend([
            "## Summary Statistics",
            "",
            f"- **Total Entities Extracted:** {totals.get('total_extracted', 0):,}",
            f"- **Total Entities Failed:** {totals.get('total_failed', 0):,}",
            f"- **Entity Types Processed:** {totals.get('entity_types_count', 0)}",
            f"- **Attachments Downloaded:** {attachment_result.get('downloaded', 0):,}",
            f"- **Attachments Failed:** {attachment_result.get('failed', 0):,}",
            f"- **Extraction Rate:** {totals.get('total_extracted', 0) / duration if duration > 0 else 0:.1f} entities/second",
            "",
        ])

        # Entity Type Breakdown
        lines.extend([
            "## Entity Type Breakdown",
            "",
            "| Entity Type | Extracted | Failed | Success Rate |",
            "|-------------|-----------|--------|--------------|",
        ])

        for entity_type, result in sorted(entity_results.items()):
            extracted = result.get("extracted", 0)
            failed = result.get("failed", 0)
            total = extracted + failed
            success_rate = (extracted / total * 100) if total > 0 else 0
            lines.append(
                f"| {entity_type} | {extracted:,} | {failed:,} | {success_rate:.1f}% |"
            )

        lines.extend(["", ""])

        # Completeness Validation
        lines.extend([
            "## Completeness Validation",
            "",
        ])

        if discrepancies:
            lines.append(f"**Status:** :warning: {len(discrepancies)} discrepancy(ies) found")
            lines.append("")
            lines.append("### Discrepancies")
            lines.append("")

            # Group discrepancies by severity
            errors = [d for d in discrepancies if d.get("severity") == "error"]
            warnings = [d for d in discrepancies if d.get("severity") == "warning"]

            if errors:
                lines.extend([
                    "#### Errors",
                    "",
                ])
                for disc in errors:
                    lines.append(f"- **{disc.get('type')}**: {disc.get('message')}")
                lines.append("")

            if warnings:
                lines.extend([
                    "#### Warnings",
                    "",
                ])
                for disc in warnings:
                    lines.append(f"- **{disc.get('type')}**: {disc.get('message')}")
                lines.append("")
        else:
            lines.append("**Status:** :white_check_mark: All entities and attachments accounted for")
            lines.append("")

        # Retry Recommendations
        lines.extend([
            "## Retry Recommendations",
            "",
        ])

        recommendations = self._generate_recommendations(
            entity_results, attachment_result, discrepancies
        )

        if recommendations:
            for rec in recommendations:
                lines.append(f"- {rec}")
        else:
            lines.append("No retry needed - extraction completed successfully!")

        lines.append("")

        # Next Steps
        lines.extend([
            "## Next Steps",
            "",
        ])

        if discrepancies:
            lines.extend([
                "1. Review discrepancies above",
                "2. Retry failed extractions using `--resume` flag",
                "3. Investigate entity-specific failures in logs",
                "4. Run reconciliation pass to detect data drift",
            ])
        else:
            lines.extend([
                "1. Verify extracted data in database",
                "2. Run data quality checks",
                "3. Archive or delete map snapshot if no longer needed",
            ])

        lines.append("")

        return "\n".join(lines)

    def _generate_json_report(
        self,
        snapshot_id: str,
        label: str,
        entity_results: dict[str, Any],
        attachment_result: dict[str, Any],
        discrepancies: list[dict[str, Any]],
        totals: dict[str, Any],
        duration: float,
    ) -> str:
        """Generate JSON format report."""
        report = {
            "snapshot_id": snapshot_id,
            "label": label,
            "generated_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "summary": {
                "total_extracted": totals.get("total_extracted", 0),
                "total_failed": totals.get("total_failed", 0),
                "entity_types_count": totals.get("entity_types_count", 0),
                "extraction_rate": totals.get("total_extracted", 0) / duration if duration > 0 else 0,
            },
            "entity_results": entity_results,
            "attachment_result": attachment_result,
            "discrepancies": discrepancies,
            "completeness": {
                "status": "passed" if not discrepancies else "failed",
                "error_count": len([d for d in discrepancies if d.get("severity") == "error"]),
                "warning_count": len([d for d in discrepancies if d.get("severity") == "warning"]),
            },
            "recommendations": self._generate_recommendations(
                entity_results, attachment_result, discrepancies
            ),
        }

        return json.dumps(report, indent=2)

    def _generate_recommendations(
        self,
        entity_results: dict[str, Any],
        attachment_result: dict[str, Any],
        discrepancies: list[dict[str, Any]],
    ) -> list[str]:
        """Generate retry recommendations based on results and discrepancies."""
        recommendations = []

        # Check for failed entities
        total_failed = sum(result.get("failed", 0) for result in entity_results.values())
        if total_failed > 0:
            recommendations.append(
                f"Retry {total_failed} failed entity extraction(s) using `tightbeam migrate extract --snapshot-id <id> --resume`"
            )

            # Per-type recommendations
            for entity_type, result in entity_results.items():
                failed = result.get("failed", 0)
                if failed > 0:
                    recommendations.append(
                        f"  - {entity_type}: {failed} failed extraction(s) - check logs for API errors"
                    )

        # Check for failed attachments
        attachment_failed = attachment_result.get("failed", 0)
        if attachment_failed > 0:
            recommendations.append(
                f"Retry {attachment_failed} failed attachment download(s) - attachments can be retried independently"
            )

        # Check for entity count mismatches (queue incomplete)
        entity_mismatches = [
            d for d in discrepancies if d.get("type") == "entity_count_mismatch"
        ]
        if entity_mismatches:
            recommendations.append(
                "Queue appears incomplete - re-run extract pass without --resume to rebuild queue from map snapshot"
            )

        return recommendations
