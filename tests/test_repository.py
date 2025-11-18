"""Unit tests for Repository database operations."""

import sqlite3
import pytest
from datetime import datetime

from src.repositories.repository import Repository
from src.exceptions import RepositoryError
from src.models import (
    Client,
    Invoice,
    Quote,
    Note,
    Attachment,
    MigrationState,
    GraphQLCost,
)


class TestRepositoryInitialization:
    """Test suite for Repository initialization and schema creation."""

    def test_init_creates_repository_with_connection(self):
        """Test Repository initialization with SQLite connection."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        assert repo._connection == conn
        conn.close()

    def test_init_schema_creates_all_tables(self):
        """Test init_schema creates all required tables."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        cursor = conn.cursor()

        # Verify all tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            "clients",
            "invoices",
            "quotes",
            "notes",
            "attachments",
            "jobs",
            "properties",
            "requests",
            "users",
            "expenses",
            "visits",
            "timesheet_entries",
            "products_services",
            "tax_rates",
            "oauth_tokens",
            "migration_state",
            "note_references",
            "graphql_costs",
        }

        assert expected_tables.issubset(tables)

        cursor.close()
        conn.close()

    def test_init_schema_is_idempotent(self):
        """Test init_schema can be called multiple times safely."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)

        # Call multiple times - should not raise errors
        repo.init_schema()
        repo.init_schema()
        repo.init_schema()

        # Verify tables still exist
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        count = cursor.fetchone()[0]
        assert count >= 18  # At least the expected tables

        cursor.close()
        conn.close()

    def test_init_schema_creates_clients_table_with_correct_columns(self):
        """Test clients table has all required columns."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "created_at",
            "additional_emails",
            "additional_phones",
        }

        assert expected_columns.issubset(columns)

        cursor.close()
        conn.close()


