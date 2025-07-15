"""Repository class for SQLite database operations."""

import sqlite3
from typing import List, Optional, Generic, TypeVar
from pathlib import Path

from ..exceptions import DatabaseError
from ..models.client import Client
from ..models.invoice import Invoice

T = TypeVar("T")


class Repository:
    """Handles SQLite database operations for Client and Invoice entities."""

    def __init__(self, db_path: Path) -> None:
        """Initialize Repository with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Establish database connection and initialize schema."""
        # TODO: Implement database connection and schema creation
        raise NotImplementedError("Repository.connect() not yet implemented")

    def disconnect(self) -> None:
        """Close database connection."""
        # TODO: Implement connection cleanup
        raise NotImplementedError("Repository.disconnect() not yet implemented")

    def save_client(self, client: Client) -> None:
        """Save a client to the database.

        Args:
            client: Client entity to save
        """
        # TODO: Implement client insertion/update
        raise NotImplementedError("Repository.save_client() not yet implemented")

    def save_invoice(self, invoice: Invoice) -> None:
        """Save an invoice to the database.

        Args:
            invoice: Invoice entity to save
        """
        # TODO: Implement invoice insertion/update
        raise NotImplementedError("Repository.save_invoice() not yet implemented")
