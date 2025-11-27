#!/usr/bin/env python3
"""Performance testing script for Max Extract pipeline.

Tests extraction performance against Jobber API and generates performance reports.

Usage:
    python scripts/performance_test.py --db test_performance.db --report performance_report.md

Requirements:
    - Valid Jobber OAuth credentials
    - Test Jobber account with representative data
    - Sufficient time (1-2 hours for complete test)

Metrics Captured:
    - Total runtime per entity type
    - Requests per second
    - GraphQL cost utilization
    - Database write throughput
    - Memory usage over time
    - Error rates and retry counts
"""

import argparse
import time
import tracemalloc
from datetime import datetime
from pathlib import Path
from typing import Any

from src.cli.services.factories import ServiceFactory
from src.coordinators.max_extract_coordinator import MaxExtractCoordinator


class PerformanceTestRunner:
    """Performance test runner for Max Extract pipeline."""

    def __init__(self, db_path: str, optimization_level: str = "moderate"):
        """Initialize performance test runner.

        Args:
            db_path: Path to test database
            optimization_level: Rate limiting level (conservative, moderate, aggressive)
        """
        self.db_path = db_path
        self.optimization_level = optimization_level
        self.metrics = {
            "entity_metrics": {},
            "overall_metrics": {},
            "system_metrics": {},
            "error_metrics": {},
        }

    def setup_environment(self) -> dict[str, Any]:
        """Set up test environment and dependencies.

        Returns:
            Dictionary of initialized components
        """
        print("🔧 Setting up performance test environment...")

        # Initialize dependencies
        config_manager = ServiceFactory.create_config_manager()
        logger = ServiceFactory.create_logger(verbose=True)
        repository = ServiceFactory.create_repository(Path(self.db_path))

        # Initialize coordinator
        auth_provider = ServiceFactory.create_auth_provider(repository, logger)
        jobber_client = ServiceFactory.create_rate_limited_jobber_client(
            auth_provider, repository, config_manager, self.optimization_level
        )
        entity_mapper = ServiceFactory.create_entity_mapper()

        coordinator = MaxExtractCoordinator(
            jobber_client=jobber_client,
            repository=repository,
            logger=logger,
            entity_mapper=entity_mapper,
        )

        print("✓ Environment setup complete")

        return {
            "coordinator": coordinator,
            "repository": repository,
            "logger": logger,
            "config_manager": config_manager,
        }

    def run_performance_test(self, components: dict[str, Any]) -> dict[str, Any]:
        """Run complete performance test suite.

        Args:
            components: Initialized components from setup_environment

        Returns:
            Dictionary of performance metrics
        """
        coordinator = components["coordinator"]
        repository = components["repository"]

        print("\n📊 Starting performance test...")
        print(f"Database: {self.db_path}")
        print(f"Optimization Level: {self.optimization_level}")
        print("-" * 60)

        # Start memory tracking
        tracemalloc.start()
        start_memory = tracemalloc.get_traced_memory()[0]

        # Track overall timing
        overall_start = time.time()

        # Run extraction for all entities
        try:
            results = coordinator.extract_all(resume=False)

            overall_end = time.time()
            overall_duration = overall_end - overall_start

            # Get final memory usage
            current_memory, peak_memory = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # Collect metrics from database
            self.metrics["overall_metrics"] = {
                "total_runtime_seconds": overall_duration,
                "total_entities": results["total_entities"],
                "entity_types_processed": len(results["results"]),
                "error_count": len(results.get("errors", [])),
            }

            self.metrics["system_metrics"] = {
                "start_memory_mb": start_memory / 1024 / 1024,
                "peak_memory_mb": peak_memory / 1024 / 1024,
                "memory_delta_mb": (peak_memory - start_memory) / 1024 / 1024,
            }

            # Collect per-entity metrics
            for entity_type, count in results["results"].items():
                self.metrics["entity_metrics"][entity_type] = {
                    "entity_count": count,
                }

            # Get GraphQL cost metrics from database
            self._collect_cost_metrics(repository)

            # Get rate limiting statistics
            self._collect_rate_limit_metrics(repository)

            print("\n✓ Performance test complete!")

        except Exception as e:
            print(f"\n❌ Performance test failed: {e}")
            traceback.print_exc()
            return {}

        return self.metrics

    def _collect_cost_metrics(self, repository: Any) -> None:
        """Collect GraphQL cost metrics from database.

        Args:
            repository: Repository instance for database queries
        """
        cursor = repository._connection.cursor()

        # Get cost statistics
        cursor.execute(
            """
            SELECT
                AVG(requested_cost) as avg_requested_cost,
                AVG(actual_cost) as avg_actual_cost,
                MAX(requested_cost) as max_requested_cost,
                MIN(available_points) as min_available_points,
                COUNT(*) as total_requests
            FROM graphql_costs
        """
        )

        row = cursor.fetchone()
        if row:
            self.metrics["overall_metrics"]["graphql_costs"] = {
                "avg_requested_cost": row[0] or 0,
                "avg_actual_cost": row[1] or 0,
                "max_requested_cost": row[2] or 0,
                "min_available_points": row[3] or 0,
                "total_requests": row[4] or 0,
            }

            # Calculate requests per second
            if self.metrics["overall_metrics"]["total_runtime_seconds"] > 0:
                self.metrics["overall_metrics"]["requests_per_second"] = (
                    row[4] / self.metrics["overall_metrics"]["total_runtime_seconds"]
                )

    def _collect_rate_limit_metrics(self, repository: Any) -> None:
        """Collect rate limiting statistics.

        Args:
            repository: Repository instance for database queries
        """
        # Note: Rate limit metrics would be collected from rate_limit_events table if implemented
        # For now, we calculate based on GraphQL requests
        pass

    def generate_report(self, output_path: str) -> None:
        """Generate performance test report in Markdown format.

        Args:
            output_path: Path to output report file
        """
        print(f"\n📝 Generating report: {output_path}")

        report = self._build_markdown_report()

        Path(output_path).write_text(report)

        print(f"✓ Report generated: {output_path}")

    def _build_markdown_report(self) -> str:
        """Build Markdown-formatted performance report.

        Returns:
            Markdown report string
        """
        metrics = self.metrics
        overall = metrics["overall_metrics"]
        system = metrics["system_metrics"]

        report = f"""# Performance Test Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Database**: {self.db_path}
**Optimization Level**: {self.optimization_level}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Runtime | {overall.get('total_runtime_seconds', 0):.2f} seconds ({overall.get('total_runtime_seconds', 0) / 60:.2f} minutes) |
| Total Entities Extracted | {overall.get('total_entities', 0):,} |
| Entity Types Processed | {overall.get('entity_types_processed', 0)} |
| Average Requests/Second | {overall.get('requests_per_second', 0):.2f} req/s |
| Peak Memory Usage | {system.get('peak_memory_mb', 0):.2f} MB |
| Error Count | {overall.get('error_count', 0)} |

## Overall Performance

### Runtime Analysis

- **Total Duration**: {overall.get('total_runtime_seconds', 0):.2f}s
- **Average Rate**: {overall.get('total_entities', 0) / max(overall.get('total_runtime_seconds', 1), 1):.2f} entities/second

### API Performance

"""

        # Add GraphQL cost metrics if available
        if "graphql_costs" in overall:
            costs = overall["graphql_costs"]
            report += f"""
| GraphQL Metric | Value |
|----------------|-------|
| Total API Requests | {costs.get('total_requests', 0):,} |
| Avg Requested Cost | {costs.get('avg_requested_cost', 0):.2f} points |
| Avg Actual Cost | {costs.get('avg_actual_cost', 0):.2f} points |
| Max Requested Cost | {costs.get('max_requested_cost', 0):.2f} points |
| Min Available Points | {costs.get('min_available_points', 0):.2f} points |

**Cost Efficiency**: {(costs.get('avg_actual_cost', 0) / max(costs.get('avg_requested_cost', 1), 1)) * 100:.1f}% (actual vs requested)

**Throttle Risk**: {"⚠️ HIGH" if costs.get('min_available_points', 10000) < 2000 else "✓ LOW"}
"""

        # Add system metrics
        report += f"""
## System Resources

### Memory Usage

| Metric | Value |
|--------|-------|
| Starting Memory | {system.get('start_memory_mb', 0):.2f} MB |
| Peak Memory | {system.get('peak_memory_mb', 0):.2f} MB |
| Memory Delta | {system.get('memory_delta_mb', 0):.2f} MB |

### Database Throughput

**Entities/Second**: {overall.get('total_entities', 0) / max(overall.get('total_runtime_seconds', 1), 1):.2f}

## Per-Entity Performance

| Entity Type | Count | Est. Time* |
|-------------|-------|------------|
"""

        # Add per-entity metrics
        entity_metrics = metrics.get("entity_metrics", {})
        for entity_type, entity_data in entity_metrics.items():
            count = entity_data.get("entity_count", 0)
            # Estimate time based on proportional entity count
            est_time = (
                count / max(overall.get("total_entities", 1), 1)
            ) * overall.get("total_runtime_seconds", 0)
            report += (
                f"| {entity_type} | {count:,} | {est_time:.2f}s ({est_time / 60:.2f}m) |\n"
            )

        report += """
*Estimated time is calculated proportionally based on entity count

## Recommendations

"""

        # Add recommendations based on metrics
        recommendations = []

        # Rate limiting recommendations
        if overall.get("requests_per_second", 0) < 2:
            recommendations.append(
                "- ⚡ **Increase Rate Limits**: Current rate is low. Consider using more aggressive optimization level."
            )
        elif overall.get("requests_per_second", 0) > 8:
            recommendations.append(
                "- ⚠️ **Reduce Rate Limits**: Approaching Jobber's 8.3 req/s limit. Use more conservative settings."
            )

        # GraphQL cost recommendations
        if "graphql_costs" in overall:
            costs = overall["graphql_costs"]
            if costs.get("min_available_points", 10000) < 2000:
                recommendations.append(
                    "- ⚠️ **Reduce Page Sizes**: GraphQL cost points running low. Reduce pagination sizes."
                )
            if costs.get("max_requested_cost", 0) > 8000:
                recommendations.append(
                    "- ⚠️ **High Query Costs**: Some queries exceed 80% of max cost. Review complex queries."
                )

        # Memory recommendations
        if system.get("peak_memory_mb", 0) > 1000:
            recommendations.append(
                "- 💾 **High Memory Usage**: Peak memory exceeds 1GB. Consider reducing batch sizes."
            )

        # Performance recommendations
        avg_rate = overall.get("total_entities", 0) / max(
            overall.get("total_runtime_seconds", 1), 1
        )
        if avg_rate < 10:
            recommendations.append(
                "- 🐌 **Slow Extraction**: Entity rate is low. Check network latency and pagination settings."
            )

        if recommendations:
            report += "\n".join(recommendations)
        else:
            report += "✓ No performance issues detected. Configuration is optimal."

        report += f"""

## Conclusion

The performance test completed {"successfully" if overall.get('error_count', 0) == 0 else "with errors"}.

**Overall Grade**: {self._calculate_performance_grade(overall, system)}

---

**Test Configuration**:
- Optimization Level: {self.optimization_level}
- Database: {self.db_path}
- Test Date: {datetime.now().strftime('%Y-%m-%d')}

**Legend**:
- ✓ Good performance
- ⚡ Optimization opportunity
- ⚠️ Performance concern
- 💾 Resource concern
"""

        return report

    def _calculate_performance_grade(
        self, overall: dict, system: dict
    ) -> str:
        """Calculate overall performance grade.

        Args:
            overall: Overall metrics
            system: System metrics

        Returns:
            Grade string (A+, A, B, C, D, F)
        """
        score = 100

        # Deduct for errors
        if overall.get("error_count", 0) > 0:
            score -= overall["error_count"] * 5

        # Deduct for low performance
        avg_rate = overall.get("total_entities", 0) / max(
            overall.get("total_runtime_seconds", 1), 1
        )
        if avg_rate < 5:
            score -= 20
        elif avg_rate < 10:
            score -= 10

        # Deduct for high memory
        if system.get("peak_memory_mb", 0) > 1000:
            score -= 10

        # Deduct for rate limit concerns
        if overall.get("requests_per_second", 0) > 8:
            score -= 15

        # Grade mapping
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"


def main():
    """Main entry point for performance testing script."""
    parser = argparse.ArgumentParser(
        description="Performance testing for Max Extract pipeline"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="test_performance.db",
        help="Test database path (default: test_performance.db)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="performance_report.md",
        help="Output report path (default: performance_report.md)",
    )
    parser.add_argument(
        "--optimization-level",
        type=str,
        choices=["conservative", "moderate", "aggressive"],
        default="moderate",
        help="Rate limiting optimization level (default: moderate)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("TightBeam Performance Test Suite")
    print("=" * 60)

    # Initialize test runner
    runner = PerformanceTestRunner(
        db_path=args.db, optimization_level=args.optimization_level
    )

    # Setup environment
    components = runner.setup_environment()

    # Run performance test
    metrics = runner.run_performance_test(components)

    if metrics:
        # Generate report
        runner.generate_report(args.report)

        print("\n" + "=" * 60)
        print("Performance test complete!")
        print(f"Report: {args.report}")
        print("=" * 60)
    else:
        print("\n❌ Performance test failed. Check logs for details.")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
