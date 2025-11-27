#!/usr/bin/env python3
"""
Audit current GraphQL queries to identify which fields are being queried.

This script analyzes jobber_client.py to extract all GraphQL queries and
compare them against available fields from introspection results.
"""

import re
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple


def load_field_inventory(inventory_path: str) -> Dict[str, Set[str]]:
    """Load field inventory from analysis output."""
    with open(inventory_path, 'r') as f:
        analysis = json.load(f)

    inventory = {}
    for type_name, type_info in analysis['field_inventory'].items():
        inventory[type_name] = {field['name'] for field in type_info['fields']}

    return inventory


def extract_query_block(content: str, query_name: str) -> str:
    """Extract a query block by finding the query method or variable."""
    # Try method pattern first: def _get_xxx_query(self): ... return f"""..."""
    method_pattern = rf'def {query_name}\(.*?\):.*?return\s+f?["\']{{3}}(.*?)["\']{{3}}'
    match = re.search(method_pattern, content, re.DOTALL)

    if match:
        return match.group(1)

    # Try constant pattern: QUERY_NAME = """...""" or QUERY_NAME = '''...'''
    constant_pattern = rf'{query_name}\s*=\s*f?["\']{{3}}(.*?)["\']{{3}}'
    match = re.search(constant_pattern, content, re.DOTALL)

    if match:
        return match.group(1)

    return ""


def parse_graphql_fields(query_text: str, entity_name: str) -> Set[str]:
    """
    Parse GraphQL query to extract field names for a specific entity.

    Handles both singular (client) and plural (clients) patterns,
    as well as connection patterns (edges/node).
    """
    fields = set()

    # Try multiple patterns:
    # 1. Plural with connection: clients(args) { edges { node { FIELDS } } }
    # 2. Singular direct: client(id: $id) { FIELDS }

    entity_lower = entity_name.lower()
    entity_plural = entity_lower + 's' if not entity_lower.endswith('s') else entity_lower

    # Pattern 1: Connection pattern (plural)
    connection_pattern = rf'{entity_plural}\s*\([^)]*\)\s*{{\s*edges\s*{{\s*node\s*{{(.*?)(?=\s*}}\s*}})'

    match = re.search(connection_pattern, query_text, re.DOTALL | re.IGNORECASE)

    if match:
        field_block = match.group(1)
    else:
        # Pattern 2: Direct pattern (singular)
        direct_pattern = rf'{entity_lower}\s*\([^)]*\)\s*{{(.*?)(?=\n\s*}}|\Z)'

        match = re.search(direct_pattern, query_text, re.DOTALL | re.IGNORECASE)

        if match:
            field_block = match.group(1)
        else:
            return fields

    # Extract field names from the block
    # We need to parse nested braces carefully to only get top-level fields

    depth = 0
    current_field = []
    in_args = False

    for char in field_block:
        if char == '(':
            in_args = True
        elif char == ')':
            in_args = False
        elif char == '{' and not in_args:
            depth += 1
            if depth == 1 and current_field:
                # We found a field with nested content
                field_name = ''.join(current_field).strip()
                if field_name and field_name not in {'edges', 'node', 'pageInfo'}:
                    fields.add(field_name)
                current_field = []
        elif char == '}' and not in_args:
            depth -= 1
        elif depth == 0 and char.isalnum() or (depth == 0 and char == '_'):
            current_field.append(char)
        elif depth == 0 and char in ('\n', ' ', '\t') and current_field:
            # End of field name
            field_name = ''.join(current_field).strip()
            if field_name and field_name not in {'edges', 'node', 'pageInfo', 'cursor',
                                                   'totalCount', 'hasNextPage', 'hasPreviousPage', 'endCursor'}:
                fields.add(field_name)
            current_field = []

    # Add any remaining field
    if current_field:
        field_name = ''.join(current_field).strip()
        if field_name and field_name not in {'edges', 'node', 'pageInfo', 'cursor',
                                               'totalCount', 'hasNextPage', 'hasPreviousPage', 'endCursor'}:
            fields.add(field_name)

    return fields


def analyze_entity_query(content: str, entity_name: str, query_patterns: List[str]) -> Dict[str, any]:
    """Analyze queries for a specific entity type."""
    all_fields = set()

    for pattern in query_patterns:
        query_text = extract_query_block(content, pattern)
        if query_text:
            fields = parse_graphql_fields(query_text, entity_name)
            all_fields.update(fields)

    return {
        'entity': entity_name,
        'fields_queried': sorted(all_fields),
        'field_count': len(all_fields)
    }


def generate_coverage_report(query_audit: Dict, field_inventory: Dict) -> Dict:
    """Generate coverage report comparing queried vs available fields."""
    report = {}

    for entity_name, audit_data in query_audit.items():
        queried = set(audit_data['fields_queried'])
        available = field_inventory.get(entity_name, set())

        missing = available - queried
        extra = queried - available  # Fields queried but not in schema (potential issues)

        coverage_pct = (len(queried) / len(available) * 100) if available else 0

        report[entity_name] = {
            'total_available': len(available),
            'total_queried': len(queried),
            'coverage_percent': round(coverage_pct, 1),
            'queried_fields': sorted(queried),
            'missing_fields': sorted(missing),
            'extra_fields': sorted(extra),  # These shouldn't exist - potential bugs
        }

    return report


