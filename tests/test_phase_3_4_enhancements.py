"""
Validation tests for Phase 3 (Entity Mapper Updates) and Phase 4 (Database Schema Updates).

These tests verify that all enhanced fields from the Jobber Schema Alignment project
are correctly mapped from GraphQL responses to database storage.
"""

import sqlite3
import pytest
from src.repositories.repository import Repository
from src.mappers.entity_mapper import EntityMapper


class TestPhase3And4Enhancements:
    """Test suite for Phase 3/4 enhanced field mappings."""

    @pytest.fixture
    def repository(self):
        """Create an in-memory database with schema and migrations."""
        conn = sqlite3.connect(":memory:")
        repo = Repository(conn)
        repo.init_schema()
        repo._migrate_existing_tables()
        yield repo
        conn.close()

    @pytest.fixture
    def mapper(self):
        """Create an EntityMapper instance."""
        return EntityMapper()

    # ========================================================================
    # Client Enhanced Fields Tests
    # ========================================================================

    def test_client_enhanced_fields_mapping(self, mapper):
        """Test that enhanced client fields are properly mapped."""
        graphql_data = {
            "id": "client-123",
            "name": {"first": "John", "last": "Doe"},
            "emails": [{"value": "john@example.com", "primary": True}],
            "phones": [{"number": "555-1234", "primary": True}],
            "createdAt": "2023-01-01T00:00:00Z",
            # Phase 3 enhanced fields
            "balance": 150.50,
            "companyName": "Acme Corp",
            "billingAddress": {
                "street": "123 Main St",
                "city": "Springfield",
                "province": "IL",
                "postalCode": "62701",
                "country": "USA"
            },
            "isArchivable": True,
            "isCompany": True
        }

        client = mapper.map_client(graphql_data)

        assert client.balance_cents == 15050  # $150.50 -> 15050 cents
        assert client.company_name == "Acme Corp"
        assert client.billing_street == "123 Main St"
        assert client.billing_city == "Springfield"
        assert client.billing_province == "IL"
        assert client.billing_postal_code == "62701"
        assert client.billing_country == "USA"
        assert client.is_archivable == 1
        assert client.is_company == 1

    def test_client_enhanced_fields_database_storage(self, repository, mapper):
        """Test that enhanced client fields are stored in database."""
        graphql_data = {
            "id": "client-456",
            "name": {"first": "Jane", "last": "Smith"},
            "emails": [{"value": "jane@example.com", "primary": True}],
            "phones": [{"number": "555-5678", "primary": True}],
            "createdAt": "2023-01-01T00:00:00Z",
            "balance": 250.75,
            "companyName": "Tech Inc",
            "isArchivable": False,
            "isCompany": True
        }

        client = mapper.map_client(graphql_data)
        repository.save_clients([client])

        # Verify data was stored correctly
        cursor = repository._connection.cursor()
        cursor.execute("SELECT balance_cents, company_name, is_archivable, is_company FROM clients WHERE id = ?",
                      ("client-456",))
        row = cursor.fetchone()

        assert row[0] == 25075  # balance_cents
        assert row[1] == "Tech Inc"  # company_name
        assert row[2] == 0  # is_archivable (False -> 0)
        assert row[3] == 1  # is_company (True -> 1)

    # ========================================================================
    # Invoice Enhanced Fields Tests
    # ========================================================================

    def test_invoice_enhanced_fields_mapping(self, mapper):
        """Test that enhanced invoice fields are properly mapped."""
        graphql_data = {
            "id": "invoice-123",
            "client": {"id": "client-123"},
            "invoiceNumber": "INV-001",
            "status": "sent",
            "issuedAt": "2023-01-15T00:00:00Z",
            # Phase 3 enhanced fields
            "amounts": {
                "total": 1000.00,
                "subtotal": 900.00,
                "taxAmount": 80.00,
                "discountAmount": 20.00,
                "depositAmount": 100.00
            },
            "invoiceNet": 900,
            "subject": "January Services",
            "message": "Thank you for your business"
        }

        invoice = mapper.map_invoice(graphql_data)

        assert invoice.total_cents == 100000  # $1000.00 -> 100000 cents
        assert invoice.subtotal == 90000  # $900.00 -> 90000 cents
        assert invoice.tax_cents == 8000  # $80.00 -> 8000 cents
        assert invoice.discount_cents == 2000  # $20.00 -> 2000 cents
        assert invoice.deposit_cents == 10000  # $100.00 -> 10000 cents
        assert invoice.invoice_net == 900  # Already in integer cents
        assert invoice.subject == "January Services"
        assert invoice.message == "Thank you for your business"

    # ========================================================================
    # Quote Enhanced Fields Tests
    # ========================================================================

    def test_quote_enhanced_fields_mapping(self, mapper):
        """Test that enhanced quote fields are properly mapped."""
        graphql_data = {
            "id": "quote-123",
            "client": {"id": "client-123"},
            "quoteNumber": "QUO-001",
            "title": "Website Redesign",
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-05T00:00:00Z",
            # Phase 3 enhanced fields
            "amounts": {
                "total": 5000.00,
                "subtotal": 4500.00,
                "taxAmount": 450.00,
                "discountAmount": 100.00
            },
            "quoteStatus": "SENT",
            "sentAt": "2023-01-10T10:30:00Z"
        }

        quote = mapper.map_quote(graphql_data)

        assert quote.total == 500000  # $5000.00 -> 500000 cents
        assert quote.subtotal == 450000  # $4500.00 -> 450000 cents
        assert quote.tax_cents == 45000  # $450.00 -> 45000 cents
        assert quote.discount_cents == 10000  # $100.00 -> 10000 cents
        assert quote.quote_status == "SENT"
        # The mapper formats ISO datetime with timezone
        assert "2023-01-10" in quote.sent_at

    # ========================================================================
    # Job Enhanced Fields Tests
    # ========================================================================

    def test_job_enhanced_fields_mapping(self, mapper):
        """Test that enhanced job fields are properly mapped."""
        graphql_data = {
            "id": "job-123",
            "client": {"id": "client-123"},
            "jobNumber": "JOB-001",
            "title": "Lawn Maintenance",
            "status": "active",
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-05T00:00:00Z",
            # Phase 3 enhanced fields
            "jobType": "RECURRING",
            "billingType": "FLAT_RATE",
            "invoicedTotal": 1500.00
        }

        job = mapper.map_job(graphql_data)

        assert job.job_type == "RECURRING"
        assert job.billing_type == "FLAT_RATE"
        assert job.invoiced_total == 150000  # $1500.00 -> 150000 cents

    # ========================================================================
    # Property Enhanced Fields Tests
    # ========================================================================

    def test_property_enhanced_fields_mapping(self, mapper):
        """Test that enhanced property fields are properly mapped."""
        graphql_data = {
            "id": "property-123",
            "client": {"id": "client-123"},
            "name": "Main Office",
            "address": {
                "line1": "456 Oak Ave",
                "city": "Chicago",
                "stateProvince": "IL",
                "postalCode": "60601",
                "country": "USA"
            },
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-05T00:00:00Z",
            # Phase 3 enhanced fields
            "taxRate": {
                "id": "tax-123",
                "name": "Standard Rate",
                "rate": 0.08
            },
            "isBillingAddress": True,
            "routingOrder": 5
        }

        property_obj = mapper.map_property(graphql_data)

        assert property_obj.tax_rate_id == "tax-123"
        assert property_obj.tax_rate_name == "Standard Rate"
        assert property_obj.tax_rate == "0.08"
        assert property_obj.is_billing_address == 1
        assert property_obj.routing_order == 5

    # ========================================================================
    # Visit Enhanced Fields Tests
    # ========================================================================

    def test_visit_enhanced_fields_mapping(self, mapper):
        """Test that enhanced visit fields are properly mapped."""
        graphql_data = {
            "id": "visit-123",
            "job": {"id": "job-123"},
            "client": {"id": "client-123"},
            "property": {"id": "property-123"},
            "assignedUsers": [{"id": "user-123"}],
            "title": "Weekly Maintenance",
            "status": "scheduled",
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-05T00:00:00Z",
            # Phase 3 enhanced fields
            "allDay": True,
            "clientConfirmed": True,
            "completedBy": {"id": "user-456"}
        }

        visit = mapper.map_visit(graphql_data)

        assert visit.all_day == 1  # Boolean -> INTEGER
        assert visit.client_confirmed == 1
        assert visit.completed_by_id == "user-456"

    # ========================================================================
    # User Enhanced Fields Tests
    # ========================================================================

    def test_user_enhanced_fields_mapping(self, mapper):
        """Test that enhanced user fields are properly mapped."""
        graphql_data = {
            "id": "user-123",
            "name": {"first": "Bob", "last": "Johnson"},
            "email": {"raw": "bob@example.com"},
            "role": "TECHNICIAN",
            "isAccountAdmin": "true",
            "isAccountOwner": "false",
            "status": "ACTIVE",
            "createdAt": "2023-01-01T00:00:00Z",
            # Phase 3 enhanced fields
            "availableForScheduling": True,
            "assignedColor": "#FF5733"
        }

        user = mapper.map_user(graphql_data)

        assert user.available_for_scheduling == 1
        assert user.assigned_color == "#FF5733"

    # ========================================================================
    # Database Schema Validation Tests
    # ========================================================================

    def test_phase_4_database_columns_exist(self, repository):
        """Test that all Phase 4 database columns were created."""
        cursor = repository._connection.cursor()

        # Check clients table
        cursor.execute("PRAGMA table_info(clients)")
        client_columns = {row[1] for row in cursor.fetchall()}
        assert "balance_cents" in client_columns
        assert "company_name" in client_columns
        assert "billing_street" in client_columns
        assert "billing_city" in client_columns
        assert "billing_province" in client_columns
        assert "billing_postal_code" in client_columns
        assert "billing_country" in client_columns
        assert "is_archivable" in client_columns
        assert "is_company" in client_columns

        # Check invoices table
        cursor.execute("PRAGMA table_info(invoices)")
        invoice_columns = {row[1] for row in cursor.fetchall()}
        assert "tax_cents" in invoice_columns
        assert "discount_cents" in invoice_columns
        assert "deposit_cents" in invoice_columns
        assert "invoice_net" in invoice_columns
        assert "subject" in invoice_columns
        assert "message" in invoice_columns

        # Check quotes table
        cursor.execute("PRAGMA table_info(quotes)")
        quote_columns = {row[1] for row in cursor.fetchall()}
        assert "tax_cents" in quote_columns
        assert "discount_cents" in quote_columns
        assert "quote_status" in quote_columns
        assert "sent_at" in quote_columns

        # Check jobs table
        cursor.execute("PRAGMA table_info(jobs)")
        job_columns = {row[1] for row in cursor.fetchall()}
        assert "job_type" in job_columns
        assert "billing_type" in job_columns
        assert "invoiced_total" in job_columns

        # Check properties table
        cursor.execute("PRAGMA table_info(properties)")
        property_columns = {row[1] for row in cursor.fetchall()}
        assert "tax_rate_id" in property_columns
        assert "tax_rate_name" in property_columns
        assert "tax_rate" in property_columns
        assert "is_billing_address" in property_columns
        assert "routing_order" in property_columns

        # Check visits table
        cursor.execute("PRAGMA table_info(visits)")
        visit_columns = {row[1] for row in cursor.fetchall()}
        assert "client_confirmed" in visit_columns
        assert "completed_by_id" in visit_columns

        # Check users table
        cursor.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cursor.fetchall()}
        assert "available_for_scheduling" in user_columns
        assert "assigned_color" in user_columns

    def test_migration_idempotency(self, repository):
        """Test that migrations can be run multiple times without errors."""
        # Run migrations again - should not raise errors
        repository._migrate_existing_tables()

        # Verify schema is still valid
        cursor = repository._connection.cursor()
        cursor.execute("PRAGMA table_info(clients)")
        columns = cursor.fetchall()
        assert len(columns) > 0

    def test_data_type_conversions(self, mapper):
        """Test that all data type conversions are correct."""
        # Money -> cents (INTEGER)
        client_data = {
            "id": "c1",
            "name": {"first": "Test", "last": "User"},
            "emails": [{"value": "test@example.com", "primary": True}],
            "phones": [{"number": "555-0000", "primary": True}],
            "createdAt": "2023-01-01T00:00:00Z",
            "balance": 123.45
        }
        client = mapper.map_client(client_data)
        assert isinstance(client.balance_cents, int)
        assert client.balance_cents == 12345

        # Boolean -> INTEGER (0/1)
        visit_data = {
            "id": "v1",
            "job": {"id": "j1"},
            "client": {"id": "c1"},
            "title": "Test",
            "status": "scheduled",
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-01T00:00:00Z",
            "allDay": True,
            "clientConfirmed": False
        }
        visit = mapper.map_visit(visit_data)
        assert isinstance(visit.all_day, int)
        assert isinstance(visit.client_confirmed, int)
        assert visit.all_day == 1
        assert visit.client_confirmed == 0

        # ISO8601DateTime -> TEXT string
        quote_data = {
            "id": "q1",
            "client": {"id": "c1"},
            "quoteNumber": "Q001",
            "title": "Test",
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-01-01T00:00:00Z",
            "sentAt": "2023-01-15T10:30:00Z"
        }
        quote = mapper.map_quote(quote_data)
        assert isinstance(quote.sent_at, str)
        assert "2023-01-15" in quote.sent_at
