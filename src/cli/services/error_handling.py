"""Centralized error handling utilities for CLI commands.

This module provides consistent error handling patterns and utilities
used across all CLI commands to reduce duplication.
"""

import sys
from typing import NoReturn, Type, Union

from rich.console import Console

from src.exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    OAuth2Error,
    RepositoryError,
)
from .shared import SharedServices


class CLIErrorHandler:
    """Centralized error handling for CLI commands.

    Provides consistent error display and exit patterns across all CLI commands.
    """

    @staticmethod
    def handle_exception(error: Exception, command_name: str = "CLI", console: Union[Console, None] = None) -> NoReturn:
        """Handle common CLI exceptions with consistent formatting.

        Args:
            error: The exception that occurred
            command_name: Name of the command that failed
            console: Optional console instance, defaults to shared console
        """
        if console is None:
            console = SharedServices.get_console()

        # Map exception types to user-friendly messages
        error_messages = {
            ConfigurationError: f"Configuration error in {command_name}",
            OAuth2Error: f"OAuth2 authentication error in {command_name}",
            RepositoryError: f"Database error in {command_name}",
            JobberApiError: f"Jobber API error in {command_name}",
            MappingError: f"Data mapping error in {command_name}",
        }

        error_type = type(error)
        error_title = error_messages.get(error_type, f"Error in {command_name}")

        # Display error with consistent formatting
        console.print(f"[red]❌ {error_title}[/red]")
        console.print(f"[red]   {str(error)}[/red]")

        # Exit with appropriate code
        sys.exit(1)

    @staticmethod
    def handle_keyboard_interrupt(command_name: str = "CLI") -> NoReturn:
        """Handle KeyboardInterrupt with consistent message.

        Args:
            command_name: Name of the command that was interrupted
        """
        console = SharedServices.get_console()
        console.print(f"\\n[yellow]⚠️  {command_name} interrupted by user[/yellow]")
        sys.exit(130)  # Standard exit code for SIGINT

    @staticmethod
    def require_condition(
        condition: bool, error_message: str, error_type: Type[Exception] = ConfigurationError
    ) -> None:
        """Require a condition to be true, raise exception if false.

        Args:
            condition: Condition that must be true
            error_message: Error message if condition fails
            error_type: Type of exception to raise
        """
        if not condition:
            raise error_type(error_message)