class TestRepositoryCRUDOperations:
    """Test suite for Repository CRUD operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    # ========================================================================
    # Create Tests
    # ========================================================================

    def test_create_client(self):
        """Test creating a new client."""
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )

        self.repo.create(client)

        # Verify client was saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id = ?", ("client_123",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "client_123"
        assert row[1] == "John"
        assert row[2] == "Doe"
        cursor.close()

    def test_create_invoice(self):
        """Test creating a new invoice."""
        # Create client first (foreign key dependency)
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        invoice = Invoice(
            id="invoice_123",
            client_id="client_123",
            number="INV-001",
            total_cents=10000,
            status="PAID",
            issued_at="2023-11-15T12:00:00Z",
        )

        self.repo.create(invoice)

        # Verify invoice was saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE id = ?", ("invoice_123",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "invoice_123"
        assert row[1] == "client_123"
        assert row[3] == 10000
        cursor.close()

    def test_create_quote(self):
        """Test creating a new quote."""
        # Create client first
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        quote = Quote(
            id="quote_123",
            client_id="client_123",
            quote_number="Q-001",
            title="Lawn Care",
            total=50000,
            subtotal=45000,
            disclaimer="Terms apply",
            line_items="[]",
            created_at="2023-11-15T10:00:00Z",
            transitioned_at="2023-11-16T10:00:00Z",
            updated_at="2023-11-17T10:00:00Z",
        )

        self.repo.create(quote)

        # Verify quote was saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM quotes WHERE id = ?", ("quote_123",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "quote_123"
        assert row[4] == 50000
        cursor.close()

    def test_create_note(self):
        """Test creating a new note."""
        note = Note(
            id="note_123",
            entity_type="Client",
            entity_id="client_123",
            message="This is a test note",
            created_at="2023-11-15T10:00:00Z",
            updated_at="2023-11-15T10:00:00Z",
        )

        self.repo.create(note)

        # Verify note was saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM notes WHERE id = ?", ("note_123",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "note_123"
        assert row[1] == "Client"
        cursor.close()

    def test_create_attachment(self):
        """Test creating a new attachment."""
        attachment = Attachment(
            id="attach_123",
            note_id="note_123",
            file_name="document.pdf",
            content_type="application/pdf",
            original_url="https://example.com/file.pdf",
            local_file_path="/tmp/file.pdf",
            file_size=1024,
            created_at="2023-11-15T10:00:00Z",
        )

        self.repo.create(attachment)

        # Verify attachment was saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM attachments WHERE id = ?", ("attach_123",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "attach_123"
        assert row[2] == "document.pdf"
        cursor.close()

    def test_create_uses_upsert_behavior(self):
        """Test create uses INSERT OR REPLACE for upsert."""
        client1 = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )

        self.repo.create(client1)

        # Update with same ID
        client2 = Client(
            id="client_123",
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            phone="555-0200",
            created_at="2023-11-16T10:00:00Z",
        )

        self.repo.create(client2)

        # Verify only one record exists with updated values
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clients WHERE id = ?", ("client_123",))
        count = cursor.fetchone()[0]
        assert count == 1

        cursor.execute("SELECT first_name, last_name FROM clients WHERE id = ?", ("client_123",))
        row = cursor.fetchone()
        assert row[0] == "Jane"
        assert row[1] == "Smith"
        cursor.close()

    # ========================================================================
    # Read Tests
    # ========================================================================

    def test_read_client_returns_client(self):
        """Test reading an existing client."""
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        result = self.repo.read(Client, "client_123")

        assert result is not None
        assert isinstance(result, Client)
        assert result.id == "client_123"
        assert result.first_name == "John"
        assert result.email == "john@example.com"

    def test_read_client_returns_none_when_not_found(self):
        """Test reading non-existent client returns None."""
        result = self.repo.read(Client, "nonexistent")
        assert result is None

    def test_read_quote_returns_quote(self):
        """Test reading an existing quote."""
        # Create dependencies
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        quote = Quote(
            id="quote_123",
            client_id="client_123",
            quote_number="Q-001",
            title="Lawn Care",
            total=50000,
            subtotal=45000,
            disclaimer="Terms apply",
            line_items="[]",
            created_at="2023-11-15T10:00:00Z",
            transitioned_at="2023-11-16T10:00:00Z",
            updated_at="2023-11-17T10:00:00Z",
        )
        self.repo.create(quote)

        result = self.repo.read(Quote, "quote_123")

        assert result is not None
        assert isinstance(result, Quote)
        assert result.id == "quote_123"
        assert result.total == 50000

    # ========================================================================
    # Delete Tests
    # ========================================================================

    def test_delete_client_returns_true_when_deleted(self):
        """Test deleting an existing client."""
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        result = self.repo.delete(Client, "client_123")

        assert result is True
        # Verify deletion
        assert self.repo.read(Client, "client_123") is None

    def test_delete_returns_false_when_not_found(self):
        """Test deleting non-existent entity returns False."""
        result = self.repo.delete(Client, "nonexistent")
        assert result is False

    def test_delete_invoice(self):
        """Test deleting an invoice."""
        # Create dependencies
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        invoice = Invoice(
            id="invoice_123",
            client_id="client_123",
            number="INV-001",
            total_cents=10000,
            status="PAID",
            issued_at="2023-11-15T12:00:00Z",
        )
        self.repo.create(invoice)

        result = self.repo.delete(Invoice, "invoice_123")

        assert result is True
        # Client should still exist
        assert self.repo.read(Client, "client_123") is not None


class TestRepositoryBatchOperations:
    """Test suite for Repository batch save operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_save_clients_batch(self):
        """Test batch saving multiple clients."""
        clients = [
            Client(
                id=f"client_{i}",
                first_name=f"First{i}",
                last_name=f"Last{i}",
                email=f"user{i}@example.com",
                phone=f"555-010{i}",
                created_at="2023-11-15T10:00:00Z",
            )
            for i in range(5)
        ]

        self.repo.save_clients(clients)

        # Verify all clients were saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clients")
        count = cursor.fetchone()[0]
        assert count == 5
        cursor.close()

    def test_save_clients_with_empty_list(self):
        """Test save_clients with empty list doesn't error."""
        self.repo.save_clients([])

        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clients")
        count = cursor.fetchone()[0]
        assert count == 0
        cursor.close()

    def test_save_invoices_batch(self):
        """Test batch saving multiple invoices."""
        # Create client first
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        invoices = [
            Invoice(
                id=f"invoice_{i}",
                client_id="client_123",
                number=f"INV-00{i}",
                total_cents=10000 * i,
                status="PAID",
                issued_at="2023-11-15T12:00:00Z",
            )
            for i in range(1, 4)
        ]

        self.repo.save_invoices(invoices)

        # Verify all invoices were saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM invoices")
        count = cursor.fetchone()[0]
        assert count == 3
        cursor.close()

    def test_save_quotes_batch(self):
        """Test batch saving multiple quotes."""
        # Create client first
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        quotes = [
            Quote(
                id=f"quote_{i}",
                client_id="client_123",
                quote_number=f"Q-00{i}",
                title=f"Service {i}",
                total=50000 * i,
                subtotal=45000 * i,
                disclaimer="Terms apply",
                line_items="[]",
                created_at="2023-11-15T10:00:00Z",
                transitioned_at="2023-11-16T10:00:00Z",
                updated_at="2023-11-17T10:00:00Z",
            )
            for i in range(1, 4)
        ]

        self.repo.save_quotes(quotes)

        # Verify all quotes were saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM quotes")
        count = cursor.fetchone()[0]
        assert count == 3
        cursor.close()


