"""Map report generator for map mode extraction results."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class MapReportGenerator:
    """
    Generator for map mode extraction reports.

    Creates detailed Markdown and JSON reports with summary statistics,
    density analysis, extraction estimates, and recommendations for
    optimizing the full extraction pass.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        """Initialize MapReportGenerator.

        Args:
            output_dir: Optional directory for report output (default: current directory)
        """
        self._output_dir = output_dir or Path(".")

    def generate_report(
        self,
        snapshot_id: str,
        label: str,
        entity_results: dict[str, Any],
        totals: dict[str, Any],
        duration: float,
        hotspots_by_type: Optional[dict[str, list[dict[str, Any]]]] = None,
        density_stats_by_type: Optional[dict[str, dict[str, Any]]] = None,
    ) -> tuple[str, str]:
        """
        Generate comprehensive map pass report in Markdown and JSON formats.

        Args:
            snapshot_id: Map snapshot UUID
            label: Snapshot label
            entity_results: Dict mapping entity type to extraction results
            totals: Dict with aggregate statistics
            duration: Total execution time in seconds
            hotspots_by_type: Optional dict mapping entity type to hotspot entities
            density_stats_by_type: Optional dict mapping entity type to density statistics

        Returns:
            Tuple of (markdown_path, json_path) for generated reports
        """
        # Generate report content
        markdown_content = self._generate_markdown_report(
            snapshot_id=snapshot_id,
            label=label,
            entity_results=entity_results,
            totals=totals,
            duration=duration,
            hotspots_by_type=hotspots_by_type or {},
            density_stats_by_type=density_stats_by_type or {},
        )

        json_content = self._generate_json_report(
            snapshot_id=snapshot_id,
            label=label,
            entity_results=entity_results,
            totals=totals,
            duration=duration,
            hotspots_by_type=hotspots_by_type or {},
            density_stats_by_type=density_stats_by_type or {},
        )

        # Write reports to files
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        markdown_filename = f"map-report-{label}-{timestamp}.md"
        json_filename = f"map-report-{label}-{timestamp}.json"

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
        totals: dict[str, Any],
        duration: float,
        hotspots_by_type: dict[str, list[dict[str, Any]]],
        density_stats_by_type: dict[str, dict[str, Any]],
    ) -> str:
        """Generate Markdown format report."""
        lines = [
            f"# Map Pass Report: {label}",
            "",
            f"**Snapshot ID:** `{snapshot_id}`  ",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Duration:** {duration:.1f}s  ",
            "",
            "## Summary Statistics",
            "",
            f"- **Total Entities Discovered:** {totals['total_entities']:,}",
            f"- **Entity Types Extracted:** {totals['entity_types_count']}",
            f"- **Average Entities/Second:** {totals['total_entities'] / duration if duration > 0 else 0:.1f}",
            "",
            "## Entity Type Breakdown",
            "",
            "| Entity Type | Count | Pages | Avg/Page |",
            "|-------------|-------|-------|----------|",
        ]

        for entity_type, result in sorted(entity_results.items()):
            total = result["total_entities"]
            pages = result["total_pages"]
            avg_per_page = total / pages if pages > 0 else 0
            lines.append(f"| {entity_type} | {total:,} | {pages} | {avg_per_page:.1f} |")

        # Add density analysis if available
        if density_stats_by_type:
            lines.extend([
                "",
                "## Density Analysis",
                "",
                "Relation counts per entity type (notes, attachments, etc.):",
                "",
                "| Entity Type | Total Entities | Avg Relations | Max Relations | With Relations |",
                "|-------------|----------------|---------------|---------------|----------------|",
            ])

            for entity_type, stats in sorted(density_stats_by_type.items()):
                lines.append(
                    f"| {entity_type} | {stats['total_entities']:,} | "
                    f"{stats['avg_relations']:.1f} | {stats['max_relations']} | "
                    f"{stats['entities_with_relations']:,} ({stats['entities_with_relations'] / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0:.0f}%) |"
                )

        # Add hotspots if available
        if hotspots_by_type:
            lines.extend([
                "",
                "## Hotspot Entities (High Relation Counts)",
                "",
                "Top entities with the most related items (notes, attachments, etc.):",
                "",
            ])

            for entity_type, hotspots in sorted(hotspots_by_type.items()):
                if hotspots:
                    lines.append(f"### {entity_type}")
                    lines.append("")
                    lines.append("| Entity ID | Total Relations | Details |")
                    lines.append("|-----------|-----------------|---------|")

                    for hotspot in hotspots[:10]:  # Top 10
                        relations_str = ", ".join(
                            f"{k}: {v}" for k, v in hotspot["relations"].items() if v > 0
                        )
                        lines.append(
                            f"| `{hotspot['entity_id']}` | {hotspot['total_relations']} | {relations_str} |"
                        )

                    lines.append("")

        # Add recommendations
        lines.extend([
            "",
            "## Extraction Recommendations",
            "",
            self._generate_recommendations(
                entity_results=entity_results,
                density_stats_by_type=density_stats_by_type,
                hotspots_by_type=hotspots_by_type,
            ),
        ])

        return "\n".join(lines)

    def _generate_json_report(
        self,
        snapshot_id: str,
        label: str,
        entity_results: dict[str, Any],
        totals: dict[str, Any],
        duration: float,
        hotspots_by_type: dict[str, list[dict[str, Any]]],
        density_stats_by_type: dict[str, dict[str, Any]],
    ) -> str:
        """Generate JSON format report."""
        report = {
            "snapshot_id": snapshot_id,
            "label": label,
            "generated_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "summary": totals,
            "entity_results": entity_results,
            "density_stats": density_stats_by_type,
            "hotspots": hotspots_by_type,
        }

        return json.dumps(report, indent=2)

    def _generate_recommendations(
        self,
        entity_results: dict[str, Any],
        density_stats_by_type: dict[str, dict[str, Any]],
        hotspots_by_type: dict[str, list[dict[str, Any]]],
    ) -> str:
        """Generate recommendations based on map pass analysis."""
        recommendations = []

        # Analyze entity counts
        for entity_type, result in sorted(entity_results.items()):
            count = result["total_entities"]
            if count > 10000:
                recommendations.append(
                    f"- **{entity_type}**: Large entity count ({count:,}). "
                    "Consider using smaller pagination sizes and monitoring rate limits closely."
                )

        # Analyze density
        for entity_type, stats in sorted(density_stats_by_type.items()):
            if stats["avg_relations"] > 20:
                recommendations.append(
                    f"- **{entity_type}**: High average relations ({stats['avg_relations']:.1f} per entity). "
                    "Full extraction will be API-intensive. Consider rate limit optimization."
                )

        # Analyze hotspots
        for entity_type, hotspots in sorted(hotspots_by_type.items()):
            if hotspots and hotspots[0]["total_relations"] > 100:
                recommendations.append(
                    f"- **{entity_type}**: Found entities with >100 related items. "
                    f"Top entity has {hotspots[0]['total_relations']} relations. "
                    "These may require special handling during extraction."
                )

        if not recommendations:
            recommendations.append(
                "- No special considerations detected. Proceed with standard extraction configuration."
            )

        return "\n".join(recommendations)
