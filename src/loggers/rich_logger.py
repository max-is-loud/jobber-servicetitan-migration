"""Rich-enhanced logger implementation with beautiful terminal formatting."""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..interfaces.logger import Logger


class RichLogger(Logger):
    """Rich implementation of Logger Protocol.

    Provides structured logging with Rich library features including
    colored output, panels, tables, and enhanced formatting while
    maintaining full compatibility with the Logger protocol.
    """

    def __init__(self, verbose: bool = False) -> None:
        """Initialize Rich logger.

        Args:
            verbose: Whether to enable debug message output
        """
        self.verbose = verbose
        self.console = Console()
        self.error_console = Console(stderr=True)

    def info(self, message: str) -> None:
        """Print informational message using Rich formatting.

        Args:
            message: The message to log
        """
        self.console.print(f"[green]INFO[/green]: {message}")

    def debug(self, message: str) -> None:
        """Print debug message if verbose mode is enabled.

        Args:
            message: The debug message to log
        """
        if not self.verbose:
            return

        self.console.print(f"[blue]DEBUG[/blue]: {message}")

    def error(self, message: str) -> None:
        """Print error message to stderr using Rich formatting.

        Args:
            message: The error message to log
        """
        self.error_console.print(f"[red]ERROR[/red]: {message}")

    def warning(self, message: str) -> None:
        """Print warning message using Rich formatting.

        Args:
            message: The warning message to log
        """
        self.console.print(f"[yellow]WARNING[/yellow]: {message}")

    def success(self, message: str) -> None:
        """Print success message using Rich formatting."""
        self.console.print(f"[bold green]SUCCESS[/bold green]: {message}")

    def log_summary(self, summary: dict[str, Any]) -> None:
        """Format and display structured summary data using Rich table.

        Args:
            summary: Dictionary containing summary information
        """
        # Create a beautiful table for the migration summary
        table = Table(
            title="Migration Summary", show_header=True, header_style="bold magenta"
        )
        table.add_column("Metric", style="dim", width=25)
        table.add_column("Value", justify="left")

        # Handle nested rate limiting metrics separately
        rate_limiting_data = None
        main_summary = {}

        for key, value in summary.items():
            if key == "rate_limiting" and isinstance(value, dict):
                rate_limiting_data = value
            else:
                main_summary[key] = value

        # Add main summary rows
        for key, value in main_summary.items():
            # Format keys to be human-readable
            formatted_key = key.replace("_", " ").title()

            # Style values based on content
            if key == "status":
                if "SUCCESS" in str(value):
                    styled_value = f"[green]{value}[/green]"
                elif "ERROR" in str(value):
                    styled_value = f"[red]{value}[/red]"
                else:
                    styled_value = f"[yellow]{value}[/yellow]"
            elif key == "errors_count":
                if value == 0:
                    styled_value = f"[green]{value}[/green]"
                else:
                    styled_value = f"[red]{value}[/red]"
            elif "processed" in key:
                styled_value = f"[cyan]{value:,}[/cyan]"
            else:
                styled_value = str(value)

            table.add_row(formatted_key, styled_value)

        # Add rate limiting metrics if present
        if rate_limiting_data:
            table.add_section()
            table.add_row("[bold]Rate Limiting Metrics[/bold]", "")
            for key, value in rate_limiting_data.items():
                formatted_key = key.replace("_", " ").title()
                if "rate" in key.lower() or "time" in key.lower():
                    styled_value = f"[yellow]{value}[/yellow]"
                elif "requests" in key.lower():
                    styled_value = f"[blue]{value}[/blue]"
                elif "errors" in key.lower() and value > 0:
                    styled_value = f"[red]{value}[/red]"
                else:
                    styled_value = f"[dim]{value}[/dim]"
                table.add_row(f"  {formatted_key}", styled_value)

        # Print the table with some spacing
        self.console.print()
        self.console.print(table)
        self.console.print()

    def print_panel(self, content: str, title: str = "", style: str = "blue") -> None:
        """Print content in a Rich panel.

        Args:
            content: The content to display in the panel
            title: Optional title for the panel
            style: Panel border style/color
        """
        panel = Panel(content, title=title, border_style=style)
        self.console.print(panel)

    def print_status(self, message: str, status: str = "info") -> None:
        """Print a status message with appropriate styling.

        Args:
            message: The status message
            status: Type of status (info, success, warning, error)
        """
        if status == "success":
            self.console.print(f"✅ {message}", style="green")
        elif status == "warning":
            self.console.print(f"⚠️ {message}", style="yellow")
        elif status == "error":
            self.console.print(f"❌ {message}", style="red")
        else:
            self.console.print(f"ℹ️ {message}", style="blue")
