"""Repository class for SQLite database operations."""

import sqlite3
from typing import Callable, List, Optional, Union

from ..exceptions import RepositoryError
from ..models import (
    Attachment,
    AttachmentQueueItem,
    Client,
    EntityInventory,
    Expense,
    ExtractQueueItem,
    GraphQLCost,
    Invoice,
    Job,
    MapSnapshot,
    MigrationState,
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

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        try:
            if self._connection:
                self._connection.close()
        except sqlite3.Error:
            pass

    def __del__(self) -> None:
        """Ensure connections are closed when repository is garbage collected."""
        try:
            self.close()
        except Exception:
            pass

    def _migrate_existing_tables(self) -> None:
        """Migrate existing tables to add new columns for enhanced models.

        Adds additional_emails and additional_phones columns to clients table,
        and due_date, subtotal, and line_items columns to invoices table.
        Extends migration_state table for entity sync tracking.
        Adds download tracking fields to attachments table.
        Phase 4: Adds enhanced fields from Jobber schema alignment (balance_cents,
        company_name, billing_address, tax/discount fields, completion tracking, etc.)
        Uses conditional ALTER TABLE statements to only add columns if they don't exist.

        Raises:
            RepositoryError: If migration fails
        """
        try:
            cursor = self._connection.cursor()

            # ===== CLIENTS TABLE =====
            cursor.execute("PRAGMA table_info(clients)")
            clients_columns = {row[1] for row in cursor.fetchall()}

            if "additional_emails" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN additional_emails TEXT DEFAULT '[]'")

            if "additional_phones" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN additional_phones TEXT DEFAULT '[]'")

            # Phase 4: Enhanced client fields
            if "balance_cents" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN balance_cents INTEGER DEFAULT 0")

            if "company_name" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN company_name TEXT DEFAULT ''")

            if "billing_street" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN billing_street TEXT DEFAULT ''")

            if "billing_city" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN billing_city TEXT DEFAULT ''")

            if "billing_province" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN billing_province TEXT DEFAULT ''")

            if "billing_postal_code" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN billing_postal_code TEXT DEFAULT ''")

            if "billing_country" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN billing_country TEXT DEFAULT ''")

            if "is_archivable" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN is_archivable INTEGER DEFAULT 0")

            if "is_company" not in clients_columns:
                cursor.execute("ALTER TABLE clients ADD COLUMN is_company INTEGER DEFAULT 0")

            # ===== INVOICES TABLE =====
            cursor.execute("PRAGMA table_info(invoices)")
            invoices_columns = {row[1] for row in cursor.fetchall()}

            if "due_date" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN due_date TEXT DEFAULT ''")

            if "subtotal" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN subtotal INTEGER DEFAULT 0")

            if "line_items" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN line_items TEXT DEFAULT '[]'")

            # Phase 4: Enhanced invoice fields
            if "tax_cents" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN tax_cents INTEGER DEFAULT 0")

            if "discount_cents" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN discount_cents INTEGER DEFAULT 0")

            if "deposit_cents" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN deposit_cents INTEGER DEFAULT 0")

            if "invoice_net" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN invoice_net INTEGER DEFAULT 0")

            if "subject" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN subject TEXT DEFAULT ''")

            if "message" not in invoices_columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN message TEXT DEFAULT ''")

            # ===== QUOTES TABLE =====
            cursor.execute("PRAGMA table_info(quotes)")
            quotes_columns = {row[1] for row in cursor.fetchall()}

            # Phase 4: Enhanced quote fields
            if "tax_cents" not in quotes_columns:
                cursor.execute("ALTER TABLE quotes ADD COLUMN tax_cents INTEGER DEFAULT 0")

            if "discount_cents" not in quotes_columns:
                cursor.execute("ALTER TABLE quotes ADD COLUMN discount_cents INTEGER DEFAULT 0")

            if "quote_status" not in quotes_columns:
                cursor.execute("ALTER TABLE quotes ADD COLUMN quote_status TEXT DEFAULT ''")

            if "sent_at" not in quotes_columns:
                cursor.execute("ALTER TABLE quotes ADD COLUMN sent_at TEXT DEFAULT ''")

            # ===== JOBS TABLE =====
            cursor.execute("PRAGMA table_info(jobs)")
            jobs_columns = {row[1] for row in cursor.fetchall()}

            # Phase 4: Enhanced job fields
            if "job_type" not in jobs_columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN job_type TEXT DEFAULT ''")

            if "billing_type" not in jobs_columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN billing_type TEXT DEFAULT ''")

            if "invoiced_total" not in jobs_columns:
                cursor.execute("ALTER TABLE jobs ADD COLUMN invoiced_total INTEGER DEFAULT 0")

            # ===== PROPERTIES TABLE =====
            cursor.execute("PRAGMA table_info(properties)")
            properties_columns = {row[1] for row in cursor.fetchall()}

            # Phase 4: Enhanced property fields
            if "tax_rate_id" not in properties_columns:
                cursor.execute("ALTER TABLE properties ADD COLUMN tax_rate_id TEXT DEFAULT ''")

            if "tax_rate_name" not in properties_columns:
                cursor.execute("ALTER TABLE properties ADD COLUMN tax_rate_name TEXT DEFAULT ''")

            if "tax_rate" not in properties_columns:
                cursor.execute("ALTER TABLE properties ADD COLUMN tax_rate TEXT DEFAULT ''")

            if "is_billing_address" not in properties_columns:
                cursor.execute("ALTER TABLE properties ADD COLUMN is_billing_address INTEGER DEFAULT 0")

            if "routing_order" not in properties_columns:
                cursor.execute("ALTER TABLE properties ADD COLUMN routing_order INTEGER DEFAULT 0")

            # ===== VISITS TABLE =====
            cursor.execute("PRAGMA table_info(visits)")
            visits_columns = {row[1] for row in cursor.fetchall()}

            # Phase 4: Enhanced visit fields (client_confirmed, completed_by_id)
            if "client_confirmed" not in visits_columns:
                cursor.execute("ALTER TABLE visits ADD COLUMN client_confirmed INTEGER DEFAULT 0")

            if "completed_by_id" not in visits_columns:
                cursor.execute("ALTER TABLE visits ADD COLUMN completed_by_id TEXT DEFAULT ''")

            # ===== REQUESTS TABLE =====
            cursor.execute("PRAGMA table_info(requests)")
            requests_columns = {row[1] for row in cursor.fetchall()}

            # Phase 5: Enhanced request fields (contact information)
            if "company_name" not in requests_columns:
                cursor.execute("ALTER TABLE requests ADD COLUMN company_name TEXT DEFAULT ''")

            if "contact_name" not in requests_columns:
                cursor.execute("ALTER TABLE requests ADD COLUMN contact_name TEXT DEFAULT ''")

            if "email" not in requests_columns:
                cursor.execute("ALTER TABLE requests ADD COLUMN email TEXT DEFAULT ''")

            if "phone" not in requests_columns:
                cursor.execute("ALTER TABLE requests ADD COLUMN phone TEXT DEFAULT ''")

            # ===== EXPENSES TABLE =====
            cursor.execute("PRAGMA table_info(expenses)")
            expenses_columns = {row[1] for row in cursor.fetchall()}

            # Phase 5: Enhanced expense fields (tracking metadata)
            if "entered_by_id" not in expenses_columns:
                cursor.execute("ALTER TABLE expenses ADD COLUMN entered_by_id TEXT DEFAULT ''")

            if "paid_by_id" not in expenses_columns:
                cursor.execute("ALTER TABLE expenses ADD COLUMN paid_by_id TEXT DEFAULT ''")

            if "reimbursable_to_id" not in expenses_columns:
                cursor.execute("ALTER TABLE expenses ADD COLUMN reimbursable_to_id TEXT DEFAULT ''")

            # ===== USERS TABLE =====
            cursor.execute("PRAGMA table_info(users)")
            users_columns = {row[1] for row in cursor.fetchall()}

            # Phase 4: Enhanced user fields
            if "available_for_scheduling" not in users_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN available_for_scheduling INTEGER DEFAULT 0")

            if "assigned_color" not in users_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN assigned_color TEXT DEFAULT ''")

            # ===== MIGRATION_STATE TABLE =====
            cursor.execute("PRAGMA table_info(migration_state)")
            migration_state_columns = {row[1] for row in cursor.fetchall()}

            if "total_fetched" not in migration_state_columns:
                cursor.execute("ALTER TABLE migration_state ADD COLUMN total_fetched INTEGER DEFAULT 0")

            if "sync_status" not in migration_state_columns:
                cursor.execute("ALTER TABLE migration_state ADD COLUMN sync_status TEXT DEFAULT 'pending'")

            if "last_sync_at" not in migration_state_columns:
                cursor.execute("ALTER TABLE migration_state ADD COLUMN last_sync_at TEXT")

            # ===== ATTACHMENTS TABLE =====
            cursor.execute("PRAGMA table_info(attachments)")
            attachments_columns = {row[1] for row in cursor.fetchall()}

            if "download_status" not in attachments_columns:
                cursor.execute("ALTER TABLE attachments ADD COLUMN download_status TEXT DEFAULT 'pending'")

            if "download_error" not in attachments_columns:
                cursor.execute("ALTER TABLE attachments ADD COLUMN download_error TEXT")

            if "downloaded_at" not in attachments_columns:
                cursor.execute("ALTER TABLE attachments ADD COLUMN downloaded_at TEXT")

            if "hash" not in attachments_columns:
                cursor.execute("ALTER TABLE attachments ADD COLUMN hash TEXT")

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
                    created_at TEXT DEFAULT (datetime('now')),
                    maximum_available INTEGER,
                    currently_available INTEGER,
                    restore_rate INTEGER
                )
            """
            cursor.execute(graphql_costs_schema)

            # Add throttle status columns if they don't exist (migration for existing databases)
            try:
                cursor.execute("SELECT maximum_available FROM graphql_costs LIMIT 1")
            except sqlite3.OperationalError:
                # Columns don't exist, add them
                cursor.execute("ALTER TABLE graphql_costs ADD COLUMN maximum_available INTEGER")
                cursor.execute("ALTER TABLE graphql_costs ADD COLUMN currently_available INTEGER")
                cursor.execute("ALTER TABLE graphql_costs ADD COLUMN restore_rate INTEGER")

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
                    company_name TEXT DEFAULT '',
                    contact_name TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
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
                    entered_by_id TEXT DEFAULT '',
                    paid_by_id TEXT DEFAULT '',
                    reimbursable_to_id TEXT DEFAULT '',
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

            # Create migration_state table for tracking cursor positions per entity type
            migration_state_schema = """
                CREATE TABLE IF NOT EXISTS migration_state (
                    entity_type TEXT PRIMARY KEY,
                    last_cursor TEXT,
                    updated_at TEXT NOT NULL
                )
            """
            cursor.execute(migration_state_schema)

            # Create indexes for foreign keys to improve query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_properties_client_id ON properties(client_id)")  # noqa: E501
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_client_id ON jobs(client_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_property_id ON jobs(property_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_quote_id ON jobs(quote_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_client_id ON requests(client_id)")  # noqa: E501
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_property_id ON requests(property_id)")  # noqa: E501
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_converted_to_quote_id ON requests(converted_to_quote_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_requests_converted_to_job_id ON requests(converted_to_job_id)"  # noqa: E501
            )

            # Also add indexes for existing foreign keys if not already present
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_client_id ON invoices(client_id)")  # noqa: E501
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_quotes_client_id ON quotes(client_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_id)")  # noqa: E501
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachments_note_id ON attachments(note_id)")  # noqa: E501
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_note_references_entity ON note_references(entity_type, entity_id)"  # noqa: E501
            )

            # Add indexes for new entity foreign keys
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_expenses_job_id ON expenses(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_visits_job_id ON visits(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_visits_client_id ON visits(client_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_visits_property_id ON visits(property_id)")  # noqa: E501
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

            # Create map_snapshot table for tracking map pass execution metadata
            map_snapshot_schema = """
                CREATE TABLE IF NOT EXISTS map_snapshot (
                    id TEXT PRIMARY KEY,
                    label TEXT,
                    created_at TEXT NOT NULL,
                    entities_included TEXT,
                    pass1_cutoff TEXT NOT NULL
                )
            """
            cursor.execute(map_snapshot_schema)

            # Create entity_inventory table for map mode discovery
            entity_inventory_schema = """
                CREATE TABLE IF NOT EXISTS entity_inventory (
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    updated_at TEXT,
                    discovered_at TEXT NOT NULL,
                    estimated_relations_json TEXT,
                    map_snapshot_id TEXT NOT NULL,
                    PRIMARY KEY (entity_type, entity_id, map_snapshot_id),
                    FOREIGN KEY (map_snapshot_id) REFERENCES map_snapshot(id) ON DELETE CASCADE
                )
            """
            cursor.execute(entity_inventory_schema)

            # Create relation_inventory table for tracking relation counts
            relation_inventory_schema = """
                CREATE TABLE IF NOT EXISTS relation_inventory (
                    parent_type TEXT NOT NULL,
                    parent_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    cursor_hint TEXT,
                    map_snapshot_id TEXT NOT NULL,
                    PRIMARY KEY (parent_type, parent_id, relation_type, map_snapshot_id),
                    FOREIGN KEY (map_snapshot_id) REFERENCES map_snapshot(id) ON DELETE CASCADE
                )
            """
            cursor.execute(relation_inventory_schema)

            # Create extract_queue table for tracking entity extraction status
            extract_queue_schema = """
                CREATE TABLE IF NOT EXISTS extract_queue (
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_error TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    map_snapshot_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (entity_type, entity_id, map_snapshot_id),
                    FOREIGN KEY (map_snapshot_id) REFERENCES map_snapshot(id) ON DELETE CASCADE
                )
            """
            cursor.execute(extract_queue_schema)

            # Create attachment_queue table for tracking attachment download status
            attachment_queue_schema = """
                CREATE TABLE IF NOT EXISTS attachment_queue (
                    parent_type TEXT NOT NULL,
                    parent_id TEXT NOT NULL,
                    attachment_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_error TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    map_snapshot_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (attachment_id, map_snapshot_id),
                    FOREIGN KEY (map_snapshot_id) REFERENCES map_snapshot(id) ON DELETE CASCADE
                )
            """
            cursor.execute(attachment_queue_schema)

            # Create indexes for multi-pass migration tables
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_inventory_snapshot ON entity_inventory(map_snapshot_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_inventory_type ON entity_inventory(entity_type)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relation_inventory_snapshot ON relation_inventory(map_snapshot_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_extract_queue_snapshot ON extract_queue(map_snapshot_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_extract_queue_status ON extract_queue(map_snapshot_id, status)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachment_queue_snapshot ON attachment_queue(map_snapshot_id)"  # noqa: E501
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachment_queue_status ON attachment_queue(map_snapshot_id, status)"  # noqa: E501
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
    ) -> Optional[Union[Client, Invoice, Quote, Note, Attachment, Job, Property, Request]]:
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
                    client.company_name,
                    client.balance_cents,
                    client.is_archivable,
                    client.is_company,
                    client.billing_street,
                    client.billing_city,
                    client.billing_province,
                    client.billing_postal_code,
                    client.billing_country,
                )
                for client in clients
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO clients
                   (id, first_name, last_name, email, phone, created_at, additional_emails, additional_phones,
                    company_name, balance_cents, is_archivable, is_company,
                    billing_street, billing_city, billing_province, billing_postal_code, billing_country)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
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
                    quote.property_id,
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
                   (id, client_id, property_id, quote_number, title, total, subtotal, disclaimer, line_items, created_at, transitioned_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
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
                    attachment.download_status,
                    attachment.hash,
                    attachment.downloaded_at,
                    attachment.download_error,
                )
                for attachment in attachments
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO attachments
                   (id, note_id, file_name, content_type, original_url, local_file_path, file_size, created_at,
                    download_status, hash, downloaded_at, download_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                """SELECT id, note_id, file_name, content_type, original_url, local_file_path, file_size, created_at,
                          download_status, hash, downloaded_at, download_error
                   FROM attachments ORDER BY id"""
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
                    download_status=row[8] or "pending",
                    hash=row[9],
                    downloaded_at=row[10],
                    download_error=row[11],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all attachments: {e}") from e

    def get_pending_attachments(self, entity_types: Optional[List[str]] = None) -> List[Attachment]:
        """Retrieve attachments with pending download status.

        Filters attachments that need to be downloaded (download_status='pending').
        Optionally filters by parent entity types via note relationships.

        Args:
            entity_types: Optional list of entity types to filter by (e.g., ['client', 'job'])
                         Filters via note.entity_type relationship

        Returns:
            List of Attachment entities with download_status='pending'

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if entity_types:
                # Join with notes table to filter by entity type
                placeholders = ",".join("?" * len(entity_types))
                query = f"""
                    SELECT a.id, a.note_id, a.file_name, a.content_type, a.original_url,
                           a.local_file_path, a.file_size, a.created_at,
                           a.download_status, a.hash, a.downloaded_at, a.download_error
                    FROM attachments a
                    JOIN notes n ON a.note_id = n.id
                    WHERE a.download_status = 'pending'
                      AND n.entity_type IN ({placeholders})
                    ORDER BY a.id
                """
                cursor.execute(query, entity_types)
            else:
                # Get all pending attachments
                cursor.execute(
                    """SELECT id, note_id, file_name, content_type, original_url, local_file_path,
                              file_size, created_at, download_status, hash, downloaded_at, download_error
                       FROM attachments
                       WHERE download_status = 'pending'
                       ORDER BY id"""
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
                    download_status=row[8] or "pending",
                    hash=row[9],
                    downloaded_at=row[10],
                    download_error=row[11],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve pending attachments: {e}") from e

    def get_attachment_by_id(self, attachment_id: str) -> Optional[Attachment]:
        """Retrieve a single attachment by ID.

        Args:
            attachment_id: Unique identifier of the attachment

        Returns:
            Attachment entity if found, None otherwise

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                """SELECT id, note_id, file_name, content_type, original_url, local_file_path, file_size, created_at,
                          download_status, hash, downloaded_at, download_error
                   FROM attachments WHERE id = ?""",
                (attachment_id,),
            )
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return None

            return Attachment(
                id=row[0],
                note_id=row[1],
                file_name=row[2],
                content_type=row[3],
                original_url=row[4],
                local_file_path=row[5],
                file_size=row[6],
                created_at=row[7],
                download_status=row[8] or "pending",
                hash=row[9],
                downloaded_at=row[10],
                download_error=row[11],
            )

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve attachment {attachment_id}: {e}") from e

    def update_attachment_download(
        self,
        attachment_id: str,
        local_file_path: Optional[str] = None,
        hash: Optional[str] = None,
        download_status: Optional[str] = None,
        downloaded_at: Optional[str] = None,
        download_error: Optional[str] = None,
    ) -> None:
        """Update attachment download tracking fields after download completion.

        Supports partial updates using COALESCE - only provided fields are updated,
        NULL values preserve existing data. This enables incremental status updates
        during multi-step download processes.

        Args:
            attachment_id: Attachment ID to update
            local_file_path: Local file system path where file was downloaded
            hash: SHA256 hash of downloaded file content
            download_status: Download status ('pending', 'completed', 'failed')
            downloaded_at: ISO8601 timestamp when download completed
            download_error: Error message if download failed

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                """UPDATE attachments
                   SET local_file_path = COALESCE(?, local_file_path),
                       hash = COALESCE(?, hash),
                       download_status = COALESCE(?, download_status),
                       downloaded_at = COALESCE(?, downloaded_at),
                       download_error = COALESCE(?, download_error)
                   WHERE id = ?""",
                (local_file_path, hash, download_status, downloaded_at, download_error, attachment_id),
            )
            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to update attachment {attachment_id}: {e}") from e

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
                if all([ref.get("note_id"), ref.get("entity_type"), ref.get("entity_id")])
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

    def get_note_references(self, limit: int = 1000, offset: int = 0) -> List[dict[str, str]]:
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

    def get_note_references_cursor_based(self, limit: int = 1000, last_id: int = 0) -> tuple[List[dict[str, str]], int]:
        """Retrieve note references using cursor-based pagination for better performance.

        Uses cursor-based pagination with 'WHERE id > last_id' instead of OFFSET,
        providing O(log n) performance instead of O(n) for large datasets.

        Args:
            limit: Maximum number of references to retrieve (default: 1000)
            last_id: ID of the last processed record (default: 0)

        Returns:
            Tuple of (list of references, last_id for next batch)

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                """SELECT id, note_id, entity_type, entity_id
                   FROM note_references
                   WHERE id > ?
                   ORDER BY id
                   LIMIT ?""",
                (last_id, limit),
            )
            rows = cursor.fetchall()
            cursor.close()

            references = [
                {
                    "note_id": row[1],
                    "entity_type": row[2],
                    "entity_id": row[3],
                }
                for row in rows
            ]

            # Get the last ID for next batch
            next_last_id = rows[-1][0] if rows else last_id

            return references, next_last_id

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

    def save_oauth_tokens(self, access_token: str, refresh_token: str, expires_at: str) -> None:
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

    def refresh_oauth_token_transactionally(
        self,
        old_refresh_token: str,
        refresh_callback: Callable[[str], dict[str, str]],
    ) -> dict[str, str]:
        """
        Refresh OAuth token transactionally to prevent race conditions.

        This method executes the refresh operation within an exclusive transaction
        to ensure that only one process refreshes the token at a time.

        Args:
            old_refresh_token: The refresh token currently held by the caller
            refresh_callback: Function to call to perform the actual refresh if needed.
                            Should accept (refresh_token) and return new token dict.

        Returns:
            dict: The valid token data (either newly refreshed or existing if already refreshed)
        """
        cursor = self._connection.cursor()
        try:
            # 1. Begin EXCLUSIVE transaction to lock the database
            cursor.execute("BEGIN EXCLUSIVE")

            # 2. Read current token state
            cursor.execute("SELECT access_token, refresh_token, expires_at FROM oauth_tokens LIMIT 1")
            row = cursor.fetchone()

            if not row:
                # No tokens found - cannot refresh
                self._connection.rollback()
                raise RepositoryError("No OAuth tokens found in database")

            current_access_token = row[0]
            current_refresh_token = row[1]
            current_expires_at = row[2]

            # 3. Check if token has already been refreshed by another process
            if current_refresh_token != old_refresh_token:
                # Token has changed! Return the new token immediately
                self._connection.commit()
                return {
                    "access_token": current_access_token,
                    "refresh_token": current_refresh_token,
                    "expires_at": current_expires_at,
                }

            # 4. Token matches old one, so we need to refresh it
            try:
                # Call the callback to perform the API request
                # Note: This is done inside the transaction lock, which is necessary
                # to prevent other processes from starting a refresh, but keeps the lock
                # held during the network request. This is a trade-off for correctness.
                new_tokens = refresh_callback(old_refresh_token)

                # Calculate new expiration
                # Handle missing expires_in field (Jobber API doesn't always include it)
                expires_in = new_tokens.get("expires_in", 3600)  # Default to 1 hour

                from datetime import datetime, timezone, timedelta

                expires_at_datetime = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                new_expires_at = expires_at_datetime.isoformat()

                # 5. Save new tokens
                cursor.execute("DELETE FROM oauth_tokens")
                cursor.execute(
                    """INSERT INTO oauth_tokens
                       (access_token, refresh_token, expires_at, created_at)
                       VALUES (?, ?, ?, datetime('now'))""",
                    (
                        new_tokens["access_token"],
                        new_tokens["refresh_token"],
                        new_expires_at,
                    ),
                )

                self._connection.commit()

                return {
                    "access_token": new_tokens["access_token"],
                    "refresh_token": new_tokens["refresh_token"],
                    "expires_at": new_expires_at,
                }

            except Exception as e:
                # If refresh fails, rollback and re-raise
                self._connection.rollback()
                raise e

        except Exception as e:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise RepositoryError(f"Transactional token refresh failed: {e}") from e
        finally:
            cursor.close()

    def save_graphql_costs(self, costs: List[dict]) -> None:
        """Batch save GraphQL cost data to the database.

        Stores GraphQL query complexity cost measurements for analysis and optimization.
        Uses batch insert for efficiency with large volumes of cost tracking data.

        Args:
            costs: List of dicts with query_type, batch_size, requested_cost,
                   actual_cost, cost_difference, timestamp, created_at, and optional
                   throttle status fields (maximum_available, currently_available, restore_rate)

        Raises:
            RepositoryError: If database operation fails
        """
        if not costs:
            return

        try:
            cursor = self._connection.cursor()

            # Prepare data tuples for executemany
            cost_data = [
                (
                    cost.get("query_type"),
                    cost.get("batch_size"),
                    cost.get("requested_cost"),
                    cost.get("actual_cost"),
                    cost.get("cost_difference"),
                    cost.get("timestamp"),
                    cost.get("created_at"),
                    cost.get("maximum_available"),
                    cost.get("currently_available"),
                    cost.get("restore_rate"),
                )
                for cost in costs
                if all(
                    [
                        cost.get("query_type"),
                        cost.get("batch_size") is not None,
                        cost.get("requested_cost") is not None,
                        cost.get("actual_cost") is not None,
                        cost.get("cost_difference") is not None,
                        cost.get("timestamp") is not None,
                        cost.get("created_at"),
                    ]
                )
            ]

            if cost_data:
                cursor.executemany(
                    """INSERT INTO graphql_costs
                       (query_type, batch_size, requested_cost, actual_cost, cost_difference,
                        timestamp, created_at, maximum_available, currently_available, restore_rate)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # noqa: E501
                    cost_data,
                )

                self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save GraphQL costs: {e}") from e

    def get_all_graphql_costs(self) -> List[GraphQLCost]:
        """Retrieve all GraphQL cost records from the database.

        Returns:
            List of all GraphQLCost entities with throttle status

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute(
                """SELECT id, query_type, batch_size, requested_cost, actual_cost, cost_difference,
                          timestamp, created_at, maximum_available, currently_available, restore_rate
                   FROM graphql_costs ORDER BY timestamp"""  # noqa: E501
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                GraphQLCost(
                    id=row[0],
                    query_type=row[1],
                    batch_size=row[2],
                    requested_cost=row[3],
                    actual_cost=row[4],
                    cost_difference=row[5],
                    timestamp=row[6],
                    created_at=row[7],
                    maximum_available=row[8],
                    currently_available=row[9],
                    restore_rate=row[10],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to retrieve all GraphQL costs: {e}") from e

    def entity_exists(self, table_name: str, entity_id: str) -> bool:
        """Check if an entity exists in the specified table using fast primary key lookup.

        Uses SELECT 1 FROM {table} WHERE id = ? LIMIT 1 pattern for O(log n) performance.
        This method provides fast existence checking for skip logic during migrations.

        Args:
            table_name: Name of the table to check (e.g., 'clients', 'invoices')
            entity_id: Primary key ID of the entity to check

        Returns:
            True if entity exists, False otherwise

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            # Use parameterized query for security and direct primary key lookup for performance
            cursor.execute(f"SELECT 1 FROM {table_name} WHERE id = ? LIMIT 1", (entity_id,))
            result = cursor.fetchone()
            cursor.close()

            return result is not None

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to check entity existence in {table_name}: {e}") from e

    def save_migration_state(
        self,
        entity_type: str,
        last_cursor: Optional[str] = None,
        total_fetched: int = 0,
        sync_status: str = "in_progress",
    ) -> None:
        """Save migration state for cursor-based resumption with progress tracking.

        Stores the last processed cursor position, total fetched count, and sync status
        for the specified entity type. Supports Phase 7's resumable extraction pattern
        where migrations can be interrupted and resumed without re-processing data.

        Args:
            entity_type: Type of entity being migrated (e.g., 'clients', 'invoices')
            last_cursor: Last processed cursor position, None if starting fresh or completed
            total_fetched: Total number of records fetched so far (default: 0)
            sync_status: Current sync status - 'pending', 'in_progress', 'completed', 'error'

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            cursor.execute(
                """INSERT OR REPLACE INTO migration_state
                   (entity_type, last_cursor, updated_at, total_fetched, sync_status, last_sync_at)
                   VALUES (?, ?, datetime('now'), ?, ?, datetime('now'))""",
                (entity_type, last_cursor, total_fetched, sync_status),
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save migration state for {entity_type}: {e}") from e

    def get_migration_state(self, entity_type: str) -> Optional[MigrationState]:
        """Retrieve migration state for the specified entity type.

        Gets the last processed cursor position, total fetched count, and sync status
        for resuming migrations from the last checkpoint.

        Args:
            entity_type: Type of entity to get state for (e.g., 'clients', 'invoices')

        Returns:
            MigrationState instance with all tracking fields if found, None if no state exists

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            cursor.execute(
                """SELECT entity_type, last_cursor, updated_at, total_fetched, sync_status, last_sync_at
                   FROM migration_state WHERE entity_type = ?""",
                (entity_type,),
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                return MigrationState(
                    entity_type=row[0],
                    last_cursor=row[1],
                    updated_at=row[2],
                    total_fetched=row[3] or 0,
                    sync_status=row[4] or "pending",
                    last_sync_at=row[5],
                )

            return None

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get migration state for {entity_type}: {e}") from e

    # Multi-pass migration methods

    def save_map_snapshot(self, snapshot: MapSnapshot) -> None:
        """Save a map snapshot to the database.

        Stores map pass execution metadata for later extract pass targeting.
        Uses INSERT OR REPLACE for upsert behavior.

        Args:
            snapshot: MapSnapshot instance to save

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            cursor.execute(
                """INSERT OR REPLACE INTO map_snapshot
                   (id, label, created_at, entities_included, pass1_cutoff)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    snapshot.id,
                    snapshot.label,
                    snapshot.created_at,
                    snapshot.entities_included,
                    snapshot.pass1_cutoff,
                ),
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save map snapshot {snapshot.id}: {e}") from e

    def get_map_snapshot(self, snapshot_id: str) -> Optional[MapSnapshot]:
        """Retrieve a map snapshot by ID or label.

        Args:
            snapshot_id: Snapshot ID or label to retrieve

        Returns:
            MapSnapshot instance if found, None otherwise

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            # Try by ID first, then by label
            cursor.execute(
                """SELECT id, label, created_at, entities_included, pass1_cutoff
                   FROM map_snapshot
                   WHERE id = ? OR label = ?
                   LIMIT 1""",
                (snapshot_id, snapshot_id),
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                return MapSnapshot(
                    id=row[0], label=row[1], created_at=row[2], entities_included=row[3], pass1_cutoff=row[4]
                )

            return None

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get map snapshot {snapshot_id}: {e}") from e

    def list_map_snapshots(self) -> List[MapSnapshot]:
        """List all map snapshots ordered by creation date (newest first).

        Returns:
            List of MapSnapshot instances

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            cursor.execute(
                """SELECT id, label, created_at, entities_included, pass1_cutoff
                   FROM map_snapshot
                   ORDER BY created_at DESC"""
            )
            rows = cursor.fetchall()
            cursor.close()

            return [
                MapSnapshot(id=row[0], label=row[1], created_at=row[2], entities_included=row[3], pass1_cutoff=row[4])
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to list map snapshots: {e}") from e

    def save_entity_inventory(self, inventory: List[EntityInventory]) -> None:
        """Batch save entity inventory records from map pass.

        Args:
            inventory: List of EntityInventory instances to save

        Raises:
            RepositoryError: If batch operation fails
        """
        if not inventory:
            return

        try:
            cursor = self._connection.cursor()

            inventory_data = [
                (
                    item.entity_type,
                    item.entity_id,
                    item.updated_at,
                    item.discovered_at,
                    item.estimated_relations_json,
                    item.map_snapshot_id,
                )
                for item in inventory
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO entity_inventory
                   (entity_type, entity_id, updated_at, discovered_at, estimated_relations_json, map_snapshot_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                inventory_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save entity inventory batch: {e}") from e

    def get_entity_inventory(self, snapshot_id: str, entity_type: Optional[str] = None) -> List[EntityInventory]:
        """Retrieve entity inventory for a snapshot, optionally filtered by entity type.

        Args:
            snapshot_id: Map snapshot ID to retrieve inventory for
            entity_type: Optional entity type filter (e.g., 'clients')

        Returns:
            List of EntityInventory instances

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if entity_type:
                cursor.execute(
                    """SELECT entity_type, entity_id, updated_at, discovered_at,
                              estimated_relations_json, map_snapshot_id
                       FROM entity_inventory
                       WHERE map_snapshot_id = ? AND entity_type = ?
                       ORDER BY entity_id""",
                    (snapshot_id, entity_type),
                )
            else:
                cursor.execute(
                    """SELECT entity_type, entity_id, updated_at, discovered_at,
                              estimated_relations_json, map_snapshot_id
                       FROM entity_inventory
                       WHERE map_snapshot_id = ?
                       ORDER BY entity_type, entity_id""",
                    (snapshot_id,),
                )

            rows = cursor.fetchall()
            cursor.close()

            return [
                EntityInventory(
                    entity_type=row[0],
                    entity_id=row[1],
                    updated_at=row[2],
                    discovered_at=row[3],
                    estimated_relations_json=row[4],
                    map_snapshot_id=row[5],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get entity inventory for snapshot {snapshot_id}: {e}") from e

    def save_relation_inventory(self, inventory: List[dict]) -> None:
        """Batch save relation inventory records from map pass.

        Args:
            inventory: List of dicts with keys: parent_type, parent_id, relation_type,
                      count, cursor_hint, map_snapshot_id

        Raises:
            RepositoryError: If batch operation fails
        """
        if not inventory:
            return

        try:
            cursor = self._connection.cursor()

            inventory_data = [
                (
                    item["parent_type"],
                    item["parent_id"],
                    item["relation_type"],
                    item["count"],
                    item.get("cursor_hint"),
                    item["map_snapshot_id"],
                )
                for item in inventory
            ]

            cursor.executemany(
                """INSERT OR REPLACE INTO relation_inventory
                   (parent_type, parent_id, relation_type, count, cursor_hint, map_snapshot_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                inventory_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to save relation inventory batch: {e}") from e

    def create_extract_queue(self, snapshot_id: str, entity_type: str) -> None:
        """Create extract queue from entity inventory for a specific entity type.

        Populates the extract_queue table with pending items from entity_inventory.

        Args:
            snapshot_id: Map snapshot ID to create queue from
            entity_type: Entity type to create queue for (e.g., 'clients')

        Raises:
            RepositoryError: If queue creation fails
        """
        try:
            cursor = self._connection.cursor()

            cursor.execute(
                """INSERT OR IGNORE INTO extract_queue
                   (entity_type, entity_id, status, map_snapshot_id, updated_at)
                   SELECT entity_type, entity_id, 'pending', map_snapshot_id, datetime('now')
                   FROM entity_inventory
                   WHERE map_snapshot_id = ? AND entity_type = ?""",
                (snapshot_id, entity_type),
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to create extract queue for {entity_type}: {e}") from e

    def get_extract_queue(
        self, snapshot_id: str, entity_type: str, status: Optional[str] = None
    ) -> List[ExtractQueueItem]:
        """Retrieve extract queue items for a snapshot and entity type.

        Args:
            snapshot_id: Map snapshot ID
            entity_type: Entity type (e.g., 'clients')
            status: Optional status filter ('pending', 'in_progress', 'done', 'failed')

        Returns:
            List of ExtractQueueItem instances

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if status:
                cursor.execute(
                    """SELECT entity_type, entity_id, status, last_error, attempt_count,
                              map_snapshot_id, updated_at
                       FROM extract_queue
                       WHERE map_snapshot_id = ? AND entity_type = ? AND status = ?
                       ORDER BY entity_id""",
                    (snapshot_id, entity_type, status),
                )
            else:
                cursor.execute(
                    """SELECT entity_type, entity_id, status, last_error, attempt_count,
                              map_snapshot_id, updated_at
                       FROM extract_queue
                       WHERE map_snapshot_id = ? AND entity_type = ?
                       ORDER BY entity_id""",
                    (snapshot_id, entity_type),
                )

            rows = cursor.fetchall()
            cursor.close()

            return [
                ExtractQueueItem(
                    entity_type=row[0],
                    entity_id=row[1],
                    status=row[2],
                    map_snapshot_id=row[5],
                    updated_at=row[6],
                    last_error=row[3],
                    attempt_count=row[4],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get extract queue for {entity_type}: {e}") from e

    def update_queue_status(self, queue_item: ExtractQueueItem) -> None:
        """Update extract queue item status.

        Args:
            queue_item: ExtractQueueItem with updated status

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            cursor.execute(
                """UPDATE extract_queue
                   SET status = ?, last_error = ?, attempt_count = ?, updated_at = datetime('now')
                   WHERE entity_type = ? AND entity_id = ? AND map_snapshot_id = ?""",
                (
                    queue_item.status,
                    queue_item.last_error,
                    queue_item.attempt_count,
                    queue_item.entity_type,
                    queue_item.entity_id,
                    queue_item.map_snapshot_id,
                ),
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(
                f"Failed to update queue status for {queue_item.entity_type}/{queue_item.entity_id}: {e}"
            ) from e

    def create_attachment_queue(self, snapshot_id: str, attachments: List[dict]) -> None:
        """Create attachment download queue from discovered attachments.

        Args:
            snapshot_id: Map snapshot ID
            attachments: List of dicts with keys: attachment_id, parent_type, parent_id

        Raises:
            RepositoryError: If batch operation fails
        """
        if not attachments:
            return

        try:
            cursor = self._connection.cursor()

            attachment_data = [
                (item["parent_type"], item["parent_id"], item["attachment_id"], "pending", snapshot_id)
                for item in attachments
            ]

            cursor.executemany(
                """INSERT OR IGNORE INTO attachment_queue
                   (parent_type, parent_id, attachment_id, status, map_snapshot_id, updated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                attachment_data,
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to create attachment queue: {e}") from e

    def get_attachment_queue(self, snapshot_id: str, status: Optional[str] = None) -> List[AttachmentQueueItem]:
        """Retrieve attachment queue items for a snapshot.

        Args:
            snapshot_id: Map snapshot ID
            status: Optional status filter ('pending', 'in_progress', 'done', 'failed')

        Returns:
            List of AttachmentQueueItem instances

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            if status:
                cursor.execute(
                    """SELECT attachment_id, parent_type, parent_id, status, last_error,
                              attempt_count, map_snapshot_id, updated_at
                       FROM attachment_queue
                       WHERE map_snapshot_id = ? AND status = ?
                       ORDER BY attachment_id""",
                    (snapshot_id, status),
                )
            else:
                cursor.execute(
                    """SELECT attachment_id, parent_type, parent_id, status, last_error,
                              attempt_count, map_snapshot_id, updated_at
                       FROM attachment_queue
                       WHERE map_snapshot_id = ?
                       ORDER BY attachment_id""",
                    (snapshot_id,),
                )

            rows = cursor.fetchall()
            cursor.close()

            return [
                AttachmentQueueItem(
                    attachment_id=row[0],
                    parent_type=row[1],
                    parent_id=row[2],
                    status=row[3],
                    map_snapshot_id=row[6],
                    updated_at=row[7],
                    last_error=row[4],
                    attempt_count=row[5],
                )
                for row in rows
            ]

        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get attachment queue: {e}") from e

    def update_attachment_queue_status(self, queue_item: AttachmentQueueItem) -> None:
        """Update attachment queue item status.

        Args:
            queue_item: AttachmentQueueItem with updated status

        Raises:
            RepositoryError: If database operation fails
        """
        try:
            cursor = self._connection.cursor()

            cursor.execute(
                """UPDATE attachment_queue
                   SET status = ?, last_error = ?, attempt_count = ?, updated_at = datetime('now')
                   WHERE attachment_id = ? AND map_snapshot_id = ?""",
                (
                    queue_item.status,
                    queue_item.last_error,
                    queue_item.attempt_count,
                    queue_item.attachment_id,
                    queue_item.map_snapshot_id,
                ),
            )

            self._connection.commit()
            cursor.close()

        except sqlite3.Error as e:
            raise RepositoryError(
                f"Failed to update attachment queue status for {queue_item.attachment_id}: {e}"
            ) from e
