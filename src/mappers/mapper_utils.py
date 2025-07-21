"""Common mapper utilities for data transformation."""

from datetime import datetime
from typing import Any, List, Optional


class MapperUtils:
    """Utility functions for common data transformations in entity mapping."""

    @staticmethod
    def format_iso_datetime(datetime_str: Optional[str]) -> str:
        """Format ISO datetime string to consistent format.

        Args:
            datetime_str: ISO datetime string or None

        Returns:
            Formatted datetime string or empty string if None
        """
        if not datetime_str:
            return ""

        try:
            # Parse ISO format and reformat consistently
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            return dt.isoformat()
        except (ValueError, AttributeError):
            return datetime_str or ""

    @staticmethod
    def extract_primary_field(
        field_list: List[dict[str, Any]],
        field_name: str = "value",
        primary_key: str = "primary",
    ) -> str:
        """Extract primary field value from a list of field objects.

        Common pattern in Jobber API for emails, phones, etc.

        Args:
            field_list: List of field dictionaries
            field_name: Name of the value field (default: "value")
            primary_key: Name of the primary indicator field (default: "primary")

        Returns:
            Primary field value or empty string if not found
        """
        if not field_list:
            return ""

        # First try to find explicitly marked primary
        for field in field_list:
            if field.get(primary_key) and field.get(field_name):
                return str(field[field_name])

        # Fall back to first non-empty value
        for field in field_list:
            if field.get(field_name):
                return str(field[field_name])

        return ""

    @staticmethod
    def extract_all_fields(
        field_list: List[dict[str, Any]], field_name: str = "value"
    ) -> List[str]:
        """Extract all field values from a list of field objects.

        Args:
            field_list: List of field dictionaries
            field_name: Name of the value field (default: "value")

        Returns:
            List of all non-empty field values
        """
        if not field_list:
            return []

        return [str(field[field_name]) for field in field_list if field.get(field_name)]

    @staticmethod
    def convert_to_cents(amount: Optional[Any]) -> int:
        """Convert monetary amount to cents.

        Handles various input formats including strings and floats.

        Args:
            amount: Monetary amount in dollars or None

        Returns:
            Amount in cents as integer, or 0 if None/invalid
        """
        if amount is None:
            return 0

        try:
            # Handle string amounts (e.g., "123.45")
            if isinstance(amount, str):
                amount = float(amount.replace(",", ""))

            # Convert to cents
            return int(float(amount) * 100)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def extract_id_from_relationship(
        relationship: Optional[dict[str, Any]], id_field: str = "id"
    ) -> str:
        """Extract ID from a relationship object.

        Common pattern for extracting IDs from nested relationships.

        Args:
            relationship: Relationship dictionary or None
            id_field: Name of the ID field (default: "id")

        Returns:
            ID string or empty string if not found
        """
        if not relationship or not isinstance(relationship, dict):
            return ""

        return str(relationship.get(id_field, ""))

    @staticmethod
    def safe_get_nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
        """Safely get nested dictionary values.

        Args:
            data: Source dictionary
            *keys: Sequence of keys to traverse
            default: Default value if path not found

        Returns:
            Value at nested path or default
        """
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return default
            else:
                return default
        return current

    @staticmethod
    def serialize_json_field(data: Any) -> str:
        """Serialize data to JSON string for storage.

        Args:
            data: Data to serialize

        Returns:
            JSON string representation
        """
        import json

        if data is None:
            return "[]"

        try:
            return json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            return "[]"

    @staticmethod
    def parse_json_field(json_str: str, default: Any = None) -> Any:
        """Parse JSON string field.

        Args:
            json_str: JSON string to parse
            default: Default value if parsing fails

        Returns:
            Parsed data or default
        """
        import json

        if not json_str:
            return default or []

        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return default or []
