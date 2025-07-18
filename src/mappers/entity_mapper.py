"""Entity mapper for transforming GraphQL data to domain models."""

from typing import Any, Optional

from ..models import Client, Invoice
from ..exceptions import MappingError


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
            # TODO: Implement Client mapping logic
            # Transform: firstName -> first_name, lastName -> last_name
            # Extract: Primary email from emails array, primary phone from phones array
            # Convert: createdAt ISO8601DateTime to string
            raise NotImplementedError("Client mapping not yet implemented")
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
            # TODO: Implement Invoice mapping logic
            # Transform: invoiceNumber -> number, invoiceStatus -> status
            # Extract: client.id for client_id foreign key
            # Convert: amounts.total to total_cents (multiply by 100)
            # Convert: issuedDate ISO8601DateTime to string
            raise NotImplementedError("Invoice mapping not yet implemented")
        except Exception as e:
            raise MappingError(f"Failed to map Invoice data: {e}") from e

    def _extract_primary_email(self, emails: list[dict[str, Any]]) -> str:
        """
        Extract primary email address from emails array.

        Args:
            emails: List of email objects from GraphQL response

        Returns:
            str: Primary email address or empty string if none found
        """
        # TODO: Implement email extraction logic
        # Look for primary email or first available email
        raise NotImplementedError("Email extraction not yet implemented")

    def _extract_primary_phone(self, phones: list[dict[str, Any]]) -> str:
        """
        Extract primary phone number from phones array.

        Args:
            phones: List of phone objects from GraphQL response

        Returns:
            str: Primary phone number or empty string if none found
        """
        # TODO: Implement phone extraction logic
        # Look for primary phone or first available phone
        raise NotImplementedError("Phone extraction not yet implemented")

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
