"""Client entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Client:
    """
    Represents a Jobber client entity.

    Matches the Jobber GraphQL Client schema exactly for seamless data mapping.
    Clients are the customers who pay for services on Jobber's platform.
    """

    id: str  # EncodedId! - The unique identifier
    first_name: str  # firstName: String! - The first name of the client
    last_name: str  # lastName: String! - The last name of the client
    email: str  # Primary email from emails array
    phone: str  # Primary phone from phones array
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
