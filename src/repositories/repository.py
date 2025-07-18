"""Repository class for SQLite database operations."""

import sqlite3
from typing import List, Optional, Union

from ..exceptions import RepositoryError
from ..models import Attachment, Client, Invoice, Note, Quote


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

    def _migrate_existing_tables(self) -> None:
        """Migrate existing tables to add new columns for enhanced models.

        Adds additional_emails and additional_phones columns to clients table,
        and due_date, subtotal, and line_items columns to invoices table.
        Uses conditional ALTER TABLE statements to only add columns if they don't exist.

        Raises:
            RepositoryError: If migration fails
        """
        try:
            cursor = self._connection.cursor()

            # Check and add additional_emails column to clients table
            cursor.execute("PRAGMA table_info(clients)")
            clients_columns = {row[1] for row in cursor.fetchall()}

            if "additional_emails" not in clients_columns:
                cursor.execute(
                    "ALTER TABLE clients ADD COLUMN additional_emails TEXT DEFAULT '[]'"
                )

            if "additional_phones" not in clients_columns:
                cursor.execute(
                    "ALTER TABLE clients ADD COLUMN additional_phones TEXT DEFAULT '[]'"
                )

            # Check and add new columns to invoices table
            cursor.execute("PRAGMA table_info(invoices)")
            invoices_columns = {row[1] for row in cursor.fetchall()}

            if "due_date" not in invoices_columns:
                cursor.execute(
                    "ALTER TABLE invoices ADD COLUMN due_date TEXT DEFAULT ''"
                )

            if "subtotal" not in invoices_columns:
                cursor.execute(
                    "ALTER TABLE invoices ADD COLUMN subtotal INTEGER DEFAULT 0"
                )

            if "line_items" not in invoices_columns:
                cursor.execute(
                    "ALTER TABLE invoices ADD COLUMN line_items TEXT DEFAULT '[]'"
                )

            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to migrate existing tables: {e}") from e

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

            # Create quotes table for quote entities
            quotes_schema = """
                CREATE TABLE IF NOT EXISTS quotes (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id),
                    quote_number TEXT,
                    title TEXT,
                    total INTEGER,
                    subtotal INTEGER,
                    disclaimer TEXT,
                    line_items TEXT,
                    created_at TEXT,
                    transitioned_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(quotes_schema)

            # Create notes table for polymorphic note entities
            notes_schema = """
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(notes_schema)

            # Create attachments table for note file attachments
            attachments_schema = """
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    note_id TEXT NOT NULL REFERENCES notes(id),
                    file_name TEXT,
                    content_type TEXT,
                    original_url TEXT,
                    local_file_path TEXT,
                    file_size INTEGER,
                    created_at TEXT
                )
            """
            cursor.execute(attachments_schema)

            # Migrate existing tables to add new columns
            self._migrate_existing_tables()

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to initialize database schema: {e}") from e

    def create(self, entity: Union[Client, Invoice, Quote, Note, Attachment]) -> None:
        """Create a new entity in the database.

        Generic method supporting Client, Invoice, Quote, Note, and Attachment entities.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            entity: Client, Invoice, Quote, Note, or Attachment entity to create

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if isinstance(entity, Client):
                cursor.execute(
                    """INSERT OR REPLACE INTO clients
                       (id, first_name, last_name, email, phone, created_at, additional_emails, additional_phones)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.first_name,
                        entity.last_name,
                        entity.email,
                        entity.phone,
                        entity.created_at,
                        entity.additional_emails,
                        entity.additional_phones,
                    ),
                )
            elif isinstance(entity, Invoice):
                cursor.execute(
                    """INSERT OR REPLACE INTO invoices
                       (id, client_id, number, total_cents, status, issued_at, due_date, subtotal, line_items)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.client_id,
                        entity.number,
                        entity.total_cents,
                        entity.status,
                        entity.issued_at,
                        entity.due_date,
                        entity.subtotal,
                        entity.line_items,
                    ),
                )
            elif isinstance(entity, Quote):
                cursor.execute(
                    """INSERT OR REPLACE INTO quotes
                       (id, client_id, quote_number, title, total, subtotal, disclaimer, line_items, created_at, transitioned_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.client_id,
                        entity.quote_number,
                        entity.title,
                        entity.total,
                        entity.subtotal,
                        entity.disclaimer,
                        entity.line_items,
                        entity.created_at,
                        entity.transitioned_at,
                        entity.updated_at,
                    ),
                )
            elif isinstance(entity, Note):
                cursor.execute(
                    """INSERT OR REPLACE INTO notes
                       (id, entity_type, entity_id, message, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.entity_type,
                        entity.entity_id,
                        entity.message,
                        entity.created_at,
                        entity.updated_at,
                    ),
                )
            elif isinstance(entity, Attachment):
                cursor.execute(
                    """INSERT OR REPLACE INTO attachments
                       (id, note_id, file_name, content_type, original_url, local_file_path, file_size, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.note_id,
                        entity.file_name,
                        entity.content_type,
                        entity.original_url,
                        entity.local_file_path,
                        entity.file_size,
                        entity.created_at,
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
    ) -> Optional[Union[Client, Invoice, Quote, Note, Attachment]]:
        """Read a single entity by ID.

        Generic method supporting Client, Invoice, Quote, Note, and Attachment entities.

        Args:
            entity_type: Client, Invoice, Quote, Note, or Attachment class type
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
                    "SELECT id, first_name, last_name, email, phone, created_at, additional_emails, additional_phones FROM clients WHERE id = ?",  # noqa: E501
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
                        additional_emails=row[6] if row[6] is not None else "[]",
                        additional_phones=row[7] if row[7] is not None else "[]",
                    )

            elif entity_type == Invoice:
                cursor.execute(
                    "SELECT id, client_id, number, total_cents, status, issued_at, due_date, subtotal, line_items FROM invoices WHERE id = ?",  # noqa: E501
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
                        due_date=row[6] if row[6] is not None else "",
                        subtotal=row[7] if row[7] is not None else 0,
                        line_items=row[8] if row[8] is not None else "[]",
                    )

            elif entity_type == Quote:
                cursor.execute(
                    "SELECT id, client_id, quote_number, title, total, subtotal, disclaimer, line_items, created_at, transitioned_at, updated_at FROM quotes WHERE id = ?",  # noqa: E501
                    (entity_id,),
                )
                row = cursor.fetchone()
                cursor.close()

                if row:
                    return Quote(
                        id=row[0],
                        client_id=row[1],
                        quote_number=row[2],
                        title=row[3],
                        total=row[4],
                        subtotal=row[5],
                        disclaimer=row[6],
                        line_items=row[7],
                        created_at=row[8],
                        transitioned_at=row[9],
                        updated_at=row[10],
                    )

            elif entity_type == Note:
                cursor.execute(
                    "SELECT id, entity_type, entity_id, message, created_at, updated_at FROM notes WHERE id = ?",  # noqa: E501
                    (entity_id,),
                )
                row = cursor.fetchone()
                cursor.close()

                if row:
                    return Note(
                        id=row[0],
                        entity_type=row[1],
                        entity_id=row[2],
                        message=row[3],
                        created_at=row[4],
                        updated_at=row[5],
                    )

            elif entity_type == Attachment:
                cursor.execute(
                    "SELECT id, note_id, file_name, content_type, original_url, local_file_path, file_size, created_at FROM attachments WHERE id = ?",  # noqa: E501
                    (entity_id,),
                )
                row = cursor.fetchone()
                cursor.close()

                if row:
                    return Attachment(
                        id=row[0],
                        note_id=row[1],
                        file_name=row[2],
                        content_type=row[3],
                        original_url=row[4],
                        local_file_path=row[5],
                        file_size=row[6],
                        created_at=row[7],
                    )
            else:
                raise RepositoryError(f"Unsupported entity type: {entity_type}")

            return None

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to read entity: {e}") from e

    def update(self, entity: Union[Client, Invoice, Quote, Note, Attachment]) -> None:
        """Update an existing entity in the database.

        Generic method supporting Client, Invoice, Quote, Note, and Attachment entities.
        Uses UPDATE with parameterized queries.

        Args:
            entity: Client, Invoice, Quote, Note, or Attachment entity to update

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if isinstance(entity, Client):
                cursor.execute(
                    """UPDATE clients SET
                       first_name = ?, last_name = ?, email = ?, phone = ?, created_at = ?, additional_emails = ?, additional_phones = ?
                       WHERE id = ?""",  # noqa: E501
                    (
                        entity.first_name,
                        entity.last_name,
                        entity.email,
                        entity.phone,
                        entity.created_at,
                        entity.additional_emails,
                        entity.additional_phones,
                        entity.id,
                    ),
                )
            elif isinstance(entity, Invoice):
                cursor.execute(
                    """UPDATE invoices SET
                       client_id = ?, number = ?, total_cents = ?, status = ?, issued_at = ?, due_date = ?, subtotal = ?, line_items = ?
                       WHERE id = ?""",  # noqa: E501
                    (
                        entity.client_id,
                        entity.number,
                        entity.total_cents,
                        entity.status,
                        entity.issued_at,
                        entity.due_date,
                        entity.subtotal,
                        entity.line_items,
                        entity.id,
                    ),
                )
            elif isinstance(entity, Quote):
                cursor.execute(
                    """UPDATE quotes SET
                       client_id = ?, quote_number = ?, title = ?, total = ?, subtotal = ?, disclaimer = ?, line_items = ?, created_at = ?, transitioned_at = ?, updated_at = ?
                       WHERE id = ?""",  # noqa: E501
                    (
                        entity.client_id,
                        entity.quote_number,
                        entity.title,
                        entity.total,
                        entity.subtotal,
                        entity.disclaimer,
                        entity.line_items,
                        entity.created_at,
                        entity.transitioned_at,
                        entity.updated_at,
                        entity.id,
                    ),
                )
            elif isinstance(entity, Note):
                cursor.execute(
                    """UPDATE notes SET
                       entity_type = ?, entity_id = ?, message = ?, created_at = ?, updated_at = ?
                       WHERE id = ?""",  # noqa: E501
                    (
                        entity.entity_type,
                        entity.entity_id,
                        entity.message,
                        entity.created_at,
                        entity.updated_at,
                        entity.id,
                    ),
                )
            elif isinstance(entity, Attachment):
                cursor.execute(
                    """UPDATE attachments SET
                       note_id = ?, file_name = ?, content_type = ?, original_url = ?, local_file_path = ?, file_size = ?, created_at = ?
                       WHERE id = ?""",  # noqa: E501
                    (
                        entity.note_id,
                        entity.file_name,
                        entity.content_type,
                        entity.original_url,
                        entity.local_file_path,
                        entity.file_size,
                        entity.created_at,
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

        Generic method supporting Client, Invoice, Quote, Note, and Attachment entities.

        Args:
            entity_type: Client, Invoice, Quote, Note, or Attachment class type
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
            elif entity_type == Quote:
                cursor.execute("DELETE FROM quotes WHERE id = ?", (entity_id,))
            elif entity_type == Note:
                cursor.execute("DELETE FROM notes WHERE id = ?", (entity_id,))
            elif entity_type == Attachment:
                cursor.execute("DELETE FROM attachments WHERE id = ?", (entity_id,))
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
                    client.additional_emails,
                    client.additional_phones,
                )
                for client in clients
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO clients
                   (id, first_name, last_name, email, phone, created_at, additional_emails, additional_phones)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
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
                    invoice.due_date,
                    invoice.subtotal,
                    invoice.line_items,
                )
                for invoice in invoices
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO invoices
                   (id, client_id, number, total_cents, status, issued_at, due_date, subtotal, line_items)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                invoice_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save invoices batch: {e}") from e

    def save_quotes(self, quotes: List[Quote]) -> None:
        """Batch save multiple quotes to the database.

        Efficiently handles List[Quote] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            quotes: List of Quote entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not quotes:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            quote_data = [
                (
                    quote.id,
                    quote.client_id,
                    quote.quote_number,
                    quote.title,
                    quote.total,
                    quote.subtotal,
                    quote.disclaimer,
                    quote.line_items,
                    quote.created_at,
                    quote.transitioned_at,
                    quote.updated_at,
                )
                for quote in quotes
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO quotes
                   (id, client_id, quote_number, title, total, subtotal, disclaimer, line_items, created_at, transitioned_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                quote_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save quotes batch: {e}") from e

    def save_notes(self, notes: List[Note]) -> None:
        """Batch save multiple notes to the database.

        Efficiently handles List[Note] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            notes: List of Note entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not notes:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            note_data = [
                (
                    note.id,
                    note.entity_type,
                    note.entity_id,
                    note.message,
                    note.created_at,
                    note.updated_at,
                )
                for note in notes
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO notes
                   (id, entity_type, entity_id, message, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",  # noqa: E501
                note_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save notes batch: {e}") from e

    def save_attachments(self, attachments: List[Attachment]) -> None:
        """Batch save multiple attachments to the database.

        Efficiently handles List[Attachment] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            attachments: List of Attachment entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not attachments:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            attachment_data = [
                (
                    attachment.id,
                    attachment.note_id,
                    attachment.file_name,
                    attachment.content_type,
                    attachment.original_url,
                    attachment.local_file_path,
                    attachment.file_size,
                    attachment.created_at,
                )
                for attachment in attachments
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO attachments
                   (id, note_id, file_name, content_type, original_url, local_file_path, file_size, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                attachment_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save attachments batch: {e}") from e

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
                "SELECT id, first_name, last_name, email, phone, created_at, additional_emails, additional_phones FROM clients ORDER BY id"  # noqa: E501
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
                    additional_emails=row[6] if row[6] is not None else "[]",
                    additional_phones=row[7] if row[7] is not None else "[]",
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
                "SELECT id, client_id, number, total_cents, status, issued_at, due_date, subtotal, line_items FROM invoices ORDER BY id"  # noqa: E501
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
                    due_date=row[6] if row[6] is not None else "",
                    subtotal=row[7] if row[7] is not None else 0,
                    line_items=row[8] if row[8] is not None else "[]",
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all invoices: {e}") from e

    def get_all_quotes(self) -> List[Quote]:
        """Retrieve all quotes from the database.

        Returns:
            List of all Quote entities

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT id, client_id, quote_number, title, total, subtotal, disclaimer, line_items, created_at, transitioned_at, updated_at FROM quotes ORDER BY id"  # noqa: E501
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                Quote(
                    id=row[0],
                    client_id=row[1],
                    quote_number=row[2],
                    title=row[3],
                    total=row[4],
                    subtotal=row[5],
                    disclaimer=row[6],
                    line_items=row[7],
                    created_at=row[8],
                    transitioned_at=row[9],
                    updated_at=row[10],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all quotes: {e}") from e

    def get_all_notes(self) -> List[Note]:
        """Retrieve all notes from the database.

        Returns:
            List of all Note entities

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT id, entity_type, entity_id, message, created_at, updated_at FROM notes ORDER BY id"  # noqa: E501
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                Note(
                    id=row[0],
                    entity_type=row[1],
                    entity_id=row[2],
                    message=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all notes: {e}") from e

    def get_all_attachments(self) -> List[Attachment]:
        """Retrieve all attachments from the database.

        Returns:
            List of all Attachment entities

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT id, note_id, file_name, content_type, original_url, local_file_path, file_size, created_at FROM attachments ORDER BY id"  # noqa: E501
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                Attachment(
                    id=row[0],
                    note_id=row[1],
                    file_name=row[2],
                    content_type=row[3],
                    original_url=row[4],
                    local_file_path=row[5],
                    file_size=row[6],
                    created_at=row[7],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all attachments: {e}") from e

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
