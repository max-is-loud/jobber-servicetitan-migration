"""Attachment entity model for Jobber data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Attachment:
    """
    Represents a Jobber attachment entity for note file attachments.

    Tracks both remote file metadata from Jobber's API and local storage information
    for downloaded files. Attachments are linked to notes through note_id foreign key
    and support binary file download tracking with metadata preservation.

    Local file storage follows the convention: ./attachments/{note_id}/{filename}
    This ensures organized storage with note-based directory separation for easy
    file management and prevents filename conflicts across different notes.
    """

    id: str  # EncodedId! - The unique identifier
    note_id: str  # Foreign key referencing the note this attachment belongs to
    file_name: str  # Original filename of the attachment
    content_type: str  # MIME type of the file (e.g., 'image/jpeg', 'application/pdf')
    original_url: str  # Remote URL from Jobber API for file download
    local_file_path: (
        str  # Local storage path following ./attachments/{note_id}/{filename}
    )
    file_size: int  # File size in bytes for storage tracking
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
