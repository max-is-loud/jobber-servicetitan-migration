"""CLI module for TightBeam v2 Jobber data migration tool."""

import os
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import parse_qs, urlparse

import typer
from dotenv import load_dotenv

from .auth import AuthProvider, OAuth2Manager
from .clients import HttpClient, JobberClient
from .config import ConfigManagerImpl
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

# Create migrate subcommand group
migrate_app = typer.Typer(
    name="migrate",
    help="Data migration commands",
    add_completion=False,
    invoke_without_command=True,
)
app.add_typer(migrate_app, name="migrate")


@migrate_app.callback()
def migrate_callback(
    ctx: typer.Context,
    db: Annotated[Optional[Path], typer.Option(help="SQLite database path")] = None,
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
    deferred_notes: Annotated[
        bool,
        typer.Option(
            "--deferred-notes/--immediate-notes",
            help="Use deferred notes loading to prevent GraphQL throttling",
        ),
    ] = True,
    enable_notes_persistence: Annotated[
        bool,
        typer.Option(
            "--enable-notes-persistence",
            help="Enable temporary storage for note references (for very large migrations)",
        ),
    ] = False,
    optimization_level: Annotated[
        str,
        typer.Option(
            help=(
                "Rate limiting optimization level:\n"
                "• conservative (4 req/s): Safest option with 52% safety margin, recommended for production\n"
                "• moderate (6 req/s): Balanced performance with 28% safety margin, default recommended\n"
                "• aggressive (8 req/s): Maximum speed with 4% safety margin, requires active monitoring"
            )
        ),
    ] = "moderate",
    enable_cost_monitoring: Annotated[
        bool,
        typer.Option(
            "--enable-cost-monitoring/--disable-cost-monitoring",
            help=(
                "Enable GraphQL cost monitoring and rate limit tracking. "
                "Provides detailed performance insights and API usage statistics. "
                "Recommended for performance analysis and optimization tuning."
            ),
        ),
    ] = True,
    cost_monitoring_verbose: Annotated[
        bool,
        typer.Option(
            "--cost-monitoring-verbose",
            help=(
                "Enable verbose cost monitoring output during migration. "
                "Shows detailed GraphQL query costs, accuracy percentages, and rate limit analysis. "
                "Use for detailed performance debugging and optimization insights."
            ),
        ),
    ] = False,
) -> None:
    """
    Data migration commands for TightBeam.

    If no subcommand is provided, runs the 'all' command by default.
    """
    # Initialize configuration manager
    try:
        config_manager = ConfigManagerImpl()
    except ConfigurationError as e:
        typer.echo(f"Error: Configuration loading failed: {e}")
        raise typer.Exit(1)

    # Validate optimization level using ConfigManager
    try:
        config_manager.get_rate_limit_config(optimization_level)
    except ConfigurationError:
        available_levels = ["conservative", "moderate", "aggressive"]
        typer.echo(
            f"Error: Invalid optimization level '{optimization_level}'. "
            f"Choose from: {', '.join(available_levels)}"
        )
        raise typer.Exit(1)

    # Store shared configuration in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "db": db or Path("tightbeam.db"),
            "verbose": verbose,
            "deferred_notes": deferred_notes,
            "enable_notes_persistence": enable_notes_persistence,
            "optimization_level": optimization_level,
            "enable_cost_monitoring": enable_cost_monitoring,
            "cost_monitoring_verbose": cost_monitoring_verbose,
        }
    )

    if ctx.invoked_subcommand is None:
        # Default to 'all' command when no subcommand is specified
        migrate_all(
            db=ctx.obj["db"],
            verbose=verbose,
            deferred_notes=deferred_notes,
            enable_notes_persistence=enable_notes_persistence,
            optimization_level=optimization_level,
            enable_cost_monitoring=enable_cost_monitoring,
            cost_monitoring_verbose=cost_monitoring_verbose,
        )


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

        # Exit successfully after OAuth completion
        sys.exit(0)

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
    server_thread = threading.Thread(
        target=server.serve_forever, name="oauth-callback-server"
    )
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
        typer.echo()

    finally:
        # Restore original environment
        if original_redirect is not None:
            os.environ["JOBBER_REDIRECT_URI"] = original_redirect
        elif "JOBBER_REDIRECT_URI" in os.environ:
            del os.environ["JOBBER_REDIRECT_URI"]

        # Shutdown server properly
        try:
            server.shutdown()
            server.server_close()
            # Wait for server thread to finish
            if server_thread.is_alive():
                server_thread.join(timeout=2.0)
        except Exception:
            # Ignore cleanup errors
            pass


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


