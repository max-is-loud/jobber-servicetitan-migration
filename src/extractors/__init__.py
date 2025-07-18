"""Extractors package for modular OO data extraction from Jobber GraphQL API.

This package contains concrete extractor implementations following the BaseExtractor
protocol, providing modular and testable data extraction components as specified
in PRD Section 3.1.
"""

from .attachment_downloader import AttachmentDownloader
from .notes_extractor import NotesExtractor
from .quotes_extractor import QuotesExtractor

__all__ = ["AttachmentDownloader", "NotesExtractor", "QuotesExtractor"]
