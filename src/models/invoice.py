"""Invoice entity model for Jobber data."""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from decimal import Decimal


@dataclass
class Invoice:
    """Represents a Jobber invoice entity."""

    id: str
    client_id: str
    invoice_number: str
    total_amount: Decimal
    status: str
    created_at: Optional[datetime] = None
    issued_date: Optional[datetime] = None
    due_date: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate invoice data after initialization."""
        if not self.id:
            raise ValueError("Invoice ID is required")
        if not self.client_id:
            raise ValueError("Client ID is required for invoice")
        if not self.invoice_number:
            raise ValueError("Invoice number is required")
