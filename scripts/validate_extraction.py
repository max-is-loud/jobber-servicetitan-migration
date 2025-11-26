#!/usr/bin/env python3
"""Validation script for Jobber data extraction integrity.

Validates:
1. Foreign key integrity - no orphaned references
2. Completeness - no null values in required NOT NULL fields
3. Notes integrity - notes have valid parent entities
4. Polymorphic relationships - notes.entity_id points to existing entities

Usage:
    python scripts/validate_extraction.py [--db jobber_export.db] [--verbose]

    # Or via CLI
    uv run python scripts/validate_extraction.py --db jobber_export.db
"""

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class ValidationIssue:
    """Represents a single validation issue found during checks."""

    severity: str  # "ERROR" or "WARNING"
    category: str  # "FK_INTEGRITY", "NULL_REQUIRED", "NOTES_INTEGRITY"
    table: str
    field: str
    message: str
    count: int = 1


class ExtractionValidator:
    """Validates extracted Jobber data for integrity and completeness."""

    def __init__(self, db_path: str, verbose: bool = False):
        """Initialize validator with database connection.

        Args:
            db_path: Path to SQLite database file
            verbose: If True, print detailed progress messages
        """
        self.db_path = db_path
        self.verbose = verbose
        self.connection = sqlite3.connect(db_path)
        self.issues: List[ValidationIssue] = []

    def log(self, message: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[DEBUG] {message}")

    def validate_foreign_key(
        self,
        child_table: str,
        child_column: str,
        parent_table: str,
        parent_column: str = "id",
        allow_null: bool = False,
    ) -> None:
        """Validate foreign key relationship between tables.

        Args:
            child_table: Table containing the foreign key
            child_column: Column in child table referencing parent
            parent_table: Table being referenced
            parent_column: Column in parent table (default: "id")
            allow_null: If True, NULL values are acceptable (optional FK)
        """
        self.log(f"Checking FK: {child_table}.{child_column} → {parent_table}.{parent_column}")

        cursor = self.connection.cursor()

        try:
            # Build NULL check clause
            null_clause = "" if allow_null else f"AND c.{child_column} IS NOT NULL"

            query = f"""
                SELECT COUNT(*) as orphan_count
                FROM {child_table} c
                LEFT JOIN {parent_table} p ON c.{child_column} = p.{parent_column}
                WHERE c.{child_column} IS NOT NULL
                  AND p.{parent_column} IS NULL
                  {null_clause}
            """

            cursor.execute(query)
            result = cursor.fetchone()
            orphan_count = result[0] if result else 0

            if orphan_count > 0:
                self.issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        category="FK_INTEGRITY",
                        table=child_table,
                        field=child_column,
                        message=f"Found {orphan_count} orphaned {child_table} records with "
                        f"invalid {child_column} references to {parent_table}",
                        count=orphan_count,
                    )
                )
        except sqlite3.OperationalError as e:
            # Table doesn't exist - skip this check
            self.log(f"Skipping FK check (table not found): {e}")

        cursor.close()

    def validate_required_field(self, table: str, column: str) -> None:
        """Validate that required (NOT NULL) fields have no null values.

        Args:
            table: Table to check
            column: Column that should not contain nulls
        """
        self.log(f"Checking required field: {table}.{column}")

        cursor = self.connection.cursor()

        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")
            result = cursor.fetchone()
            null_count = result[0] if result else 0

            if null_count > 0:
                self.issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        category="NULL_REQUIRED",
                        table=table,
                        field=column,
                        message=f"Found {null_count} {table} records with NULL {column} "
                        f"(field is required)",
                        count=null_count,
                    )
                )
        except sqlite3.OperationalError as e:
            # Table doesn't exist - skip this check
            self.log(f"Skipping required field check (table not found): {e}")

        cursor.close()

    def validate_notes_polymorphic_integrity(self) -> None:
        """Validate that notes.entity_id points to existing parent entities.

        Notes can reference: clients, jobs, quotes, requests, invoices
        """
        self.log("Checking polymorphic notes integrity")

        cursor = self.connection.cursor()

        # Check each entity type that notes can reference
        entity_types = [
            ("Client", "clients"),
            ("Job", "jobs"),
            ("Quote", "quotes"),
            ("Request", "requests"),
            ("Invoice", "invoices"),
        ]

        for entity_name, entity_table in entity_types:
            try:
                query = f"""
                    SELECT COUNT(*) as orphan_count
                    FROM notes n
                    LEFT JOIN {entity_table} e ON n.entity_id = e.id
                    WHERE n.entity_type = '{entity_name}'
                      AND e.id IS NULL
                """

                cursor.execute(query)
                result = cursor.fetchone()
                orphan_count = result[0] if result else 0

                if orphan_count > 0:
                    self.issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            category="NOTES_INTEGRITY",
                            table="notes",
                            field="entity_id",
                            message=f"Found {orphan_count} notes with entity_type='{entity_name}' "
                            f"pointing to non-existent {entity_table} records",
                            count=orphan_count,
                        )
                    )
            except sqlite3.OperationalError as e:
                # Table doesn't exist - skip this check
                self.log(f"Skipping notes integrity check for {entity_table}: {e}")

        cursor.close()

    def validate_all_foreign_keys(self) -> None:
        """Validate all foreign key relationships in the database."""
        print("🔍 Validating foreign key integrity...")

        # Invoices
        self.validate_foreign_key("invoices", "client_id", "clients")

        # Quotes
        self.validate_foreign_key("quotes", "client_id", "clients")

        # Properties
        self.validate_foreign_key("properties", "client_id", "clients")

        # Jobs
        self.validate_foreign_key("jobs", "client_id", "clients")
        self.validate_foreign_key("jobs", "property_id", "properties", allow_null=True)
        self.validate_foreign_key("jobs", "quote_id", "quotes", allow_null=True)

        # Requests
        self.validate_foreign_key("requests", "client_id", "clients")
        self.validate_foreign_key("requests", "property_id", "properties", allow_null=True)
        self.validate_foreign_key(
            "requests", "converted_to_quote_id", "quotes", allow_null=True
        )
        self.validate_foreign_key("requests", "converted_to_job_id", "jobs", allow_null=True)

        # Expenses
        self.validate_foreign_key("expenses", "job_id", "jobs")

        # Visits
        self.validate_foreign_key("visits", "job_id", "jobs")
        self.validate_foreign_key("visits", "client_id", "clients")
        self.validate_foreign_key("visits", "property_id", "properties", allow_null=True)
        self.validate_foreign_key("visits", "assigned_user_id", "users", allow_null=True)

        # Timesheet Entries
        self.validate_foreign_key("timesheet_entries", "user_id", "users")
        self.validate_foreign_key("timesheet_entries", "job_id", "jobs")
        self.validate_foreign_key("timesheet_entries", "visit_id", "visits", allow_null=True)
        self.validate_foreign_key(
            "timesheet_entries", "approved_by_id", "users", allow_null=True
        )
        self.validate_foreign_key("timesheet_entries", "paid_by_id", "users", allow_null=True)

        # Attachments
        self.validate_foreign_key("attachments", "note_id", "notes")

    def validate_all_required_fields(self) -> None:
        """Validate that all NOT NULL fields have values."""
        print("📋 Validating required fields...")

        # These are the NOT NULL fields from the schema
        required_fields = [
            ("invoices", "client_id"),
            ("quotes", "client_id"),
            ("properties", "client_id"),
            ("jobs", "client_id"),
            ("requests", "client_id"),
            ("expenses", "job_id"),
            ("visits", "job_id"),
            ("visits", "client_id"),
            ("timesheet_entries", "user_id"),
            ("timesheet_entries", "job_id"),
            ("attachments", "note_id"),
            ("notes", "entity_type"),
            ("notes", "entity_id"),
        ]

        for table, column in required_fields:
            self.validate_required_field(table, column)

    def get_table_counts(self) -> dict:
        """Get row counts for all main tables."""
        cursor = self.connection.cursor()

        tables = [
            "clients",
            "users",
            "properties",
            "jobs",
            "quotes",
            "requests",
            "invoices",
            "visits",
            "expenses",
            "timesheet_entries",
            "notes",
            "attachments",
            "products_services",
            "tax_rates",
        ]

        counts = {}
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                result = cursor.fetchone()
                counts[table] = result[0] if result else 0
            except sqlite3.OperationalError:
                # Table doesn't exist yet - skip it
                self.log(f"Table {table} does not exist - skipping")
                continue

        cursor.close()
        return counts

    def run_validation(self) -> Tuple[bool, int]:
        """Run all validation checks.

        Returns:
            Tuple of (success: bool, issue_count: int)
        """
        print(f"\n🚀 Starting validation of {self.db_path}\n")

        # Show table counts
        print("📊 Database Statistics:")
        counts = self.get_table_counts()
        if not counts:
            print("   ⚠️  No tables found in database")
            print("   Run 'tightbeam migrate max-extract' to extract data first")
        else:
            for table, count in sorted(counts.items()):
                print(f"   {table:20s}: {count:>6,d} records")
        print()

        # Run validation checks
        self.validate_all_foreign_keys()
        self.validate_all_required_fields()
        self.validate_notes_polymorphic_integrity()

        # Generate report
        print("\n" + "=" * 80)
        print("VALIDATION REPORT")
        print("=" * 80 + "\n")

        if not self.issues:
            print("✅ No issues found - extraction is valid!\n")
            return True, 0

        # Group issues by severity
        errors = [i for i in self.issues if i.severity == "ERROR"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]

        if errors:
            print(f"❌ Found {len(errors)} ERRORS:\n")
            for issue in errors:
                print(f"  [{issue.category}] {issue.table}.{issue.field}")
                print(f"     {issue.message}")
                print()

        if warnings:
            print(f"⚠️  Found {len(warnings)} WARNINGS:\n")
            for issue in warnings:
                print(f"  [{issue.category}] {issue.table}.{issue.field}")
                print(f"     {issue.message}")
                print()

        # Summary
        total_orphans = sum(i.count for i in errors if i.category == "FK_INTEGRITY")
        total_nulls = sum(i.count for i in errors if i.category == "NULL_REQUIRED")
        total_note_issues = sum(i.count for i in errors if i.category == "NOTES_INTEGRITY")

        print("=" * 80)
        print(f"Total Issues: {len(errors)} errors, {len(warnings)} warnings")
        if total_orphans:
            print(f"   Orphaned FK records: {total_orphans:,d}")
        if total_nulls:
            print(f"   NULL in required fields: {total_nulls:,d}")
        if total_note_issues:
            print(f"   Invalid note references: {total_note_issues:,d}")
        print("=" * 80 + "\n")

        return len(errors) == 0, len(self.issues)

    def close(self) -> None:
        """Close database connection."""
        self.connection.close()


def main() -> int:
    """Main entry point for validation script."""
    parser = argparse.ArgumentParser(
        description="Validate Jobber data extraction integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        type=str,
        default="jobber_export.db",
        help="Path to SQLite database file (default: jobber_export.db)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug output",
    )

    args = parser.parse_args()

    # Check if database exists
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ Error: Database file not found: {db_path}", file=sys.stderr)
        return 1

    # Run validation
    validator = ExtractionValidator(str(db_path), verbose=args.verbose)
    try:
        success, issue_count = validator.run_validation()
        return 0 if success else 1
    finally:
        validator.close()


if __name__ == "__main__":
    sys.exit(main())
