"""TightBeam v2 - Jobber Data Migration Tool

A command-line tool for extracting client and invoice data from Jobber GraphQL API
and persisting it to SQLite database using object-oriented architecture.
"""

from .mappers import EntityMapper

__version__ = "0.1.0"
__all__ = ["EntityMapper"]
