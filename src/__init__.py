"""TightBeam v2 - Jobber Data Migration Tool

A command-line tool for extracting client and invoice data from Jobber GraphQL API
and persisting it to SQLite database using object-oriented architecture.
"""

# Core components for Phase 3 integration

from .auth import (
    AuthProvider,
    OAuth2Manager,
    get_token_expiration,
    is_token_expired,
    is_token_valid,
)
from .clients import HttpClient, JobberClient

# Configuration management
from .config import ConfigManagerImpl

# Coordination components
from .coordinators import MigrationCoordinator, RichMigrationCoordinator

# Exception classes for error handling
from .exceptions import (
    ConfigurationError,
    JobberApiError,
    MappingError,
    OAuth2Error,
    RepositoryError,
    TightBeamError,
)

# Logging components
from .interfaces import ConfigManager, Logger
from .loggers import ConsoleLogger, RichLogger
from .mappers import EntityMapper
from .models import Client, Invoice, MigrationSummary
from .repositories import Repository

# Logging components

__version__ = "0.1.0"
__all__ = [
    # Core components
    "AuthProvider",
    "OAuth2Manager",
    "get_token_expiration",
    "is_token_expired",
    "is_token_valid",
    "HttpClient",
    "JobberClient",
    "EntityMapper",
    "Client",
    "Invoice",
    "MigrationSummary",
    "Repository",
    # Configuration management
    "ConfigManager",
    "ConfigManagerImpl",
    # Logging components
    "Logger",
    "ConsoleLogger",
    "RichLogger",
    # Coordination components
    "MigrationCoordinator",
    "RichMigrationCoordinator",
    # Exception classes
    "TightBeamError",
    "ConfigurationError",
    "JobberApiError",
    "MappingError",
    "OAuth2Error",
    "RepositoryError",
]