def main():
    """Main audit workflow."""
    base_path = Path(__file__).parent.parent
    client_file = base_path / 'src' / 'clients' / 'jobber_client.py'
    analysis_file = base_path / 'analysis_output' / 'field_analysis.json'
    output_dir = base_path / 'analysis_output'

    print(f"Loading field inventory from: {analysis_file}")
    field_inventory = load_field_inventory(str(analysis_file))

    print(f"Reading GraphQL queries from: {client_file}")
    with open(client_file, 'r') as f:
        content = f.read()

    print("\nAnalyzing queries for each entity...")

    # Define query patterns for each entity
    entity_queries = {
        'Client': ['CLIENTS_QUERY', '_get_clients_query', '_get_clients_map_query'],
        'Invoice': ['INVOICES_QUERY', '_get_invoices_query', '_get_invoices_map_query'],
        'Quote': ['QUOTES_QUERY', '_get_quotes_query', '_get_quotes_map_query'],
        'Job': ['JOBS_QUERY', '_get_jobs_query', '_get_jobs_map_query'],
        'Property': ['PROPERTIES_QUERY', '_get_properties_query', '_get_properties_map_query'],
        'Request': ['REQUESTS_QUERY', '_get_requests_query', '_get_requests_map_query'],
        'Visit': ['_get_visits_query', '_get_visits_map_query'],
        'User': ['USERS_QUERY'],
        'Expense': ['EXPENSES_QUERY', '_get_expenses_query'],
        'TimeSheetEntry': ['TIMESHEET_ENTRIES_QUERY', '_get_timesheet_entries_query'],
        'ProductOrService': ['PRODUCTS_SERVICES_QUERY', '_get_products_services_query'],
    }

    query_audit = {}
    for entity_name, patterns in entity_queries.items():
        audit_data = analyze_entity_query(content, entity_name, patterns)
        query_audit[entity_name] = audit_data
        print(f"  {entity_name}: {audit_data['field_count']} fields queried")

    print("\nGenerating coverage report...")
    coverage_report = generate_coverage_report(query_audit, field_inventory)

    # Save detailed audit
    with open(output_dir / 'query_audit.json', 'w') as f:
        json.dump({
            'query_audit': query_audit,
            'coverage_report': coverage_report
        }, f, indent=2)

    print(f"✓ Query audit saved: {output_dir / 'query_audit.json'}")

    # Generate summary markdown
    with open(output_dir / 'query_coverage_summary.md', 'w') as f:
        f.write("# GraphQL Query Coverage Analysis\n\n")
        f.write("## Summary by Entity\n\n")
        f.write("| Entity | Available | Queried | Coverage | Missing |\n")
        f.write("|--------|-----------|---------|----------|----------|\n")

        for entity_name, report in sorted(coverage_report.items()):
            f.write(
                f"| {entity_name} | {report['total_available']} | "
                f"{report['total_queried']} | {report['coverage_percent']}% | "
                f"{len(report['missing_fields'])} |\n"
            )

        f.write("\n## High-Value Missing Fields\n\n")

        # Highlight important missing fields
        priority_fields = {
            'Client': ['balance', 'companyName', 'billingAddress', 'isArchivable'],
            'Invoice': ['amounts', 'dueDate', 'invoiceNet'],
            'Quote': ['amounts'],
            'Job': ['billingType', 'completedAt', 'instructions', 'invoicedTotal'],
            'Property': ['name', 'taxRate', 'isBillingAddress', 'routingOrder'],
            'Visit': ['completedAt', 'completedBy', 'allDay', 'clientConfirmed'],
            'User': ['isAccountAdmin', 'isAccountOwner', 'availableForScheduling', 'assignedColor'],
        }

        for entity_name, priority in priority_fields.items():
            if entity_name in coverage_report:
                missing = coverage_report[entity_name]['missing_fields']
                priority_missing = [f for f in priority if f in missing]

                if priority_missing:
                    f.write(f"\n### {entity_name}\n")
                    for field in priority_missing:
                        f.write(f"- `{field}`\n")

        f.write("\n## Potential Issues\n\n")
        f.write("Fields queried but not in schema (may indicate bugs or outdated queries):\n\n")

        for entity_name, report in sorted(coverage_report.items()):
            if report['extra_fields']:
                f.write(f"\n### {entity_name}\n")
                for field in report['extra_fields']:
                    f.write(f"- `{field}` ⚠️\n")

    print(f"✓ Coverage summary saved: {output_dir / 'query_coverage_summary.md'}")

    print("\n✓ Query audit complete!")
    print(f"\nKey findings:")
    avg_coverage = sum(r['coverage_percent'] for r in coverage_report.values()) / len(coverage_report)
    print(f"  - Average field coverage: {avg_coverage:.1f}%")
    total_missing = sum(len(r['missing_fields']) for r in coverage_report.values())
    print(f"  - Total missing high-value fields: {total_missing}")
    total_extra = sum(len(r['extra_fields']) for r in coverage_report.values())
    if total_extra > 0:
        print(f"  - ⚠️  Fields queried but not in schema: {total_extra}")


if __name__ == '__main__':
    main()
