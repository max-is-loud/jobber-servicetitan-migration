"""Property entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Property:
    """
    Represents a Jobber property entity.

    Properties are physical locations where services are performed. A client
    can have multiple properties (e.g., home address, business locations).
    Jobs are typically associated with a specific property.

    Address fields follow standard address formatting for complete location data.
    """

    id: str  # EncodedId! - The unique identifier
    client_id: str  # client.id - Client who owns this property
    name: str  # name: String - Property name/label (e.g., "Main Office", "Home")
    address_line1: str  # address.line1: String! - Street address
    address_line2: str  # address.line2: String - Apartment, suite, unit, etc.
    city: str  # address.city: String! - City name
    state_province: str  # address.stateProvince: String! - State or province
    postal_code: str  # address.postalCode: String - ZIP or postal code
    country: str  # address.country: String! - Country code or name
    latitude: str  # coordinates.latitude: Float - GPS latitude
    longitude: str  # coordinates.longitude: Float - GPS longitude
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
    updated_at: str  # updatedAt: ISO8601DateTime! - ISO format string
    tax_rate_id: str = ""  # taxRate.id - Tax rate relationship ID
    tax_rate_name: str = ""  # taxRate.name - Tax rate name
    tax_rate: str = ""  # taxRate.rate - Tax rate percentage
    is_billing_address: int = 0  # isBillingAddress: Boolean! - Billing address flag (0/1)
    routing_order: int = 0  # routingOrder: Int - Order for route optimization
