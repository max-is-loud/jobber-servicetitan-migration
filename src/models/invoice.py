"""Invoice entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Invoice:
    """
    Represents a Jobber invoice entity.

    Matches the Jobber GraphQL Invoice schema exactly for seamless data mapping.
    A receipt detailing the work done as well as the cost of the service provided.
    """

    id: str  # EncodedId! - The unique identifier
    client_id: str  # client.id - Client relationship ID for foreign key
    number: str  # invoiceNumber: String! - The invoice number
    total_cents: int  # amounts.total converted to cents for precision
    status: str  # invoiceStatus: InvoiceStatusTypeEnum! - The status of the invoice
    issued_at: str  # issuedDate: ISO8601DateTime - ISO format string
