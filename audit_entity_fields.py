#!/usr/bin/env python3
"""
Detailed entity field audit script.

Compares GraphQL queries with mappers to identify missing or mismatched fields
across all entity types.
"""

import re
from pathlib import Path
from typing import Dict, List, Set


def extract_graphql_fields_detailed(query_text: str, root_pattern: str) -> Dict[str, Set[str]]:
    """Extract field names from GraphQL query, organized by nested structure."""

    # Find the main entity block (e.g., "clients {" or "invoices {")
    # Use non-greedy match for arguments to handle f-strings containing parentheses
    # Handle both single { and double {{ braces (for f-strings)
    # Using concatenation to avoid f-string escaping hell
    entity_pattern = (
        root_pattern + r"\s*\(.*?\)\s*\{{1,2}\s*edges\s*\{{1,2}\s*node\s*\{{1,2}(.*?)\}{1,2}\s*\}{1,2}\s*pageInfo"
    )
    match = re.search(entity_pattern, query_text, re.DOTALL | re.IGNORECASE)

    if not match:
        return {}

    node_content = match.group(1)

    # Extract all field names (simple fields and nested objects)
    fields = {}

    # Simple fields (no braces)
    simple_pattern = r"\n\s+([a-z][a-zA-Z0-9]*)\s*\n"
    simple_fields = set(re.findall(simple_pattern, node_content))
    fields["simple"] = simple_fields

    # Nested object fields (e.g., "emails { address }")
    nested_pattern = r"([a-z][a-zA-Z0-9]*)\s*\{([^}]+)\}"
    nested_matches = re.findall(nested_pattern, node_content)

    for parent, children in nested_matches:
        child_fields = re.findall(r"\b([a-z][a-zA-Z0-9]*)\b", children)
        # Filter out GraphQL keywords
        child_fields = [f for f in child_fields if f not in {"edges", "node", "on", "first", "after"}]
        if child_fields:
            fields[parent] = set(child_fields)

    return fields


def extract_mapper_field_accesses(mapper_code: str) -> Dict[str, List[str]]:
    """Extract all field access patterns from mapper code."""
    accesses = {}

    # Find extract_primary_field calls
    primary_pattern = r'MapperUtils\.extract_primary_field\(([^,]+),\s*["\']([^"\']+)["\']'
    matches = re.findall(primary_pattern, mapper_code)
    for var_name, field_name in matches:
        var_name = var_name.strip()
        if var_name not in accesses:
            accesses[var_name] = []
        accesses[var_name].append(f"extract_primary_field(..., '{field_name}')")

    # Find extract_all_fields calls
    all_pattern = r'MapperUtils\.extract_all_fields\(([^,]+),\s*["\']([^"\']+)["\']'
    matches = re.findall(all_pattern, mapper_code)
    for var_name, field_name in matches:
        var_name = var_name.strip()
        if var_name not in accesses:
            accesses[var_name] = []
        accesses[var_name].append(f"extract_all_fields(..., '{field_name}')")

    # Find data.get() calls (handling optional default value)
    get_pattern = r'data\.get\(["\']([^"\']+)["\']'
    matches = re.findall(get_pattern, mapper_code)
    accesses["data"] = [f"get('{m}')" for m in matches]

    # Find extract_id_from_relationship calls
    id_rel_pattern = r'MapperUtils\.extract_id_from_relationship\(data\.get\(["\']([^"\']+)["\']'
    matches = re.findall(id_rel_pattern, mapper_code)
    for field_name in matches:
        if "relationships" not in accesses:
            accesses["relationships"] = []
        accesses["relationships"].append(f"extract_id('{field_name}')")

    # Find safe_get_nested calls
    nested_pattern = r'MapperUtils\.safe_get_nested\([^,]+,\s*["\']([^"\']+)["\']'
    matches = re.findall(nested_pattern, mapper_code)
    for field_name in matches:
        if "nested" not in accesses:
            accesses["nested"] = []
        accesses["nested"].append(f"safe_get('{field_name}')")

    # DEBUG: Print extracted code length
    # print(f"DEBUG: Extracted mapper code length: {len(mapper_code)}")
    # print(f"DEBUG: First 50 chars: {mapper_code[:50]}")

    return accesses