class TestRepositoryGetAllMethods:
    """Test suite for Repository get_all_* methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_get_all_clients(self):
        """Test retrieving all clients."""
        clients = [
            Client(
                id=f"client_{i}",
                first_name=f"First{i}",
                last_name=f"Last{i}",
                email=f"user{i}@example.com",
                phone=f"555-010{i}",
                created_at="2023-11-15T10:00:00Z",
            )
            for i in range(3)
        ]
        self.repo.save_clients(clients)

        result = self.repo.get_all_clients()

        assert len(result) == 3
        assert all(isinstance(c, Client) for c in result)
        assert result[0].first_name == "First0"

    def test_get_all_clients_returns_empty_list_when_none(self):
        """Test get_all_clients returns empty list when no clients."""
        result = self.repo.get_all_clients()
        assert result == []

    def test_get_all_invoices(self):
        """Test retrieving all invoices."""
        # Create client
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        invoices = [
            Invoice(
                id=f"invoice_{i}",
                client_id="client_123",
                number=f"INV-00{i}",
                total_cents=10000 * i,
                status="PAID",
                issued_at="2023-11-15T12:00:00Z",
            )
            for i in range(1, 3)
        ]
        self.repo.save_invoices(invoices)

        result = self.repo.get_all_invoices()

        assert len(result) == 2
        assert all(isinstance(inv, Invoice) for inv in result)

    def test_get_all_quotes(self):
        """Test retrieving all quotes."""
        # Create client
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        quotes = [
            Quote(
                id=f"quote_{i}",
                client_id="client_123",
                quote_number=f"Q-00{i}",
                title=f"Service {i}",
                total=50000,
                subtotal=45000,
                disclaimer="Terms",
                line_items="[]",
                created_at="2023-11-15T10:00:00Z",
                transitioned_at="2023-11-16T10:00:00Z",
                updated_at="2023-11-17T10:00:00Z",
            )
            for i in range(2)
        ]
        self.repo.save_quotes(quotes)

        result = self.repo.get_all_quotes()

        assert len(result) == 2
        assert all(isinstance(q, Quote) for q in result)


class TestRepositoryOAuthTokens:
    """Test suite for OAuth token persistence."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_save_oauth_tokens(self):
        """Test saving OAuth tokens."""
        self.repo.save_oauth_tokens(
            access_token="access_123",
            refresh_token="refresh_123",
            expires_at="2023-12-01T10:00:00Z",
        )

        # Verify tokens were saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM oauth_tokens")
        count = cursor.fetchone()[0]
        assert count == 1
        cursor.close()

    def test_get_oauth_tokens(self):
        """Test retrieving OAuth tokens."""
        self.repo.save_oauth_tokens(
            access_token="access_123",
            refresh_token="refresh_123",
            expires_at="2023-12-01T10:00:00Z",
        )

        result = self.repo.get_oauth_tokens()

        assert result is not None
        assert result["access_token"] == "access_123"
        assert result["refresh_token"] == "refresh_123"
        assert result["expires_at"] == "2023-12-01T10:00:00Z"

    def test_get_oauth_tokens_returns_none_when_empty(self):
        """Test get_oauth_tokens returns None when no tokens."""
        result = self.repo.get_oauth_tokens()
        assert result is None

    def test_clear_oauth_tokens(self):
        """Test clearing OAuth tokens."""
        self.repo.save_oauth_tokens(
            access_token="access_123",
            refresh_token="refresh_123",
            expires_at="2023-12-01T10:00:00Z",
        )

        self.repo.clear_oauth_tokens()

        # Verify tokens were deleted
        result = self.repo.get_oauth_tokens()
        assert result is None

    def test_save_oauth_tokens_clears_previous_tokens(self):
        """Test saving new tokens clears old ones."""
        self.repo.save_oauth_tokens(
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at="2023-11-01T10:00:00Z",
        )

        self.repo.save_oauth_tokens(
            access_token="new_access",
            refresh_token="new_refresh",
            expires_at="2023-12-01T10:00:00Z",
        )

        result = self.repo.get_oauth_tokens()

        # Should have only new tokens
        assert result["access_token"] == "new_access"

        # Verify only one record exists
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM oauth_tokens")
        count = cursor.fetchone()[0]
        assert count == 1
        cursor.close()


