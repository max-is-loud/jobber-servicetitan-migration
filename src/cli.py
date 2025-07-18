"""CLI module for TightBeam v2 Jobber data migration tool."""

import os
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Annotated, Optional, cast
from urllib.parse import parse_qs, urlparse

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
from .rate_limiting import (
    ExponentialBackoffStrategy,
    MetricsCollector,
    RateLimitedHttpClient,
    TokenBucketRateLimiter,
)
from .repositories import Repository

# Load environment variables from .env file
load_dotenv()

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
    typer.echo(
        "To authenticate with the Jobber API, you need to set up the following environment variables:"  # noqa: E501
    )
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


# OAuth2 command subgroup
oauth_app = typer.Typer(help="OAuth2 authentication management commands")
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

        # Handle missing expires_in field (Jobber API doesn't always include it)
        expires_in = token_data.get(
            "expires_in", 3600
        )  # Default to 1 hour if not provided
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

        expires_in = token_data.get("expires_in")
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise OAuth2Error("Invalid or missing 'expires_in' field in token data.")
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
def oauth_status() -> None:
    """
    Check the status of authentication configuration.
    Shows current authentication mode and token status.
    """
    typer.echo("🔍 TightBeam Authentication Status")
    typer.echo("==================================")
    typer.echo()

    # Check for environment token first
    jobber_token = os.environ.get("JOBBER_TOKEN")
    if jobber_token:
        typer.echo("🔑 Authentication Mode: Environment Token")
        typer.echo("✅ JOBBER_TOKEN environment variable is set")
        typer.echo()

        try:
            # Test token with simple API call using HttpClient directly
            http_client = HttpClient()
            headers = {
                "Authorization": f"Bearer {jobber_token}",
                "Content-Type": "application/json",
            }

            # Test API call
            test_query = {
                "query": """
                query TestConnection {
                  __schema {
                    queryType {
                      name
                    }
                  }
                }
                """
            }

            response = http_client.post(
                url="https://api.getjobber.com/api/graphql",
                headers=headers,
                json=test_query,
            )

            if response and "data" in response:
                typer.echo("✅ Authentication token is valid and API is accessible")
                typer.echo("🎉 Authentication setup is working correctly!")
            else:
                typer.echo("⚠️  API returned unexpected response format", err=True)

        except Exception as e:
            typer.echo("❌ Token validation failed:", err=True)
            typer.echo(f"   {e}", err=True)
        return

    # Check OAuth2 configuration
    try:
        oauth_manager = _create_oauth2_manager()
        repository = _create_repository()

        # Check for stored tokens
        stored_tokens = repository.get_oauth_tokens()

        if stored_tokens:
            typer.echo("🔑 Authentication Mode: OAuth2")
            typer.echo("✅ OAuth2 tokens are stored")

            # Test token validity
            try:
                auth_provider = AuthProvider(oauth_manager, repository)
                auth_provider.get_token()  # Verify it works
                typer.echo("✅ OAuth2 tokens are valid")
                typer.echo("🎉 Authentication setup is working correctly!")
            except Exception as e:
                typer.echo("⚠️  OAuth2 token validation failed:", err=True)
                typer.echo(f"   {e}", err=True)
                typer.echo("💡 Try running 'tightbeam oauth init' to re-authorize")
        else:
            typer.echo("🔑 Authentication Mode: OAuth2 (Not Configured)")
            typer.echo("⚠️  OAuth2 environment variables are set but no tokens stored")
            typer.echo("💡 Run 'tightbeam oauth init' to complete OAuth2 setup")

    except ConfigurationError:
        typer.echo("🔑 Authentication Mode: Not Configured")
        typer.echo("❌ No authentication configured")
        typer.echo()
        typer.echo("💡 To configure authentication:")
        typer.echo("   Option 1: Set JOBBER_TOKEN environment variable")
        typer.echo("   Option 2: Configure OAuth2 and run 'tightbeam oauth init'")


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
    pagination and stores them in the specified SQLite database. Requires authentication
    via JOBBER_TOKEN environment variable or OAuth2 configuration.

    Authentication options:
    1. Set JOBBER_TOKEN environment variable with a valid Jobber API token
    2. Configure OAuth2 variables (JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, JOBBER_REDIRECT_URI)
       and run 'tightbeam oauth init'

    Args:
        db: Path to SQLite database file (will be created if it doesn't exist)
        verbose: Enable verbose logging output for debugging
    """  # noqa: E501
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

        # Core dependencies with rate limiting integration
        jobber_client = JobberClient(auth_provider)

        # Initialize rate limiting components
        logger.debug("Setting up rate limiting (2000 tokens, 400/minute)")
        rate_limiter = TokenBucketRateLimiter(capacity=2000, refill_rate=400)
        backoff_strategy = ExponentialBackoffStrategy()
        metrics_collector = MetricsCollector()

        # Wrap HTTP client with rate limiting
        http_client = HttpClient()
        rate_limited_client = RateLimitedHttpClient(
            http_client,
            rate_limiter,
            backoff_strategy,
            max_retries=5,
            metrics_collector=metrics_collector,
        )
        jobber_client.http_client = cast(HttpClient, rate_limited_client)

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

        # Display final summary with rate limiting metrics
        rate_metrics = metrics_collector.get_human_readable_summary()
        summary_data = {
            "clients_processed": summary.clients_processed,
            "invoices_processed": summary.invoices_processed,
            "duration": summary.format_duration(),
            "errors_count": len(summary.errors),
            "status": (
                "SUCCESS" if len(summary.errors) == 0 else "COMPLETED_WITH_ERRORS"
            ),
            # Add rate limiting metrics
            "rate_limiting": {
                "requests_per_minute": rate_metrics["requests_per_minute"],
                "total_requests": rate_metrics["total_requests"],
                "throttled_requests": rate_metrics["throttled_requests"],
                "rate_limit_errors": rate_metrics["rate_limit_errors"],
                "average_response_time": rate_metrics["average_response_time"],
                "throttle_rate": rate_metrics["throttle_rate"],
            },
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
        typer.echo(
            "  1. Run 'tightbeam oauth init' to set up OAuth authentication", err=True
        )  # noqa: E501
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
