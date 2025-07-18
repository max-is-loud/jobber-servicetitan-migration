"""Console logger implementation with color output and verbose control."""

import sys
from typing import Any

from ..interfaces.logger import Logger


class ConsoleLogger(Logger):  # Explicit inheritance
    """Console implementation of Logger Protocol.

    Provides structured logging to stdout/stderr with optional verbose mode
    and color output for better user experience.
    """

    def __init__(self, verbose: bool = False) -> None:
        """Initialize console logger.

        Args:
            verbose: Whether to enable debug message output
        """
        self.verbose = verbose

    def info(self, message: str) -> None:
        """Print informational message to stdout.

        Args:
            message: The message to log
        """
        # Use green color for info messages if terminal supports it
        if sys.stdout.isatty():
            print(f"\033[32mINFO\033[0m: {message}")
        else:
            print(f"INFO: {message}")

    def debug(self, message: str) -> None:
        """Print debug message to stdout if verbose mode is enabled.

        Args:
            message: The debug message to log
        """
        if not self.verbose:
            return

        # Use blue color for debug messages if terminal supports it
        if sys.stdout.isatty():
            print(f"\033[34mDEBUG\033[0m: {message}")
        else:
            print(f"DEBUG: {message}")

    def error(self, message: str) -> None:
        """Print error message to stderr.

        Args:
            message: The error message to log
        """
        # Use red color for error messages if terminal supports it
        if sys.stderr.isatty():
            print(f"\033[31mERROR\033[0m: {message}", file=sys.stderr)
        else:
            print(f"ERROR: {message}", file=sys.stderr)

    def log_summary(self, summary: dict[str, Any]) -> None:
        """Format and display structured summary data.

        Args:
            summary: Dictionary containing summary information
        """
        print("\n" + "=" * 50)
        print("MIGRATION SUMMARY")
        print("=" * 50)

        for key, value in summary.items():
            # Format keys to be human-readable
            formatted_key = key.replace("_", " ").title()
            print(f"{formatted_key}: {value}")

        print("=" * 50)
