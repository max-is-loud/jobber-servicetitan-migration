"""Unit tests for entity mapper field alignment fixes.

This test suite validates that GraphQL query fields are correctly mapped to
entity model fields, preventing data loss from field mismatches.

Tests cover:
- TaxRate: All 12 fields properly mapped
- ProductService: Category and onlineBookingsEnabled field fixes
- Visit: completedBy scalar handling and updatedAt removal
- Request: Contact field mapping
- Expense: Tracking field mapping
"""

import pytest
from src.mappers.entity_mapper import EntityMapper
from src.models import TaxRate, ProductService, Visit, Request, Expense


class TestTaxRateFieldAlignment:
    """Test TaxRate query-to-mapper field alignment."""

    def test_all_tax_rate_fields_mapped(self):
        """Verify all 12 TaxRate fields from query are captured in mapper."""
        mapper = EntityMapper()

        # Simulate GraphQL response with all fields
        tax_rate_data = {
            "id": "tax_123",
            "name": "GST",
            "description": "Goods and Services Tax",
            "rate": "5.0",
            "region": "BC",
            "compound": False,
            "active": True,
            "taxNumber": "TAX-001",
            "displayOrder": 1,
            "defaultForRegion": True,
            "createdAt": "2023-01-01T00:00:00Z",
            "updatedAt": "2023-06-01T00:00:00Z"
        }

        result = mapper.map_tax_rate(tax_rate_data)

        # Verify all fields are captured (no data loss)
        assert result.id == "tax_123"
        assert result.name == "GST"
        assert result.description == "Goods and Services Tax"
        assert result.rate_percentage == "5.0"
        assert result.region == "BC"
        assert result.compound == "false"
        assert result.active == "true"
        assert result.tax_number == "TAX-001"
        assert result.display_order == 1
        assert result.default_for_region == "true"
        assert result.created_at == "2023-01-01T00:00:00+00:00"
        assert result.updated_at == "2023-06-01T00:00:00+00:00"


class TestProductServiceFieldAlignment:
    """Test ProductService query-to-mapper field alignment."""

    def test_category_as_scalar_string(self):
        """Verify category field handles scalar string correctly."""
        mapper = EntityMapper()

        # API returns category as scalar string (not object)
        product_data = {
            "id": "prod_123",
            "name": "Test Service",
            "category": "Lawn Care",  # Scalar, not {"name": "Lawn Care"}
            "defaultUnitCost": 100.00,
            "internalUnitCost": 80.00,
            "markup": 25.0,
            "durationMinutes": 60,
            "taxable": True,
            "visible": True,
            "onlineBookingsEnabled": True,  # Correct field name with 's'
            "onlineBookingSortOrder": 1
        }

        result = mapper.map_product_service(product_data)

        # Verify category is captured as string
        assert result.category == "Lawn Care"
        assert result.online_booking_enabled == "true"

    def test_category_as_object_fallback(self):
        """Verify category field handles object format as fallback."""
        mapper = EntityMapper()

        product_data = {
            "id": "prod_123",
            "name": "Test Service",
            "category": {"name": "Plumbing"},  # Object format
            "defaultUnitCost": 100.00,
            "internalUnitCost": 80.00,
            "markup": 25.0,
            "durationMinutes": 60,
            "taxable": True,
            "visible": True,
            "onlineBookingsEnabled": True,
            "onlineBookingSortOrder": 1
        }

        result = mapper.map_product_service(product_data)

        # Verify category is extracted from object
        assert result.category == "Plumbing"

    def test_online_bookings_enabled_field_name(self):
        """Verify onlineBookingsEnabled (with 's') is correctly mapped."""
        mapper = EntityMapper()

        product_data = {
            "id": "prod_123",
            "name": "Test Service",
            "category": "General",
            "defaultUnitCost": 100.00,
            "internalUnitCost": 80.00,
            "markup": 25.0,
            "durationMinutes": 60,
            "taxable": True,
            "visible": True,
            "onlineBookingsEnabled": True,  # Note the 's' in 'Bookings'
            "onlineBookingSortOrder": 1
        }

        result = mapper.map_product_service(product_data)

        # Verify field is read correctly (was previously reading "onlineBookingEnabled" without 's')
        assert result.online_booking_enabled == "true"


