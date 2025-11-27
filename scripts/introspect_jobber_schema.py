#!/usr/bin/env python3
"""
Introspect Jobber GraphQL schema to get exact type definitions.

Usage:
    1. First authenticate: uv run tightbeam oauth init
    2. Then run: uv run python scripts/introspect_jobber_schema.py

This will query the Jobber GraphQL API for all type definitions and save
the results to introspection_results.json
"""

import json
import sys
from pathlib import Path

# Add src to path so we can import from the project
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.clients.jobber_client import JobberClient
from src.config import ConfigManagerImpl
from src.loggers.rich_logger import RichLogger
from src.cli.services.factories import ServiceFactory


# All introspection queries we need to run
INTROSPECTION_QUERIES = {
    "UserEmail": """
    {
      __type(name: "UserEmail") {
        name
        kind
        fields {
          name
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
    """,
    "UserPhone": """
    {
      __type(name: "UserPhone") {
        name
        kind
        fields {
          name
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
    """,
    "Timezone": """
    {
      __type(name: "Timezone") {
        name
        kind
        fields {
          name
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
    """,
    "PropertyAddress": """
    {
      __type(name: "PropertyAddress") {
        name
        kind
        fields {
          name
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
    """,
    "Property": """
    {
      __type(name: "Property") {
        name
        kind
        fields {
          name
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
    """,
    "QuoteLineItem": """
    {
      __type(name: "QuoteLineItem") {
        name
        kind
        fields {
          name
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
    """,
    "InvoiceLineItem": """
    {
      __type(name: "InvoiceLineItem") {
        name
        kind
        fields {
          name
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
    """,
    "Visit": """
    {
      __type(name: "Visit") {
        name
        kind
        fields {
          name
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
    """,
    "RequestNoteUnion": """
    {
      __type(name: "RequestNoteUnion") {
        name
        kind
        possibleTypes {
          name
        }
      }
    }
    """,
    "QuoteNoteUnion": """
    {
      __type(name: "QuoteNoteUnion") {
        name
        kind
        possibleTypes {
          name
        }
      }
    }
    """,
    "JobNoteUnion": """
    {
      __type(name: "JobNoteUnion") {
        name
        kind
        possibleTypes {
          name
        }
      }
    }
    """,
    "InvoiceNoteUnion": """
    {
      __type(name: "InvoiceNoteUnion") {
        name
        kind
        possibleTypes {
          name
        }
      }
    }
    """,
    "Client": """
    {
      __type(name: "Client") {
        name
        kind
        fields {
          name
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
    """,
    "Email": """
    {
      __type(name: "Email") {
        name
        kind
        fields {
          name
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
    """,
    "ClientPhoneNumber": """
    {
      __type(name: "ClientPhoneNumber") {
        name
        kind
        fields {
          name
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
    """,
    "ClientAddress": """
    {
      __type(name: "ClientAddress") {
        name
        kind
        fields {
          name
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
    """,
    "Request": """
    {
      __type(name: "Request") {
        name
        kind
        fields {
          name
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
    """,
    "Quote": """
    {
      __type(name: "Quote") {
        name
        kind
        fields {
          name
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
    """,
    "Job": """
    {
      __type(name: "Job") {
        name
        kind
        fields {
          name
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
    """,
    "Invoice": """
    {
      __type(name: "Invoice") {
        name
        kind
        fields {
          name
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
    """,
    "User": """
    {
      __type(name: "User") {
        name
        kind
        fields {
          name
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
    """,
    "Expense": """
    {
      __type(name: "Expense") {
        name
        kind
        fields {
          name
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
    """,
    "TimeSheetEntry": """
    {
      __type(name: "TimeSheetEntry") {
        name
        kind
        fields {
          name
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
    """,
    "ProductOrService": """
    {
      __type(name: "ProductOrService") {
        name
        kind
        fields {
          name
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
    """,
    "QuoteAmounts": """
    {
      __type(name: "QuoteAmounts") {
        name
        kind
        fields {
          name
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
    """,
    "InvoiceAmounts": """
    {
      __type(name: "InvoiceAmounts") {
        name
        kind
        fields {
          name
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
    """,
}


def main():
    """Run all introspection queries and save results."""

    # Initialize logger and config
    logger = RichLogger(verbose=True)
    config_manager = ConfigManagerImpl()

    logger.info("Initializing Jobber client...")

    # Create services using ServiceFactory (will use existing OAuth tokens from tightbeam.sqlite)
    try:
        from pathlib import Path
        repository = ServiceFactory.create_repository(db=Path("tightbeam.sqlite"))
        auth_provider = ServiceFactory.create_auth_provider(repository, logger)
        client = JobberClient(
            auth_provider=auth_provider,
            config_manager=config_manager
        )
    except Exception as e:
        logger.error(f"Failed to initialize Jobber client: {e}")
        logger.error("Make sure you've run: uv run tightbeam oauth init")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    logger.info(f"Running {len(INTROSPECTION_QUERIES)} introspection queries...")

    results = {}
    errors = {}

    for type_name, query in INTROSPECTION_QUERIES.items():
        logger.info(f"Introspecting {type_name}...")

        try:
            # Execute the introspection query using the private method
            response = client._execute_graphql_request(query)

            if "errors" in response:
                errors[type_name] = response["errors"]
                logger.warning(f"  ⚠️  Errors for {type_name}: {response['errors']}")
            else:
                results[type_name] = response.get("data", {}).get("__type")

                # Show field count for object types
                if results[type_name]:
                    if results[type_name].get("kind") == "OBJECT":
                        field_count = len(results[type_name].get("fields", []))
                        logger.success(f"  ✓ {type_name}: {field_count} fields")
                    elif results[type_name].get("kind") == "UNION":
                        type_count = len(results[type_name].get("possibleTypes", []))
                        logger.success(f"  ✓ {type_name}: {type_count} possible types")
                    elif results[type_name].get("kind") == "SCALAR":
                        logger.success(f"  ✓ {type_name}: SCALAR type")
                else:
                    logger.warning(f"  ⚠️  {type_name}: Type not found in schema")

        except Exception as e:
            errors[type_name] = str(e)
            logger.error(f"  ✗ Failed to introspect {type_name}: {e}")

    # Save results
    output_file = Path(__file__).parent.parent / "introspection_results.json"

    output_data = {
        "results": results,
        "errors": errors,
        "summary": {
            "total_queries": len(INTROSPECTION_QUERIES),
            "successful": len(results),
            "failed": len(errors)
        }
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.success(f"\n✓ Introspection complete!")
    logger.info(f"  Results saved to: {output_file}")
    logger.info(f"  Successful: {len(results)}/{len(INTROSPECTION_QUERIES)}")

    if errors:
        logger.warning(f"  Errors: {len(errors)}")
        logger.info("\nErrors:")
        for type_name, error in errors.items():
            logger.error(f"  - {type_name}: {error}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
