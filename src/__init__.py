"""TightBeam v2 - Jobber Data Migration Tool

A command-line tool for extracting client and invoice data from Jobber GraphQL API
and persisting it to SQLite database using object-oriented architecture.
"""

# Core components for Phase 3 integration
from .auth import AuthProvider
from .clients import JobberClient
from .mappers import EntityMapper
from .models import Client, Invoice
from .repositories import Repository

# Logging components
from .interfaces import Logger
from .loggers import ConsoleLogger

# Exception classes for error handling
from .exceptions import (
    TightBeamError,
    ConfigurationError,
    JobberApiError,
    MappingError,
    RepositoryError,
)

__version__ = "0.1.0"
__all__ = [
    # Core components
    "AuthProvider",
    "JobberClient",
    "EntityMapper",
    "Client",
    "Invoice",
    "Repository",
    # Logging components
    "Logger",
    "ConsoleLogger",
    # Exception classes
    "TightBeamError",
    "ConfigurationError",
    "JobberApiError",
    "MappingError",
    "RepositoryError",
]
