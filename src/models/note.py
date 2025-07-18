"""Note entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Note:
    """
    Represents a Jobber note entity with polymorphic entity relationships.

    Notes can be attached to various entity types (clients, jobs, quotes, invoices)
    through a polymorphic relationship pattern. The entity_type field acts as a
    discriminator to determine which entity the note belongs to, while entity_id
    provides the foreign key reference to the specific entity instance.

    Supported entity_type values:
    - 'client': Notes attached to Client entities
    - 'job': Notes attached to Job entities
    - 'quote': Notes attached to Quote entities
    - 'invoice': Notes attached to Invoice entities
    - 'request': Notes attached to Request entities
    """

    id: str  # EncodedId! - The unique identifier
    entity_type: str  # Discriminator for polymorphic relationship ('client'/'job'/'quote'/'invoice'/'request')  # noqa: E501
    entity_id: str  # Foreign key ID referencing the entity this note belongs to
    message: str  # The note content/message text
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
    updated_at: str  # updatedAt: ISO8601DateTime! - ISO format string
