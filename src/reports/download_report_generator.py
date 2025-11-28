"""Download report generator for binary download pass results."""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class DownloadReportGenerator:
    """
    Generator for download mode pass reports.

    Creates detailed Markdown and JSON reports with download statistics,
    success/failure analysis, error tracking, and bandwidth metrics.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        """Initialize DownloadReportGenerator.

        Args:
            output_dir: Optional directory for report output (default: current directory)
        """
        self._output_dir = output_dir or Path(".")

    def generate_report(
        self,
        snapshot_id: str,
        total_attachments: int,
        downloaded: int,
        failed: int,
        skipped: int,
        total_bytes: int,
        duration: float,
        failed_items: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[str, str]:
        """
        Generate comprehensive download pass report in Markdown and JSON formats.

        Args:
            snapshot_id: Map snapshot UUID
            total_attachments: Total number of attachments processed
            downloaded: Number successfully downloaded
            failed: Number that failed download
            skipped: Number skipped (already done)
            total_bytes: Total bytes downloaded
            duration: Total execution time in seconds
            failed_items: Optional list of failed items with attachment_id, error, attempt_count

        Returns:
            Tuple of (markdown_path, json_path) for generated reports
        """
        # Generate report content
        markdown_content = self._generate_markdown_report(
            snapshot_id=snapshot_id,
            total_attachments=total_attachments,
            downloaded=downloaded,
            failed=failed,
            skipped=skipped,
            total_bytes=total_bytes,
            duration=duration,
            failed_items=failed_items or [],
        )

        json_content = self._generate_json_report(
            snapshot_id=snapshot_id,
            total_attachments=total_attachments,
            downloaded=downloaded,
            failed=failed,
            skipped=skipped,
            total_bytes=total_bytes,
            duration=duration,
            failed_items=failed_items or [],
        )

        # Write reports to files
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snapshot_short = snapshot_id[:8] if snapshot_id else "unknown"
        markdown_filename = f"download-report-{snapshot_short}-{timestamp}.md"
        json_filename = f"download-report-{snapshot_short}-{timestamp}.json"

        markdown_path = self._output_dir / markdown_filename
        json_path = self._output_dir / json_filename

        markdown_path.write_text(markdown_content, encoding="utf-8")
        json_path.write_text(json_content, encoding="utf-8")

        return str(markdown_path), str(json_path)

    def _generate_markdown_report(
        self,
        snapshot_id: str,
        total_attachments: int,
        downloaded: int,
        failed: int,
        skipped: int,
        total_bytes: int,
        duration: float,
        failed_items: List[Dict[str, Any]],
    ) -> str:
        """Generate Markdown format report."""
        # Calculate metrics
        success_rate = (downloaded / total_attachments * 100) if total_attachments > 0 else 0
        avg_speed = (total_bytes / duration) if duration > 0 else 0
        downloads_per_sec = (downloaded / duration) if duration > 0 else 0

        lines = [
            f"# Download Pass Report",
            "",
            f"**Snapshot ID:** `{snapshot_id}`  ",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Duration:** {duration:.1f}s  ",
            "",
            "## Summary Statistics",
            "",
            f"- **Total Attachments:** {total_attachments:,}",
            f"- **Successfully Downloaded:** {downloaded:,} ({success_rate:.1f}%)",
            f"- **Failed:** {failed:,}",
            f"- **Skipped (Already Done):** {skipped:,}",
            f"- **Total Bytes Downloaded:** {self._format_bytes(total_bytes)}",
            "",
            "## Performance Metrics",
            "",
            f"- **Average Download Speed:** {self._format_bytes(avg_speed)}/s",
            f"- **Downloads Per Second:** {downloads_per_sec:.2f}",
            f"- **Average Time Per File:** {(duration / downloaded) if downloaded > 0 else 0:.2f}s",
            "",
        ]

        # Add error analysis if there were failures
        if failed > 0 and failed_items:
            lines.extend(self._generate_error_analysis_markdown(failed_items))

        # Add recommendations
        lines.extend(self._generate_recommendations_markdown(
            success_rate=success_rate,
            failed=failed,
            avg_speed=avg_speed,
        ))

        return "\n".join(lines)

    def _generate_error_analysis_markdown(
        self,
        failed_items: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate error analysis section for Markdown report."""
        lines = [
            "## Error Analysis",
            "",
        ]

        # Count errors by type
        error_counter = Counter()
        for item in failed_items:
            error_msg = item.get("last_error", "Unknown error")
            # Extract error type (first line or first 50 chars)
            error_type = error_msg.split("\n")[0][:50] if error_msg else "Unknown"
            error_counter[error_type] += 1

        # Show top 10 errors
        lines.append("### Top Errors")
        lines.append("")
        lines.append("| Error Type | Count |")
        lines.append("|------------|-------|")

        for error_type, count in error_counter.most_common(10):
            lines.append(f"| {error_type} | {count} |")

        lines.append("")

        # Show failed attachments (limit to first 20)
        lines.append("### Failed Attachments")
        lines.append("")
        lines.append("| Attachment ID | Error | Attempts |")
        lines.append("|---------------|-------|----------|")

        for item in failed_items[:20]:
            attachment_id = item.get("attachment_id", "Unknown")[:12]
            error = item.get("last_error", "Unknown")[:50]
            attempts = item.get("attempt_count", 0)
            lines.append(f"| `{attachment_id}...` | {error} | {attempts} |")

        if len(failed_items) > 20:
            lines.append("")
            lines.append(f"*...and {len(failed_items) - 20} more failures (see JSON report for complete list)*")

        lines.append("")

        return lines

    def _generate_recommendations_markdown(
        self,
        success_rate: float,
        failed: int,
        avg_speed: float,
    ) -> List[str]:
        """Generate recommendations section for Markdown report."""
        lines = [
            "## Recommendations",
            "",
        ]

        # Success rate recommendations
        if success_rate < 95.0 and failed > 0:
            lines.append(f"- ⚠️ **Success rate ({success_rate:.1f}%) is below 95%**")
            lines.append(f"  - Run download pass again with `--resume` to retry {failed} failed downloads")
            lines.append("  - Review error analysis above to identify common failure patterns")
            lines.append("")
        elif success_rate == 100.0:
            lines.append("- ✅ **Perfect download success rate (100%)**")
            lines.append("")

        # Speed recommendations
        if avg_speed < 1024 * 1024:  # Less than 1 MB/s
            lines.append(f"- 💡 **Download speed ({self._format_bytes(avg_speed)}/s) is low**")
            lines.append("  - Check network connection")
            lines.append("  - Consider running downloads during off-peak hours")
            lines.append("")
        elif avg_speed > 100 * 1024 * 1024:  # More than 100 MB/s
            lines.append(f"- 🚀 **Excellent download speed ({self._format_bytes(avg_speed)}/s)**")
            lines.append("")

        # General recommendations
        lines.append("### Next Steps")
        lines.append("")
        if failed > 0:
            lines.append("1. Review error details above")
            lines.append(f"2. Run `tightbeam migrate download --snapshot-id {snapshot_id[:8]}... --resume` to retry failures")
            lines.append("3. Run `tightbeam migrate reconcile` to verify completeness")
        else:
            lines.append("1. Run `tightbeam migrate reconcile` to verify extraction completeness")
            lines.append("2. Proceed with data transformation or import")

        lines.append("")

        return lines

    def _generate_json_report(
        self,
        snapshot_id: str,
        total_attachments: int,
        downloaded: int,
        failed: int,
        skipped: int,
        total_bytes: int,
        duration: float,
        failed_items: List[Dict[str, Any]],
    ) -> str:
        """Generate JSON format report."""
        # Calculate metrics
        success_rate = (downloaded / total_attachments * 100) if total_attachments > 0 else 0
        avg_speed = (total_bytes / duration) if duration > 0 else 0
        downloads_per_sec = (downloaded / duration) if duration > 0 else 0

        report = {
            "snapshot_id": snapshot_id,
            "generated_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "summary": {
                "total_attachments": total_attachments,
                "downloaded": downloaded,
                "failed": failed,
                "skipped": skipped,
                "success_rate": round(success_rate, 2),
            },
            "bytes": {
                "total_downloaded": total_bytes,
                "human_readable": self._format_bytes(total_bytes),
            },
            "performance": {
                "average_speed_bytes_per_sec": round(avg_speed, 2),
                "average_speed_human": f"{self._format_bytes(avg_speed)}/s",
                "downloads_per_second": round(downloads_per_sec, 2),
                "average_time_per_file_seconds": round((duration / downloaded) if downloaded > 0 else 0, 2),
            },
            "failed_attachments": failed_items,
        }

        # Add error summary
        if failed_items:
            error_counter = Counter()
            for item in failed_items:
                error_msg = item.get("last_error", "Unknown error")
                error_type = error_msg.split("\n")[0][:50] if error_msg else "Unknown"
                error_counter[error_type] += 1

            report["error_summary"] = [
                {"error_type": error_type, "count": count}
                for error_type, count in error_counter.most_common()
            ]

        return json.dumps(report, indent=2, ensure_ascii=False)

    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Format bytes as human-readable string.

        Args:
            bytes_count: Number of bytes

        Returns:
            Human-readable string (e.g., "1.5 MB", "234 KB")
        """
        if bytes_count < 1024:
            return f"{bytes_count} B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"
