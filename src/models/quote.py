"""Quote entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    """
    Represents a Jobber quote entity.

    Matches the Jobber GraphQL Quote schema exactly for seamless data mapping.
    A cost estimate which service providers send to their clients before any work
    is done. Quotes can be converted to jobs and invoices after client approval.
    """

    id: str  # EncodedId! - The unique identifier
    client_id: str  # client.id - Client relationship ID for foreign key
    property_id: str  # property.id - Property relationship ID for foreign key (optional)
    quote_number: str  # quoteNumber: String! - A non-unique number assigned to the quote
    title: str  # title: String - The description of the quote
    total: int  # amounts.total converted to cents for precision
    subtotal: int  # amounts.subtotal converted to cents for precision
    disclaimer: str  # message: String - The message to the client/disclaimer
    line_items: str  # lineItems: QuoteLineItemConnection! stored as JSONB string
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
    transitioned_at: str  # transitionedAt: ISO8601DateTime! - ISO format string
    updated_at: str  # updatedAt: ISO8601DateTime! - ISO format string
    quote_status: str = ""  # quoteStatus: QuoteStatusTypeEnum! - Quote status
    sent_at: str = ""  # sentAt: ISO8601DateTime - When quote was sent to client
    tax_cents: int = 0  # amounts.taxAmount converted to cents for precision
    discount_cents: int = 0  # amounts.discountAmount converted to cents for precision