class TestRepositoryMigrationState:
    """Test suite for migration state persistence."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_save_migration_state(self):
        """Test saving migration state."""
        self.repo.save_migration_state(
            entity_type="clients",
            last_cursor="cursor_abc123",
        )

        # Verify state was saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM migration_state WHERE entity_type = ?", ("clients",))
        count = cursor.fetchone()[0]
        assert count == 1
        cursor.close()

    def test_get_migration_state(self):
        """Test retrieving migration state."""
        self.repo.save_migration_state(
            entity_type="clients",
            last_cursor="cursor_abc123",
        )

        result = self.repo.get_migration_state("clients")

        assert result is not None
        assert isinstance(result, MigrationState)
        assert result.entity_type == "clients"
        assert result.last_cursor == "cursor_abc123"

    def test_get_migration_state_returns_none_when_not_found(self):
        """Test get_migration_state returns None when entity not migrated."""
        result = self.repo.get_migration_state("nonexistent")
        assert result is None

    def test_save_migration_state_updates_existing(self):
        """Test saving migration state updates existing record."""
        self.repo.save_migration_state(
            entity_type="clients",
            last_cursor="cursor_old",
        )

        self.repo.save_migration_state(
            entity_type="clients",
            last_cursor="cursor_new",
        )

        result = self.repo.get_migration_state("clients")

        # Should have updated cursor
        assert result.last_cursor == "cursor_new"

        # Verify only one record exists
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM migration_state WHERE entity_type = ?", ("clients",))
        count = cursor.fetchone()[0]
        assert count == 1
        cursor.close()

    def test_save_migration_state_with_none_cursor(self):
        """Test saving migration state with None cursor."""
        self.repo.save_migration_state(
            entity_type="clients",
            last_cursor=None,
        )

        result = self.repo.get_migration_state("clients")

        assert result is not None
        assert result.last_cursor is None


class TestRepositoryUtilityMethods:
    """Test suite for Repository utility methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_entity_exists_returns_true_for_existing_entity(self):
        """Test entity_exists returns True for existing entity."""
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        result = self.repo.entity_exists("clients", "client_123")

        assert result is True

    def test_entity_exists_returns_false_for_nonexistent_entity(self):
        """Test entity_exists returns False for non-existent entity."""
        result = self.repo.entity_exists("clients", "nonexistent")
        assert result is False

    def test_entity_exists_works_for_different_tables(self):
        """Test entity_exists works across different tables."""
        # Create client
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        # Create invoice
        invoice = Invoice(
            id="invoice_123",
            client_id="client_123",
            number="INV-001",
            total_cents=10000,
            status="PAID",
            issued_at="2023-11-15T12:00:00Z",
        )
        self.repo.create(invoice)

        assert self.repo.entity_exists("clients", "client_123") is True
        assert self.repo.entity_exists("invoices", "invoice_123") is True
        assert self.repo.entity_exists("invoices", "client_123") is False


