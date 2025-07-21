"""Request entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Request:
    """
    Represents a Jobber request entity.

    Requests are initial inquiries or service requests from clients that can
    be converted into quotes or jobs. They capture the initial client need
    before formal quoting or scheduling occurs.

    Workflow: Request -> Quote -> Job -> Invoice
    """

    id: str  # EncodedId! - The unique identifier
    client_id: str  # client.id - Client who made the request
    property_id: str  # property.id - Optional property for the request
    title: str  # title: String! - Brief description of the request
    description: str  # description: String - Detailed request information
    status: str  # status: String! - Request status (e.g., new, contacted, converted)
    priority: str  # priority: String - Priority level (e.g., low, medium, high)
    source: str  # source: String - How the request came in (e.g., web, phone, email)
    assigned_to: str  # assignedTo: String - Team member handling the request
    converted_to_quote_id: str  # convertedToQuote.id - Quote created from this request
    converted_to_job_id: str  # convertedToJob.id - Job created from this request
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
    updated_at: str  # updatedAt: ISO8601DateTime! - ISO format string
