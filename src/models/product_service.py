"""ProductService entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductService:
    """
    Represents a Jobber product or service entity.

    ProductServices define the catalog of items that can be added to quotes,
    jobs, and invoices. They include both physical products (materials, parts)
    and services (labor, consultations) with pricing and categorization.

    Pricing Information:
    - default_unit_cost_cents: Base price in cents for financial precision
    - internal_unit_cost_cents: Internal cost for margin calculation
    - markup: Markup percentage applied to internal cost
    - taxable: Whether item is subject to taxation

    Service Configuration:
    - duration_minutes: Default service duration for scheduling
    - online_booking_enabled: Whether available for online booking
    - visible: Whether appears in autocomplete suggestions
    """

    id: str  # EncodedId! - The unique identifier
    name: str  # name: String! - The name of the product or service
    description: str  # description: String - Description of product/service
    category: str  # category.name: String - Item category for organization
    default_unit_cost_cents: int  # defaultUnitCost: Float! converted to cents
    internal_unit_cost_cents: int  # internalUnitCost: Float converted to cents
    markup_percentage: str  # markup: Float - Markup percentage as string
    duration_minutes: int  # durationMinutes: Minutes - Service duration
    taxable: str  # taxable: Boolean - Whether item is taxable
    visible: str  # visible: Boolean - Whether visible in autocomplete
    online_booking_enabled: str  # onlineBookingEnabled: Boolean - Online booking flag
    online_booking_sort_order: int  # onlineBookingSortOrder: Int - Sort order
    active: str  # Derived from visible flag and business logic
    created_at: str  # createdAt: ISO8601DateTime! - When item was created
    updated_at: str  # updatedAt: ISO8601DateTime! - Last modification timestamp
