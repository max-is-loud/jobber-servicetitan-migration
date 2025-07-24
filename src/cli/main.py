"""Main CLI entry point for TightBeam v2.

This module serves as the new modular CLI entry point, registering
subcommand modules using Typer's add_typer functionality.
"""

import typer
from dotenv import load_dotenv

from .migrate import migrate_app
from .oauth import oauth_app
from .services import ServiceFactory

# Load environment variables from .env file
load_dotenv()

# Get shared console instance
console = ServiceFactory.get_console()

# Create main Typer application
app = typer.Typer(
    name="tightbeam",
    help="TightBeam v2 - Jobber Data Migration Tool",
    add_completion=False,
)

# Register subcommand modules
app.add_typer(oauth_app, name="oauth")
app.add_typer(migrate_app, name="migrate")


def main() -> None:
    """Entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
