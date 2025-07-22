"""Client entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Client:
    """
    Represents a Jobber client entity.

    Matches the Jobber GraphQL Client schema exactly for seamless data mapping.
    Clients are the customers who pay for services on Jobber's platform.

    Contact Information:
    - email/phone: Primary contact methods (single values for backward compatibility)
    - additional_emails/additional_phones: Additional contact methods stored as
    JSON arrays in string format for SQLite TEXT storage. Examples:
      * additional_emails: '["secondary@example.com", "work@company.com"]'
      * additional_phones: '["+1234567890", "+0987654321"]'
      * Empty arrays stored as: '[]'
    """

    id: str  # EncodedId! - The unique identifier
    first_name: str  # firstName: String! - The first name of the client
    last_name: str  # lastName: String! - The last name of the client
    email: str  # Primary email from emails array
    phone: str  # Primary phone from phones array
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
    additional_emails: str = "[]"  # Additional emails as JSON array string
    additional_phones: str = "[]"  # Additional phones as JSON array string