class TestVisitFieldAlignment:
    """Test Visit query-to-mapper field alignment."""

    def test_completed_by_as_scalar_string(self):
        """Verify completedBy is handled as scalar string, not relationship object."""
        mapper = EntityMapper()

        visit_data = {
            "id": "visit_123",
            "job": {"id": "job_123"},
            "client": {"id": "client_123"},
            "property": {"id": "prop_123"},
            "assignedTo": {"id": "user_123"},
            "title": "Service Visit",
            "instructions": "Check equipment",
            "visitStatus": "completed",
            "allDay": False,
            "duration": 120,
            "clientConfirmed": True,
            "completedBy": "user_456",  # Scalar string, not {"id": "user_456"}
            "startAt": "2023-11-15T10:00:00Z",
            "endAt": "2023-11-15T12:00:00Z",
            "completedAt": "2023-11-15T12:00:00Z",
            "createdAt": "2023-11-01T00:00:00Z"
            # Note: updatedAt is NOT in the API response
        }

        result = mapper.map_visit(visit_data)

        # Verify completedBy is captured as scalar
        assert result.completed_by_id == "user_456"

        # Verify updatedAt is handled gracefully (should be None)
        assert result.updated_at is None

    def test_updated_at_field_absent(self):
        """Verify updatedAt field absence is handled correctly."""
        mapper = EntityMapper()

        visit_data = {
            "id": "visit_123",
            "job": {"id": "job_123"},
            "client": {"id": "client_123"},
            "property": {"id": "prop_123"},
            "assignedTo": {"id": "user_123"},
            "title": "Service Visit",
            "instructions": "Check equipment",
            "visitStatus": "scheduled",
            "allDay": False,
            "duration": 60,
            "clientConfirmed": False,
            "startAt": "2023-11-20T14:00:00Z",
            "endAt": "2023-11-20T15:00:00Z",
            "createdAt": "2023-11-01T00:00:00Z"
        }

        result = mapper.map_visit(visit_data)

        # Verify no error is raised and updatedAt is None
        assert result.updated_at is None


class TestRequestFieldAlignment:
    """Test Request query-to-mapper field alignment."""

    def test_contact_fields_captured(self):
        """Verify all contact fields are captured from query."""
        mapper = EntityMapper()

        request_data = {
            "id": "req_123",
            "client": {"id": "client_123"},
            "property": {"id": "prop_123"},
            "title": "New Service Request",
            "requestStatus": "new",
            "source": "web",
            "companyName": "ABC Company",
            "contactName": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "createdAt": "2023-11-15T10:00:00Z",
            "updatedAt": "2023-11-15T11:00:00Z"
        }

        result = mapper.map_request(request_data)

        # Verify contact fields are captured (were previously lost)
        assert result.company_name == "ABC Company"
        assert result.contact_name == "John Doe"
        assert result.email == "john@example.com"
        assert result.phone == "555-1234"

    def test_contact_fields_with_empty_values(self):
        """Verify contact fields handle empty/missing values gracefully."""
        mapper = EntityMapper()

        request_data = {
            "id": "req_123",
            "client": {"id": "client_123"},
            "title": "Service Request",
            "requestStatus": "new",
            "createdAt": "2023-11-15T10:00:00Z",
            "updatedAt": "2023-11-15T11:00:00Z"
        }

        result = mapper.map_request(request_data)

        # Verify empty defaults
        assert result.company_name == ""
        assert result.contact_name == ""
        assert result.email == ""
        assert result.phone == ""


