#!/usr/bin/env python3
"""
Script to explore Jobber API entities using the OAuth token stored in tightbeam.db.

This script piggybacks on tightbeam's OAuth authentication to explore the Jobber API
and identify important top-level entities that would need to be migrated to another service.
"""  # noqa: E501

import json
import sqlite3
import sys
from datetime import datetime
from typing import Any, Optional

import requests


def get_oauth_token(db_path: str = "tightbeam.db") -> Optional[str]:
    """Retrieve the OAuth access token from tightbeam's database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT access_token, expires_at
            FROM oauth_tokens
            ORDER BY id DESC
            LIMIT 1
        """
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            access_token, expires_at = result
            # Check if token is expired
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry > datetime.now(expiry.tzinfo):
                return access_token
            else:
                print("⚠️  Token is expired. Please run 'tightbeam oauth init' to refresh.")
                return None
        else:
            print("❌ No OAuth token found. Please run 'tightbeam oauth init' first.")
            return None

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return None


def query_graphql(query: str, token: str) -> dict[str, Any]:
    """Execute a GraphQL query against the Jobber API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-JOBBER-GRAPHQL-VERSION": "2023-11-15",  # Required API version header
    }

    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": query},
        headers=headers,
    )

    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ API Error: {response.status_code}")
        print(response.text)
        return {}


def explore_schema(token: str) -> None:
    """Explore the GraphQL schema to find top-level query fields."""
    print("\n🔍 Exploring Jobber API Schema...")
    print("=" * 60)

    # Query to get the root query type fields
    schema_query = """
    query IntrospectionQuery {
      __schema {
        queryType {
          name
          fields {
            name
            description
            type {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
        }
      }
    }
    """

    result = query_graphql(schema_query, token)

    if "data" in result:
        fields = result["data"]["__schema"]["queryType"]["fields"]

        print(f"\n📊 Found {len(fields)} top-level query fields:\n")

        # Group fields by category
        entity_fields = []
        other_fields = []

        for field in fields:
            field_info = {
                "name": field["name"],
                "description": field.get("description", "No description"),
                "type": field["type"]["name"] or field["type"]["ofType"]["name"],
            }

            # Categorize based on field name patterns
            if any(
                field["name"].startswith(prefix)
                for prefix in [
                    "clients",
                    "jobs",
                    "quotes",
                    "invoices",
                    "requests",
                    "properties",
                    "users",
                    "expenses",
                    "assessments",
                    "timesheetEntries",
                    "productsAndServices",
                    "accounts",
                ]
            ):
                entity_fields.append(field_info)
            else:
                other_fields.append(field_info)

        # Print entity fields
        print("🏢 MAIN ENTITIES (likely need migration):")
        print("-" * 50)
        for field in sorted(entity_fields, key=lambda x: x["name"]):
            print(f"• {field['name']:<25} → {field['type']}")
            if field["description"] and field["description"] != "No description":
                print(f"  {field['description'][:70]}...")

        print("\n🔧 OTHER FIELDS:")
        print("-" * 50)
        for field in sorted(other_fields, key=lambda x: x["name"]):
            print(f"• {field['name']:<25} → {field['type']}")


def sample_entities(token: str) -> None:
    """Query sample data from major entities to understand their structure."""
    print("\n\n📋 Sampling Major Entities...")
    print("=" * 60)

    # Define queries for major entities
    entity_queries = {
        "Clients": """
            query {
                clients(first: 2) {
                    nodes {
                        id
                        name
                        firstName
                        lastName
                        companyName
                        isCompany
                        isLead
                        balance
                        createdAt
                        emails { address primary }
                        phones { number primary }
                    }
                    pageInfo { hasNextPage endCursor }
                    totalCount
                }
            }
        """,
        "Jobs": """
            query {
                jobs(first: 2) {
                    nodes {
                        id
                        jobNumber
                        title
                        jobStatus
                        jobType
                        total
                        client { name }
                        property { address { street city } }
                        createdAt
                    }
                    pageInfo { hasNextPage endCursor }
                    totalCount
                }
            }
        """,
        "Quotes": """
            query {
                quotes(first: 2) {
                    nodes {
                        id
                        quoteNumber
                        title
                        quoteStatus
                        amounts { total subtotal }
                        client { name }
                        createdAt
                    }
                    pageInfo { hasNextPage endCursor }
                    totalCount
                }
            }
        """,
        "Invoices": """
            query {
                invoices(first: 2) {
                    nodes {
                        id
                        invoiceNumber
                        subject
                        invoiceStatus
                        amounts { total subtotal }
                        client { name }
                        dueDate
                        issuedDate
                    }
                    pageInfo { hasNextPage endCursor }
                    totalCount
                }
            }
        """,
        "Properties": """
            query {
                properties(first: 2) {
                    nodes {
                        id
                        address { street city province postalCode }
                        client { name }
                        taxRate { name }
                    }
                    pageInfo { hasNextPage endCursor }
                    totalCount
                }
            }
        """,
        "Users": """
            query {
                users(first: 2) {
                    nodes {
                        id
                        name { first last }
                        role { name }
                        createdAt
                    }
                    pageInfo { hasNextPage endCursor }
                    totalCount
                }
            }
        """,
    }

    # Execute each query and display results
    for entity_name, query in entity_queries.items():
        print(f"\n🔸 {entity_name}:")
        print("-" * 40)

        result = query_graphql(query, token)

        if "data" in result and entity_name.lower() in result["data"]:
            data = result["data"][entity_name.lower()]

            # Show total count if available
            if "totalCount" in data:
                print(f"Total count: {data['totalCount']}")

            # Show sample records
            if "nodes" in data and data["nodes"]:
                print(f"Sample records ({len(data['nodes'])}):")
                for i, node in enumerate(data["nodes"], 1):
                    print(f"\n  Record {i}:")
                    print(json.dumps(node, indent=4))
            else:
                print("No records found.")

        elif "errors" in result:
            print(f"Error: {result['errors'][0]['message']}")


def analyze_relationships(token: str) -> None:
    """Analyze relationships between entities."""
    print("\n\n🔗 Entity Relationships Analysis...")
    print("=" * 60)

    # Query to understand relationships
    relationship_query = """
    query {
        clients(first: 1) {
            nodes {
                id
                name
                # Related entities
                jobs { totalCount }
                quotes { totalCount }
                invoices { totalCount }
                requests { totalCount }
                clientProperties { totalCount }
                notes { totalCount }
                noteAttachments { totalCount }
            }
        }

        jobs(first: 1) {
            nodes {
                id
                title
                # Related entities
                client { id name }
                property { id }
                invoices { totalCount }
                expenses { totalCount }
                timesheetEntries { totalCount }
                visits { totalCount }
                lineItems { totalCount }
                notes { totalCount }
            }
        }
    }
    """

    result = query_graphql(relationship_query, token)

    if "data" in result:
        print("\n📊 Entity Relationship Summary:\n")

        # Client relationships
        if "clients" in result["data"] and result["data"]["clients"]["nodes"]:
            client = result["data"]["clients"]["nodes"][0]
            print("CLIENT entity connects to:")
            for key, value in client.items():
                if isinstance(value, dict) and "totalCount" in value:
                    print(f"  → {key}: {value['totalCount']} records")

        # Job relationships
        if "jobs" in result["data"] and result["data"]["jobs"]["nodes"]:
            job = result["data"]["jobs"]["nodes"][0]
            print("\nJOB entity connects to:")
            for key, value in job.items():
                if isinstance(value, dict):
                    if "totalCount" in value:
                        print(f"  → {key}: {value['totalCount']} records")
                    elif "id" in value:
                        print(f"  → {key}: linked entity")


def main():
    """Main function to explore Jobber API."""
    print("🚀 Jobber API Explorer")
    print("=" * 60)

    # Get OAuth token from tightbeam database
    token = get_oauth_token()
    if not token:
        sys.exit(1)

    print("✅ Successfully retrieved OAuth token from tightbeam.db")

    # Explore the API
    explore_schema(token)
    sample_entities(token)
    analyze_relationships(token)

    # Summary of migration requirements
    print("\n\n📝 MIGRATION REQUIREMENTS SUMMARY")
    print("=" * 60)
    print(
        """
Based on the API exploration, here are the key entities that would need
to be migrated when moving from Jobber to another service:

CORE BUSINESS ENTITIES:
1. **Clients** - Customer records with contact info, leads, and balances
2. **Jobs** - Scheduled work events with visits and billing
3. **Quotes** - Cost estimates sent to clients
4. **Invoices** - Billing records with payments and line items
5. **Properties** - Service locations linked to clients

OPERATIONAL ENTITIES:
6. **Requests** - Work requests from clients
7. **Assessments** - Property assessments for planning
8. **Visits** - Individual service visits for jobs
9. **Expenses** - Business expenses and reimbursements
10. **TimeSheet Entries** - Time tracking for work performed

SUPPORTING ENTITIES:
11. **Users** - Team members and their roles
12. **Products/Services** - Service catalog with pricing
13. **Notes & Attachments** - Documentation and files
14. **Custom Fields** - Business-specific data fields
15. **Tags** - Categorization system

FINANCIAL ENTITIES:
16. **Payment Records** - Payment transactions
17. **Line Items** - Invoice/quote/job details
18. **Tax Rates** - Tax configuration by location

The migration would need to preserve the relationships between these
entities, especially the Client → Job → Invoice → Payment flow which
is central to the business operations.
"""
    )


if __name__ == "__main__":
    main()
