"""CLI module for TightBeam v2 Jobber data migration tool."""

import os
import sqlite3
import sys
import webbrowser
from pathlib import Path
from typing import Annotated, Optional

import typer

from .auth import AuthProvider, OAuth2Manager
from .clients import JobberClient, HttpClient
from .coordinators import MigrationCoordinator
from .exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    OAuth2Error,
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

# OAuth2 command subgroup
oauth_app = typer.Typer(
    name="oauth",
    help="OAuth2 authentication management commands",
    add_completion=False,
)
app.add_typer(oauth_app, name="oauth")


def _get_oauth2_config() -> tuple[str, str, str]:
    """
    Get OAuth2 configuration from environment variables.

    Returns:
        Tuple of (client_id, client_secret, redirect_uri)

    Raises:
        ConfigurationError: If required OAuth2 environment variables are missing
    """
    client_id = os.environ.get("JOBBER_CLIENT_ID")
    client_secret = os.environ.get("JOBBER_CLIENT_SECRET")
    redirect_uri = os.environ.get("JOBBER_REDIRECT_URI")

    if not client_id:
        raise ConfigurationError(
            "JOBBER_CLIENT_ID environment variable is required for OAuth2 operations"
        )
    if not client_secret:
        raise ConfigurationError(
            "JOBBER_CLIENT_SECRET environment variable is required for OAuth2 operations"
        )
    if not redirect_uri:
        raise ConfigurationError(
            "JOBBER_REDIRECT_URI environment variable is required for OAuth2 operations"
        )

    return client_id, client_secret, redirect_uri


def _create_oauth2_manager() -> OAuth2Manager:
    """
    Create OAuth2Manager instance with environment configuration.

    Returns:
        Configured OAuth2Manager instance

    Raises:
        ConfigurationError: If OAuth2 configuration is invalid
    """
    client_id, client_secret, redirect_uri = _get_oauth2_config()
    http_client = HttpClient()

    return OAuth2Manager(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        http_client=http_client,
    )


def _create_repository(db_path: Optional[Path] = None) -> Repository:
    """
    Create Repository instance with database connection.

    Args:
        db_path: Optional database path, defaults to ./tightbeam.db

    Returns:
        Repository instance with database connection
    """
    if db_path is None:
        db_path = Path("./tightbeam.db")

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.Connection(str(db_path))

    return Repository(connection)


@oauth_app.command("init")
def oauth_init(
    db: Annotated[
        Optional[Path], typer.Option(help="SQLite database path for token storage")
    ] = None,
) -> None:
    """
    Initialize OAuth2 authorization flow.

    Generates an authorization URL and opens it in the default browser.
    After user authorization, use 'oauth callback' command with the authorization code.
    """
    try:
        # Create OAuth2 manager
        oauth_manager = _create_oauth2_manager()

        # Generate authorization URL
        auth_url, state = oauth_manager.get_authorization_url()

        typer.echo("🔐 OAuth2 Authorization Required")
        typer.echo("=" * 50)
        typer.echo()
        typer.echo("Opening authorization URL in your browser...")
        typer.echo(f"URL: {auth_url}")
        typer.echo()
        typer.echo(
            "After authorization, copy the authorization code from the callback URL"
        )
        typer.echo("and run: tightbeam oauth callback --code YOUR_AUTHORIZATION_CODE")
        typer.echo()
        typer.echo(f"State parameter (for verification): {state}")

        # Open browser
        try:
            webbrowser.open(auth_url)
            typer.echo("✅ Browser opened successfully")
        except Exception as e:
            typer.echo(f"⚠️ Could not open browser: {e}", err=True)
            typer.echo("Please manually open the URL above")

    except ConfigurationError as e:
        typer.echo(f"Configuration Error: {e}", err=True)
        typer.echo(
            "Please ensure JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, and JOBBER_REDIRECT_URI are set.",
            err=True,
        )
        sys.exit(1)

    except Exception as e:
        typer.echo(f"Unexpected Error: {e}", err=True)
        sys.exit(5)


@oauth_app.command("callback")
def oauth_callback(
    code: Annotated[str, typer.Option(help="Authorization code from OAuth2 callback")],
    db: Annotated[
        Optional[Path], typer.Option(help="SQLite database path for token storage")
    ] = None,
) -> None:
    """
    Handle OAuth2 callback and exchange authorization code for tokens.

    Use this command after completing the authorization flow initiated by 'oauth init'.
    """
    try:
        # Create OAuth2 manager and repository
        oauth_manager = _create_oauth2_manager()
        repository = _create_repository(db)

        typer.echo("🔄 Exchanging authorization code for tokens...")

        # Exchange code for tokens
        token_data = oauth_manager.exchange_code_for_tokens(code)

        # Store tokens in database
        from datetime import datetime, timezone, timedelta

        expires_in = token_data["expires_in"]
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()

        repository.save_oauth_tokens(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=expires_at,
        )

        typer.echo("✅ OAuth2 tokens stored successfully!")
        typer.echo()
        typer.echo("You can now use the migration tool with OAuth2 authentication.")
        typer.echo("Run 'tightbeam oauth status' to check token status.")

    except ConfigurationError as e:
        typer.echo(f"Configuration Error: {e}", err=True)
        sys.exit(1)

    except OAuth2Error as e:
        typer.echo(f"OAuth2 Error: {e}", err=True)
        typer.echo(
            "Please try the authorization flow again with 'tightbeam oauth init'",
            err=True,
        )
        sys.exit(1)

    except RepositoryError as e:
        typer.echo(f"Database Error: {e}", err=True)
        typer.echo("Please check database file permissions.", err=True)
        sys.exit(4)

    except Exception as e:
        typer.echo(f"Unexpected Error: {e}", err=True)
        sys.exit(5)


