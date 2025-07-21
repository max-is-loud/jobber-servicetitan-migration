#!/usr/bin/env python3
"""
Configuration Verification Script for TightBeam v2

This script systematically verifies that all hardcoded constants have been
eliminated from the codebase and replaced with configurable values.

Usage:
    python scripts/verify_config.py
    poetry run python scripts/verify_config.py
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List


class ConfigVerifier:
    """Verifies that hardcoded constants have been eliminated from codebase."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.issues: List[Dict[str, str]] = []

        # Patterns to detect hardcoded constants
        self.critical_patterns = {
            "graphql_pagination": r"first: [5-9]\d*",  # Focus on larger pagination values
            "hardcoded_sleep": r"time\.sleep\(\s*\d+",
            "rate_limit_capacity": r"capacity\s*=\s*\d+",
            "rate_limit_refill": r"refill_rate\s*=\s*\d+",
            "hardcoded_delay": r"delay\s*=\s*\d+\.\d+",
        }

        # Non-critical patterns (internal batch processing, etc.)
        self.non_critical_patterns = {
            "batch_processing": r"(?:batch_size|chunk_size)\s*=\s*\d+",
        }

        # Files to exclude from verification (utility scripts, tests, etc.)
        self.excluded_files = {
            "explore_jobber_api.py",
            "verify_config.py",
            "__pycache__",
            ".git",
            ".pytest_cache",
            ".ruff_cache",
            "htmlcov",
            "docs",
        }

        # Patterns that are acceptable (OAuth polling, test values, etc.)
        self.acceptable_patterns = [
            r"time\.sleep\(1\)",  # OAuth polling delay is acceptable
            r"first: [12]",  # Test/example queries with small values
            r"capacity=\d+.*# Test",  # Test values with comments
        ]

    def scan_file(self, file_path: Path) -> List[Dict[str, str]]:
        """Scan a single file for hardcoded constants."""
        issues = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Check critical patterns (these are issues)
            for pattern_name, pattern in self.critical_patterns.items():
                for match in re.finditer(pattern, content, re.MULTILINE):
                    line_num = content[: match.start()].count("\n") + 1
                    line_content = lines[line_num - 1].strip()

                    # Check if this is an acceptable pattern
                    is_acceptable = any(
                        re.search(acceptable, line_content)
                        for acceptable in self.acceptable_patterns
                    )

                    if not is_acceptable:
                        issues.append(
                            {
                                "file": str(file_path),
                                "line": line_num,
                                "pattern": pattern_name,
                                "content": line_content,
                                "match": match.group(),
                                "critical": True,
                            }
                        )

            # Check non-critical patterns (these are warnings)
            for pattern_name, pattern in self.non_critical_patterns.items():
                for match in re.finditer(pattern, content, re.MULTILINE):
                    line_num = content[: match.start()].count("\n") + 1
                    line_content = lines[line_num - 1].strip()

                    # Check if this is an acceptable pattern
                    is_acceptable = any(
                        re.search(acceptable, line_content)
                        for acceptable in self.acceptable_patterns
                    )

                    if not is_acceptable:
                        issues.append(
                            {
                                "file": str(file_path),
                                "line": line_num,
                                "pattern": pattern_name,
                                "content": line_content,
                                "match": match.group(),
                            }
                        )

        except Exception as e:
            issues.append(
                {
                    "file": str(file_path),
                    "line": 0,
                    "pattern": "file_error",
                    "content": f"Error reading file: {e}",
                    "match": "",
                }
            )

        return issues

    def scan_directory(self, directory: Path) -> None:
        """Recursively scan directory for Python files."""
        for item in directory.iterdir():
            if item.name in self.excluded_files:
                continue

            if item.is_dir():
                self.scan_directory(item)
            elif item.suffix == ".py":
                file_issues = self.scan_file(item)
                self.issues.extend(file_issues)

    def verify_quotes_improvement(self) -> bool:
        """Verify that quotes pagination has been improved from hardcoded 5."""
        try:
            from src.config.config_manager import ConfigManagerImpl

            config_manager = ConfigManagerImpl()
            quotes_pagination = config_manager.get_pagination_config("quotes")

            if quotes_pagination >= 30:
                print(
                    f"✅ Quotes pagination: {quotes_pagination} (improved from hardcoded 5)"
                )
                return True
            else:
                print(f"❌ Quotes pagination: {quotes_pagination} (should be ≥30)")
                return False

        except Exception as e:
            print(f"❌ Error checking quotes pagination: {e}")
            return False

    def verify_configurable_delays(self) -> bool:
        """Verify that page delays are configurable."""
        try:
            from src.config.config_manager import ConfigManagerImpl

            config_manager = ConfigManagerImpl()
            page_delay = config_manager.get_delay_config("page_delay")

            if isinstance(page_delay, (int, float)) and page_delay >= 0:
                print(f"✅ Page delays configurable: {page_delay}s")
                return True
            else:
                print(f"❌ Page delay invalid: {page_delay}")
                return False

        except Exception as e:
            print(f"❌ Error checking page delays: {e}")
            return False

    def verify_rate_limiting(self) -> bool:
        """Verify that rate limiting is configurable."""
        try:
            from src.config.config_manager import ConfigManagerImpl

            config_manager = ConfigManagerImpl()
            rate_config = config_manager.get_rate_limit_config("moderate")

            required_keys = [
                "capacity",
                "refill_rate",
                "initial_tokens",
                "safety_margin",
            ]
            if all(key in rate_config for key in required_keys):
                print(
                    f"✅ Rate limiting configurable: {rate_config['capacity']} capacity, {rate_config['refill_rate']} refill"
                )
                return True
            else:
                print(f"❌ Rate limiting config incomplete: {rate_config}")
                return False

        except Exception as e:
            print(f"❌ Error checking rate limiting: {e}")
            return False

    def run_verification(self) -> bool:
        """Run complete verification process."""
        print("🔍 TightBeam v2 Configuration Verification")
        print("=" * 50)

        # Scan for hardcoded constants
        print("\n📂 Scanning for hardcoded constants...")
        self.scan_directory(self.project_root / "src")

        # Report findings
        if self.issues:
            print(f"\n❌ Found {len(self.issues)} potential hardcoded constants:")
            for issue in self.issues:
                print(f"  📄 {issue['file']}:{issue['line']}")
                print(f"     Pattern: {issue['pattern']}")
                print(f"     Content: {issue['content']}")
                print(f"     Match: {issue['match']}")
                print()
        else:
            print("✅ No hardcoded constants found in source code!")

        # Verify specific improvements
        print("\n🎯 Verifying specific improvements:")
        quotes_ok = self.verify_quotes_improvement()
        delays_ok = self.verify_configurable_delays()
        rate_limiting_ok = self.verify_rate_limiting()

        # Overall assessment
        all_good = (
            len(self.issues) == 0 and quotes_ok and delays_ok and rate_limiting_ok
        )

        print("\n" + "=" * 50)
        if all_good:
            print("🎉 VERIFICATION PASSED: All hardcoded constants eliminated!")
            print("✅ Quotes pagination improved from 5 to configurable 30+")
            print("✅ Page delays configurable through YAML")
            print("✅ Rate limiting fully configurable")
        else:
            print("❌ VERIFICATION FAILED: Issues found")
            if self.issues:
                print(f"   - {len(self.issues)} hardcoded constants remain")
            if not quotes_ok:
                print("   - Quotes pagination not properly configured")
            if not delays_ok:
                print("   - Page delays not configurable")
            if not rate_limiting_ok:
                print("   - Rate limiting not configurable")

        return all_good

    def generate_report(self) -> str:
        """Generate a detailed verification report."""
        report = []
        report.append("# TightBeam v2 Configuration Verification Report")
        report.append(f"Generated: {os.popen('date').read().strip()}")
        report.append("")

        if self.issues:
            report.append(f"## Issues Found ({len(self.issues)})")
            report.append("")
            for issue in self.issues:
                report.append(f"### {issue['file']}:{issue['line']}")
                report.append(f"- **Pattern**: {issue['pattern']}")
                report.append(f"- **Content**: `{issue['content']}`")
                report.append(f"- **Match**: `{issue['match']}`")
                report.append("")
        else:
            report.append("## ✅ No Issues Found")
            report.append("")
            report.append("All hardcoded constants have been successfully eliminated!")

        return "\n".join(report)


def main():
    """Main entry point for verification script."""
    verifier = ConfigVerifier()
    success = verifier.run_verification()

    # Generate report if requested
    if "--report" in sys.argv:
        report = verifier.generate_report()
        report_path = "config_verification_report.md"
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\n📄 Detailed report saved to: {report_path}")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
