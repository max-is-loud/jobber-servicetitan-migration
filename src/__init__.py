"""TightBeam v2 - Jobber Data Migration Tool

A command-line tool for extracting client and invoice data from Jobber GraphQL API
and persisting it to SQLite database using object-oriented architecture.
"""

# Core components for Phase 3 integration
from .auth import AuthProvider, OAuthProvider
from .clients import JobberClient

# Coordination components
from .coordinators import MigrationCoordinator

# Exception classes for error handling
from .exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    RepositoryError,
    TightBeamError,
)

# Logging components
from .interfaces import Logger
from .loggers import ConsoleLogger
from .mappers import EntityMapper
from .models import Client, Invoice, MigrationSummary
from .repositories import Repository

__version__ = "0.1.0"
__all__ = [
    # Core components
    "AuthProvider",
    "OAuthProvider",
    "JobberClient",
    "EntityMapper",
    "Client",
    "Invoice",
    "MigrationSummary",
    "Repository",
    # Logging components
    "Logger",
    "ConsoleLogger",
    # Coordination components
    "MigrationCoordinator",
    # Exception classes
    "TightBeamError",
    "ConfigurationError",
    "JobberApiError",
    "MappingError",
    "RepositoryError",
]
