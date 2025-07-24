"""Service factory for dependency injection and service creation.

This module implements factory patterns for creating and managing
service dependencies used across CLI commands.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from src.auth import AuthProvider, OAuth2Manager
from src.clients import HttpClient
from src.repositories import Repository
from .shared import SharedServices


class ServiceFactory:
    """Factory class for creating and configuring services with dependency injection.

    This factory centralizes the creation of commonly used services like Repository,
    OAuth2Manager, and HttpClient to eliminate duplication across CLI commands.
    """

    @staticmethod
    def create_repository(db: Optional[Path] = None) -> Repository:
        """Create Repository with database connection and initialize schema.

        Args:
            db: Optional database path, defaults to SharedServices.DEFAULT_DB_PATH

        Returns:
            Repository: Configured repository with initialized schema
        """
        db_path = SharedServices.resolve_db_path(db)

        # Ensure parent directories exist
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create database connection
        connection = sqlite3.Connection(str(db_path))
        repository = Repository(connection)

        # Initialize schema including oauth_tokens table
        repository.init_schema()

        return repository

    @staticmethod
    def create_oauth2_manager() -> OAuth2Manager:
        """Create OAuth2Manager with configuration from environment.

        Returns:
            OAuth2Manager: Configured OAuth2Manager with environment config
        """
        client_id, client_secret, redirect_uri = AuthProvider.get_oauth2_config()
        http_client = ServiceFactory.create_http_client()

        return OAuth2Manager(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            http_client=http_client,
        )

    @staticmethod
    def create_http_client() -> HttpClient:
        """Create HttpClient instance.

        Returns:
            HttpClient: Basic HTTP client instance
        """
        return HttpClient()

    @staticmethod
    def get_console():
        """Get shared console instance.

        Returns:
            Console: Shared Rich console for output
        """
        return SharedServices.get_console()
