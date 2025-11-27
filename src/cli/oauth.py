"""OAuth authentication commands for TightBeam CLI."""

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import parse_qs, urlparse

import typer
from rich.panel import Panel
from rich.status import Status
from rich.table import Table

from src.auth import AuthProvider
from src.constants import (
    DEFAULT_PORT,
    OAUTH_EMOJI,
    OAUTH_TIMEOUT_SECONDS,
    REQUIRED_OAUTH_VARS,
    SUCCESS_EMOJI,
    ERROR_EMOJI,
    WARNING_EMOJI,
    INFO_EMOJI,
)
from src.exceptions import ConfigurationError, OAuth2Error, RepositoryError
from src.utils import (
    complete_oauth_flow,
    display_manual_auth_instructions,
    display_oauth_success,
    display_server_auth_info,
    open_browser,
)
from .services import CLIErrorHandler, ServiceFactory, SharedServices

# Get shared console instance
console = ServiceFactory.get_console()


def _validate_oauth_config(console, verbose: bool = False) -> None:
    """Validate OAuth configuration before running OAuth commands."""
    import os
    import sys

    missing_vars = []

    for var_name, description in REQUIRED_OAUTH_VARS.items():
        value = os.environ.get(var_name)
        if not value or not value.strip():
            missing_vars.append((var_name, description))
        elif verbose:
            console.print(f"{SUCCESS_EMOJI} [green]{var_name}[/green] is configured", style="dim")

    if missing_vars:
        console.print(f"\n[red]{ERROR_EMOJI} OAuth Configuration Error[/red]")
        console.print("The following required environment variables are missing or empty:")

        for var_name, description in missing_vars:
            console.print(f"  • [yellow]{var_name}[/yellow] - {description}")

        console.print(f"\n[bold cyan]{INFO_EMOJI} To fix this:[/bold cyan]")
        console.print("1. Run '[green]tightbeam oauth setup[/green]' for detailed setup instructions")
        console.print("2. Set the missing environment variables in your shell or .env file")
        console.print("3. Use '[green]--no-check-config[/green]' to skip this validation")

        sys.exit(1)
    elif verbose:
        console.print(f"{SUCCESS_EMOJI} [green]OAuth configuration validated successfully[/green]", style="dim")


# Create OAuth subcommand group
oauth_app = typer.Typer(
    name="oauth",
    help="OAuth authentication setup commands",
    add_completion=False,
)


@oauth_app.callback()
def oauth_group_callback(
    ctx: typer.Context,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose output for OAuth operations")
    ] = False,
    # check_config: Annotated[
    #     bool, typer.Option("--check-config/--no-check-config", help="Validate OAuth configuration before commands")
    # ] = True,
) -> None:
    """
    OAuth 2.0 authentication management.

    Manage OAuth tokens, authorization flows, and authentication status
    for connecting to the Jobber API.
    """
    # Store shared options in context for all oauth commands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    # ctx.obj["check_config"] = check_config

    if verbose:
        console.print(f"{OAUTH_EMOJI} [bold blue]OAuth Verbose Mode:[/bold blue] Detailed output enabled", style="dim")

    # Validate OAuth configuration if requested (and not running setup/status commands)
    # if check_config and ctx.invoked_subcommand not in ["setup", "status"]:
    #     _validate_oauth_config(console, verbose)


# These functions are now provided by ServiceFactory
_create_oauth2_manager = ServiceFactory.create_oauth2_manager
_create_repository = ServiceFactory.create_repository


