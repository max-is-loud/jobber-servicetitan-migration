"""Shared services and factories for CLI modules.

This module provides shared business logic, configuration management,
and service instantiation patterns used across CLI subcommands.
"""

from .error_handling import CLIErrorHandler
from .factories import ServiceFactory
from .shared import SharedServices

__all__ = ["ServiceFactory", "SharedServices", "CLIErrorHandler"]
