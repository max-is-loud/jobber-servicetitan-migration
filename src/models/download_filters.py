"""Download filters model for controlling attachment download selection."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DownloadFilters:
    """Filters for selective attachment downloads.

    Enables fine-grained control over which attachments to download during
    the download pass. Filters can be combined for precise selection.

    Attributes:
        file_types: Optional list of file extensions to include (e.g., ["jpeg", "pdf", "png"])
                   Extensions are case-insensitive and can be with or without leading dot
        min_size: Optional minimum file size in bytes (inclusive)
        max_size: Optional maximum file size in bytes (inclusive)
        parent_entity_types: Optional list of parent entity types (e.g., ["clients", "jobs"])
                            Used to download only attachments from specific entity types

    Examples:
        # Download only images under 10MB
        filters = DownloadFilters(
            file_types=["jpeg", "jpg", "png"],
            max_size=10 * 1024 * 1024
        )

        # Download only client attachments
        filters = DownloadFilters(
            parent_entity_types=["clients"]
        )

        # Download large PDFs from invoices
        filters = DownloadFilters(
            file_types=["pdf"],
            min_size=1 * 1024 * 1024,
            parent_entity_types=["invoices"]
        )
    """

    file_types: Optional[List[str]] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    parent_entity_types: Optional[List[str]] = None

    def __post_init__(self) -> None:
        """Validate and normalize filter parameters."""
        # Normalize file types: lowercase, strip dots
        if self.file_types:
            self.file_types = [
                ft.lower().lstrip(".") for ft in self.file_types
            ]

        # Normalize parent entity types: lowercase
        if self.parent_entity_types:
            self.parent_entity_types = [
                pet.lower() for pet in self.parent_entity_types
            ]

        # Validate size ranges
        if self.min_size is not None and self.min_size < 0:
            raise ValueError("min_size must be non-negative")

        if self.max_size is not None and self.max_size < 0:
            raise ValueError("max_size must be non-negative")

        if (
            self.min_size is not None
            and self.max_size is not None
            and self.min_size > self.max_size
        ):
            raise ValueError("min_size cannot be greater than max_size")

    def matches_file_type(self, filename: str) -> bool:
        """Check if filename matches file type filter.

        Args:
            filename: The attachment filename to check

        Returns:
            True if file type filter is not set or filename matches, False otherwise
        """
        if not self.file_types:
            return True

        if not filename:
            return False

        # Extract extension (case-insensitive, without dot)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in self.file_types

    def matches_size(self, file_size: Optional[int]) -> bool:
        """Check if file size matches size filter.

        Args:
            file_size: The attachment file size in bytes (None if unknown)

        Returns:
            True if size filter is not set or file size matches, False otherwise
        """
        if file_size is None:
            # Unknown size - allow if no size filters set
            return self.min_size is None and self.max_size is None

        if self.min_size is not None and file_size < self.min_size:
            return False

        if self.max_size is not None and file_size > self.max_size:
            return False

        return True

    def matches_parent_type(self, parent_type: str) -> bool:
        """Check if parent entity type matches filter.

        Args:
            parent_type: The parent entity type (e.g., "clients", "invoices")

        Returns:
            True if parent type filter is not set or parent type matches, False otherwise
        """
        if not self.parent_entity_types:
            return True

        return parent_type.lower() in self.parent_entity_types
