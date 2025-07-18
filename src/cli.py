"""CLI module for TightBeam v2 Jobber data migration tool."""

import sqlite3
import sys
from pathlib import Path
from typing import Annotated

import typer

from .auth import AuthProvider
from .clients import JobberClient
from .coordinators import MigrationCoordinator
from .exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    RepositoryError,
)
from .loggers import ConsoleLogger
from .mappers import EntityMapper
from .repositories import Repository

# Create Typer application
app = typer.Typer(
    name="tightbeam",
    help="TightBeam v2 - Jobber Data Migration Tool",
    add_completion=False,
)

# Create OAuth subcommand group
oauth_app = typer.Typer(help="OAuth2 authentication management commands")
app.add_typer(oauth_app, name="oauth")


@oauth_app.command()
def status() -> None:
    """
    Check the status of OAuth2 authentication configuration.
    
    Verifies that the JOBBER_TOKEN environment variable is set and validates
    the token by making a test API call to the Jobber GraphQL endpoint.
    This helps troubleshoot authentication issues before running data migration.
    """
    try:
        # Test authentication configuration
        auth_provider = AuthProvider()
        
        # Check if token is available
        typer.echo("🔍 Checking OAuth2 configuration...")
        token = auth_provider.get_token()
        typer.echo("✅ JOBBER_TOKEN environment variable is set")
        
        # Test API connectivity with a minimal query
        typer.echo("🔗 Testing API connectivity...")
        jobber_client = JobberClient(auth_provider)
        
        # Use a simple introspection query to validate the token
        test_query = """
        query TestConnection {
          __schema {
            queryType {
              name
            }
          }
        }
        """
        
        # Make test API call
        response = jobber_client._execute_graphql_request(test_query)
        
        # Check if we got a valid response
        if response and "data" in response:
            typer.echo("✅ OAuth2 token is valid and API is accessible")
            typer.echo("🎉 Authentication setup is working correctly!")
        else:
            typer.echo("⚠️  API returned unexpected response format", err=True)
            typer.echo("Please verify your token permissions.", err=True)
            sys.exit(1)
            
    except ConfigurationError as e:
        typer.echo("❌ Configuration Error:", err=True)
        typer.echo(f"   {e}", err=True)
        typer.echo("\n💡 To fix this:", err=True)
        typer.echo("   1. Set JOBBER_TOKEN environment variable:", err=True)
        typer.echo("      export JOBBER_TOKEN=\"your_token_here\"", err=True)
        typer.echo("   2. Or create a .env file with:", err=True)
        typer.echo("      JOBBER_TOKEN=your_token_here", err=True)
        sys.exit(1)
        
    except JobberApiError as e:
        typer.echo("❌ API Connection Error:", err=True)
        typer.echo(f"   {e}", err=True)
        typer.echo("\n💡 To fix this:", err=True)
        typer.echo("   1. Check your internet connection", err=True)
        typer.echo("   2. Verify your token is not expired", err=True)
        typer.echo("   3. Ensure your token has proper permissions", err=True)
        sys.exit(2)
        
    except Exception as e:
        typer.echo("❌ Unexpected Error:", err=True)
        typer.echo(f"   {e}", err=True)
        typer.echo("Please report this issue with the full error message.", err=True)
        sys.exit(5)


@app.command()
def migrate(
    db: Annotated[Path, typer.Option(help="SQLite database path")],
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
) -> None:
    """
    Migrate client and invoice data from Jobber API to SQLite database.

    Fetches all clients and invoices from the Jobber GraphQL API using cursor-based
    pagination and stores them in the specified SQLite database. Requires JOBBER_TOKEN
    environment variable to be set with a valid Jobber API token.

    Args:
        db: Path to SQLite database file (will be created if it doesn't exist)
        verbose: Enable verbose logging output for debugging
    """
    connection = None

    try:
        # Create database connection
        logger = ConsoleLogger(verbose=verbose)
        logger.info(f"Connecting to database: {db}")

        # Ensure parent directory exists
        db.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.Connection(str(db))

        # Dependency injection - wire up all components
        logger.debug("Initializing application components")

        # Core dependencies
        auth_provider = AuthProvider()
        jobber_client = JobberClient(auth_provider)
        entity_mapper = EntityMapper()
        repository = Repository(connection)

        # Create migration coordinator with all dependencies
        migration_coordinator = MigrationCoordinator(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
        )

        # Execute migration workflow
        logger.info("Starting migration process")
        summary = migration_coordinator.migrate()

        # Display final summary
        summary_data = {
            "clients_processed": summary.clients_processed,
            "invoices_processed": summary.invoices_processed,
            "duration": summary.format_duration(),
            "errors_count": len(summary.errors),
            "status": (
                "SUCCESS" if len(summary.errors) == 0 else "COMPLETED_WITH_ERRORS"
            ),
        }

        logger.log_summary(summary_data)

        # Display errors if any
        if summary.errors:
            logger.error(
                f"Migration completed with {len(summary.errors)} non-fatal errors:"
            )
            for i, error in enumerate(summary.errors, 1):
                logger.error(f"  {i}. {error}")

        # Exit with appropriate code
        exit_code = 0 if len(summary.errors) == 0 else 1
        logger.info(f"Migration completed with exit code {exit_code}")
        sys.exit(exit_code)

    except ConfigurationError as e:
        # Configuration/environment issues
        typer.echo(f"Configuration Error: {e}", err=True)
        typer.echo("Please ensure JOBBER_TOKEN environment variable is set.", err=True)
        sys.exit(1)

    except JobberApiError as e:
        # API communication issues
        typer.echo(f"API Error: {e}", err=True)
        typer.echo(
            "Please check your internet connection and API token validity.", err=True
        )
        sys.exit(2)

    except MappingError as e:
        # Data transformation issues
        typer.echo(f"Data Mapping Error: {e}", err=True)
        typer.echo(
            "The API response format may have changed. Please check for updates.",
            err=True,
        )
        sys.exit(3)

    except RepositoryError as e:
        # Database operation issues
        typer.echo(f"Database Error: {e}", err=True)
        typer.echo("Please check database file permissions and disk space.", err=True)
        sys.exit(4)

    except KeyboardInterrupt:
        # User interruption
        typer.echo("\\nMigration interrupted by user.", err=True)
        sys.exit(130)

    except Exception as e:
        # Unexpected errors
        typer.echo(f"Unexpected Error: {e}", err=True)
        typer.echo("Please report this issue with the full error message.", err=True)
        sys.exit(5)

    finally:
        # Ensure database connection is always closed
        if connection:
            connection.close()


def main() -> None:
    """Entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
