"""Attachment entity model for Jobber data."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Attachment:
    """
    Represents a Jobber attachment entity for note file attachments.

    Tracks both remote file metadata from Jobber's API and local storage information
    for downloaded files. Attachments are linked to notes through note_id foreign key
    and support binary file download tracking with metadata preservation.

    Local file storage uses hash-based content addressing: ./attachments/{sha256_hash}.{ext}
    This ensures deduplication (identical files stored once), integrity verification,
    and prevents accidental overwrites through immutable hash-based naming.

    Download tracking fields (download_status, hash, downloaded_at, download_error)
    support the two-phase extraction pattern: Phase 1 extracts metadata with
    download_status='pending', Phase 2 downloads binaries and updates tracking fields.
    """

    id: str  # EncodedId! - The unique identifier
    note_id: str  # Foreign key referencing the note this attachment belongs to
    file_name: str  # Original filename of the attachment (fileName field from API)
    content_type: str  # MIME type of the file (contentType field from API)
    original_url: str  # Remote download URL from Jobber API (url field from API)
    local_file_path: str  # Local storage path using hash-based naming: ./attachments/{sha256_hash}.{ext}
    file_size: int  # File size in bytes for storage tracking (fileSize field from API)
    created_at: str  # createdAt: ISO8601DateTime! - ISO format string
    download_status: str = "pending"  # Download status: pending, completed, failed
    hash: Optional[str] = None  # SHA256 hash of downloaded file for integrity verification
    downloaded_at: Optional[str] = None  # ISO timestamp when file was successfully downloaded
    download_error: Optional[str] = None  # Error message if download failed
