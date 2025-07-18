"""Repository class for SQLite database operations."""

import sqlite3
from typing import List, Optional, Union

from ..exceptions import RepositoryError
from ..models import Client, Invoice


class Repository:
    """Repository for SQLite database operations with Client and Invoice entities.

    Implements the Repository pattern with dependency injection for SQLite3.Connection.
    Provides generic CRUD operations and batch save methods for Client and Invoice
    entities.
    All SQL operations use parameterized queries for security.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Initialize Repository with SQLite connection dependency.

        Args:
            connection: SQLite database connection for operations
        """
        self._connection = connection

    def init_schema(self) -> None:
        """Initialize database schema with clients and invoices tables.

        Creates tables if they don't exist, matching exact schema from shrimp-rules.md.
        Uses CREATE TABLE IF NOT EXISTS for safe initialization.

        Raises:
            RepositoryError: If schema creation fails
        """
        try:
            cursor = self._connection.cursor()

            # Create clients table with exact schema from shrimp-rules.md
            clients_schema = """
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    email TEXT,
                    phone TEXT,
                    created_at TEXT
                )
            """
            cursor.execute(clients_schema)

            # Create invoices table with exact schema from shrimp-rules.md
            invoices_schema = """
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id),
                    number TEXT,
                    total_cents INTEGER,
                    status TEXT,
                    issued_at TEXT
                )
            """
            cursor.execute(invoices_schema)

            # Create oauth_tokens table for OAuth2 token storage
            oauth_tokens_schema = """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    id INTEGER PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """
            cursor.execute(oauth_tokens_schema)

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to initialize database schema: {e}") from e

    def create(self, entity: Union[Client, Invoice]) -> None:
        """Create a new entity in the database.

        Generic method supporting both Client and Invoice entities.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            entity: Client or Invoice entity to create

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if isinstance(entity, Client):
                cursor.execute(
                    """INSERT OR REPLACE INTO clients
                       (id, first_name, last_name, email, phone, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        entity.id,
                        entity.first_name,
                        entity.last_name,
                        entity.email,
                        entity.phone,
                        entity.created_at,
                    ),
                )
            elif isinstance(entity, Invoice):
                cursor.execute(
                    """INSERT OR REPLACE INTO invoices
                       (id, client_id, number, total_cents, status, issued_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        entity.id,
                        entity.client_id,
                        entity.number,
                        entity.total_cents,
                        entity.status,
                        entity.issued_at,
                    ),
                )
            else:
                raise RepositoryError(f"Unsupported entity type: {type(entity)}")

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to create entity: {e}") from e

    def read(
        self, entity_type: type, entity_id: str
    ) -> Optional[Union[Client, Invoice]]:
        """Read a single entity by ID.

        Generic method supporting both Client and Invoice entities.

        Args:
            entity_type: Client or Invoice class type
            entity_id: Entity ID to retrieve

        Returns:
            Entity instance if found, None otherwise

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if entity_type == Client:
                cursor.execute(
                    "SELECT id, first_name, last_name, email, phone, created_at FROM clients WHERE id = ?",  # noqa: E501
                    (entity_id,),
                )
                row = cursor.fetchone()
                cursor.close()

                if row:
                    return Client(
                        id=row[0],
                        first_name=row[1],
                        last_name=row[2],
                        email=row[3],
                        phone=row[4],
                        created_at=row[5],
                    )

            elif entity_type == Invoice:
                cursor.execute(
                    "SELECT id, client_id, number, total_cents, status, issued_at FROM invoices WHERE id = ?",  # noqa: E501
                    (entity_id,),
                )
                row = cursor.fetchone()
                cursor.close()

                if row:
                    return Invoice(
                        id=row[0],
                        client_id=row[1],
                        number=row[2],
                        total_cents=row[3],
                        status=row[4],
                        issued_at=row[5],
                    )
            else:
                raise RepositoryError(f"Unsupported entity type: {entity_type}")

            return None

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to read entity: {e}") from e

    def update(self, entity: Union[Client, Invoice]) -> None:
        """Update an existing entity in the database.

        Generic method supporting both Client and Invoice entities.
        Uses UPDATE with parameterized queries.

        Args:
            entity: Client or Invoice entity to update

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if isinstance(entity, Client):
                cursor.execute(
                    """UPDATE clients SET
                       first_name = ?, last_name = ?, email = ?, phone = ?, created_at = ?
                       WHERE id = ?""",  # noqa: E501
                    (
                        entity.first_name,
                        entity.last_name,
                        entity.email,
                        entity.phone,
                        entity.created_at,
                        entity.id,
                    ),
                )
            elif isinstance(entity, Invoice):
                cursor.execute(
                    """UPDATE invoices SET
                       client_id = ?, number = ?, total_cents = ?, status = ?, issued_at = ?
                       WHERE id = ?""",  # noqa: E501
                    (
                        entity.client_id,
                        entity.number,
                        entity.total_cents,
                        entity.status,
                        entity.issued_at,
                        entity.id,
                    ),
                )
            else:
                raise RepositoryError(f"Unsupported entity type: {type(entity)}")

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to update entity: {e}") from e

    def delete(self, entity_type: type, entity_id: str) -> bool:
        """Delete an entity by ID.

        Generic method supporting both Client and Invoice entities.

        Args:
            entity_type: Client or Invoice class type
            entity_id: Entity ID to delete

        Returns:
            True if entity was deleted, False if not found

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if entity_type == Client:
                cursor.execute("DELETE FROM clients WHERE id = ?", (entity_id,))
            elif entity_type == Invoice:
                cursor.execute("DELETE FROM invoices WHERE id = ?", (entity_id,))
            else:
                raise RepositoryError(f"Unsupported entity type: {entity_type}")

            rows_affected = cursor.rowcount
            self._connection.commit()
            cursor.close()

            return rows_affected > 0

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to delete entity: {e}") from e

    def save_clients(self, clients: List[Client]) -> None:
        """Batch save multiple clients to the database.

        Efficiently handles List[Client] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            clients: List of Client entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not clients:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            client_data = [
                (
                    client.id,
                    client.first_name,
                    client.last_name,
                    client.email,
                    client.phone,
                    client.created_at,
                )
                for client in clients
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO clients
                   (id, first_name, last_name, email, phone, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                client_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save clients batch: {e}") from e

    def save_invoices(self, invoices: List[Invoice]) -> None:
        """Batch save multiple invoices to the database.

        Efficiently handles List[Invoice] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            invoices: List of Invoice entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not invoices:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            invoice_data = [
                (
                    invoice.id,
                    invoice.client_id,
                    invoice.number,
                    invoice.total_cents,
                    invoice.status,
                    invoice.issued_at,
                )
                for invoice in invoices
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO invoices
                   (id, client_id, number, total_cents, status, issued_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                invoice_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save invoices batch: {e}") from e

    def get_all_clients(self) -> List[Client]:
        """Retrieve all clients from the database.

        Returns:
            List of all Client entities

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT id, first_name, last_name, email, phone, created_at FROM clients ORDER BY id"  # noqa: E501
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                Client(
                    id=row[0],
                    first_name=row[1],
                    last_name=row[2],
                    email=row[3],
                    phone=row[4],
                    created_at=row[5],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all clients: {e}") from e

    def get_all_invoices(self) -> List[Invoice]:
        """Retrieve all invoices from the database.

        Returns:
            List of all Invoice entities

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT id, client_id, number, total_cents, status, issued_at FROM invoices ORDER BY id"  # noqa: E501
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                Invoice(
                    id=row[0],
                    client_id=row[1],
                    number=row[2],
                    total_cents=row[3],
                    status=row[4],
                    issued_at=row[5],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all invoices: {e}") from e

    def save_oauth_tokens(
        self, access_token: str, refresh_token: str, expires_at: str
    ) -> None:
        """Save OAuth2 tokens to the database.

        Stores access token, refresh token, and expiration information in the oauth_tokens
        table. Uses INSERT OR REPLACE to maintain only one set of tokens at a time.
        Includes created_at timestamp for audit purposes.

        Args:
            access_token: OAuth2 access token for API authentication
            refresh_token: OAuth2 refresh token for token renewal
            expires_at: ISO 8601 formatted expiration timestamp

        Raises:
            RepositoryError: If database operation fails
        """  # noqa: E501
        try:
            cursor = self._connection.cursor()

            # Clear existing tokens and insert new ones (maintain single token set)
            cursor.execute("DELETE FROM oauth_tokens")

            # Insert new tokens with current timestamp
            cursor.execute(
                """INSERT INTO oauth_tokens
                   (access_token, refresh_token, expires_at, created_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                (access_token, refresh_token, expires_at),
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save OAuth tokens: {e}") from e

    def get_oauth_tokens(self) -> Optional[dict[str, str]]:
        """Retrieve OAuth2 tokens from the database.

        Fetches the most recently stored OAuth tokens including access token,
        refresh token, expiration time, and creation timestamp.

        Returns:
            Dictionary containing token information with keys:
            - access_token: OAuth2 access token
            - refresh_token: OAuth2 refresh token
            - expires_at: ISO 8601 formatted expiration timestamp
            - created_at: ISO 8601 formatted creation timestamp
            Returns None if no tokens are stored.

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                """SELECT access_token, refresh_token, expires_at, created_at
                   FROM oauth_tokens
                   ORDER BY id DESC
                   LIMIT 1"""
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                return {
                    "access_token": row[0],
                    "refresh_token": row[1],
                    "expires_at": row[2],
                    "created_at": row[3],
                }

            return None

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve OAuth tokens: {e}") from e

    def clear_oauth_tokens(self) -> None:
        """Clear all OAuth2 tokens from the database.

        Removes all stored OAuth tokens, effectively logging out the user from
        OAuth2 authentication. This is useful for logout operations or when
        tokens become invalid.

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute("DELETE FROM oauth_tokens")
            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to clear OAuth tokens: {e}") from e
