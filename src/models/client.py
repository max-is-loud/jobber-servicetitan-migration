"""Client entity model for Jobber data."""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class Client:
    """Represents a Jobber client entity."""

    id: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate client data after initialization."""
        if not self.id:
            raise ValueError("Client ID is required")
        if not self.first_name and not self.last_name:
            raise ValueError("Client must have at least first name or last name")