@migrate_app.command("all")
def migrate_all(
    db: Annotated[Path, typer.Option(help="SQLite database path")] = Path(
        "tightbeam.db"
    ),
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
    deferred_notes: Annotated[
        bool,
        typer.Option(
            "--deferred-notes/--immediate-notes",
            help="Use deferred notes loading to prevent GraphQL throttling",
        ),
    ] = True,
    enable_notes_persistence: Annotated[
        bool,
        typer.Option(
            "--enable-notes-persistence",
            help="Enable temporary storage for note references (for very large migrations)",
        ),
    ] = False,
    optimization_level: str = "moderate",
    enable_cost_monitoring: bool = True,
    cost_monitoring_verbose: bool = False,
) -> None:
    """
    Migrate all data from Jobber API to SQLite database.

    Fetches all clients, invoices, quotes, notes, and attachments from the Jobber
    GraphQL API using cursor-based pagination and stores them in the specified SQLite
    database. Attachment files are downloaded to ./attachments directory. Features
    deferred notes loading by default to prevent GraphQL throttling issues.

    Deferred Notes Loading (Default):
    - Collects note IDs during client/invoice processing
    - Processes notes separately to avoid nested query complexity
    - Prevents GraphQL throttling on large datasets
    - Use --immediate-notes to disable (legacy mode)

    Authentication options:
    1. Set JOBBER_TOKEN environment variable with a valid Jobber API token
    2. Configure OAuth2 variables (JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, JOBBER_REDIRECT_URI)
       and run 'tightbeam oauth init'

    Args:
        db: Path to SQLite database file (defaults to tightbeam.db, will be created if it doesn't exist)
        verbose: Enable verbose logging output for debugging
        deferred_notes: Use deferred notes loading to prevent throttling (default: True)
        enable_notes_persistence: Enable temporary storage for very large migrations (default: False)
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
        # Initialize configuration manager for consistent settings
        config_manager = ConfigManagerImpl()

        # Initialize metrics collector for cost monitoring if enabled
        metrics_collector = (
            MetricsCollector(repository=repository) if enable_cost_monitoring else None
        )
        jobber_client = JobberClient(
            auth_provider,
            metrics_collector=metrics_collector,
            config_manager=config_manager,
        )

        # Initialize rate limiting components with dynamic optimization settings
        rate_config = config_manager.get_rate_limit_config(optimization_level)
        capacity = rate_config["capacity"]
        refill_rate = rate_config["refill_rate"]
        initial_tokens = rate_config["initial_tokens"]
        requests_per_second = refill_rate / 60
        logger.info(
            f"Setting up {optimization_level.upper()} rate limiting "
            f"({capacity} tokens, {refill_rate}/minute, ~{requests_per_second:.0f} req/sec)"
        )
        # Dynamic optimization for Jobber GraphQL API based on user selection
        rate_limiter = TokenBucketRateLimiter(
            capacity=capacity, refill_rate=refill_rate, initial_tokens=initial_tokens
        )
        # Use backoff strategy from configuration for GraphQL throttling
        backoff_config = config_manager.get_backoff_config()
        backoff_strategy = ExponentialBackoffStrategy(
            initial_delay=backoff_config["initial_delay"],
            max_delay=backoff_config["max_delay"],
            multiplier=backoff_config["multiplier"],
            jitter_factor=backoff_config["jitter_factor"],
        )

        # Wrap HTTP client with rate limiting - maximum retries for Jobber GraphQL API
        http_client = HttpClient()
        rate_limited_client = RateLimitedHttpClient(
            http_client,
            rate_limiter,
            backoff_strategy,
            max_retries=15,  # Maximum retries for GraphQL throttling
            metrics_collector=metrics_collector,
            auth_provider=auth_provider,  # Enable reactive OAuth token refresh on 401 errors
        )
        jobber_client.set_http_client(rate_limited_client)

        # Verify rate limiting is properly configured
        logger.info(
            f"Rate limiter configured: {rate_limiter.get_capacity()} tokens, "
            f"{rate_limiter.get_refill_rate()}/min, "
            f"{rate_limiter.get_available_tokens():.1f} available"
        )
        logger.info(
            f"Jobber-optimized settings: ~3 requests per second maximum, "
            f"starting with {rate_limiter.get_available_tokens():.0f} tokens"
        )

        entity_mapper = EntityMapper()

        # Create optional extractors for enhanced entity coverage
        from .extractors import (
            AttachmentDownloader,
            NoteReferenceCollector,
            NotesExtractor,
            QuotesExtractor,
        )

        # Create note components for deferred processing if enabled
        note_reference_collector = None
        notes_extractor = None

        if deferred_notes:
            logger.info(
                "🔄 Deferred notes loading enabled - preventing GraphQL throttling"
            )
            note_reference_collector = NoteReferenceCollector(
                repository=repository,
                logger=logger,
                enable_persistence=enable_notes_persistence,
                batch_size=1000,
            )
            notes_extractor = NotesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                config_manager=config_manager,
            )

            if enable_notes_persistence:
                logger.info("💾 Notes persistence enabled for large migration volumes")
        else:
            logger.info("⚡ Immediate notes processing enabled (legacy mode)")

        quotes_extractor = QuotesExtractor(
            jobber_client,
            entity_mapper,
            repository,
            logger,
            config_manager=config_manager,
        )
        attachment_downloader = AttachmentDownloader(
            jobber_client,
            entity_mapper,
            repository,
            logger,
            base_download_path="./attachments",
            config_manager=config_manager,
        )

        # Create migration coordinator with all dependencies including optional extractors  # noqa: E501
        migration_coordinator = MigrationCoordinator(
            jobber_client=jobber_client,
            entity_mapper=entity_mapper,
            repository=repository,
            logger=logger,
            note_reference_collector=note_reference_collector,
            notes_extractor=notes_extractor,
            quotes_extractor=quotes_extractor,
            attachment_downloader=attachment_downloader,
            config_manager=config_manager,
        )

        # Execute migration workflow
        logger.info("Starting migration process")

        # Enhanced startup logging for optimization configuration
        logger.info("🚀 Performance Configuration:")
        logger.info(f"   • Optimization level: {optimization_level.upper()}")
        logger.info(f"   • Target rate: {requests_per_second:.0f} requests/sec")

        # Calculate safety margin
        api_limit_per_sec = 500 / 60  # 500 req/min = ~8.33 req/sec
        safety_margin = (
            (api_limit_per_sec - requests_per_second) / api_limit_per_sec
        ) * 100
        logger.info(f"   • Safety margin: {safety_margin:.0f}% below API limits")

        # Cost monitoring status
        if enable_cost_monitoring:
            logger.info("   • GraphQL cost monitoring: ENABLED")
            if cost_monitoring_verbose:
                logger.info("   • Verbose cost monitoring: ENABLED")
        else:
            logger.info("   • GraphQL cost monitoring: DISABLED")

        logger.info("🔍 Rate Limiter Status:")
        logger.info(
            f"   • Available tokens: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}"
        )
        logger.info(
            f"   • Refill rate: {rate_limiter.get_refill_rate()}/min (~{rate_limiter.get_refill_rate()/60:.1f}/sec)"
        )

        summary = migration_coordinator.migrate()

        # Enhanced performance logging and metrics display
        logger.info("\n📊 Migration Performance Analysis:")

        # Calculate migration speed
        total_entities = (
            summary.clients_processed
            + summary.invoices_processed
            + summary.quotes_processed
            + summary.notes_processed
            + summary.attachments_processed
        )
        if summary.duration_seconds > 0:
            entities_per_minute = (total_entities / summary.duration_seconds) * 60
            logger.info(
                f"   • Migration speed: {entities_per_minute:.1f} entities/minute"
            )
            logger.info(
                f"   • Total entities: {total_entities} in {summary.duration_seconds:.1f}s"
            )

        # Enhanced rate limiting and cost metrics display
        if metrics_collector:
            rate_metrics = metrics_collector.get_human_readable_summary()
            cost_stats = metrics_collector.get_cost_statistics()
            rate_limit_status = metrics_collector.get_rate_limit_status()

            # GraphQL cost monitoring (verbose mode)
            if cost_monitoring_verbose and cost_stats["total_queries"] > 0:
                logger.info("🧮 GraphQL Cost Analysis:")
                logger.info(f"   • Total queries: {cost_stats['total_queries']}")
                logger.info(
                    f"   • Avg requested cost: {cost_stats['avg_requested_cost']:.0f}"
                )
                logger.info(
                    f"   • Avg actual cost: {cost_stats['avg_actual_cost']:.0f}"
                )
                logger.info(
                    f"   • Cost accuracy: {cost_stats['cost_accuracy_percentage']:.1f}%"
                )

            # Rate limit status
            if rate_limit_status["remaining_requests"] is not None:
                logger.info("🔄 Rate Limit Status:")
                logger.info(
                    f"   • Remaining requests: {rate_limit_status['remaining_requests']}"
                )
                if (
                    rate_limit_status["seconds_until_reset"] is not None
                    and rate_limit_status["seconds_until_reset"] > 0
                ):
                    logger.info(
                        f"   • Reset in: {rate_limit_status['seconds_until_reset']:.0f}s"
                    )
        else:
            logger.info("   • Cost monitoring: DISABLED")
            rate_metrics = {
                "throttle_rate": "0.0%",
                "throttled_requests": 0,
                "requests_per_minute": "N/A",
            }
        summary_data = {
            "clients_processed": summary.clients_processed,
            "invoices_processed": summary.invoices_processed,
            "quotes_processed": summary.quotes_processed,
            "notes_processed": summary.notes_processed,
            "note_references_collected": summary.note_references_collected,
            "attachments_processed": summary.attachments_processed,
            "files_downloaded": summary.files_downloaded,
            "total_bytes_downloaded": summary.total_bytes_downloaded,
            "download_failures": summary.download_failures,
            "duration": summary.format_duration(),
            "errors_count": len(summary.errors),
            "status": (
                "SUCCESS" if len(summary.errors) == 0 else "COMPLETED_WITH_ERRORS"
            ),
            # Add migration mode information
            "deferred_notes_enabled": deferred_notes,
            "notes_persistence_enabled": enable_notes_persistence,
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

        # Display deferred notes performance information
        if deferred_notes and summary.note_references_collected > 0:
            logger.info("📊 Deferred Notes Processing Performance:")
            logger.info(
                f"   • Note references collected: {summary.note_references_collected:,}"
            )
            logger.info(f"   • Notes processed separately: {summary.notes_processed:,}")
            throttle_rate = float(rate_metrics["throttle_rate"].rstrip("%"))
            if throttle_rate < 5.0:  # Less than 5% throttling
                logger.info("   ✅ GraphQL throttling successfully minimized!")
            else:
                logger.info(
                    f"   ⚠️  Some throttling occurred: {rate_metrics['throttle_rate']} of requests"
                )
            logger.info(
                "   🎯 Trading complex nested queries for simple individual queries"
            )

        # Display final token status and rate limiting effectiveness
        logger.info("🔍 Final Token Status:")
        logger.info(
            f"   • Tokens remaining: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}"
        )
        logger.info(
            f"   • Total requests: {rate_metrics['total_requests']} "
            f"(avg: {rate_metrics['requests_per_minute']}/min)"
        )
        logger.info(
            f"   • Throttling rate: {rate_metrics['throttle_rate']} "
            f"({rate_metrics['throttled_requests']} throttled)"
        )
        if float(rate_metrics["throttle_rate"].rstrip("%")) < 1.0:
            logger.info("   ✅ Jobber-optimized rate limiting working effectively!")
        elif float(rate_metrics["throttle_rate"].rstrip("%")) < 5.0:
            logger.info("   ⚠️  Minor throttling - rate limiting working well")
        else:
            logger.info(
                "   🔴 Significant throttling - consider further rate limit tuning"
            )

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


@migrate_app.command("quotes")
def migrate_quotes(
    ctx: typer.Context,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
) -> None:
    """
    Extract quote data from Jobber API to SQLite database.

    Fetches all quotes from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Uses centralized rate limiting
    configuration from parent command options.

    Note: Individual migrate commands use simplified GraphQL queries and don't
    support deferred notes loading. For deferred notes, use 'migrate all' command.

    Args:
        page_limit: Optional limit on number of pages to process (for testing)
    """  # noqa: E501
    # Get shared configuration from context
    config = ctx.obj or {}

    # NOTE: Individual migrate commands don't currently support deferred notes
    # The deferred_notes setting only applies to 'migrate all' command
    # Individual commands use simplified GraphQL queries to reduce complexity

    _execute_entity_extraction(
        entity_type="quotes",
        db=config.get("db", Path("tightbeam.db")),
        verbose=config.get("verbose", False),
        page_limit=page_limit,
        optimization_level=config.get("optimization_level", "moderate"),
    )


@migrate_app.command("attachments")
def migrate_attachments(
    ctx: typer.Context,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
    download_path: Annotated[
        str, typer.Option("--download-path", help="Base path for attachment downloads")
    ] = "./attachments",
) -> None:
    """
    Extract attachment data and download files from Jobber API to local storage.

    Fetches all attachments from the Jobber GraphQL API using cursor-based pagination,
    downloads the binary files to organized local storage, and stores metadata in the
    specified SQLite database. Uses centralized rate limiting configuration from parent
    command options (--optimization-level).

    Args:
        page_limit: Optional limit on number of pages to process (for testing)
        download_path: Base directory for attachment file downloads
    """  # noqa: E501
    # Get shared configuration from context
    config = ctx.obj or {}

    _execute_entity_extraction(
        entity_type="attachments",
        db=config.get("db", Path("tightbeam.db")),
        verbose=config.get("verbose", False),
        page_limit=page_limit,
        download_path=download_path,
        optimization_level=config.get("optimization_level", "moderate"),
    )


@migrate_app.command("users")
def migrate_users(
    ctx: typer.Context,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
) -> None:
    """
    Extract user data from Jobber API to SQLite database.

    Fetches all users from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Includes user notes extraction
    for performance tracking and administrative information. Uses centralized rate
    limiting configuration from parent command options (--optimization-level).

    Args:
        page_limit: Optional limit on number of pages to process (for testing)
    """
    # Get shared configuration from context
    config = ctx.obj or {}

    _execute_entity_extraction(
        entity_type="users",
        db=config.get("db", Path("tightbeam.db")),
        verbose=config.get("verbose", False),
        page_limit=page_limit,
        optimization_level=config.get("optimization_level", "moderate"),
    )


@migrate_app.command("expenses")
def migrate_expenses(
    db: Annotated[Path, typer.Option(help="SQLite database path")] = Path(
        "tightbeam.db"
    ),
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
) -> None:
    """
    Extract expense data from Jobber API to SQLite database.

    Fetches all expenses from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Includes job-related cost
    tracking and vendor information for financial management. Requires authentication
    via JOBBER_TOKEN environment variable or OAuth2 configuration.

    Args:
        db: Path to SQLite database file (defaults to tightbeam.db, will be created
            if it doesn't exist)
        verbose: Enable verbose logging output for debugging
        page_limit: Optional limit on number of pages to process (for testing)
    """
    _execute_entity_extraction(
        entity_type="expenses",
        db=db,
        verbose=verbose,
        page_limit=page_limit,
    )


@migrate_app.command("visits")
def migrate_visits(
    db: Annotated[Path, typer.Option(help="SQLite database path")] = Path(
        "tightbeam.db"
    ),
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
) -> None:
    """
    Extract visit data from Jobber API to SQLite database.

    Fetches all visits from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Includes visit notes extraction
    for appointment instructions and completion details. Requires authentication
    via JOBBER_TOKEN environment variable or OAuth2 configuration.

    Args:
        db: Path to SQLite database file (defaults to tightbeam.db, will be created if it doesn't exist)
        verbose: Enable verbose logging output for debugging
        page_limit: Optional limit on number of pages to process (for testing)
    """
    _execute_entity_extraction(
        entity_type="visits",
        db=db,
        verbose=verbose,
        page_limit=page_limit,
    )


@migrate_app.command("timesheet-entries")
def migrate_timesheet_entries(
    db: Annotated[Path, typer.Option(help="SQLite database path")] = Path(
        "tightbeam.db"
    ),
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
) -> None:
    """
    Extract timesheet entry data from Jobber API to SQLite database.

    Fetches all timesheet entries from the Jobber GraphQL API using cursor-based
    pagination and stores them in the specified SQLite database. Includes time
    tracking, approval workflows, and payroll processing data. Requires authentication
    via JOBBER_TOKEN environment variable or OAuth2 configuration.

    Args:
        db: Path to SQLite database file (defaults to tightbeam.db, will be created if it doesn't exist)
        verbose: Enable verbose logging output for debugging
        page_limit: Optional limit on number of pages to process (for testing)
    """
    _execute_entity_extraction(
        entity_type="timesheet-entries",
        db=db,
        verbose=verbose,
        page_limit=page_limit,
    )


@migrate_app.command("products")
def migrate_products(
    db: Annotated[Path, typer.Option(help="SQLite database path")] = Path(
        "tightbeam.db"
    ),
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
) -> None:
    """
    Extract product/service data from Jobber API to SQLite database.

    Fetches all products and services from the Jobber GraphQL API using cursor-based
    pagination and stores them in the specified SQLite database. Includes pricing,
    duration, category, and online booking configuration. Requires authentication
    via JOBBER_TOKEN environment variable or OAuth2 configuration.

    Args:
        db: Path to SQLite database file (defaults to tightbeam.db, will be created if it doesn't exist)
        verbose: Enable verbose logging output for debugging
        page_limit: Optional limit on number of pages to process (for testing)
    """
    _execute_entity_extraction(
        entity_type="products",
        db=db,
        verbose=verbose,
        page_limit=page_limit,
    )


@migrate_app.command("tax-rates")
def migrate_tax_rates(
    db: Annotated[Path, typer.Option(help="SQLite database path")] = Path(
        "tightbeam.db"
    ),
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
    page_limit: Annotated[
        Optional[int], typer.Option("--limit", help="Limit number of pages for testing")
    ] = None,
) -> None:
    """
    Extract tax rate data from Jobber API to SQLite database.

    Fetches all tax rates from the Jobber GraphQL API using cursor-based pagination
    and stores them in the specified SQLite database. Includes regional tax
    configuration, rates, and government tax numbers. Requires authentication
    via JOBBER_TOKEN environment variable or OAuth2 configuration.

    Args:
        db: Path to SQLite database file (defaults to tightbeam.db, will be created if it doesn't exist)
        verbose: Enable verbose logging output for debugging
        page_limit: Optional limit on number of pages to process (for testing)
    """
    _execute_entity_extraction(
        entity_type="tax-rates",
        db=db,
        verbose=verbose,
        page_limit=page_limit,
    )


def _execute_entity_extraction(
    entity_type: str,
    db: Path,
    verbose: bool = False,
    page_limit: Optional[int] = None,
    download_path: str = "./attachments",
    optimization_level: str = "moderate",
) -> None:
    """
    Common entity extraction workflow for all supported entity types.

    Args:
        entity_type: Type of entity to extract ('quotes', 'notes', 'attachments',
                    'users', 'expenses', 'visits', 'timesheet-entries', 'products', 'tax-rates')
        db: Path to SQLite database file
        verbose: Enable verbose logging
        page_limit: Optional limit on number of pages to process
        download_path: Base directory for attachment downloads (attachments only)
    """
    connection = None

    try:
        # Create database connection and logger
        logger = ConsoleLogger(verbose=verbose)
        logger.info(f"Starting {entity_type} extraction to database: {db}")

        # Ensure parent directory exists
        db.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.Connection(str(db))

        # Initialize repository
        repository = Repository(connection)

        # Create OAuth2 components with error handling
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

        # Initialize configuration manager for consistent settings
        config_manager = ConfigManagerImpl()

        # Setup JobberClient with rate limiting
        jobber_client = JobberClient(auth_provider, config_manager=config_manager)

        # Initialize rate limiting components with dynamic optimization settings
        rate_config = config_manager.get_rate_limit_config(optimization_level)
        capacity = rate_config["capacity"]
        refill_rate = rate_config["refill_rate"]
        initial_tokens = rate_config["initial_tokens"]
        requests_per_second = refill_rate / 60
        logger.info(
            f"Setting up {optimization_level.upper()} rate limiting for entity extraction "
            f"({capacity} tokens, {refill_rate}/minute, ~{requests_per_second:.0f} req/sec)"
        )
        rate_limiter = TokenBucketRateLimiter(
            capacity=capacity, refill_rate=refill_rate, initial_tokens=initial_tokens
        )
        backoff_config = config_manager.get_backoff_config()
        backoff_strategy = ExponentialBackoffStrategy(
            initial_delay=backoff_config["initial_delay"],
            max_delay=backoff_config["max_delay"],
            multiplier=backoff_config["multiplier"],
            jitter_factor=backoff_config["jitter_factor"],
        )
        metrics_collector = MetricsCollector(repository=repository)

        rate_limited_client = RateLimitedHttpClient(
            HttpClient(),
            rate_limiter,
            backoff_strategy,
            max_retries=15,
            metrics_collector=metrics_collector,
        )
        jobber_client.set_http_client(rate_limited_client)

        # Create entity mapper
        entity_mapper = EntityMapper()

        # Import and create appropriate extractor based on entity type
        if entity_type == "quotes":
            from .extractors import QuotesExtractor

            extractor = QuotesExtractor(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                config_manager=config_manager,
            )

        elif entity_type == "attachments":
            from .extractors import AttachmentDownloader

            extractor = AttachmentDownloader(
                jobber_client,
                entity_mapper,
                repository,
                logger,
                base_download_path=download_path,
                config_manager=config_manager,
            )

        elif entity_type == "users":
            from .extractors import UsersExtractor

            extractor = UsersExtractor(jobber_client, entity_mapper, repository, logger)

        elif entity_type == "expenses":
            from .extractors import ExpensesExtractor

            extractor = ExpensesExtractor(
                jobber_client, entity_mapper, repository, logger
            )

        elif entity_type == "visits":
            from .extractors import VisitsExtractor

            extractor = VisitsExtractor(
                jobber_client, entity_mapper, repository, logger
            )

        elif entity_type == "timesheet-entries":
            from .extractors import TimesheetEntriesExtractor

            extractor = TimesheetEntriesExtractor(
                jobber_client, entity_mapper, repository, logger
            )

        elif entity_type == "products":
            from .extractors import ProductServicesExtractor

            extractor = ProductServicesExtractor(
                jobber_client, entity_mapper, repository, logger
            )

        elif entity_type == "tax-rates":
            from .extractors import TaxRatesExtractor

            extractor = TaxRatesExtractor(
                jobber_client, entity_mapper, repository, logger
            )

        else:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        # Validate dependencies
        logger.debug("Validating extractor dependencies")
        extractor.validate_dependencies()

        # Execute extraction
        logger.info(f"Starting {entity_type} extraction workflow")
        logger.info("🔍 Initial Token Status:")
        logger.info(
            f"   • Available tokens: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}"
        )
        start_time = time.time()

        result = extractor.extract(page_limit=page_limit)

        extraction_time = time.time() - start_time

        # Get extraction summary and enhanced performance metrics
        extraction_summary = extractor.get_extraction_summary()

        # Enhanced performance logging
        logger.info(f"\n📊 {entity_type.title()} Extraction Analysis:")
        if extraction_time > 0:
            entities_per_minute = (result["entities_processed"] / extraction_time) * 60
            logger.info(
                f"   • Extraction speed: {entities_per_minute:.1f} entities/minute"
            )
            logger.info(
                f"   • Total entities: {result['entities_processed']} in {extraction_time:.1f}s"
            )

        # Create default rate metrics if metrics_collector is None (moderate default)
        rate_metrics = {
            "throttle_rate": "0.0%",
            "throttled_requests": 0,
            "requests_per_minute": "N/A",
        }

        # Build comprehensive summary
        summary_data = {
            "entity_type": entity_type,
            "entities_processed": result["entities_processed"],
            "pages_processed": result["pages_processed"],
            "extraction_time": extraction_time,
            "has_next_page": result["has_next_page"],
            "status": (
                "SUCCESS"
                if extraction_summary["error_count"] == 0
                else "COMPLETED_WITH_ERRORS"
            ),
            "errors_count": extraction_summary["error_count"],
            "rate_limiting": {
                "requests_per_minute": rate_metrics["requests_per_minute"],
                "total_requests": rate_metrics["total_requests"],
                "throttled_requests": rate_metrics["throttled_requests"],
                "rate_limit_errors": rate_metrics["rate_limit_errors"],
                "average_response_time": rate_metrics["average_response_time"],
                "throttle_rate": rate_metrics["throttle_rate"],
            },
        }

        # Add attachment-specific metrics
        if entity_type == "attachments":
            summary_data.update(
                {
                    "files_downloaded": result.get("files_downloaded", 0),
                    "total_bytes_downloaded": result.get("total_bytes_downloaded", 0),
                    "download_failures": result.get("download_failures", 0),
                    "download_path": download_path,
                }
            )

        # Display final token status and rate limiting effectiveness
        logger.info("🔍 Final Token Status:")
        logger.info(
            f"   • Tokens remaining: {rate_limiter.get_available_tokens():.1f}/{rate_limiter.get_capacity()}"
        )
        logger.info(
            f"   • Throttling rate: {rate_metrics['throttle_rate']} "
            f"({rate_metrics['throttled_requests']} throttled)"
        )
        if float(rate_metrics["throttle_rate"].rstrip("%")) < 1.0:
            logger.info("   ✅ Jobber-optimized rate limiting working effectively!")
        elif float(rate_metrics["throttle_rate"].rstrip("%")) < 5.0:
            logger.info("   ⚠️  Minor throttling - rate limiting working well")
        else:
            logger.info(
                "   🔴 Significant throttling - consider further rate limit tuning"
            )

        # Display results
        logger.log_summary(summary_data)

        # Log entity-specific success messages
        if entity_type == "quotes":
            logger.info(
                f"✅ Quote extraction completed: {result['entities_processed']} quotes processed"  # noqa: E501
            )
        elif entity_type == "notes":
            logger.info(
                f"✅ Note extraction completed: {result['entities_processed']} notes processed"  # noqa: E501
            )
        elif entity_type == "attachments":
            files_downloaded = result.get("files_downloaded", 0)
            total_bytes = result.get("total_bytes_downloaded", 0)
            logger.info(
                f"✅ Attachment extraction completed: {result['entities_processed']} attachments processed, "  # noqa: E501
                f"{files_downloaded} files downloaded ({total_bytes} bytes)"
            )
        elif entity_type == "users":
            logger.info(
                f"✅ User extraction completed: {result['entities_processed']} users processed"  # noqa: E501
            )
        elif entity_type == "expenses":
            logger.info(
                f"✅ Expense extraction completed: {result['entities_processed']} expenses processed"  # noqa: E501
            )
        elif entity_type == "visits":
            logger.info(
                f"✅ Visit extraction completed: {result['entities_processed']} visits processed"  # noqa: E501
            )
        elif entity_type == "timesheet-entries":
            logger.info(
                f"✅ Timesheet entry extraction completed: {result['entities_processed']} timesheet entries processed"  # noqa: E501
            )
        elif entity_type == "products":
            logger.info(
                f"✅ Product/service extraction completed: {result['entities_processed']} products/services processed"  # noqa: E501
            )
        elif entity_type == "tax-rates":
            logger.info(
                f"✅ Tax rate extraction completed: {result['entities_processed']} tax rates processed"  # noqa: E501
            )

        # Handle continuation if more pages available
        if result["has_next_page"] and page_limit is None:
            logger.info(
                f"📄 More {entity_type} pages available. Run again to continue extraction."  # noqa: E501
            )
            logger.info(f"Next cursor: {result.get('end_cursor', 'N/A')}")

        # Exit with appropriate code
        exit_code = 0 if extraction_summary["error_count"] == 0 else 1
        logger.info(
            f"{entity_type.capitalize()} extraction completed with exit code {exit_code}"  # noqa: E501
        )
        sys.exit(exit_code)

    except ConfigurationError as e:
        typer.echo(f"Configuration Error: {e}", err=True)
        typer.echo("To configure authentication, you can either:", err=True)
        typer.echo(
            "  1. Run 'tightbeam oauth init' to set up OAuth authentication", err=True
        )
        typer.echo("  2. Manually set the following environment variables:", err=True)
        typer.echo("     - JOBBER_CLIENT_ID", err=True)
        typer.echo("     - JOBBER_CLIENT_SECRET", err=True)
        typer.echo("     - JOBBER_REDIRECT_URI", err=True)
        typer.echo("     - JOBBER_TOKEN", err=True)
        sys.exit(1)

    except JobberApiError as e:
        typer.echo(f"API Error: {e}", err=True)
        typer.echo(
            "Please check your internet connection and OAuth2 token validity.", err=True
        )
        sys.exit(2)

    except MappingError as e:
        typer.echo(f"Data Mapping Error: {e}", err=True)
        typer.echo(
            "The API response format may have changed. Please check for updates.",
            err=True,
        )
        sys.exit(3)

    except RepositoryError as e:
        typer.echo(f"Database Error: {e}", err=True)
        typer.echo("Please check database file permissions and disk space.", err=True)
        sys.exit(4)

    except KeyboardInterrupt:
        typer.echo(
            f"\n{entity_type.capitalize()} extraction interrupted by user.", err=True
        )
        sys.exit(130)

    except Exception as e:
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
