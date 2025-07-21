"""Extractors package for modular OO data extraction from Jobber GraphQL API.

This package contains concrete extractor implementations following the BaseExtractor
protocol, providing modular and testable data extraction components as specified
in PRD Section 3.1.

Core entity extractors: JobsExtractor, PropertiesExtractor, RequestsExtractor provide
complete coverage for Jobber's primary business entities with proper cursor-based
pagination and related entity extraction.

Phase 2 entity extractors: UsersExtractor, ExpensesExtractor, VisitsExtractor,
TimesheetEntriesExtractor, ProductServicesExtractor, TaxRatesExtractor provide
complete coverage for business-critical operational entities achieving 100%
Jobber migration capability.
"""

from .attachment_downloader import AttachmentDownloader
from .base_extractor import BaseExtractor
from .expenses_extractor import ExpensesExtractor
from .jobs_extractor import JobsExtractor
from .note_reference_collector import NoteReferenceCollector
from .notes_extractor import NotesExtractor
from .product_services_extractor import ProductServicesExtractor
from .properties_extractor import PropertiesExtractor
from .quotes_extractor import QuotesExtractor
from .requests_extractor import RequestsExtractor
from .tax_rates_extractor import TaxRatesExtractor
from .timesheet_entries_extractor import TimesheetEntriesExtractor
from .users_extractor import UsersExtractor
from .visits_extractor import VisitsExtractor

__all__ = [
    "AttachmentDownloader",
    "BaseExtractor",
    "ExpensesExtractor",
    "JobsExtractor",
    "NoteReferenceCollector",
    "NotesExtractor",
    "ProductServicesExtractor",
    "PropertiesExtractor",
    "QuotesExtractor",
    "RequestsExtractor",
    "TaxRatesExtractor",
    "TimesheetEntriesExtractor",
    "UsersExtractor",
    "VisitsExtractor",
]