def audit_entity(
    entity_name: str,
    query_method: str,
    mapper_method: str,
    jobber_client_code: str,
    entity_mapper_code: str,
    query_root: str = None,
) -> Dict:
    """Audit a single entity for field completeness."""

    # Extract GraphQL query
    # Try method pattern first
    query_pattern = rf'def {query_method}\(self.*?\).*?return f?"""(.*?)"""'
    query_match = re.search(query_pattern, jobber_client_code, re.DOTALL)

    if not query_match:
        # Try constant pattern
        query_pattern = rf'{query_method}\s*=\s*f?"""(.*?)"""'
        query_match = re.search(query_pattern, jobber_client_code, re.DOTALL)

    if not query_match:
        return {
            "entity": entity_name,
            "status": "ERROR",
            "message": f"Could not find query method/constant {query_method}",
        }

    query_text = query_match.group(1)

    # Determine query root pattern
    if query_root:
        root_pattern = re.escape(query_root)
    else:
        root_pattern = rf"{entity_name.lower()}s?"

    graphql_fields = extract_graphql_fields_detailed(query_text, root_pattern)

    # Extract mapper method
    mapper_pattern = rf"def {mapper_method}\(self.*?\).*?(?=\n    def |\nclass |\Z)"
    mapper_match = re.search(mapper_pattern, entity_mapper_code, re.DOTALL)

    if not mapper_match:
        return {"entity": entity_name, "status": "ERROR", "message": f"Could not find mapper method {mapper_method}"}

    mapper_code = mapper_match.group(0)
    mapper_accesses = extract_mapper_field_accesses(mapper_code)

    return {
        "entity": entity_name,
        "status": "OK",
        "graphql_fields": graphql_fields,
        "mapper_accesses": mapper_accesses,
        "query_sample": query_text[:300] + "...",
    }


def main() -> None:
    """Run detailed entity field audit."""

    base_path = Path(__file__).parent

    # Read source files
    jobber_client_file = base_path / "src" / "clients" / "jobber_client.py"
    entity_mapper_file = base_path / "src" / "mappers" / "entity_mapper.py"

    jobber_client_code = jobber_client_file.read_text()
    entity_mapper_code = entity_mapper_file.read_text()

    # Entities to audit: (Name, QueryMethod, MapperMethod, QueryRoot)
    entities = [
        ("Client", "_get_clients_query", "map_client", "clients"),
        ("Invoice", "_get_invoices_query", "map_invoice", "invoices"),
        ("Quote", "_get_quotes_query", "map_quote", "quotes"),
        ("Job", "_get_jobs_query", "map_job", "jobs"),
        ("Request", "_get_requests_query", "map_request", "requests"),
        ("Property", "PROPERTIES_QUERY", "map_property", "properties"),
        ("User", "USERS_QUERY", "map_user", "users"),
        ("Expense", "EXPENSES_QUERY", "map_expense", "expenses"),
        ("Visit", "VISITS_QUERY", "map_visit", "visits"),
        ("TimesheetEntry", "TIMESHEET_ENTRIES_QUERY", "map_timesheet_entry", "timesheetEntries"),
        ("ProductService", "PRODUCTS_SERVICES_QUERY", "map_product_service", "productsAndServices"),
        ("TaxRate", "TAX_RATES_QUERY", "map_tax_rate", "taxRates"),
    ]

    print("=" * 80)
    print("DETAILED ENTITY FIELD AUDIT")
    print("=" * 80)
    print()

    for entity_name, query_method, mapper_method, query_root in entities:
        print(f"\n{'=' * 80}")
        print(f"ENTITY: {entity_name}")
        print("=" * 80)

        result = audit_entity(
            entity_name, query_method, mapper_method, jobber_client_code, entity_mapper_code, query_root
        )

        if result["status"] == "ERROR":
            print(f"❌ {result['message']}")
            continue

        print("\nGraphQL Query Fields:")
        for field_type, fields in result["graphql_fields"].items():
            if fields:
                print(f"  {field_type}: {', '.join(sorted(fields))}")

        print("\nMapper Field Accesses:")
        for var_name, accesses in result["mapper_accesses"].items():
            if accesses:
                print(f"  {var_name}: {', '.join(accesses[:5])}")

        # Check for potential issues
        issues = []

        # Check emails/phones specifically
        if "emails" in result["graphql_fields"]:
            email_fields = result["graphql_fields"]["emails"]
            if "address" in email_fields:
                # Check if mapper uses correct field
                email_accesses = result["mapper_accesses"].get("emails", [])
                if any("'value'" in acc for acc in email_accesses):
                    issues.append("⚠️  Emails: GraphQL has 'address' but mapper uses 'value'")
                elif any("'address'" in acc for acc in email_accesses):
                    issues.append("✅ Emails: Correctly using 'address'")

        if "phones" in result["graphql_fields"]:
            phone_fields = result["graphql_fields"]["phones"]
            if "number" in phone_fields:
                phone_accesses = result["mapper_accesses"].get("phones", [])
                if any("'value'" in acc for acc in phone_accesses):
                    issues.append("⚠️  Phones: GraphQL has 'number' but mapper uses 'value'")
                elif any("'number'" in acc for acc in phone_accesses):
                    issues.append("✅ Phones: Correctly using 'number'")

        if issues:
            print("\nIssues Found:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n✅ No obvious field mapping issues detected")


if __name__ == "__main__":
    main()