@oauth_app.command("status")
def oauth_status(
    db: Annotated[
        Optional[Path], typer.Option(help="SQLite database path for token storage")
    ] = None,
) -> None:
    """
    Show current OAuth2 token status and expiration information.

    Displays whether OAuth2 tokens are stored, their expiration status,
    and authentication mode recommendations.
    """
    try:
        # Check environment token first
        env_token = os.environ.get("JOBBER_TOKEN")
        if env_token:
            typer.echo("🔑 Authentication Status: Environment Token Mode")
            typer.echo("=" * 50)
            typer.echo("Using JOBBER_TOKEN environment variable")
            typer.echo("OAuth2 features are available but not active")
            typer.echo()
            typer.echo(
                "To use OAuth2, unset JOBBER_TOKEN and run 'tightbeam oauth init'"
            )
            return

        # Check OAuth2 configuration
        try:
            _get_oauth2_config()
        except ConfigurationError as e:
            typer.echo("🔑 Authentication Status: No Configuration")
            typer.echo("=" * 50)
            typer.echo("Neither JOBBER_TOKEN nor OAuth2 configuration found")
            typer.echo()
            typer.echo("Options:")
            typer.echo("1. Set JOBBER_TOKEN environment variable, OR")
            typer.echo(
                "2. Set OAuth2 environment variables and run 'tightbeam oauth init'"
            )
            typer.echo(
                "   Required: JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, JOBBER_REDIRECT_URI"
            )
            return

        # Check OAuth2 tokens
        repository = _create_repository(db)
        token_data = repository.get_oauth_tokens()

        if not token_data:
            typer.echo("🔑 Authentication Status: OAuth2 Not Authorized")
            typer.echo("=" * 50)
            typer.echo("OAuth2 configuration found but no tokens stored")
            typer.echo("Run 'tightbeam oauth init' to authorize")
            return

        # Check token expiration
        from .auth.token_utils import is_token_expired, get_token_expiration

        access_token = token_data["access_token"]
        created_at = token_data["created_at"]

        typer.echo("🔑 Authentication Status: OAuth2 Active")
        typer.echo("=" * 50)
        typer.echo(f"Tokens created: {created_at}")

        try:
            expiration = get_token_expiration(access_token)
            if expiration:
                typer.echo(f"Token expires: {expiration.isoformat()}")

                if is_token_expired(access_token):
                    typer.echo(
                        "⚠️ Token Status: EXPIRED (will auto-refresh on next use)"
                    )
                else:
                    typer.echo("✅ Token Status: VALID")
            else:
                typer.echo("Token expiration: Unknown (no exp claim)")
        except Exception:
            typer.echo("Token expiration: Unable to determine")

        typer.echo()
        typer.echo("OAuth2 authentication is ready for use!")

    except RepositoryError as e:
        typer.echo(f"Database Error: {e}", err=True)
        sys.exit(4)

    except Exception as e:
        typer.echo(f"Unexpected Error: {e}", err=True)
        sys.exit(5)


@oauth_app.command("clear")
def oauth_clear(
    db: Annotated[
        Optional[Path], typer.Option(help="SQLite database path for token storage")
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")
    ] = False,
) -> None:
    """
    Clear stored OAuth2 tokens from database.

    This will log out the user from OAuth2 authentication.
    The user will need to re-authorize using 'oauth init' command.
    """
    try:
        repository = _create_repository(db)
        token_data = repository.get_oauth_tokens()

        if not token_data:
            typer.echo("No OAuth2 tokens found to clear.")
            return

        # Confirmation prompt
        if not confirm:
            proceed = typer.confirm(
                "Are you sure you want to clear OAuth2 tokens? You will need to re-authorize."
            )
            if not proceed:
                typer.echo("Operation cancelled.")
                return

        # Clear tokens
        repository.clear_oauth_tokens()

        typer.echo("✅ OAuth2 tokens cleared successfully!")
        typer.echo("Run 'tightbeam oauth init' to re-authorize if needed.")

    except RepositoryError as e:
        typer.echo(f"Database Error: {e}", err=True)
        sys.exit(4)

    except Exception as e:
        typer.echo(f"Unexpected Error: {e}", err=True)
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
