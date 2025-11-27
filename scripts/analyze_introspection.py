#!/usr/bin/env python3
"""
Parse introspection_results.json and generate comprehensive field inventory.

This script analyzes the Jobber GraphQL schema introspection results to:
- List all types and their fields
- Generate field inventory reports (JSON/CSV)
- Identify nested structures and relationships
- Document complex types (InvoiceAmounts, QuoteAmounts, etc.)
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict


def load_introspection_data(filepath: str) -> Dict[str, Any]:
    """Load introspection results from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data.get('results', {})


def extract_type_name(type_obj: Dict[str, Any]) -> str:
    """Extract the actual type name from nested type objects."""
    if type_obj is None:
        return "Unknown"

    if type_obj.get('name'):
        return type_obj['name']

    # Handle NON_NULL and LIST wrappers
    if type_obj.get('kind') in ['NON_NULL', 'LIST']:
        of_type = type_obj.get('ofType')
        if of_type:
            return extract_type_name(of_type)

    return "Unknown"


def format_type_string(type_obj: Dict[str, Any]) -> str:
    """Format type with NON_NULL (!) and LIST ([]) notation."""
    if type_obj is None:
        return "Unknown"

    kind = type_obj.get('kind')
    name = type_obj.get('name')
    of_type = type_obj.get('ofType')

    if kind == 'NON_NULL':
        inner = format_type_string(of_type)
        return f"{inner}!"
    elif kind == 'LIST':
        inner = format_type_string(of_type)
        return f"[{inner}]"
    elif name:
        return name
    else:
        return "Unknown"


def analyze_types(results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze all types and their fields."""
    analysis = {
        'by_kind': defaultdict(list),
        'field_inventory': {},
        'nested_structures': [],
        'statistics': {
            'total_types': 0,
            'object_types': 0,
            'scalar_types': 0,
            'union_types': 0,
            'enum_types': 0,
        }
    }

    for type_name, type_data in results.items():
        kind = type_data.get('kind', 'UNKNOWN')
        analysis['by_kind'][kind].append(type_name)
        analysis['statistics']['total_types'] += 1

        if kind == 'OBJECT':
            analysis['statistics']['object_types'] += 1
            fields = type_data.get('fields', [])

            field_list = []
            for field in fields:
                field_info = {
                    'name': field['name'],
                    'type': format_type_string(field['type']),
                    'raw_type': extract_type_name(field['type']),
                    'is_nullable': field['type'].get('kind') != 'NON_NULL'
                }
                field_list.append(field_info)

            analysis['field_inventory'][type_name] = {
                'kind': kind,
                'field_count': len(fields),
                'fields': field_list
            }

            # Identify complex nested structures
            if any(f['raw_type'] not in ['String', 'Int', 'Float', 'Boolean', 'ID']
                   for f in field_list):
                analysis['nested_structures'].append(type_name)

        elif kind == 'SCALAR':
            analysis['statistics']['scalar_types'] += 1
        elif kind == 'UNION':
            analysis['statistics']['union_types'] += 1
        elif kind == 'ENUM':
            analysis['statistics']['enum_types'] += 1

    return analysis


def generate_csv_report(analysis: Dict[str, Any], output_path: str):
    """Generate CSV report of all fields across all types."""
    rows = []

    for type_name, type_info in analysis['field_inventory'].items():
        for field in type_info['fields']:
            rows.append({
                'Type': type_name,
                'Field': field['name'],
                'GraphQL Type': field['type'],
                'Base Type': field['raw_type'],
                'Nullable': 'Yes' if field['is_nullable'] else 'No',
                'Kind': type_info['kind']
            })

    # Sort by Type, then Field
    rows.sort(key=lambda x: (x['Type'], x['Field']))

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Type', 'Field', 'GraphQL Type', 'Base Type', 'Nullable', 'Kind'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"✓ CSV report generated: {output_path}")


def generate_json_report(analysis: Dict[str, Any], output_path: str):
    """Generate detailed JSON report."""
    with open(output_path, 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"✓ JSON report generated: {output_path}")


def generate_entity_summary(analysis: Dict[str, Any], output_path: str):
    """Generate summary report for key entities."""
    key_entities = [
        'Client', 'Invoice', 'Quote', 'Job', 'Property',
        'Request', 'Visit', 'User', 'Expense', 'TimeSheetEntry',
        'ProductOrService', 'TaxRate', 'Note'
    ]

    with open(output_path, 'w') as f:
        f.write("# Jobber GraphQL Schema - Entity Field Summary\n\n")
        f.write("## Key Entities\n\n")

        for entity in key_entities:
            if entity in analysis['field_inventory']:
                entity_info = analysis['field_inventory'][entity]
                f.write(f"### {entity} ({entity_info['field_count']} fields)\n\n")
                f.write("| Field | Type | Nullable |\n")
                f.write("|-------|------|----------|\n")

                for field in entity_info['fields']:
                    nullable = "✓" if field['is_nullable'] else "✗"
                    f.write(f"| {field['name']} | {field['type']} | {nullable} |\n")

                f.write("\n")

        f.write("\n## Complex Types\n\n")
        complex_types = ['InvoiceAmounts', 'QuoteAmounts', 'ClientAddress',
                        'PropertyAddress', 'ArrivalWindow']

        for type_name in complex_types:
            if type_name in analysis['field_inventory']:
                type_info = analysis['field_inventory'][type_name]
                f.write(f"### {type_name}\n\n")
                f.write("| Field | Type |\n")
                f.write("|-------|------|\n")

                for field in type_info['fields']:
                    f.write(f"| {field['name']} | {field['type']} |\n")

                f.write("\n")

        f.write(f"\n## Statistics\n\n")
        stats = analysis['statistics']
        f.write(f"- Total types: {stats['total_types']}\n")
        f.write(f"- Object types: {stats['object_types']}\n")
        f.write(f"- Scalar types: {stats['scalar_types']}\n")
        f.write(f"- Union types: {stats['union_types']}\n")
        f.write(f"- Enum types: {stats['enum_types']}\n")

    print(f"✓ Entity summary generated: {output_path}")


def main():
    """Main analysis workflow."""
    base_path = Path(__file__).parent.parent
    introspection_file = base_path / 'introspection_results.json'
    output_dir = base_path / 'analysis_output'

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    print(f"Loading introspection data from: {introspection_file}")
    results = load_introspection_data(str(introspection_file))

    print(f"Analyzing {len(results)} types...")
    analysis = analyze_types(results)

    print(f"\nStatistics:")
    for key, value in analysis['statistics'].items():
        print(f"  {key}: {value}")

    print(f"\nGenerating reports...")

    # Generate reports
    generate_csv_report(analysis, str(output_dir / 'field_inventory.csv'))
    generate_json_report(analysis, str(output_dir / 'field_analysis.json'))
    generate_entity_summary(analysis, str(output_dir / 'entity_summary.md'))

    print(f"\n✓ Analysis complete! Reports saved to: {output_dir}")
    print(f"\nKey findings:")
    print(f"  - {len(analysis['field_inventory'])} object types with fields")
    print(f"  - {len(analysis['nested_structures'])} types with nested structures")
    print(f"  - Reports: field_inventory.csv, field_analysis.json, entity_summary.md")


if __name__ == '__main__':
    main()