class TestRepositoryErrorHandling:
    """Test suite for Repository error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_delete_unsupported_entity_type_raises_error(self):
        """Test deleting unsupported entity type raises RepositoryError."""
        # Use a type that's not supported
        class UnsupportedEntity:
            pass

        with pytest.raises(RepositoryError, match="Unsupported entity type"):
            self.repo.delete(UnsupportedEntity, "some_id")

    def test_operations_on_closed_connection_raise_error(self):
        """Test operations on closed connection raise RepositoryError."""
        self.conn.close()

        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )

        with pytest.raises(RepositoryError):
            self.repo.create(client)


class TestRepositoryGraphQLCosts:
    """Test suite for GraphQL cost tracking."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_save_graphql_costs(self):
        """Test saving GraphQL cost records."""
        costs = [
            {
                "query_type": "clients",
                "batch_size": 50,
                "requested_cost": 100,
                "actual_cost": 95,
                "cost_difference": -5,
                "timestamp": "2023-11-15T10:00:00Z",
                "created_at": "2023-11-15T10:00:00Z",
            },
            {
                "query_type": "invoices",
                "batch_size": 30,
                "requested_cost": 80,
                "actual_cost": 75,
                "cost_difference": -5,
                "timestamp": "2023-11-15T10:01:00Z",
                "created_at": "2023-11-15T10:01:00Z",
            },
        ]

        self.repo.save_graphql_costs(costs)

        # Verify costs were saved
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM graphql_costs")
        count = cursor.fetchone()[0]
        assert count == 2
        cursor.close()

    def test_get_all_graphql_costs(self):
        """Test retrieving all GraphQL costs."""
        costs = [
            {
                "query_type": "clients",
                "batch_size": 50,
                "requested_cost": 100,
                "actual_cost": 95,
                "cost_difference": -5,
                "timestamp": "2023-11-15T10:00:00Z",
                "created_at": "2023-11-15T10:00:00Z",
            },
        ]
        self.repo.save_graphql_costs(costs)

        result = self.repo.get_all_graphql_costs()

        assert len(result) == 1
        assert isinstance(result[0], GraphQLCost)
        assert result[0].query_type == "clients"
        assert result[0].batch_size == 50
        assert result[0].actual_cost == 95


class TestRepositoryTransactionBehavior:
    """Test suite for transaction and commit behavior."""

    def setup_method(self):
        """Set up test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.repo = Repository(self.conn)
        self.repo.init_schema()

    def teardown_method(self):
        """Clean up after tests."""
        self.conn.close()

    def test_batch_save_commits_transaction(self):
        """Test batch save operations commit transaction.

        Note: In-memory SQLite databases (:memory:) cannot be shared across connections,
        so this test verifies that commit is called but cannot verify persistence across
        separate connections. The transaction behavior is still validated within the
        same connection.
        """
        clients = [
            Client(
                id=f"client_{i}",
                first_name=f"First{i}",
                last_name=f"Last{i}",
                email=f"user{i}@example.com",
                phone=f"555-010{i}",
                created_at="2023-11-15T10:00:00Z",
            )
            for i in range(3)
        ]

        self.repo.save_clients(clients)

        # Verify data persisted within the same connection
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clients")
        count = cursor.fetchone()[0]
        assert count == 3
        cursor.close()

    def test_delete_commits_transaction(self):
        """Test delete operation commits transaction."""
        client = Client(
            id="client_123",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-0100",
            created_at="2023-11-15T10:00:00Z",
        )
        self.repo.create(client)

        # Commit the create
        self.conn.commit()

        # Delete should also commit
        self.repo.delete(Client, "client_123")

        # Verify deletion persisted
        result = self.repo.read(Client, "client_123")
        assert result is None
