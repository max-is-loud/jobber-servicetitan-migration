"""Entity mapper for transforming GraphQL data to domain models."""

import json
from typing import Any, Optional

from ..exceptions import MappingError
from ..models import Attachment, Client, Invoice, Note, Quote
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
            emails = data.get("emails", [])
            email = MapperUtils.extract_primary_field(emails, "value", "primary")

            # Extract primary phone from phones array
            phones = data.get("phones", [])
            phone = MapperUtils.extract_primary_field(phones, "value", "primary")

            # Format ISO datetime
            created_at = MapperUtils.format_iso_datetime(data.get("createdAt"))

            return Client(
                id=client_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                created_at=created_at,
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

            # Extract and convert total amount to cents
            amounts = data.get("amounts", {})
            total_amount = None
            if isinstance(amounts, dict):
                total_amount = amounts.get("total")
            total_cents = MapperUtils.convert_to_cents(total_amount)

            # Extract invoice status
            status = data.get("invoiceStatus", "")

            # Format issued date
            issued_at = self._format_iso_datetime(data.get("issuedDate"))

            return Invoice(
                id=invoice_id,
                client_id=client_id,
                number=number,
                total_cents=total_cents,
                status=status,
                issued_at=issued_at,
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

    def map_note(self, data: dict[str, Any]) -> Note:
        """
        Map GraphQL Note data to Note domain model.

        Handles polymorphic note types from different GraphQL fragments
        (ClientNote, JobNote, QuoteNote, InvoiceNote) and extracts the
        appropriate entity type and ID relationships.

        Args:
            data: Raw GraphQL Note node data from polymorphic query

        Returns:
            Note: Typed Note dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            note_id = data.get("id")
            if not note_id:
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
                raise MappingError("Note entity relationship is required but missing")

            if not entity_id:
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

    def map_attachment(self, data: dict[str, Any]) -> Attachment:
        """
        Map GraphQL Attachment data to Attachment domain model.

        Args:
            data: Raw GraphQL Attachment (noteFile) node data

        Returns:
            Attachment: Typed Attachment dataclass instance

        Raises:
            MappingError: If required fields are missing or invalid
        """
        try:
            # Extract required fields with validation
            attachment_id = data.get("id")
            if not attachment_id:
                raise MappingError("Attachment ID is required but missing")

            # Extract note ID from note relationship
            note = data.get("note", {})
            note_id = ""
            if isinstance(note, dict):
                note_id = note.get("id", "")
            if not note_id:
                raise MappingError("Attachment note ID is required but missing")

            # Extract file metadata
            file_name = data.get("fileName", "")
            content_type = data.get("contentType", "")
            original_url = data.get("downloadUrl", "")

            # Generate local file path following convention:
            # ./attachments/{note_id}/{filename}
            local_file_path = (
                f"./attachments/{note_id}/{file_name}" if file_name else ""
            )

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
            )

        except Exception as e:
            raise MappingError(f"Failed to map Attachment data: {e}") from e

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