@oauth_app.command("init")
def oauth_init(
    db: Annotated[Optional[Path], typer.Option(help="SQLite database path for token storage")] = None,
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

    By default, starts a local callback server to automatically handle the
    OAuth2 callback. Alternatively, generates an authorization URL for manual
    completion.
    """
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
        console.print(f"[red]Configuration Error:[/red] {e}")
        console.print(
            "[yellow]Please ensure JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, " "and JOBBER_REDIRECT_URI are set.[/yellow]"
        )
        sys.exit(1)

    except Exception as e:
        console.print(f"[red]Unexpected Error:[/red] {e}")
        sys.exit(5)


@oauth_app.command("setup")
def oauth_setup() -> None:
    """
    Display OAuth authentication setup instructions.

    Guides you through setting up the required environment variables
    for Jobber API OAuth authentication.
    """
    # Create a panel with OAuth setup instructions
    setup_content = """To authenticate with the Jobber API, you need to set up
the following environment variables:

[bold cyan]Required OAuth Environment Variables:[/bold cyan]
  • [green]JOBBER_CLIENT_ID[/green] - Your Jobber application's client ID
  • [green]JOBBER_CLIENT_SECRET[/green] - Your Jobber application's client secret
  • [green]JOBBER_REDIRECT_URI[/green] - OAuth redirect URI for your application
  • [green]JOBBER_TOKEN[/green] - Valid Jobber API access token

[bold yellow]You can set these in your shell environment:[/bold yellow]
  export JOBBER_CLIENT_ID='your_client_id'
  export JOBBER_CLIENT_SECRET='your_client_secret'
  export JOBBER_REDIRECT_URI='your_redirect_uri'
  export JOBBER_TOKEN='your_access_token'

[bold yellow]Or create a .env file in your project directory with these values.[/bold yellow]

[bold blue]For more information on obtaining these credentials, visit:[/bold blue]
📖 https://developer.getjobber.com/docs/authentication"""  # noqa: E501

    console.print(Panel(setup_content, title="🔧 TightBeam OAuth Setup", border_style="blue"))


def _oauth_init_with_server(db: Optional[Path], port: int) -> None:
    """Initialize OAuth2 flow with local callback server using Rich UI."""

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
    server_thread = threading.Thread(target=server.serve_forever, name="oauth-callback-server")
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
        typer.echo("   Complete the authorization in your browser, then come back here!")

        # Display Rich UI for OAuth setup
        display_server_auth_info(auth_url, port, console)

        # Open browser using helper function
        open_browser(auth_url, console)

        # Wait for callback (with timeout)
        timeout = 300  # 5 minutes
        start_time = time.time()

        with Status("[bold green]Waiting for authorization...", console=console, spinner="dots"):
            while time.time() - start_time < timeout:
                if auth_result["code"] or auth_result["error"]:
                    break
                time.sleep(1)

        if auth_result["error"]:
            console.print(f"\n❌ [red]Authorization failed:[/red] {auth_result['error']}")
            sys.exit(1)
        elif not auth_result["code"]:
            console.print(f"\n⏰ [yellow]Authorization timed out after {timeout} seconds[/yellow]")
            console.print("[dim]Please try again or use manual mode: " "tightbeam oauth init --no-auto[/dim]")

            sys.exit(1)

        # Verify state parameter
        if auth_result["state"] != state:
            console.print("\n🔒 [red]Security Error: State parameter mismatch[/red]")
            sys.exit(1)

        # Format code for display (show only first 8 chars for security)
        code_display = (
            f"{auth_result['code'][:8]}..."
            if auth_result["code"] and len(auth_result["code"]) > 8
            else auth_result["code"]
        )

        console.print(f"\n🎉 [green]Authorization code received:[/green] {code_display}")

        # Automatically complete the OAuth2 flow
        with Status(
            "[bold green]Exchanging authorization code for tokens...",
            console=console,
            spinner="dots",
        ):
            repository = _create_repository(db)

            # Complete OAuth flow using helper function
            complete_oauth_flow(auth_result["code"], oauth_manager, repository, 3600, console)

        # Display success message using helper function with actual database path
        db_path_used = str(db if db is not None else SharedServices.get_default_db_path())
        display_oauth_success("server", console, db_path_used)

        # Explicit clean exit after successful OAuth completion
        sys.exit(0)

    finally:
        # Restore original environment
        if original_redirect is not None:
            os.environ["JOBBER_REDIRECT_URI"] = original_redirect
        elif "JOBBER_REDIRECT_URI" in os.environ:
            del os.environ["JOBBER_REDIRECT_URI"]

        # Enhanced server cleanup with isolated error handling
        try:
            server.shutdown()
        except Exception:
            # Ignore server shutdown errors
            pass

        try:
            server.server_close()
        except Exception:
            # Ignore server close errors
            pass

        try:
            if server_thread.is_alive():
                server_thread.join(timeout=2.0)
                if server_thread.is_alive():
                    console.print("[dim]Warning: OAuth server thread did not terminate cleanly[/dim]")
        except Exception:
            # Ignore thread join errors
            pass


def _oauth_init_manual(db: Optional[Path]) -> None:
    """Initialize OAuth2 flow manually (original behavior)."""
    # Create OAuth2 manager
    oauth_manager = _create_oauth2_manager()

    # Generate authorization URL
    auth_url, state = oauth_manager.get_authorization_url()

    # Display manual authorization instructions using helper function
    display_manual_auth_instructions(auth_url, state, console)

    # Open browser using helper function
    open_browser(auth_url, console)


@oauth_app.command("callback")
def oauth_callback(
    code: Annotated[str, typer.Option(help="Authorization code from OAuth2 callback")],
    db: Annotated[Optional[Path], typer.Option(help="SQLite database path for token storage")] = None,
) -> None:
    """
    Handle OAuth2 callback and exchange authorization code for tokens.

    Use this command after completing the authorization flow initiated by 'oauth init'.
    """
    try:
        # Create OAuth2 manager and repository
        oauth_manager = _create_oauth2_manager()
        repository = _create_repository(db)

        with Status(
            "[bold green]Exchanging authorization code for tokens...",
            console=console,
            spinner="dots",
        ):
            # Complete OAuth flow using helper function with default expires_in handling
            complete_oauth_flow(
                code,
                oauth_manager,
                repository,
                expires_in_default=3600,
                console=console,
            )

        # Display success message using helper function with actual database path
        db_path_used = str(db if db is not None else SharedServices.get_default_db_path())
        display_oauth_success("callback", console, db_path_used)

    except ConfigurationError as e:
        console.print(f"[red]Configuration Error:[/red] {e}")
        sys.exit(1)

    except OAuth2Error as e:
        console.print(f"[red]OAuth2 Error:[/red] {e}")
        console.print("[yellow]Please try the authorization flow again with " "'tightbeam oauth init'[/yellow]")
        sys.exit(1)

    except RepositoryError as e:
        console.print(f"[red]Database Error:[/red] {e}")
        console.print("[yellow]Please check database file permissions.[/yellow]")
        sys.exit(4)

    except Exception as e:
        console.print(f"[red]Unexpected Error:[/red] {e}")
        sys.exit(5)


@oauth_app.command("status")
def oauth_status() -> None:
    """
    Check the status of authentication configuration.
    Shows current authentication mode and token status.
    """
    # Create a table for authentication status
    status_table = Table(
        title="🔍 TightBeam Authentication Status",
        show_header=True,
        header_style="bold magenta",
    )
    status_table.add_column("Component", style="dim", width=20)
    status_table.add_column("Status", justify="left")
    status_table.add_column("Details", justify="left")

    recommendations: list[str] = []

    # Check for environment token first
    jobber_token = os.environ.get("JOBBER_TOKEN")
    if jobber_token:
        status_table.add_row(
            "Authentication Mode",
            "[green]Environment Token[/green]",
            "JOBBER_TOKEN variable is set",
        )

        try:
            # Test token with simple API call using ServiceFactory
            http_client = ServiceFactory.create_http_client()
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

            with Status("[bold green]Testing API connection...", console=console, spinner="dots"):
                response = http_client.post(
                    url="https://api.getjobber.com/api/graphql",
                    headers=headers,
                    json=test_query,
                )

            if response and "data" in response:
                status_table.add_row(
                    "Token Validation",
                    "[green]✅ Valid[/green]",
                    "API connection successful",
                )
                status_table.add_row(
                    "Ready to Use",
                    "[green]🎉 Yes[/green]",
                    "Authentication working correctly",
                )
            else:
                status_table.add_row(
                    "Token Validation",
                    "[yellow]⚠️ Warning[/yellow]",
                    "Unexpected API response format",
                )

        except Exception as e:
            status_table.add_row("Token Validation", "[red]❌ Failed[/red]", f"Error: {e}")

        console.print(status_table)
        return

    # Check OAuth2 configuration
    try:
        oauth_manager = _create_oauth2_manager()
        repository = _create_repository()

        status_table.add_row(
            "Authentication Mode",
            "[blue]🔐 OAuth2[/blue]",
            "OAuth2 environment variables configured",
        )

        # Check for stored tokens
        stored_tokens = repository.get_oauth_tokens()

        if stored_tokens:
            status_table.add_row("Token Storage", "[green]✅ Found[/green]", "OAuth2 tokens are stored")

            # Test token validity
            try:
                with Status(
                    "[bold green]Validating OAuth2 tokens...",
                    console=console,
                    spinner="dots",
                ):
                    auth_provider = AuthProvider(oauth_manager, repository)
                    auth_provider.get_token()  # Verify it works

                status_table.add_row(
                    "Token Validation",
                    "[green]✅ Valid[/green]",
                    "OAuth2 tokens are working",
                )
                status_table.add_row(
                    "Ready to Use",
                    "[green]🎉 Yes[/green]",
                    "Authentication working correctly",
                )
            except Exception as e:
                status_table.add_row("Token Validation", "[red]❌ Failed[/red]", f"Error: {e}")
                recommendations.append("💡 Action Needed: Run 'tightbeam oauth init' to re-authorize.")
        else:
            status_table.add_row("Token Storage", "[red]❌ Missing[/red]", "No tokens stored yet")
            recommendations.append("💡 Action Needed: Run 'tightbeam oauth init' to complete setup.")

    except ConfigurationError:
        status_table.add_row(
            "Authentication Mode",
            "[red]❌ Not Configured[/red]",
            "No authentication method available",
        )
        status_table.add_row("Option 1", "[blue]Environment Token[/blue]", "Set JOBBER_TOKEN variable")
        status_table.add_row(
            "Option 2",
            "[blue]OAuth2 Setup[/blue]",
            "Configure OAuth2 and run 'tightbeam oauth init'",
        )
        recommendations.append("💡 Action Needed: Configure auth and rerun 'tightbeam oauth init'.")

    console.print(status_table)
    for rec in recommendations:
        console.print(rec)


@oauth_app.command("clear")
def oauth_clear(
    db: Annotated[Optional[Path], typer.Option(help="SQLite database path for token storage")] = None,
    confirm: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")] = False,
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
            console.print("[yellow]No OAuth2 tokens found to clear.[/yellow]")
            return

        # Confirmation prompt
        if not confirm:
            console.print("[yellow]⚠️ This will log you out from OAuth2 authentication.[/yellow]")
            proceed = typer.confirm("Are you sure you want to clear OAuth2 tokens?")
            if not proceed:
                console.print("[dim]Operation cancelled.[/dim]")
                return

        # Clear tokens
        with Status("[bold red]Clearing OAuth2 tokens...", console=console, spinner="dots"):
            repository.clear_oauth_tokens()

        success_content = """[bold green]✅ OAuth2 tokens cleared successfully![/bold green]

[bold cyan]💡 To re-authorize:[/bold cyan]
Run [bold]tightbeam oauth init[/bold] when needed"""  # noqa: E501

        console.print(Panel(success_content, title="🗑️ Tokens Cleared", border_style="red"))

    except RepositoryError as e:
        console.print(f"[red]Database Error:[/red] {e}")
        sys.exit(4)

    except Exception as e:
        console.print(f"[red]Unexpected Error:[/red] {e}")
        sys.exit(5)
