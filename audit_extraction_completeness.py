#!/usr/bin/env python3
"""
Audit script to verify data extraction completeness.

This script compares GraphQL queries with their corresponding mappers and models
to identify any missing fields or mismatches that could cause data loss during migration.
"""

import re
import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


def extract_graphql_fields(query_text: str) -> Set[str]:
    """Extract all field names from a GraphQL query."""
    fields = set()

    # Remove comments and string literals
    query_text = re.sub(r"#.*", "", query_text)

    # Find all field names (word followed by optional arguments and {)
    # This matches patterns like: fieldName, fieldName(args), fieldName {
    pattern = r"\b([a-z][a-zA-Z0-9]*)\s*(?:\([^)]*\))?\s*[{\s]"
    matches = re.findall(pattern, query_text)

    # Also match simple fields without braces
    simple_pattern = r"\n\s+([a-z][a-zA-Z0-9]*)\s*\n"
    simple_matches = re.findall(simple_pattern, query_text)

    fields.update(matches)
    fields.update(simple_matches)

    # Remove GraphQL keywords
    keywords = {"query", "mutation", "fragment", "on", "first", "after", "edges", "node", "pageInfo"}
    fields = {f for f in fields if f not in keywords}

    return fields


def extract_mapper_fields(mapper_code: str, method_name: str) -> Set[str]:
    """Extract all fields accessed in a mapper method using data.get()."""
    fields = set()

    # Find all data.get("fieldName") patterns
    pattern = r'data\.get\(["\']([^"\']+)["\']\)'
    matches = re.findall(pattern, mapper_code)
    fields.update(matches)

    # Find nested access patterns like address.get("line1")
    nested_pattern = r'\.get\(["\']([^"\']+)["\']\)'
    nested_matches = re.findall(nested_pattern, mapper_code)
    fields.update(nested_matches)

    return fields


def extract_model_fields(model_file: Path) -> Set[str]:
    """Extract all fields from a dataclass model."""
    fields = set()

    try:
        content = model_file.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.add(item.target.id)
    except Exception as e:
        print(f"  ⚠️  Error parsing {model_file}: {e}")

    return fields


def analyze_entity_extraction(
    entity_name: str,
    query_method: str,
    mapper_method: str,
    model_file: Path,
    jobber_client_code: str,
    entity_mapper_code: str,
) -> Dict:
    """Analyze a single entity's extraction completeness."""

    # Extract GraphQL query
    query_pattern = rf'def {query_method}\(self.*?\).*?return f?"""(.*?)"""'
    query_match = re.search(query_pattern, jobber_client_code, re.DOTALL)

    if not query_match:
        return {"entity": entity_name, "status": "ERROR", "message": f"Could not find query method {query_method}"}

    query_text = query_match.group(1)
    graphql_fields = extract_graphql_fields(query_text)

    # Extract mapper method
    mapper_pattern = rf"def {mapper_method}\(self.*?\).*?(?=\n    def |\nclass |\Z)"
    mapper_match = re.search(mapper_pattern, entity_mapper_code, re.DOTALL)

    if not mapper_match:
        return {"entity": entity_name, "status": "ERROR", "message": f"Could not find mapper method {mapper_method}"}

    mapper_code = mapper_match.group(0)
    mapper_fields = extract_mapper_fields(mapper_code, mapper_method)

    # Extract model fields
    model_fields = extract_model_fields(model_file)

    # Find discrepancies
    in_query_not_mapper = graphql_fields - mapper_fields
    in_mapper_not_query = mapper_fields - graphql_fields

    # Filter out common nested fields and metadata
    common_nested = {
        "address",
        "number",
        "value",
        "email",
        "first",
        "last",
        "identifier",
        "line1",
        "line2",
        "city",
        "stateProvince",
        "postalCode",
        "country",
        "latitude",
        "longitude",
        "primary",
        "description",
    }

    in_query_not_mapper = {f for f in in_query_not_mapper if f not in common_nested}

    return {
        "entity": entity_name,
        "status": "OK" if not in_query_not_mapper else "WARNING",
        "graphql_fields": sorted(graphql_fields),
        "mapper_fields": sorted(mapper_fields),
        "model_fields": sorted(model_fields),
        "in_query_not_mapper": sorted(in_query_not_mapper),
        "in_mapper_not_query": sorted(in_mapper_not_query),
        "query_sample": query_text[:200] + "..." if len(query_text) > 200 else query_text,
    }


def main():
    """Run the extraction completeness audit."""

    base_path = Path(__file__).parent

    # Read source files
    jobber_client_file = base_path / "src" / "clients" / "jobber_client.py"
    entity_mapper_file = base_path / "src" / "mappers" / "entity_mapper.py"
    models_dir = base_path / "src" / "models"

    jobber_client_code = jobber_client_file.read_text()
    entity_mapper_code = entity_mapper_file.read_text()

    # Define entities to audit (extract mode queries)
    entities_to_audit = [
        ("Client", "_get_clients_query", "map_client", "client.py"),
        ("Invoice", "_get_invoices_query", "map_invoice", "invoice.py"),
        ("Quote", "_get_quotes_query", "map_quote", "quote.py"),
        ("Job", "_get_jobs_query", "map_job", "job.py"),
        ("Request", "_get_requests_query", "map_request", "request.py"),
        # Note: Some entities only have map queries, not full extract queries
    ]

    print("=" * 80)
    print("DATA EXTRACTION COMPLETENESS AUDIT")
    print("=" * 80)
    print()

    results = []

    for entity_name, query_method, mapper_method, model_filename in entities_to_audit:
        print(f"Analyzing {entity_name}...")
        model_file = models_dir / model_filename

        result = analyze_entity_extraction(
            entity_name, query_method, mapper_method, model_file, jobber_client_code, entity_mapper_code
        )

        results.append(result)

        if result["status"] == "ERROR":
            print(f"  ❌ {result['message']}")
        elif result["status"] == "WARNING":
            print(f"  ⚠️  Found {len(result['in_query_not_mapper'])} fields in query not accessed by mapper")
            for field in result["in_query_not_mapper"]:
                print(f"      - {field}")
        else:
            print(f"  ✅ OK")
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    warnings = [r for r in results if r["status"] == "WARNING"]
    errors = [r for r in results if r["status"] == "ERROR"]

    print(f"Total entities audited: {len(results)}")
    print(f"OK: {len(results) - len(warnings) - len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Errors: {len(errors)}")
    print()

    if warnings:
        print("ENTITIES WITH POTENTIAL DATA LOSS:")
        for result in warnings:
            print(f"  - {result['entity']}: {len(result['in_query_not_mapper'])} fields not mapped")
            print(f"    Missing: {', '.join(result['in_query_not_mapper'])}")

    print()
    print("=" * 80)
    print("DETAILED FINDINGS")
    print("=" * 80)
    print()

    # Detailed report for Client (the one we know has issues)
    client_result = next((r for r in results if r["entity"] == "Client"), None)
    if client_result:
        print("CLIENT ENTITY DETAILED ANALYSIS:")
        print(f"  GraphQL fields requested: {', '.join(client_result['graphql_fields'][:10])}...")
        print(f"  Mapper fields accessed: {', '.join(client_result['mapper_fields'][:10])}...")
        print(f"  Model fields defined: {', '.join(client_result['model_fields'])}")
        print()


if __name__ == "__main__":
    main()
