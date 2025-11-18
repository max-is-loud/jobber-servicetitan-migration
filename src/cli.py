"""Main CLI entry point for TightBeam v2 - Thin Orchestrator.

This module serves as the main CLI entry point that registers
subcommand modules using Typer's add_typer functionality.
It's designed to be minimal and maintainable.
"""

import typer
from dotenv import load_dotenv
from typing import Annotated

from src.cli.migrate import migrate_app
from src.cli.oauth import oauth_app
from src.cli.services import ServiceFactory
from src.constants import (
    APP_VERSION,
    CLI_HELP_TEXT,
    VERSION_DISPLAY,
    VERSION_SUBTITLE,
)

# Application version (imported from constants)
__version__ = APP_VERSION

# Load environment variables from .env file
load_dotenv()

# Get shared console instance
console = ServiceFactory.get_console()


# Version callback
def version_callback(value: bool) -> None:
    """Display application version and exit."""
    # Handle case where Typer passes string "False" instead of bool False
    if isinstance(value, str):
        value = value.lower() in ('true', '1', 'yes')

    if value:
        console.print(f"[bold blue]{VERSION_DISPLAY}[/bold blue]")
        console.print(VERSION_SUBTITLE)
        raise typer.Exit()


# Create main Typer application
app = typer.Typer(
    name="tightbeam",
    help=CLI_HELP_TEXT,
    add_completion=False,
)


@app.callback()
def main_callback(
    version: Annotated[
        bool, typer.Option("--version", "-V", help="Show version and exit", callback=version_callback, is_eager=True)
    ] = False,
) -> None:
    """
    TightBeam v2 - Jobber Data Migration Tool.

    Extract and migrate data from the Jobber API to SQLite database.
    """
    pass


# Register subcommand modules using add_typer
app.add_typer(oauth_app, name="oauth")
app.add_typer(migrate_app, name="migrate")


def main() -> None:
    """Entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
