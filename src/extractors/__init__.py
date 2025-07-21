"""Extractors package for modular OO data extraction from Jobber GraphQL API.

This package contains concrete extractor implementations following the BaseExtractor
protocol, providing modular and testable data extraction components as specified
in PRD Section 3.1.

Core entity extractors: JobsExtractor, PropertiesExtractor, RequestsExtractor provide
complete coverage for Jobber's primary business entities with proper cursor-based
pagination and related entity extraction.
"""

from .attachment_downloader import AttachmentDownloader
from .base_extractor import BaseExtractor
from .jobs_extractor import JobsExtractor
from .notes_extractor import NotesExtractor
from .properties_extractor import PropertiesExtractor
from .quotes_extractor import QuotesExtractor
from .requests_extractor import RequestsExtractor

__all__ = [
    "AttachmentDownloader",
    "BaseExtractor",
    "JobsExtractor",
    "NotesExtractor",
    "PropertiesExtractor",
    "QuotesExtractor",
    "RequestsExtractor",
]
