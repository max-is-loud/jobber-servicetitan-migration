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
oauth_app = typer.Typer(
    name="oauth",
    help="OAuth authentication setup commands",
    add_completion=False,
)
app.add_typer(oauth_app, name="oauth")


@oauth_app.command()
def init() -> None:
    """
    Initialize OAuth authentication setup.
    
    Guides you through setting up the required environment variables
    for Jobber API OAuth authentication.
    """
    typer.echo("🔧 TightBeam OAuth Setup")
    typer.echo("========================")
    typer.echo()
    typer.echo("To authenticate with the Jobber API, you need to set up the following environment variables:")
    typer.echo()
    typer.echo("Required OAuth Environment Variables:")
    typer.echo("  • JOBBER_CLIENT_ID - Your Jobber application's client ID")
    typer.echo("  • JOBBER_CLIENT_SECRET - Your Jobber application's client secret")
    typer.echo("  • JOBBER_REDIRECT_URI - OAuth redirect URI for your application")
    typer.echo("  • JOBBER_TOKEN - Valid Jobber API access token")
    typer.echo()
    typer.echo("You can set these in your shell environment:")
    typer.echo()
    typer.echo("  export JOBBER_CLIENT_ID='your_client_id'")
    typer.echo("  export JOBBER_CLIENT_SECRET='your_client_secret'")
    typer.echo("  export JOBBER_REDIRECT_URI='your_redirect_uri'")
    typer.echo("  export JOBBER_TOKEN='your_access_token'")
    typer.echo()
    typer.echo("Or create a .env file in your project directory with these values.")
    typer.echo()
    typer.echo("For more information on obtaining these credentials, visit:")
    typer.echo("📖 https://developer.getjobber.com/docs/authentication")


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
        typer.echo("To configure authentication, you can either:", err=True)
        typer.echo("  1. Run 'tightbeam oauth init' to set up OAuth authentication", err=True)
        typer.echo("  2. Manually set the following environment variables:", err=True)
        typer.echo("     - JOBBER_CLIENT_ID", err=True)
        typer.echo("     - JOBBER_CLIENT_SECRET", err=True)
        typer.echo("     - JOBBER_REDIRECT_URI", err=True)
        typer.echo("     - JOBBER_TOKEN", err=True)
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
