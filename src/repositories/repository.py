"""Repository class for SQLite database operations."""

import sqlite3
from typing import List, Optional, Union

from ..exceptions import RepositoryError
from ..models import (
    Attachment,
    Client,
    Expense,
    Invoice,
    Job,
    Note,
    ProductService,
    Property,
    Quote,
    Request,
    TaxRate,
    TimeSheetEntry,
    User,
    Visit,
)


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

            # Create note_references table for temporary storage during large migrations
            note_references_schema = """
                CREATE TABLE IF NOT EXISTS note_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """
            cursor.execute(note_references_schema)

            # Create graphql_costs table for GraphQL query complexity points tracking
            graphql_costs_schema = """
                CREATE TABLE IF NOT EXISTS graphql_costs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_type TEXT NOT NULL,
                    batch_size INTEGER NOT NULL,
                    requested_cost INTEGER NOT NULL,
                    actual_cost INTEGER NOT NULL,
                    cost_difference INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """
            cursor.execute(graphql_costs_schema)

            # Create properties table for service locations
            properties_schema = """
                CREATE TABLE IF NOT EXISTS properties (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    name TEXT,
                    address_line1 TEXT,
                    address_line2 TEXT,
                    city TEXT,
                    state_province TEXT,
                    postal_code TEXT,
                    country TEXT,
                    latitude TEXT,
                    longitude TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(properties_schema)

            # Create jobs table for work units
            jobs_schema = """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    property_id TEXT REFERENCES properties(id) ON DELETE SET NULL,
                    quote_id TEXT REFERENCES quotes(id) ON DELETE SET NULL,
                    job_number TEXT,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    scheduled_start_at TEXT,
                    scheduled_end_at TEXT,
                    completed_at TEXT,
                    total INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(jobs_schema)

            # Create requests table for service requests
            requests_schema = """
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    property_id TEXT REFERENCES properties(id) ON DELETE SET NULL,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    priority TEXT,
                    source TEXT,
                    assigned_to TEXT,
                    converted_to_quote_id TEXT REFERENCES quotes(id) ON DELETE SET NULL,
                    converted_to_job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(requests_schema)

            # Create users table for team member entities
            users_schema = """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    email TEXT,
                    role TEXT,
                    is_account_admin TEXT,
                    is_account_owner TEXT,
                    status TEXT,
                    phone TEXT,
                    timezone TEXT,
                    created_at TEXT,
                    last_login_at TEXT
                )
            """
            cursor.execute(users_schema)

            # Create expenses table for job-related expenses
            expenses_schema = """
                CREATE TABLE IF NOT EXISTS expenses (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    amount_cents INTEGER,
                    description TEXT,
                    category TEXT,
                    receipt_url TEXT,
                    vendor TEXT,
                    expense_date TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(expenses_schema)

            # Create visits table for scheduled service visits
            visits_schema = """
                CREATE TABLE IF NOT EXISTS visits (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    property_id TEXT REFERENCES properties(id) ON DELETE SET NULL,
                    assigned_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    title TEXT,
                    instructions TEXT,
                    status TEXT,
                    all_day TEXT,
                    duration_minutes INTEGER,
                    start_at TEXT,
                    end_at TEXT,
                    completed_at TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(visits_schema)

            # Create timesheet_entries table for time tracking
            timesheet_entries_schema = """
                CREATE TABLE IF NOT EXISTS timesheet_entries (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    visit_id TEXT REFERENCES visits(id) ON DELETE SET NULL,
                    approved_by_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    paid_by_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    label TEXT,
                    note TEXT,
                    labour_rate TEXT,
                    final_duration_seconds INTEGER,
                    visit_duration_total_seconds INTEGER,
                    approved TEXT,
                    ticking TEXT,
                    start_at TEXT,
                    end_at TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(timesheet_entries_schema)

            # Create products_services table for service catalog
            products_services_schema = """
                CREATE TABLE IF NOT EXISTS products_services (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    category TEXT,
                    default_unit_cost_cents INTEGER,
                    internal_unit_cost_cents INTEGER,
                    markup_percentage TEXT,
                    duration_minutes INTEGER,
                    taxable TEXT,
                    visible TEXT,
                    online_booking_enabled TEXT,
                    online_booking_sort_order INTEGER,
                    active TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(products_services_schema)

            # Create tax_rates table for regional tax configuration
            tax_rates_schema = """
                CREATE TABLE IF NOT EXISTS tax_rates (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    rate_percentage TEXT,
                    region TEXT,
                    compound TEXT,
                    active TEXT,
                    description TEXT,
                    tax_number TEXT,
                    display_order INTEGER,
                    default_for_region TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """
            cursor.execute(tax_rates_schema)

            # Create indexes for foreign keys to improve query performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_properties_client_id ON properties(client_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_client_id ON jobs(client_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_property_id ON jobs(property_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_quote_id ON jobs(quote_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_client_id ON requests(client_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_property_id ON requests(property_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_converted_to_quote_id ON requests(converted_to_quote_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_converted_to_job_id ON requests(converted_to_job_id)"  # noqa: E501
            )

            # Also add indexes for existing foreign keys if not already present
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoices_client_id ON invoices(client_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_quotes_client_id ON quotes(client_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachments_note_id ON attachments(note_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_note_references_entity ON note_references(entity_type, entity_id)"  # noqa: E501
            )

            # Add indexes for new entity foreign keys
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_expenses_job_id ON expenses(job_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_visits_job_id ON visits(job_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_visits_client_id ON visits(client_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_visits_property_id ON visits(property_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_visits_assigned_user_id ON visits(assigned_user_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timesheet_entries_user_id ON timesheet_entries(user_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timesheet_entries_job_id ON timesheet_entries(job_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timesheet_entries_visit_id ON timesheet_entries(visit_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timesheet_entries_approved_by_id ON timesheet_entries(approved_by_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timesheet_entries_paid_by_id ON timesheet_entries(paid_by_id)"  # noqa: E501
            )

            # Migrate existing tables to add new columns
            self._migrate_existing_tables()

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to initialize database schema: {e}") from e

    def create(
        self,
        entity: Union[Client, Invoice, Quote, Note, Attachment, Job, Property, Request],
    ) -> None:
        """Create a new entity in the database.

        Generic method supporting all entity types.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            entity: Entity to create (Client, Invoice, Quote, Note, Attachment, Job,
                    Property, or Request)

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
            elif isinstance(entity, Job):
                cursor.execute(
                    """INSERT OR REPLACE INTO jobs
                       (id, client_id, property_id, quote_id, job_number, title, description, status,
                        scheduled_start_at, scheduled_end_at, completed_at, total, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.client_id,
                        entity.property_id,
                        entity.quote_id,
                        entity.job_number,
                        entity.title,
                        entity.description,
                        entity.status,
                        entity.scheduled_start_at,
                        entity.scheduled_end_at,
                        entity.completed_at,
                        entity.total,
                        entity.created_at,
                        entity.updated_at,
                    ),
                )
            elif isinstance(entity, Property):
                cursor.execute(
                    """INSERT OR REPLACE INTO properties
                       (id, client_id, name, address_line1, address_line2, city, state_province,
                        postal_code, country, latitude, longitude, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.client_id,
                        entity.name,
                        entity.address_line1,
                        entity.address_line2,
                        entity.city,
                        entity.state_province,
                        entity.postal_code,
                        entity.country,
                        entity.latitude,
                        entity.longitude,
                        entity.created_at,
                        entity.updated_at,
                    ),
                )
            elif isinstance(entity, Request):
                cursor.execute(
                    """INSERT OR REPLACE INTO requests
                       (id, client_id, property_id, title, description, status, priority, source,
                        assigned_to, converted_to_quote_id, converted_to_job_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    (
                        entity.id,
                        entity.client_id,
                        entity.property_id,
                        entity.title,
                        entity.description,
                        entity.status,
                        entity.priority,
                        entity.source,
                        entity.assigned_to,
                        entity.converted_to_quote_id,
                        entity.converted_to_job_id,
                        entity.created_at,
                        entity.updated_at,
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
    ) -> Optional[
        Union[Client, Invoice, Quote, Note, Attachment, Job, Property, Request]
    ]:
        """Read a single entity by ID.

        Generic method supporting all entity types.

        Args:
            entity_type: Entity class type (Client, Invoice, Quote, Note, Attachment,
                         Job, Property, or Request)
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

        Generic method supporting all entity types.

        Args:
            entity_type: Entity class type (Client, Invoice, Quote, Note, Attachment,
                         Job, Property, or Request)
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
            elif entity_type == Job:
                cursor.execute("DELETE FROM jobs WHERE id = ?", (entity_id,))
            elif entity_type == Property:
                cursor.execute("DELETE FROM properties WHERE id = ?", (entity_id,))
            elif entity_type == Request:
                cursor.execute("DELETE FROM requests WHERE id = ?", (entity_id,))
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

    def save_jobs(self, jobs: List[Job]) -> None:
        """Batch save multiple jobs to the database.

        Efficiently handles List[Job] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            jobs: List of Job entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not jobs:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            job_data = [
                (
                    job.id,
                    job.client_id,
                    job.property_id,
                    job.quote_id,
                    job.job_number,
                    job.title,
                    job.description,
                    job.status,
                    job.scheduled_start_at,
                    job.scheduled_end_at,
                    job.completed_at,
                    job.total,
                    job.created_at,
                    job.updated_at,
                )
                for job in jobs
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO jobs
                   (id, client_id, property_id, quote_id, job_number, title, description, status,
                    scheduled_start_at, scheduled_end_at, completed_at, total, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                job_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save jobs batch: {e}") from e

    def save_properties(self, properties: List[Property]) -> None:
        """Batch save multiple properties to the database.

        Efficiently handles List[Property] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            properties: List of Property entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not properties:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            property_data = [
                (
                    prop.id,
                    prop.client_id,
                    prop.name,
                    prop.address_line1,
                    prop.address_line2,
                    prop.city,
                    prop.state_province,
                    prop.postal_code,
                    prop.country,
                    prop.latitude,
                    prop.longitude,
                    prop.created_at,
                    prop.updated_at,
                )
                for prop in properties
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO properties
                   (id, client_id, name, address_line1, address_line2, city, state_province,
                    postal_code, country, latitude, longitude, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                property_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save properties batch: {e}") from e

    def save_requests(self, requests: List[Request]) -> None:
        """Batch save multiple requests to the database.

        Efficiently handles List[Request] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            requests: List of Request entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not requests:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            request_data = [
                (
                    request.id,
                    request.client_id,
                    request.property_id,
                    request.title,
                    request.description,
                    request.status,
                    request.priority,
                    request.source,
                    request.assigned_to,
                    request.converted_to_quote_id,
                    request.converted_to_job_id,
                    request.created_at,
                    request.updated_at,
                )
                for request in requests
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO requests
                   (id, client_id, property_id, title, description, status, priority, source,
                    assigned_to, converted_to_quote_id, converted_to_job_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                request_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save requests batch: {e}") from e

    def save_users(self, users: List[User]) -> None:
        """Batch save multiple users to the database.

        Efficiently handles List[User] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            users: List of User entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not users:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            user_data = [
                (
                    user.id,
                    user.first_name,
                    user.last_name,
                    user.email,
                    user.role,
                    user.is_account_admin,
                    user.is_account_owner,
                    user.status,
                    user.phone,
                    user.timezone,
                    user.created_at,
                    user.last_login_at,
                )
                for user in users
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO users
                   (id, first_name, last_name, email, role, is_account_admin, is_account_owner,
                    status, phone, timezone, created_at, last_login_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                user_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save users batch: {e}") from e

    def save_expenses(self, expenses: List[Expense]) -> None:
        """Batch save multiple expenses to the database.

        Efficiently handles List[Expense] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            expenses: List of Expense entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not expenses:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            expense_data = [
                (
                    expense.id,
                    expense.job_id,
                    expense.amount_cents,
                    expense.description,
                    expense.category,
                    expense.receipt_url,
                    expense.vendor,
                    expense.expense_date,
                    expense.created_at,
                    expense.updated_at,
                )
                for expense in expenses
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO expenses
                   (id, job_id, amount_cents, description, category, receipt_url, vendor,
                    expense_date, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                expense_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save expenses batch: {e}") from e

    def save_visits(self, visits: List[Visit]) -> None:
        """Batch save multiple visits to the database.

        Efficiently handles List[Visit] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            visits: List of Visit entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not visits:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            visit_data = [
                (
                    visit.id,
                    visit.job_id,
                    visit.client_id,
                    visit.property_id,
                    visit.assigned_user_id,
                    visit.title,
                    visit.instructions,
                    visit.status,
                    visit.all_day,
                    visit.duration_minutes,
                    visit.start_at,
                    visit.end_at,
                    visit.completed_at,
                    visit.created_at,
                    visit.updated_at,
                )
                for visit in visits
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO visits
                   (id, job_id, client_id, property_id, assigned_user_id, title, instructions,
                    status, all_day, duration_minutes, start_at, end_at, completed_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                visit_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save visits batch: {e}") from e

    def save_timesheet_entries(self, timesheet_entries: List[TimeSheetEntry]) -> None:
        """Batch save multiple timesheet entries to the database.

        Efficiently handles List[TimeSheetEntry] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            timesheet_entries: List of TimeSheetEntry entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not timesheet_entries:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            timesheet_data = [
                (
                    entry.id,
                    entry.user_id,
                    entry.job_id,
                    entry.visit_id,
                    entry.approved_by_id,
                    entry.paid_by_id,
                    entry.label,
                    entry.note,
                    entry.labour_rate,
                    entry.final_duration_seconds,
                    entry.visit_duration_total_seconds,
                    entry.approved,
                    entry.ticking,
                    entry.start_at,
                    entry.end_at,
                    entry.created_at,
                    entry.updated_at,
                )
                for entry in timesheet_entries
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO timesheet_entries
                   (id, user_id, job_id, visit_id, approved_by_id, paid_by_id, label, note,
                    labour_rate, final_duration_seconds, visit_duration_total_seconds,
                    approved, ticking, start_at, end_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                timesheet_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save timesheet entries batch: {e}") from e

    def save_products_services(self, products_services: List[ProductService]) -> None:
        """Batch save multiple products/services to the database.

        Efficiently handles List[ProductService] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            products_services: List of ProductService entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not products_services:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            product_data = [
                (
                    product.id,
                    product.name,
                    product.description,
                    product.category,
                    product.default_unit_cost_cents,
                    product.internal_unit_cost_cents,
                    product.markup_percentage,
                    product.duration_minutes,
                    product.taxable,
                    product.visible,
                    product.online_booking_enabled,
                    product.online_booking_sort_order,
                    product.active,
                    product.created_at,
                    product.updated_at,
                )
                for product in products_services
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO products_services
                   (id, name, description, category, default_unit_cost_cents, internal_unit_cost_cents,
                    markup_percentage, duration_minutes, taxable, visible, online_booking_enabled,
                    online_booking_sort_order, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                product_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save products/services batch: {e}") from e

    def save_tax_rates(self, tax_rates: List[TaxRate]) -> None:
        """Batch save multiple tax rates to the database.

        Efficiently handles List[TaxRate] using executemany for bulk operations.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            tax_rates: List of TaxRate entities to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not tax_rates:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            tax_rate_data = [
                (
                    tax_rate.id,
                    tax_rate.name,
                    tax_rate.rate_percentage,
                    tax_rate.region,
                    tax_rate.compound,
                    tax_rate.active,
                    tax_rate.description,
                    tax_rate.tax_number,
                    tax_rate.display_order,
                    tax_rate.default_for_region,
                    tax_rate.created_at,
                    tax_rate.updated_at,
                )
                for tax_rate in tax_rates
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO tax_rates
                   (id, name, rate_percentage, region, compound, active, description, tax_number,
                    display_order, default_for_region, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                tax_rate_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save tax rates batch: {e}") from e

    def save_entities(
        self,
        entities: List[
            Union[
                Client,
                Invoice,
                Quote,
                Note,
                Attachment,
                Job,
                Property,
                Request,
                User,
                Expense,
                Visit,
                TimeSheetEntry,
                ProductService,
                TaxRate,
            ]
        ],
        entity_type: type,
    ) -> None:
        """Generic batch save method for any supported entity type.

        Delegates to the appropriate specific save method based on entity type.
        Provides a unified interface for saving different entity types.

        Args:
            entities: List of entities to save
            entity_type: Type of entities being saved

        Raises:
            RepositoryError: If entity type is unsupported or save fails
        """
        if not entities:
            return

        # Map entity types to their specific save methods
        save_methods = {
            Client: self.save_clients,
            Invoice: self.save_invoices,
            Quote: self.save_quotes,
            Note: self.save_notes,
            Attachment: self.save_attachments,
            Job: self.save_jobs,
            Property: self.save_properties,
            Request: self.save_requests,
            User: self.save_users,
            Expense: self.save_expenses,
            Visit: self.save_visits,
            TimeSheetEntry: self.save_timesheet_entries,
            ProductService: self.save_products_services,
            TaxRate: self.save_tax_rates,
        }

        save_method = save_methods.get(entity_type)
        if not save_method:
            raise RepositoryError(f"Unsupported entity type for save: {entity_type}")

        # Call the appropriate save method
        save_method(entities)

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

    def save_note_references(self, references: List[dict[str, str]]) -> None:
        """Batch save note references to temporary storage.

        Stores note references for deferred processing during large migrations.
        Uses batch insert for efficiency with large volumes.

        Args:
            references: List of dicts with note_id, entity_type, entity_id

        Raises:
            RepositoryError: If database operation fails
        """
        if not references:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            reference_data = [
                (ref.get("note_id"), ref.get("entity_type"), ref.get("entity_id"))
                for ref in references
                if all(
                    [ref.get("note_id"), ref.get("entity_type"), ref.get("entity_id")]
                )
            ]

            if reference_data:
                cursor.executemany(
                    """INSERT INTO note_references (note_id, entity_type, entity_id)
                       VALUES (?, ?, ?)""",
                    reference_data,
                )

                self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save note references: {e}") from e

    def get_note_references(
        self, limit: int = 1000, offset: int = 0
    ) -> List[dict[str, str]]:
        """Retrieve note references from temporary storage with pagination.

        Supports batch processing of large reference collections by providing
        pagination through limit and offset parameters.

        Args:
            limit: Maximum number of references to retrieve (default: 1000)
            offset: Number of references to skip (default: 0)

        Returns:
            List of dictionaries with note_id, entity_type, entity_id

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                """SELECT note_id, entity_type, entity_id
                   FROM note_references
                   ORDER BY id
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                {
                    "note_id": row[0],
                    "entity_type": row[1],
                    "entity_id": row[2],
                }
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve note references: {e}") from e

    def get_note_references_count(self) -> int:
        """Get total count of note references in temporary storage.

        Returns:
            Total number of note references stored

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM note_references")
            count = cursor.fetchone()[0]
            cursor.close()
            return count

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to count note references: {e}") from e

    def clear_note_references(self) -> None:
        """Clear all note references from temporary storage.

        Removes all stored note references, typically called after successful
        note processing completion.

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute("DELETE FROM note_references")
            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to clear note references: {e}") from e

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
