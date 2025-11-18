"""Logger Protocol for structured logging and dependency injection."""

from typing import Any, Protocol


class Logger(Protocol):
    """Logger interface for structured logging throughout the application.

    This Protocol enables dependency injection of logging implementations,
    allowing for easy testing with mock loggers and flexible output options.
    """

    def info(self, message: str) -> None:
        """Log an informational message.

        Args:
            message: The message to log
        """
        ...

    def debug(self, message: str) -> None:
        """Log a debug message.

        Args:
            message: The debug message to log
        """
        ...

    def error(self, message: str) -> None:
        """Log an error message.

        Args:
            message: The error message to log
        """
        ...

    def warning(self, message: str) -> None:
        """Log a warning message.

        Args:
            message: The warning message to log
        """
        ...

    def log_summary(self, summary: dict[str, Any]) -> None:
        """Log structured summary data.

        Args:
            summary: Dictionary containing summary information
        """
        ...
