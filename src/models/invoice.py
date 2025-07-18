"""Invoice entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Invoice:
    """
    Represents a Jobber invoice entity.

    Matches the Jobber GraphQL Invoice schema exactly for seamless data mapping.
    A receipt detailing the work done as well as the cost of the service provided.

    Extended Invoice Information:
    - total_cents: Total amount in cents for precision (existing field)
    - subtotal: Subtotal amount in cents before taxes/fees (new field)
    - due_date: Payment due date in ISO8601DateTime format (new field)
    - line_items: Detailed invoice items stored as JSON array in string format
      for SQLite TEXT storage. Examples:
      * line_items: '[{"description": "Lawn Care", "quantity": 1, "rate": 125.00,
      "amount": 12500}]'
      * Empty line items stored as: '[]'
    """

    id: str  # EncodedId! - The unique identifier
    client_id: str  # client.id - Client relationship ID for foreign key
    number: str  # invoiceNumber: String! - The invoice number
    total_cents: int  # amounts.total converted to cents for precision
    status: str  # invoiceStatus: InvoiceStatusTypeEnum! - The status of the invoice
    issued_at: str  # issuedDate: ISO8601DateTime - ISO format string
    due_date: str = ""  # dueDate: ISO8601DateTime - Payment due date
    subtotal: int = 0  # amounts.subtotal converted to cents for precision
    line_items: str = "[]"  # lineItems: InvoiceLineItemConnection! as JSON array string
