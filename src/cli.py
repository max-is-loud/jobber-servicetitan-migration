"""CLI module for TightBeam v2 Jobber data migration tool."""

import os
import sqlite3
import sys
import webbrowser
from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv

from .auth import AuthProvider, OAuth2Manager
from .clients import HttpClient, JobberClient
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

# Load environment variables from .env file
load_dotenv()

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
            "JOBBER_CLIENT_SECRET environment variable is required for OAuth2 operations"  # noqa: E501
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
        Repository instance with database connection and initialized schema
    """
    if db_path is None:
        db_path = Path("./tightbeam.db")

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.Connection(str(db_path))

    # Create repository and initialize schema
    repository = Repository(connection)
    repository.init_schema()

    return repository


@oauth_app.command("init")
def oauth_init(
    db: Annotated[
        Optional[Path], typer.Option(help="SQLite database path for token storage")
    ] = None,
    port: Annotated[int, typer.Option(help="Local callback server port")] = 8080,
    auto_complete: Annotated[
        bool,
        typer.Option(
            "--auto",
            help="Automatically complete OAuth2 flow with local callback server",
        ),
    ] = True,
) -> None:
    """
    Initialize OAuth2 authorization flow.

    By default, starts a local callback server to automatically handle the OAuth2 callback.
    Alternatively, generates an authorization URL for manual completion.
    """  # noqa: E501
    try:
        if auto_complete:
            # Start local callback server and auto-complete OAuth2 flow
            _oauth_init_with_server(db, port)
        else:
            # Manual OAuth2 flow (original behavior)
            _oauth_init_manual(db)

    except ConfigurationError as e:
        typer.echo(f"Configuration Error: {e}", err=True)
        typer.echo(
            "Please ensure JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, and JOBBER_REDIRECT_URI are set.",  # noqa: E501
            err=True,
        )
        sys.exit(1)

    except Exception as e:
        typer.echo(f"Unexpected Error: {e}", err=True)
        sys.exit(5)


def _oauth_init_with_server(db: Optional[Path], port: int) -> None:
    """Initialize OAuth2 flow with local callback server."""
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    # Storage for the authorization code
    auth_result: dict[str, Optional[str]] = {"code": None, "error": None, "state": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Parse the callback URL
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Extract authorization code and state
            code = query_params.get("code", [None])[0]
            error = query_params.get("error", [None])[0]
            state = query_params.get("state", [None])[0]

            if error:
                auth_result["error"] = error
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    f"""
                <html><body>
                <h1>❌ Authorization Failed</h1>
                <p>Error: {error}</p>
                <p>You can close this window and check your terminal.</p>
                </body></html>
                """.encode()
                )
            elif code:
                auth_result["code"] = code
                auth_result["state"] = state
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    """
                <html><body>
                <h1>✅ Authorization Successful!</h1>
                <p>Authorization code received. You can close this window.</p>
                <p>TightBeam is completing the setup automatically...</p>
                </body></html>
                """.encode()
                )
            else:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    """
                <html><body>
                <h1>⚠️ Invalid Callback</h1>
                <p>No authorization code received.</p>
                </body></html>
                """.encode()
                )

        def log_message(self, format, *args):
            # Suppress server logs
            pass

    # Create local callback server
    server = HTTPServer(("localhost", port), CallbackHandler)

    # Start server in background thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # Save original redirect URI
    original_redirect = os.environ.get("JOBBER_REDIRECT_URI")
    local_redirect = f"http://localhost:{port}/callback"

    try:
        # Temporarily set local redirect URI
        os.environ["JOBBER_REDIRECT_URI"] = local_redirect

        # Create OAuth2 manager with local redirect
        oauth_manager = _create_oauth2_manager()

        # Generate authorization URL
        auth_url, state = oauth_manager.get_authorization_url()

        typer.echo("🚀 Starting OAuth2 Authorization with Local Callback Server")
        typer.echo("=" * 60)
        typer.echo(f"🌐 Local callback server started on http://localhost:{port}")
        typer.echo()
        typer.echo("Opening authorization URL in your browser...")
        typer.echo(f"URL: {auth_url}")
        typer.echo()
        typer.echo("⏳ Waiting for authorization... (this will happen automatically)")
        typer.echo(
            "   Complete the authorization in your browser, then come back here!"
        )

        # Open browser
        try:
            webbrowser.open(auth_url)
            typer.echo("✅ Browser opened successfully")
        except Exception as e:
            # In WSL environment, try alternative methods
            import subprocess

            if "wsl" in os.uname().release.lower():
                try:
                    # Try using Windows browser via WSL
                    subprocess.run(
                        ["cmd.exe", "/c", "start", auth_url],
                        check=True,
                        capture_output=True,
                    )
                    typer.echo("✅ Browser opened via Windows")
                except subprocess.CalledProcessError:
                    typer.echo("⚠️ Could not open browser automatically", err=True)
                    typer.echo(
                        "🔗 Please manually copy and paste this URL into your browser:"
                    )
                    typer.echo(f"   {auth_url}")
            else:
                typer.echo(f"⚠️ Could not open browser: {e}", err=True)
                typer.echo(
                    "🔗 Please manually copy and paste this URL into your browser:"
                )
                typer.echo(f"   {auth_url}")

        # Wait for callback (with timeout)
        timeout = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < timeout:
            if auth_result["code"] or auth_result["error"]:
                break
            time.sleep(1)

        if auth_result["error"]:
            typer.echo(f"\n❌ Authorization failed: {auth_result['error']}")
            sys.exit(1)
        elif not auth_result["code"]:
            typer.echo(f"\n⏰ Authorization timed out after {timeout} seconds")
            typer.echo(
                "Please try again or use manual mode: tightbeam oauth init --no-auto"
            )
            sys.exit(1)

        # Verify state parameter
        if auth_result["state"] != state:
            typer.echo("\n🔒 Security Error: State parameter mismatch")
            sys.exit(1)

        typer.echo(f"\n🎉 Authorization code received: {auth_result['code'][:20]}...")
        typer.echo("🔄 Exchanging authorization code for tokens...")

        # Automatically complete the OAuth2 flow
        repository = _create_repository(db)

        # Exchange code for tokens
        token_data = oauth_manager.exchange_code_for_tokens(auth_result["code"])

        # Store tokens in database
        from datetime import datetime, timedelta, timezone

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
        typer.echo("🚀 You're all set! You can now run:")
        typer.echo("   tightbeam migrate --db ./your_data.sqlite")

    finally:
        # Restore original environment
        if original_redirect is not None:
            os.environ["JOBBER_REDIRECT_URI"] = original_redirect
        elif "JOBBER_REDIRECT_URI" in os.environ:
            del os.environ["JOBBER_REDIRECT_URI"]

        # Shutdown server
        server.shutdown()
        server.server_close()


def _oauth_init_manual(db: Optional[Path]) -> None:
    """Initialize OAuth2 flow manually (original behavior)."""
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
    typer.echo("After authorization, copy the authorization code from the callback URL")
    typer.echo("and run: tightbeam oauth callback --code YOUR_AUTHORIZATION_CODE")
    typer.echo()
    typer.echo(f"State parameter (for verification): {state}")

    # Open browser
    try:
        webbrowser.open(auth_url)
        typer.echo("✅ Browser opened successfully")
    except Exception as e:
        # In WSL environment, try alternative methods
        import subprocess

        if "wsl" in os.uname().release.lower():
            try:
                # Try using Windows browser via WSL
                subprocess.run(
                    ["cmd.exe", "/c", "start", auth_url],
                    check=True,
                    capture_output=True,
                )
                typer.echo("✅ Browser opened via Windows")
            except subprocess.CalledProcessError:
                typer.echo("⚠️ Could not open browser automatically", err=True)
                typer.echo(
                    "🔗 Please manually copy and paste this URL into your browser:"
                )
                typer.echo(f"   {auth_url}")
        else:
            typer.echo(f"⚠️ Could not open browser: {e}", err=True)
            typer.echo("🔗 Please manually copy and paste this URL into your browser:")
            typer.echo(f"   {auth_url}")


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
        from datetime import datetime, timedelta, timezone

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
    and OAuth2 configuration status.
    """
    try:
        # Check OAuth2 configuration
        try:
            _get_oauth2_config()
        except ConfigurationError:
            typer.echo("🔑 Authentication Status: No OAuth2 Configuration")
            typer.echo("=" * 50)
            typer.echo("OAuth2 environment variables not found")
            typer.echo()
            typer.echo("Required OAuth2 environment variables:")
            typer.echo("- JOBBER_CLIENT_ID")
            typer.echo("- JOBBER_CLIENT_SECRET")
            typer.echo("- JOBBER_REDIRECT_URI")
            typer.echo()
            typer.echo(
                "After setting variables, run 'tightbeam oauth init' to authorize"
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
        from .auth.token_utils import get_token_expiration, is_token_expired

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
                "Are you sure you want to clear OAuth2 tokens? You will need to re-authorize."  # noqa: E501
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

        # Initialize repository first for OAuth token storage
        repository = Repository(connection)

        # Create OAuth2 components
        try:
            client_id, client_secret, redirect_uri = AuthProvider.get_oauth2_config()
            http_client = HttpClient()
            oauth_manager = OAuth2Manager(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                http_client=http_client,
            )
            auth_provider = AuthProvider(oauth_manager, repository)
        except ConfigurationError as e:
            raise ConfigurationError(
                f"OAuth2 configuration error: {e}. "
                "Please ensure JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, and JOBBER_REDIRECT_URI "  # noqa: E501
                "are set and run 'tightbeam oauth init' to authorize."
            ) from None

        # Core dependencies
        jobber_client = JobberClient(auth_provider)
        entity_mapper = EntityMapper()

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
        typer.echo(
            "Please ensure OAuth2 environment variables are set and run 'tightbeam oauth init' to authorize.",  # noqa: E501
            err=True,
        )
        sys.exit(1)

    except JobberApiError as e:
        # API communication issues
        typer.echo(f"API Error: {e}", err=True)
        typer.echo(
            "Please check your internet connection and OAuth2 token validity.", err=True
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
