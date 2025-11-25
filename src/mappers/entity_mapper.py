"""Entity mapper for transforming GraphQL data to domain models."""

import json
from typing import Any, Optional

from ..exceptions import MappingError
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
from .mapper_utils import MapperUtils


class EntityMapper:
    """
    Maps GraphQL response data to domain model entities.

    Transforms raw API data structures to typed dataclass instances,
    handling field name transformations and data type conversions.
    """

    def map_client(self, data: dict[str, Any]) -> Client:
        """
        Map GraphQL Client data to Client domain model.

        Args:
            data: Raw GraphQL Client node data

        Returns:
            Client: Typed Client dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            client_id = data.get("id")
            if not client_id:
                raise MappingError("Client ID is required but missing")

            first_name = data.get("firstName", "")
            last_name = data.get("lastName", "")

            # Extract primary email from emails array
            # GraphQL returns: emails { address }
            emails = data.get("emails", [])
            email = MapperUtils.extract_primary_field(emails, "address", "primary")

            # Extract primary phone from phones array
            # GraphQL returns: phones { number }
            phones = data.get("phones", [])
            phone = MapperUtils.extract_primary_field(phones, "number", "primary")

            # Extract ALL emails and phones for additional contact methods
            all_emails = MapperUtils.extract_all_fields(emails, "address")
            all_phones = MapperUtils.extract_all_fields(phones, "number")

            # Remove primary from additional lists to avoid duplication
            additional_emails = [e for e in all_emails if e != email]
            additional_phones = [p for p in all_phones if p != phone]

            # Serialize to JSON for SQLite TEXT storage
            additional_emails_json = MapperUtils.serialize_json_field(additional_emails)
            additional_phones_json = MapperUtils.serialize_json_field(additional_phones)

            # Format ISO datetime
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))

            return Client(
                id=client_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                created_at=created_at,
                additional_emails=additional_emails_json,
                additional_phones=additional_phones_json,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Client data: {e}") from e

    def map_invoice(self, data: dict[str, Any]) -> Invoice:
        """
        Map GraphQL Invoice data to Invoice domain model.

        Args:
            data: Raw GraphQL Invoice node data

        Returns:
            Invoice: Typed Invoice dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            invoice_id = data.get("id")
            if not invoice_id:
                raise MappingError("Invoice ID is required but missing")

            # Extract client ID from client relationship
            client = data.get("client", {})
            client_id = ""
            if isinstance(client, dict):
                client_id = client.get("id", "")
            if not client_id:
                raise MappingError("Invoice client ID is required but missing")

            # Extract invoice number
            number = data.get("invoiceNumber", "")

            # Extract and convert amounts to cents
            amounts = data.get("amounts", {})
            total_amount = None
            subtotal_amount = None
            if isinstance(amounts, dict):
                total_amount = amounts.get("total")
                subtotal_amount = amounts.get("subtotal")

            total_cents = MapperUtils.convert_to_cents(total_amount)
            subtotal = MapperUtils.convert_to_cents(subtotal_amount)

            # Extract invoice status
            status = data.get("invoiceStatus", "")

            # Format dates
            issued_at = self._format_iso_datetime(data.get("issuedDate"))
            due_date = MapperUtils.format_iso_datetime(data.get("dueDate"))

            # Extract and serialize line items
            line_items_data = data.get("lineItems", {})
            line_items = self._serialize_line_items(line_items_data)

            return Invoice(
                id=invoice_id,
                client_id=client_id,
                number=number,
                total_cents=total_cents,
                status=status,
                issued_at=issued_at,
                due_date=due_date,
                subtotal=subtotal,
                line_items=line_items,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Invoice data: {e}") from e

    def map_quote(self, data: dict[str, Any]) -> Quote:
        """
        Map GraphQL Quote data to Quote domain model.

        Args:
            data: Raw GraphQL Quote node data

        Returns:
            Quote: Typed Quote dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            quote_id = data.get("id")
            if not quote_id:
                raise MappingError("Quote ID is required but missing")

            # Extract client ID from client relationship
            client = data.get("client", {})
            client_id = ""
            if isinstance(client, dict):
                client_id = client.get("id", "")
            if not client_id:
                raise MappingError("Quote client ID is required but missing")

            # Extract quote number
            quote_number = data.get("quoteNumber", "")

            # Extract title
            title = data.get("title", "")

            # Extract and convert amounts to cents
            amounts = data.get("amounts", {})
            total_amount = None
            subtotal_amount = None
            if isinstance(amounts, dict):
                total_amount = amounts.get("total")
                subtotal_amount = amounts.get("subtotal")

            total = self._convert_to_cents(total_amount)
            subtotal = self._convert_to_cents(subtotal_amount)

            # Extract disclaimer/message
            disclaimer = data.get("message", "")

            # Extract and serialize line items to JSON string
            line_items_data = data.get("lineItems", {})
            line_items = self._serialize_line_items(line_items_data)

            # Format ISO datetimes
            created_at = self._format_iso_datetime(data.get("createdAt"))
            transitioned_at = self._format_iso_datetime(data.get("transitionedAt"))
            updated_at = self._format_iso_datetime(data.get("updatedAt"))

            return Quote(
                id=quote_id,
                client_id=client_id,
                quote_number=quote_number,
                title=title,
                total=total,
                subtotal=subtotal,
                disclaimer=disclaimer,
                line_items=line_items,
                created_at=created_at,
                transitioned_at=transitioned_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Quote data: {e}") from e

    def map_note(self, data: dict[str, Any], lenient: bool = False) -> Note:
        """
        Map GraphQL Note data to Note domain model.

        Handles polymorphic note types from different GraphQL fragments
        (ClientNote, JobNote, QuoteNote, InvoiceNote) and extracts the
        appropriate entity type and ID relationships.

        Args:
            data: Raw GraphQL Note node data from polymorphic query
            lenient: If True, use placeholder values for missing required fields
                    instead of raising MappingError (useful for orphaned notes)

        Returns:
            Note: Typed Note dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid (unless lenient=True)
        """
        try:
            # Extract required fields with validation
            note_id = data.get("id")
            if not note_id:
                if lenient:
                    note_id = "ORPHANED_NOTE_MISSING_ID"
                else:
                    raise MappingError("Note ID is required but missing")

            # Extract message
            message = data.get("message", "")

            # Determine entity type and ID based on available relationships
            entity_type = ""
            entity_id = ""

            # Check for client relationship (ClientNote)
            if "client" in data and isinstance(data["client"], dict):
                entity_type = "client"
                entity_id = data["client"].get("id", "")
            # Check for job relationship (JobNote)
            elif "job" in data and isinstance(data["job"], dict):
                entity_type = "job"
                entity_id = data["job"].get("id", "")
            # Check for quote relationship (QuoteNote)
            elif "quote" in data and isinstance(data["quote"], dict):
                entity_type = "quote"
                entity_id = data["quote"].get("id", "")
            # Check for invoice relationship (InvoiceNote)
            elif "invoice" in data and isinstance(data["invoice"], dict):
                entity_type = "invoice"
                entity_id = data["invoice"].get("id", "")
            else:
                if lenient:
                    entity_type = "ORPHANED"
                    entity_id = "UNKNOWN"
                else:
                    raise MappingError("Note entity relationship is required but missing")

            if not entity_id:
                if lenient:
                    entity_id = "UNKNOWN"
                else:
                    raise MappingError(f"Note {entity_type} ID is required but missing")

            # Format ISO datetimes
            created_at = self._format_iso_datetime(data.get("createdAt"))
            updated_at = self._format_iso_datetime(data.get("updatedAt"))

            return Note(
                id=note_id,
                entity_type=entity_type,
                entity_id=entity_id,
                message=message,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Note data: {e}") from e

    def map_attachment(self, data: dict[str, Any], lenient: bool = False, parent_entity_id: str = "") -> Attachment:
        """
        Map GraphQL Attachment data to Attachment domain model.

        Args:
            data: Raw GraphQL Attachment (noteFile) node data
            lenient: If True, use placeholder values for missing required fields
                    instead of raising MappingError (useful for orphaned attachments)
            parent_entity_id: Parent entity ID (job/client/etc) for organizing orphaned attachments

        Returns:
            Attachment: Typed Attachment dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid (unless lenient=True)
        """
        try:
            # Extract required fields with validation
            attachment_id = data.get("id")
            if not attachment_id:
                if lenient:
                    attachment_id = "ORPHANED_ATTACHMENT_MISSING_ID"
                else:
                    raise MappingError("Attachment ID is required but missing")

            # Extract note ID from note relationship
            note = data.get("note", {})
            note_id = ""
            if isinstance(note, dict):
                note_id = note.get("id", "")
            if not note_id:
                if lenient:
                    # Use ORPHANED marker so files get organized in orphaned directory
                    note_id = "ORPHANED"
                else:
                    raise MappingError("Attachment note ID is required but missing")

            # Extract file metadata
            file_name = data.get("fileName", "")
            content_type = data.get("contentType", "")
            # NOTE: Field is 'url', not 'downloadUrl' (verified via GraphiQL introspection)
            original_url = data.get("url", "")

            # Generate local file path following convention:
            # For orphaned: ./attachments/ORPHANED/{parent_entity_id}/{filename}
            # For normal: ./attachments/{note_id}/{filename}
            if note_id == "ORPHANED" and parent_entity_id:
                local_file_path = f"./attachments/ORPHANED/{parent_entity_id}/{file_name}" if file_name else ""
            else:
                local_file_path = f"./attachments/{note_id}/{file_name}" if file_name else ""

            # Extract file size
            file_size = data.get("fileSize", 0)
            if not isinstance(file_size, int):
                file_size = 0

            # Format ISO datetime
            created_at = self._format_iso_datetime(data.get("createdAt"))

            return Attachment(
                id=attachment_id,
                note_id=note_id,
                file_name=file_name,
                content_type=content_type,
                original_url=original_url,
                local_file_path=local_file_path,
                file_size=file_size,
                created_at=created_at,
                download_status="pending",  # Initial state for metadata-only extraction
                hash=None,  # Computed during binary download phase
                downloaded_at=None,  # Set when download completes
                download_error=None,  # Set if download fails
            )

        except Exception as e:
            raise MappingError(f"Failed to map Attachment data: {e}") from e

    def map_job(self, data: dict[str, Any]) -> Job:
        """
        Map GraphQL Job data to Job domain model.

        Args:
            data: Raw GraphQL Job node data

        Returns:
            Job: Typed Job dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            job_id = data.get("id")
            if not job_id:
                raise MappingError("Job ID is required but missing")

            # Extract client ID from client relationship
            client_id = MapperUtils.extract_id_from_relationship(data.get("client"))
            if not client_id:
                raise MappingError("Job client ID is required but missing")

            # Extract optional property ID from property relationship
            property_id = MapperUtils.extract_id_from_relationship(data.get("property"))

            # Extract optional quote ID from quote relationship
            quote_id = MapperUtils.extract_id_from_relationship(data.get("quote"))

            # Extract job details
            job_number = data.get("jobNumber", "")
            title = data.get("title", "")
            # API provides 'instructions' field, use it for description
            description = data.get("instructions", "")
            # API uses 'jobStatus' not 'status'
            status = data.get("jobStatus", "")

            # Extract scheduling information
            # API uses 'startAt' and 'endAt' not 'scheduledStartAt' and 'scheduledEndAt'
            scheduled_start_at = MapperUtils.format_iso_datetime(data.get("startAt"))
            scheduled_end_at = MapperUtils.format_iso_datetime(data.get("endAt"))
            completed_at = MapperUtils.format_iso_datetime(data.get("completedAt"))

            # Extract and convert total amount to cents
            # API provides 'total' directly, not nested in 'amounts'
            total_amount = data.get("total")
            total = MapperUtils.convert_to_cents(total_amount)

            # Format ISO datetimes
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))

            return Job(
                id=job_id,
                client_id=client_id,
                property_id=property_id,
                quote_id=quote_id,
                job_number=job_number,
                title=title,
                description=description,
                status=status,
                scheduled_start_at=scheduled_start_at,
                scheduled_end_at=scheduled_end_at,
                completed_at=completed_at,
                total=total,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Job data: {e}") from e

    def map_property(self, data: dict[str, Any]) -> Property:
        """
        Map GraphQL Property data to Property domain model.

        Args:
            data: Raw GraphQL Property node data

        Returns:
            Property: Typed Property dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            property_id = data.get("id")
            if not property_id:
                raise MappingError("Property ID is required but missing")

            # Extract client ID from client relationship
            client_id = MapperUtils.extract_id_from_relationship(data.get("client"))
            if not client_id:
                raise MappingError("Property client ID is required but missing")

            # Extract property name
            name = data.get("name", "")

            # Extract address information
            address = data.get("address", {})
            address_line1 = MapperUtils.safe_get_nested(address, "line1", default="")
            address_line2 = MapperUtils.safe_get_nested(address, "line2", default="")
            city = MapperUtils.safe_get_nested(address, "city", default="")
            state_province = MapperUtils.safe_get_nested(address, "stateProvince", default="")
            postal_code = MapperUtils.safe_get_nested(address, "postalCode", default="")
            country = MapperUtils.safe_get_nested(address, "country", default="")

            # Extract GPS coordinates
            coordinates = data.get("coordinates", {})
            latitude = str(MapperUtils.safe_get_nested(coordinates, "latitude", default=""))
            longitude = str(MapperUtils.safe_get_nested(coordinates, "longitude", default=""))

            # Format ISO datetimes
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))

            return Property(
                id=property_id,
                client_id=client_id,
                name=name,
                address_line1=address_line1,
                address_line2=address_line2,
                city=city,
                state_province=state_province,
                postal_code=postal_code,
                country=country,
                latitude=latitude,
                longitude=longitude,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Property data: {e}") from e

    def map_request(self, data: dict[str, Any]) -> Request:
        """
        Map GraphQL Request data to Request domain model.

        Based on Jobber API schema: https://developer.getjobber.com/docs/
        Available fields: id, client, property, title, source, requestStatus,
        companyName, contactName, email, phone, notes, noteAttachments, createdAt, updatedAt

        Args:
            data: Raw GraphQL Request node data

        Returns:
            Request: Typed Request dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            request_id = data.get("id")
            if not request_id:
                raise MappingError("Request ID is required but missing")

            # Extract client ID from client relationship
            client_id = MapperUtils.extract_id_from_relationship(data.get("client"))
            if not client_id:
                raise MappingError("Request client ID is required but missing")

            # Extract optional property ID from property relationship
            property_id = MapperUtils.extract_id_from_relationship(data.get("property"))

            # Extract request details - using correct API field names
            title = data.get("title", "")
            source = data.get("source", "")
            # API uses 'requestStatus' not 'status'
            status = data.get("requestStatus", "")

            # Additional contact fields from API
            company_name = data.get("companyName", "")
            contact_name = data.get("contactName", "")
            email = data.get("email", "")
            phone = data.get("phone", "")

            # Fields not available in API - use empty defaults
            description = ""  # Not in API schema
            priority = ""  # Not in API schema
            assigned_to = ""  # Not in API schema
            converted_to_quote_id = ""  # Not in API schema (use quotes connection instead)
            converted_to_job_id = ""  # Not in API schema (use jobs connection instead)

            # Format ISO datetimes
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))

            return Request(
                id=request_id,
                client_id=client_id,
                property_id=property_id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                source=source,
                assigned_to=assigned_to,
                converted_to_quote_id=converted_to_quote_id,
                converted_to_job_id=converted_to_job_id,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Request data: {e}") from e

    def map_user(self, data: dict[str, Any]) -> User:
        """
        Map GraphQL User data to User domain model.

        Args:
            data: Raw GraphQL User node data

        Returns:
            User: Typed User dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            user_id = data.get("id")
            if not user_id:
                raise MappingError("User ID is required but missing")

            # Extract name components
            name = data.get("name", {})
            first_name = MapperUtils.safe_get_nested(name, "first", default="")
            last_name = MapperUtils.safe_get_nested(name, "last", default="")

            # Extract email
            email_obj = data.get("email", {})
            email = MapperUtils.safe_get_nested(email_obj, "email", default="")

            # Derive role from admin flags
            is_account_admin = data.get("isAccountAdmin", False)
            is_account_owner = data.get("isAccountOwner", False)
            if is_account_owner:
                role = "owner"
            elif is_account_admin:
                role = "admin"
            else:
                role = "employee"

            # Extract other fields
            is_account_admin_str = str(is_account_admin).lower()
            is_account_owner_str = str(is_account_owner).lower()
            status = data.get("status", "")

            # Extract phone
            phone_obj = data.get("phone", {})
            phone = MapperUtils.safe_get_nested(phone_obj, "number", default="")

            # Extract timezone
            timezone_obj = data.get("timezone", {})
            timezone = MapperUtils.safe_get_nested(timezone_obj, "identifier", default="")

            # Format ISO datetimes
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            last_login_at = MapperUtils.format_iso_datetime(data.get("lastLoginAt"))

            return User(
                id=user_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=role,
                is_account_admin=is_account_admin_str,
                is_account_owner=is_account_owner_str,
                status=status,
                phone=phone,
                timezone=timezone,
                created_at=created_at,
                last_login_at=last_login_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map User data: {e}") from e

    def map_expense(self, data: dict[str, Any]) -> Expense:
        """
        Map GraphQL Expense data to Expense domain model.

        Args:
            data: Raw GraphQL Expense node data

        Returns:
            Expense: Typed Expense dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            expense_id = data.get("id")
            if not expense_id:
                raise MappingError("Expense ID is required but missing")

            # Extract job ID from linkedJob relationship
            job_id = MapperUtils.extract_id_from_relationship(data.get("linkedJob"))
            if not job_id:
                raise MappingError("Expense job ID is required but missing")

            # Extract expense details
            title = data.get("title", "")
            description = data.get("description", "")

            # Extract and convert total amount to cents
            total_amount = data.get("total")
            amount_cents = MapperUtils.convert_to_cents(total_amount)

            # For receipt URL and vendor, use title/description as fallback
            receipt_url = ""  # Not available in current GraphQL schema
            vendor = title  # Use title as vendor name

            # Derive category from description or title
            category = "general"  # Default category

            # Extract expense date
            expense_date = MapperUtils.format_iso_datetime(data.get("date"))

            # Format ISO datetimes
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))

            return Expense(
                id=expense_id,
                job_id=job_id,
                amount_cents=amount_cents,
                description=description,
                category=category,
                receipt_url=receipt_url,
                vendor=vendor,
                expense_date=expense_date,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Expense data: {e}") from e

    def map_visit(self, data: dict[str, Any]) -> Visit:
        """
        Map GraphQL Visit data to Visit domain model.

        Args:
            data: Raw GraphQL Visit node data

        Returns:
            Visit: Typed Visit dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            visit_id = data.get("id")
            if not visit_id:
                raise MappingError("Visit ID is required but missing")

            # Extract relationship IDs
            job_id = MapperUtils.extract_id_from_relationship(data.get("job"))
            if not job_id:
                raise MappingError("Visit job ID is required but missing")

            client_id = MapperUtils.extract_id_from_relationship(data.get("client"))
            if not client_id:
                raise MappingError("Visit client ID is required but missing")

            property_id = MapperUtils.extract_id_from_relationship(data.get("property"))

            # Extract assigned user ID (first user from assignedUsers)
            assigned_users = data.get("assignedUsers", {})
            assigned_user_id = ""
            if isinstance(assigned_users, dict):
                edges = assigned_users.get("edges", [])
                if isinstance(edges, list) and len(edges) > 0:
                    first_edge = edges[0]
                    if isinstance(first_edge, dict):
                        node = first_edge.get("node", {})
                        if isinstance(node, dict):
                            assigned_user_id = node.get("id", "")

            # Extract visit details
            title = data.get("title", "")
            instructions = data.get("instructions", "")
            status = data.get("visitStatus", "")
            all_day = str(data.get("allDay", False)).lower()

            # Extract duration
            duration = data.get("duration", 0)
            duration_minutes = int(duration) if isinstance(duration, (int, float)) else 0

            # Format ISO datetimes
            start_at = MapperUtils.format_iso_datetime(data.get("startAt"))
            end_at = MapperUtils.format_iso_datetime(data.get("endAt"))
            completed_at = MapperUtils.format_iso_datetime(data.get("completedAt"))
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            updated_at = MapperUtils.format_iso_datetime(data.get("createdAt"))  # Use createdAt for updated_at

            return Visit(
                id=visit_id,
                job_id=job_id,
                client_id=client_id,
                property_id=property_id,
                assigned_user_id=assigned_user_id,
                title=title,
                instructions=instructions,
                status=status,
                all_day=all_day,
                duration_minutes=duration_minutes,
                start_at=start_at,
                end_at=end_at,
                completed_at=completed_at,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map Visit data: {e}") from e

    def map_timesheet_entry(self, data: dict[str, Any]) -> TimeSheetEntry:
        """
        Map GraphQL TimeSheetEntry data to TimeSheetEntry domain model.

        Args:
            data: Raw GraphQL TimeSheetEntry node data

        Returns:
            TimeSheetEntry: Typed TimeSheetEntry dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            timesheet_id = data.get("id")
            if not timesheet_id:
                raise MappingError("TimeSheetEntry ID is required but missing")

            # Extract relationship IDs
            user_id = MapperUtils.extract_id_from_relationship(data.get("user"))
            if not user_id:
                raise MappingError("TimeSheetEntry user ID is required but missing")

            job_id = MapperUtils.extract_id_from_relationship(data.get("job"))
            if not job_id:
                raise MappingError("TimeSheetEntry job ID is required but missing")

            # Extract optional relationship IDs
            visit_id = MapperUtils.extract_id_from_relationship(data.get("visit"))
            approved_by_id = MapperUtils.extract_id_from_relationship(data.get("approvedBy"))
            paid_by_id = MapperUtils.extract_id_from_relationship(data.get("paidBy"))

            # Extract timesheet details
            label = data.get("label", "")
            note = data.get("note", "")
            labour_rate = str(data.get("labourRate", "0.00"))

            # Extract duration information
            final_duration = data.get("finalDuration", 0)
            final_duration_seconds = int(final_duration) if isinstance(final_duration, (int, float)) else 0

            visit_duration_total = data.get("visitDurationTotal", 0)
            visit_duration_total_seconds = (
                int(visit_duration_total) if isinstance(visit_duration_total, (int, float)) else 0
            )

            # Extract status flags
            approved = str(data.get("approved", False)).lower()
            ticking = str(data.get("ticking", False)).lower()

            # Format ISO datetimes
            start_at = MapperUtils.format_iso_datetime(data.get("startAt"))
            end_at = MapperUtils.format_iso_datetime(data.get("endAt"))
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))

            return TimeSheetEntry(
                id=timesheet_id,
                user_id=user_id,
                job_id=job_id,
                visit_id=visit_id,
                approved_by_id=approved_by_id,
                paid_by_id=paid_by_id,
                label=label,
                note=note,
                labour_rate=labour_rate,
                final_duration_seconds=final_duration_seconds,
                visit_duration_total_seconds=visit_duration_total_seconds,
                approved=approved,
                ticking=ticking,
                start_at=start_at,
                end_at=end_at,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map TimeSheetEntry data: {e}") from e

    def map_product_service(self, data: dict[str, Any]) -> ProductService:
        """
        Map GraphQL ProductOrService data to ProductService domain model.

        Args:
            data: Raw GraphQL ProductOrService node data

        Returns:
            ProductService: Typed ProductService dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            product_id = data.get("id")
            if not product_id:
                raise MappingError("ProductService ID is required but missing")

            # Extract product/service details
            name = data.get("name", "")
            description = data.get("description", "")

            # Extract category
            category_obj = data.get("category", {})
            category = MapperUtils.safe_get_nested(category_obj, "name", default="")

            # Extract and convert pricing to cents
            default_unit_cost = data.get("defaultUnitCost", 0)
            default_unit_cost_cents = MapperUtils.convert_to_cents(default_unit_cost)

            internal_unit_cost = data.get("internalUnitCost", 0)
            internal_unit_cost_cents = MapperUtils.convert_to_cents(internal_unit_cost)

            # Extract markup percentage
            markup = data.get("markup", 0)
            markup_percentage = str(markup)

            # Extract service configuration
            duration_minutes = data.get("durationMinutes", 0)
            duration_minutes = int(duration_minutes) if isinstance(duration_minutes, (int, float)) else 0

            # Extract flags
            taxable = str(data.get("taxable", False)).lower()
            visible = str(data.get("visible", True)).lower()
            online_booking_enabled = str(data.get("onlineBookingEnabled", False)).lower()

            # Extract ordering
            online_booking_sort_order = data.get("onlineBookingSortOrder", 0)
            online_booking_sort_order = (
                int(online_booking_sort_order) if isinstance(online_booking_sort_order, (int, float)) else 0
            )

            # Derive active status from visible flag
            active = visible

            # Use current timestamp for created/updated dates (not available in schema)
            created_at = ""
            updated_at = ""

            return ProductService(
                id=product_id,
                name=name,
                description=description,
                category=category,
                default_unit_cost_cents=default_unit_cost_cents,
                internal_unit_cost_cents=internal_unit_cost_cents,
                markup_percentage=markup_percentage,
                duration_minutes=duration_minutes,
                taxable=taxable,
                visible=visible,
                online_booking_enabled=online_booking_enabled,
                online_booking_sort_order=online_booking_sort_order,
                active=active,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map ProductService data: {e}") from e

    def map_tax_rate(self, data: dict[str, Any]) -> TaxRate:
        """
        Map GraphQL TaxRate data to TaxRate domain model.

        Args:
            data: Raw GraphQL TaxRate node data

        Returns:
            TaxRate: Typed TaxRate dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            tax_rate_id = data.get("id")
            if not tax_rate_id:
                raise MappingError("TaxRate ID is required but missing")

            # Extract tax rate details
            name = data.get("name", "")
            rate = data.get("rate", 0)
            rate_percentage = str(rate)

            # Extract geographic and configuration details
            region = data.get("region", "")
            compound = str(data.get("compound", False)).lower()
            active = str(data.get("active", True)).lower()
            description = data.get("description", "")
            tax_number = data.get("taxNumber", "")

            # Extract display configuration
            display_order = data.get("displayOrder", 0)
            display_order = int(display_order) if isinstance(display_order, (int, float)) else 0

            default_for_region = str(data.get("defaultForRegion", False)).lower()

            # Format ISO datetimes
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))
            updated_at = MapperUtils.format_iso_datetime(data.get("updatedAt"))

            return TaxRate(
                id=tax_rate_id,
                name=name,
                rate_percentage=rate_percentage,
                region=region,
                compound=compound,
                active=active,
                description=description,
                tax_number=tax_number,
                display_order=display_order,
                default_for_region=default_for_region,
                created_at=created_at,
                updated_at=updated_at,
            )

        except Exception as e:
            raise MappingError(f"Failed to map TaxRate data: {e}") from e

    def _extract_primary_email(self, emails: list[dict[str, Any]]) -> str:
        """
        Extract primary email address from emails array.

        Args:
            emails: List of email objects from GraphQL response

        Returns:
            str: Primary email address or empty string if none found
        """
        if not emails or not isinstance(emails, list):
            return ""

        # Look for first available email address
        for email_obj in emails:
            if isinstance(email_obj, dict):
                address = email_obj.get("address", "").strip()
                if address:
                    return address

        return ""

    def _extract_primary_phone(self, phones: list[dict[str, Any]]) -> str:
        """
        Extract primary phone number from phones array.

        Args:
            phones: List of phone objects from GraphQL response

        Returns:
            str: Primary phone number or empty string if none found
        """
        if not phones or not isinstance(phones, list):
            return ""

        # Look for first available phone number
        for phone_obj in phones:
            if isinstance(phone_obj, dict):
                number = phone_obj.get("number", "").strip()
                if number:
                    return number

        return ""

    def _convert_to_cents(self, amount: Optional[float]) -> int:
        """
        Convert monetary amount to integer cents for precision.

        Args:
            amount: Monetary amount as float or None

        Returns:
            int: Amount in cents (0 if None)
        """
        if amount is None:
            return 0
        return int(round(amount * 100))

    def _format_iso_datetime(self, iso_datetime: Optional[str]) -> str:
        """
        Format ISO8601DateTime to string representation.

        Args:
            iso_datetime: ISO datetime string or None

        Returns:
            str: Formatted datetime string or empty string if None
        """
        if iso_datetime is None:
            return ""
        return str(iso_datetime)

    def _serialize_line_items(self, line_items_data: dict[str, Any]) -> str:
        """
        Serialize GraphQL line items connection to JSON string.

        Args:
            line_items_data: Line items connection data from GraphQL response

        Returns:
            str: JSON string representation of line items or empty list if None
        """
        if not line_items_data or not isinstance(line_items_data, dict):
            return "[]"

        # Extract edges array from connection
        edges = line_items_data.get("edges", [])
        if not isinstance(edges, list):
            return "[]"

        # Extract node data from each edge
        line_items = []
        for edge in edges:
            if isinstance(edge, dict) and "node" in edge:
                node = edge["node"]
                if isinstance(node, dict):
                    line_items.append(node)

        # Serialize to JSON string
        try:
            return json.dumps(line_items)
        except (TypeError, ValueError):
            return "[]"