class TestExpenseFieldAlignment:
    """Test Expense query-to-mapper field alignment."""

    def test_tracking_fields_captured(self):
        """Verify all tracking fields are captured from query."""
        mapper = EntityMapper()

        expense_data = {
            "id": "exp_123",
            "linkedJob": {"id": "job_123"},
            "title": "Equipment Purchase",
            "description": "New tools",
            "total": 150.99,
            "date": "2023-11-15T00:00:00Z",
            "enteredBy": {"id": "user_123"},
            "paidBy": {"id": "user_456"},
            "reimbursableTo": {"id": "user_789"},
            "createdAt": "2023-11-15T10:00:00Z",
            "updatedAt": "2023-11-15T11:00:00Z"
        }

        result = mapper.map_expense(expense_data)

        # Verify tracking fields are captured (were previously lost)
        assert result.entered_by_id == "user_123"
        assert result.paid_by_id == "user_456"
        assert result.reimbursable_to_id == "user_789"

    def test_tracking_fields_with_missing_relationships(self):
        """Verify tracking fields handle missing relationships gracefully."""
        mapper = EntityMapper()

        expense_data = {
            "id": "exp_123",
            "linkedJob": {"id": "job_123"},
            "title": "Office Supplies",
            "description": "Pens and paper",
            "total": 25.50,
            "date": "2023-11-15T00:00:00Z",
            "createdAt": "2023-11-15T10:00:00Z",
            "updatedAt": "2023-11-15T11:00:00Z"
        }

        result = mapper.map_expense(expense_data)

        # Verify empty defaults for missing relationships
        assert result.entered_by_id == ""
        assert result.paid_by_id == ""
        assert result.reimbursable_to_id == ""


class TestFieldMismatchPrevention:
    """Integration tests to prevent common field mismatch patterns."""

    def test_scalar_vs_object_handling(self):
        """Verify mappers correctly handle both scalar and object field types."""
        mapper = EntityMapper()

        # Test category as scalar
        product_scalar = {
            "id": "prod_1",
            "name": "Service A",
            "category": "Type A",
            "defaultUnitCost": 100.00,
            "internalUnitCost": 80.00,
            "markup": 25.0,
            "durationMinutes": 60,
            "taxable": True,
            "visible": True,
            "onlineBookingsEnabled": True,
            "onlineBookingSortOrder": 1
        }

        result_scalar = mapper.map_product_service(product_scalar)
        assert result_scalar.category == "Type A"

        # Test category as object
        product_object = {
            "id": "prod_2",
            "name": "Service B",
            "category": {"name": "Type B"},
            "defaultUnitCost": 100.00,
            "internalUnitCost": 80.00,
            "markup": 25.0,
            "durationMinutes": 60,
            "taxable": True,
            "visible": True,
            "onlineBookingsEnabled": True,
            "onlineBookingSortOrder": 1
        }

        result_object = mapper.map_product_service(product_object)
        assert result_object.category == "Type B"

    def test_field_name_exact_match(self):
        """Verify field names match exactly (case-sensitive, plural/singular)."""
        mapper = EntityMapper()

        # Test onlineBookingsEnabled (with 's') vs onlineBookingEnabled (without 's')
        product_data = {
            "id": "prod_123",
            "name": "Test Service",
            "category": "General",
            "defaultUnitCost": 100.00,
            "internalUnitCost": 80.00,
            "markup": 25.0,
            "durationMinutes": 60,
            "taxable": True,
            "visible": True,
            "onlineBookingsEnabled": True,  # Correct field name
            "onlineBookingSortOrder": 1
        }

        result = mapper.map_product_service(product_data)

        # This would have been "false" if reading "onlineBookingEnabled" (wrong name)
        assert result.online_booking_enabled == "true"

    def test_nonexistent_field_handling(self):
        """Verify mappers gracefully handle missing/nonexistent fields."""
        mapper = EntityMapper()

        # Visit with no updatedAt field (doesn't exist in API)
        visit_data = {
            "id": "visit_123",
            "job": {"id": "job_123"},
            "client": {"id": "client_123"},
            "property": {"id": "prop_123"},
            "assignedTo": {"id": "user_123"},
            "title": "Service Visit",
            "instructions": "Check equipment",
            "visitStatus": "scheduled",
            "allDay": False,
            "duration": 60,
            "clientConfirmed": False,
            "startAt": "2023-11-20T14:00:00Z",
            "endAt": "2023-11-20T15:00:00Z",
            "createdAt": "2023-11-01T00:00:00Z"
            # No updatedAt field - it doesn't exist in API
        }

        result = mapper.map_visit(visit_data)

        # Should handle gracefully with None or empty value
        assert result.updated_at is None
