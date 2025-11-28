"""TaxRate entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxRate:
    """
    Represents a Jobber tax rate entity.

    Note: The Jobber GraphQL API TaxRate type only exposes 'id' and 'name' fields.
    Detailed tax configuration (rate percentage, region, compound, etc.) is not
    available through the public API. TaxRates are primarily used as reference
    entities linked from Properties and Invoices.

    Usage Context:
    - Referenced from Properties via Property.taxRate relationship
    - Referenced from Invoices for tax calculations
    - Serves as configuration reference in billing workflows
    """

    id: str  # EncodedId! - The unique identifier
    name: str  # String! - Display name for the tax rate (e.g., "HST", "GST+PST", "Sales Tax")
