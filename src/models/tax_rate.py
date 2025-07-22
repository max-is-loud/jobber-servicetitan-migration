"""TaxRate entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxRate:
    """
    Represents a Jobber tax rate entity.

    TaxRates define the taxation rules applied to invoices, properties,
    and line items. They ensure compliance with local, regional, and
    national tax regulations and support automated tax calculations.

    Tax Configuration:
    - rate_percentage: The actual tax rate as a percentage (e.g., 13.5 for 13.5%)
    - region: Geographic region or jurisdiction (e.g., "Ontario", "California")
    - compound: Whether this tax compounds with other taxes
    - active: Whether the tax rate is currently in use

    Usage Context:
    - Applied to invoices via Invoice.taxRate relationship
    - Can be set as default for properties via Property.taxRate
    - Used in tax calculation methods and billing workflows
    """

    id: str  # EncodedId! - The unique identifier
    name: str  # name: String! - Display name for the tax rate (e.g., "HST", "GST+PST")
    rate_percentage: str  # rate: Float! - Tax rate percentage (stored as string for precision)
    region: str  # region: String - Geographic region or jurisdiction
    compound: str  # compound: Boolean - Whether tax compounds with others
    active: str  # active: Boolean - Whether tax rate is currently active
    description: str  # description: String - Additional tax rate details
    tax_number: str  # taxNumber: String - Government tax identification number
    display_order: int  # displayOrder: Int - Order for UI display
    default_for_region: str  # defaultForRegion: Boolean - Whether default for region
    created_at: str  # createdAt: ISO8601DateTime! - When tax rate was created
    updated_at: str  # updatedAt: ISO8601DateTime! - Last modification timestamp
