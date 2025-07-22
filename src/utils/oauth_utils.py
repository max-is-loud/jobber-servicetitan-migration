"""OAuth utility functions for browser opening and token completion.

Extracted from CLI module to eliminate duplication between _oauth_init_with_server()
and _oauth_init_manual() functions. Maintains WSL-aware browser opening and Rich UI
formatting patterns.
"""

import os
import subprocess
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TYPE_CHECKING

from rich.console import Console

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from ..auth import OAuth2Manager
    from ..repositories import Repository


def open_browser(auth_url: str, console: Optional[Console] = None) -> None:
    """Open browser with OAuth authorization URL, with WSL environment support.

    Attempts to open the browser using webbrowser module first, then falls back
    to subprocess methods for WSL environments. Maintains Rich UI formatting
    for status messages.

    Args:
        auth_url: OAuth2 authorization URL to open in browser
        console: Optional Rich Console for formatted output
    """
    if console is None:
        console = Console()

    try:
        webbrowser.open(auth_url)
        console.print("✅ [green]Browser opened successfully[/green]")
    except Exception as e:
        # In WSL environment, try alternative methods
        if "wsl" in os.uname().release.lower():
            try:
                # Try using Windows browser via WSL
                subprocess.run(
                    ["cmd.exe", "/c", "start", auth_url],
                    check=True,
                    capture_output=True,
                )
                console.print("✅ [green]Browser opened via Windows[/green]")
            except subprocess.CalledProcessError:
                console.print("⚠️ [yellow]Could not open browser automatically[/yellow]")
                console.print(
                    f"🔗 [blue]Please manually copy and paste this URL:[/blue]\n"
                    f"   {auth_url}"
                )
        else:
            console.print(f"⚠️ [yellow]Could not open browser: {e}[/yellow]")
            console.print(
                f"🔗 [blue]Please manually copy and paste this URL:[/blue]\n"
                f"   {auth_url}"
            )


def complete_oauth_flow(
    auth_code: str,
    oauth_manager: "OAuth2Manager",
    repository: "Repository",
    expires_in_default: int = 3600,
    console: Optional[Console] = None,
) -> dict[str, Any]:
    """Complete OAuth2 flow by exchanging authorization code for tokens.

    Exchanges the authorization code for access and refresh tokens, calculates
    expiration time with fallback handling for missing expires_in field, and
    stores tokens in the repository.

    Args:
        auth_code: Authorization code from OAuth2 callback
        oauth_manager: OAuth2Manager instance for token exchange
        repository: Repository instance for token storage
        expires_in_default: Default expiration time in seconds if missing from response
        console: Optional Rich Console for formatted output

    Returns:
        Dictionary containing token data from OAuth2 provider

    Raises:
        OAuth2Error: If token exchange fails or token data is invalid
    """
    if console is None:
        console = Console()

    # Exchange code for tokens
    token_data = oauth_manager.exchange_code_for_tokens(auth_code)

    # Handle missing expires_in field (Jobber API doesn't always include it)
    # Use provided default value for fallback
    expires_in = token_data.get("expires_in", expires_in_default)

    # Calculate expiration timestamp
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()

    # Store tokens in repository
    repository.save_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
    )

    return token_data


def display_manual_auth_instructions(
    auth_url: str, state: str, console: Optional[Console] = None
) -> None:
    """Display Rich UI panel with manual authorization instructions.

    Shows formatted instructions for manual OAuth2 authorization including
    the authorization URL, next steps, and state parameter for verification.

    Args:
        auth_url: OAuth2 authorization URL for manual completion
        state: State parameter for OAuth2 security verification
        console: Optional Rich Console for formatted output
    """
    if console is None:
        console = Console()

    from rich.panel import Panel

    manual_content = f"""[bold blue]🔗 Authorization URL:[/bold blue]
{auth_url}

[bold yellow]📋 Next Steps:[/bold yellow]
1. Complete authorization in your browser
2. Copy the authorization code from the callback URL
3. Run: [bold]tightbeam oauth callback --code YOUR_AUTHORIZATION_CODE[/bold]

[bold dim]State parameter (for verification): {state}[/bold dim]"""

    console.print(
        Panel(
            manual_content, title="🔐 OAuth2 Manual Authorization", border_style="blue"
        )
    )


def display_server_auth_info(
    auth_url: str, port: int, console: Optional[Console] = None
) -> None:
    """Display Rich UI panel with local callback server authorization info.

    Shows formatted information for OAuth2 authorization with local callback
    server including server details, authorization URL, and waiting status.

    Args:
        auth_url: OAuth2 authorization URL for server-based completion
        port: Local callback server port number
        console: Optional Rich Console for formatted output
    """
    if console is None:
        console = Console()

    from rich.panel import Panel

    server_info = (
        f"[bold green]🌐 Local callback server:[/bold green] "
        f"http://localhost:{port}\n"
        f"[bold blue]🔗 Authorization URL:[/bold blue] {auth_url}\n\n"
        f"[bold yellow]⏳ Waiting for authorization...[/bold yellow]\n"
        f"Complete the authorization in your browser, then come back here!"
    )

    console.print(
        Panel(
            server_info,
            title="🚀 OAuth2 Authorization with Local Server",
            border_style="green",
        )
    )


def display_oauth_success(
    mode: str = "callback", console: Optional[Console] = None
) -> None:
    """Display Rich UI panel with OAuth2 completion success message.

    Shows formatted success message after OAuth2 tokens have been stored,
    with mode-specific content and next steps.

    Args:
        mode: OAuth2 completion mode ('callback' or 'server')
        console: Optional Rich Console for formatted output
    """
    if console is None:
        console = Console()

    from rich.panel import Panel

    if mode == "server":
        success_content = """[bold green]✅ OAuth2 tokens stored successfully![/bold green]

[bold cyan]🚀 You're all set! You can now run:[/bold cyan]
   [bold]tightbeam migrate --db ./your_data.sqlite[/bold]"""
        title = "🎉 OAuth2 Setup Complete"
    else:  # callback mode
        success_content = """[bold green]✅ OAuth2 tokens stored successfully![/bold green]

[bold cyan]🎯 Next Steps:[/bold cyan]
• Use the migration tool with OAuth2 authentication
• Run [bold]tightbeam oauth status[/bold] to check token status"""
        title = "🎉 OAuth2 Callback Complete"

    console.print(
        Panel(
            success_content,
            title=title,
            border_style="green",
        )
    )
