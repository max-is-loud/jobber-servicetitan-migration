# AI Agent Development Guidelines - Enhanced Jobber Data Coverage Tool

## Project Overview

- **Purpose**: Modular OO CLI tool for comprehensive Jobber GraphQL data extraction with attachment downloading and SQLite persistence
- **Technology Stack**: Python, Poetry (dependency management), Typer (CLI), SQLite3, requests (HTTP), GraphQL, Rich (CLI formatting)
- **Architecture**: Protocol-based OO with BaseExtractor inheritance, dependency injection, single responsibility principle
- **Version**: Enhanced Jobber Data Coverage - Production ready with 8+ entity types and attachment handling

## Project Architecture Rules

### Entity Coverage

- **COMPLETE ENTITIES**: Client, Invoice, Quote, Note, Attachment, Job, Property, Request
- **MIGRATION SUMMARY**: MigrationSummary dataclass for structured reporting
- **ATTACHMENT HANDLING**: Binary file download and metadata persistence required
- **EXPANSION READY**: Architecture supports additional Jobber entities

### Core Protocol-Based Architecture

- **MUST** implement Protocol-based interfaces for testability and dependency injection:
  - `BaseExtractor` Protocol: Abstract interface for all entity extractors
  - `Logger` Protocol: Interface for CLI output and formatting
  - Concrete implementations inherit from abstract base classes

### Modular OO Extractor Pattern

- **REQUIRED EXTRACTORS**: All inherit from abstract `BaseExtractor` class:
  - `QuotesExtractor`: Estimates/quotes with line items and metadata
  - `NotesExtractor`: Client/job notes with attachment references
  - `JobsExtractor`: Jobs with notes extraction and relationship handling
  - `PropertiesExtractor`: Service locations with address/GPS data
  - `RequestsExtractor`: Service requests with conversion tracking
  - `AttachmentDownloader`: Binary file handling with metadata capture
  - Existing: `ClientExtractor`, `InvoiceExtractor` (expanded functionality)

### BaseExtractor Implementation Requirements

- **MUST** inherit from abstract `BaseExtractor` class in `src/extractors/base_extractor.py`
- **MUST** implement abstract methods: `extract_entities()`, `get_entity_name()`
- **MUST** use generic pagination, error handling, progress tracking from base class
- **MUST** follow Template Method pattern with entity-specific hooks
- **MUST** support related entity extraction (e.g., notes on quotes)

### Dependency Injection Architecture

- **MUST** inject all dependencies via constructor parameters
- **FACTORY PATTERN**: CLI uses factory pattern dependency injection: sqlite3.Connection → all components → RichMigrationCoordinator
- **PROTOCOL INTERFACES**: Use Protocol-based interfaces for all major components
- **PROHIBITED**: Global variables, singleton patterns, direct instantiation within classes

## Code Standards

### Type Hints and Imports (UP035 Rule Compliance)

- **MUST** use built-in `dict` type instead of `typing.Dict` (UP035 linting rule - ENFORCED)
- **MUST** use `list[EntityType]` not `typing.List` when supported
- **MUST** import `from typing import Optional, Protocol, Generic` when needed
- **PROHIBITED**: `from typing import Dict` - Ruff linting rule violation

### Naming Conventions

- **MUST** use PascalCase for class names: `JobsExtractor`, `AttachmentDownloader`
- **MUST** use snake_case for methods/variables: `extract_quotes()`, `attachment_path`
- **MUST** prefix private methods with underscore: `_download_file()`
- **MUST** use descriptive names reflecting single responsibility

### Error Handling

- **MUST** define domain-specific exceptions: `ConfigurationError`, `JobberApiError`, `DownloadError`
- **MUST** let exceptions bubble up to CLI layer for handling
- **MUST** implement retry logic for attachment downloads and API rate limiting
- **PROHIBITED**: Generic Exception, print() statements for errors

## File Organization Rules

### Directory Structure

```sh
tightbeam-v2/
├── src/
│   ├── auth/                     # OAuth2 authentication
│   ├── clients/                  # JobberClient with rate limiting
│   ├── extractors/               # All entity extractors + AttachmentDownloader
│   │   ├── __init__.py           # Export all extractors
│   │   ├── base_extractor.py     # Abstract BaseExtractor class
│   │   ├── quotes_extractor.py   # QuotesExtractor implementation
│   │   ├── notes_extractor.py    # NotesExtractor implementation
│   │   ├── jobs_extractor.py     # JobsExtractor implementation
│   │   ├── properties_extractor.py  # PropertiesExtractor implementation
│   │   ├── requests_extractor.py    # RequestsExtractor implementation
│   │   └── attachment_downloader.py # AttachmentDownloader implementation
│   ├── interfaces/               # Protocol definitions
│   │   ├── base_extractor.py     # BaseExtractor Protocol
│   │   └── logger.py             # Logger Protocol
│   ├── models/                   # All entity dataclasses
│   │   ├── client.py, invoice.py, quote.py, note.py
│   │   ├── attachment.py, job.py, property.py, request.py
│   │   └── migration_summary.py  # MigrationSummary dataclass
│   ├── mappers/                  # EntityMapper + MapperUtils
│   ├── repositories/             # Repository with generic save_entities()
│   ├── coordinators/             # RichMigrationCoordinator orchestration
│   ├── loggers/                  # ConsoleLogger implementation
│   ├── rate_limiting/            # Rate limiting functionality
│   ├── exceptions/               # Domain-specific exceptions
│   └── cli.py                    # Typer CLI with subcommands
├── attachments/                  # Downloaded attachment storage
├── pyproject.toml               # Poetry dependency management
└── shrimp-rules.md              # This file
```

### Module Dependencies

- **IMPORT HIERARCHY**: CLI → Coordinator → (Extractors, Repository, Mappers) → Models
- **PROHIBITED**: Circular imports between same-level modules
- **EXTRACTORS PACKAGE**: Must export all extractors in `__init__.py` with proper `__all__` list
- **PROTOCOL INTERFACES**: Use Protocol imports for dependency injection

## CLI Implementation Standards

### Command Structure (Based on PRD Section 4.1)

- **MAIN APP**: `tightbeam` with subcommand groups
- **MIGRATE COMMANDS**: `tightbeam migrate [subcommand]`
  - `tightbeam migrate` or `tightbeam migrate all` - Run complete migration
  - `tightbeam migrate quotes` - Extract quotes/estimates only
  - `tightbeam migrate notes` - Extract notes only  
  - `tightbeam migrate attachments` - Download attachments only
- **OAUTH COMMANDS**: `tightbeam oauth [subcommand]` - OAuth2 setup and management

### Typer Configuration Requirements

- **MUST** use `typer.Typer()` for main app and subcommand groups
- **MUST** implement subcommand structure with `add_typer()` for organization
- **MUST** support `--db` parameter for SQLite database path
- **MUST** support `--verbose` flag for detailed logging
- **MUST** use Rich formatting for enhanced CLI output

### Environment Variable Handling

- **MUST** validate `JOBBER_TOKEN` in AuthProvider, not CLI
- **MUST** support OAuth2 flow for token acquisition
- **PROHIBITED**: Direct `os.environ` access outside auth module

## Database Operations Standards

### Repository Pattern Implementation

- **MUST** implement generic `save_entities(entities, entity_type)` method
- **MUST** delegate to specific save methods based on entity type
- **MUST** support batch insert/update for performance
- **MUST** use parameterized queries for all SQL operations

### Schema Management for All Entities

- **MUST** implement `init_schema()` method supporting all entity tables
- **REQUIRED TABLES**: clients, invoices, quotes, notes, attachments, jobs, properties, requests
- **MUST** define foreign key relationships in SQL
- **ATTACHMENT STORAGE**: Metadata in attachments table, files in `attachments/` directory

### Complete Table Schema Requirements

```sql
-- Core business entities
CREATE TABLE IF NOT EXISTS clients (
  id TEXT PRIMARY KEY,
  first_name TEXT, last_name TEXT, email TEXT, phone TEXT,
  additional_emails TEXT, additional_phones TEXT,  -- Multi-contact support
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS properties (
  id TEXT PRIMARY KEY,
  client_id TEXT REFERENCES clients(id),
  address_line1 TEXT, address_line2 TEXT, city TEXT, state TEXT, postal_code TEXT,
  latitude REAL, longitude REAL,  -- GPS coordinates
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY,
  client_id TEXT REFERENCES clients(id),
  property_id TEXT REFERENCES properties(id),
  title TEXT, description TEXT, status TEXT,
  converted_to_quote_id TEXT, converted_to_job_id TEXT,  -- Conversion tracking
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS quotes (
  id TEXT PRIMARY KEY,
  client_id TEXT REFERENCES clients(id),
  property_id TEXT REFERENCES properties(id),
  request_id TEXT REFERENCES requests(id),
  quote_number TEXT, title TEXT, total_cents INTEGER, subtotal_cents INTEGER,
  line_items TEXT,  -- JSON serialized line items
  disclaimer TEXT, status TEXT,
  created_at TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  client_id TEXT REFERENCES clients(id),
  property_id TEXT REFERENCES properties(id),
  quote_id TEXT REFERENCES quotes(id),
  job_number TEXT, title TEXT, status TEXT,
  scheduled_start TEXT, scheduled_end TEXT, actual_start TEXT, actual_end TEXT,
  total_cents INTEGER,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY,
  client_id TEXT REFERENCES clients(id),
  job_id TEXT REFERENCES jobs(id),
  number TEXT, total_cents INTEGER, subtotal_cents INTEGER,
  due_date TEXT,  -- Expanded field support
  line_items TEXT,  -- JSON serialized line items
  status TEXT, issued_at TEXT
);

CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  client_id TEXT REFERENCES clients(id),
  job_id TEXT REFERENCES jobs(id),
  note_type TEXT,  -- client_note, job_note, etc.
  message TEXT,
  has_attachments BOOLEAN DEFAULT FALSE,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY,
  note_id TEXT REFERENCES notes(id),
  original_filename TEXT,
  content_type TEXT,
  file_size INTEGER,
  original_url TEXT,
  local_file_path TEXT,  -- Path in attachments/ directory
  download_status TEXT,  -- downloaded, failed, pending
  created_at TEXT, downloaded_at TEXT
);
```

## Attachment Handling Standards

### AttachmentDownloader Requirements

- **MUST** implement as separate extractor class inheriting from BaseExtractor
- **MUST** download all binary files with original filenames preserved
- **MUST** handle file overwrites/conflicts with versioning or unique naming
- **MUST** capture complete metadata: filename, content type, file size, URLs
- **MUST** implement retry logic for failed downloads with exponential backoff
- **STORAGE LOCATION**: `attachments/` directory relative to project root

### File Management

- **MUST** create directory structure: `attachments/notes/{note_id}/`
- **MUST** preserve original filenames when possible
- **MUST** handle filename conflicts with sequential numbering
- **MUST** track download status and provide reporting

## GraphQL Client Standards

### Cursor-Based Pagination (GraphQL Connection Specification)

- **MUST** use cursor-based pagination with `$cursor` variable for all entities
- **MUST** handle GraphQL Connection specification: edges/nodes/pageInfo structure
- **MUST** implement pagination loops in BaseExtractor base class
- **MUST** return raw dict payloads from JobberClient, transformation in EntityMapper

### Rate Limiting and Error Handling

- **MUST** implement configurable rate limiting patterns
- **MUST** handle API throttling with retry/backoff logic
- **MUST** support runtime configuration of rate limit error patterns
- **MUST** include authentication headers from AuthProvider

## Multi-File Coordination Rules

### Adding New Entity Types

- **WHEN** adding new entity extractor:
  - **MUST** create new model in `src/models/` directory with dataclass
  - **MUST** create new extractor in `src/extractors/` inheriting from BaseExtractor
  - **MUST** update `src/extractors/__init__.py` to export new extractor in `__all__` list
  - **MUST** add mapper methods in EntityMapper or create dedicated mapper
  - **MUST** extend Repository with new table creation in `init_schema()`
  - **MUST** add CLI subcommand for entity-specific extraction
  - **MUST** update RichMigrationCoordinator to orchestrate new extractor

### Extractor Implementation Pattern

- **WHEN** implementing new extractor:
  - **MUST** inherit from `BaseExtractor` abstract class
  - **MUST** implement required abstract methods: `extract_entities()`, `get_entity_name()`
  - **MUST** use base class pagination, error handling, progress tracking
  - **MUST** follow naming pattern: `{Entity}Extractor` (e.g., `TasksExtractor`)
  - **MUST** include comprehensive docstring explaining entity coverage

### Schema Evolution

- **WHEN** modifying entity models:
  - **MUST** update corresponding extractor implementation
  - **MUST** update table schema in Repository `init_schema()`
  - **MUST** update EntityMapper transformation logic
  - **MUST** verify GraphQL query fields match model attributes
  - **MUST** consider migration strategy for existing databases

### CLI Command Changes

- **WHEN** adding new migration commands:
  - **MUST** add subcommand to migrate command group
  - **MUST** create corresponding method in RichMigrationCoordinator
  - **MUST** follow naming pattern: `migrate_{entity}()` function
  - **MUST** include proper error handling and Rich formatting

## AI Decision-Making Standards

### Extractor Responsibility Assignment

- **IF** unsure which extractor should handle functionality:
  - **PRIORITY 1**: Check entity type → corresponding EntityExtractor
  - **PRIORITY 2**: Check if binary file handling → AttachmentDownloader
  - **PRIORITY 3**: Check if orchestration needed → RichMigrationCoordinator
  - **PRIORITY 4**: Check if transformation needed → EntityMapper

### Dependency Direction Rules

- **IF** extractor needs functionality from another component:
  - **MUST** inject via constructor following BaseExtractor pattern
  - **MUST** use Protocol interfaces for loose coupling
  - **PROHIBITED**: Direct imports between extractor classes

### Architecture Extension Guidelines

- **IF** adding new Jobber entity support:
  - **MUST** follow modular OO extractor pattern
  - **MUST** inherit from BaseExtractor for consistency
  - **MUST** implement complete data pipeline: GraphQL → Model → Database
  - **MUST** add CLI subcommand for entity-specific extraction

## Poetry and Dependency Management

### Package Management

- **MUST** use Poetry for all dependency management (not requirements.txt)
- **MUST** update `pyproject.toml` for new dependencies
- **MUST** use `poetry add` for adding new packages
- **MUST** maintain version constraints for stability

### Development Dependencies

- **REQUIRED DEV DEPENDENCIES**: pytest, pytest-cov, black, isort, mypy, ruff
- **MUST** run `ruff check` to enforce UP035 and other linting rules
- **MUST** maintain type hints for mypy compatibility

## Prohibited Actions

### Architecture Violations

- **PROHIBITED**: Direct database access from extractors (use Repository)
- **PROHIBITED**: GraphQL queries outside JobberClient
- **PROHIBITED**: Authentication logic outside auth module
- **PROHIBITED**: Binary file handling outside AttachmentDownloader
- **PROHIBITED**: CLI argument parsing outside cli.py

### Code Quality Violations

- **PROHIBITED**: Using `typing.Dict` (use built-in `dict` - UP035 rule)
- **PROHIBITED**: Global variables or module-level state
- **PROHIBITED**: print() statements (use Logger Protocol interface)
- **PROHIBITED**: Hardcoded attachment paths (use configurable base directory)

### Entity Coverage Violations

- **PROHIBITED**: Partial entity implementation (must implement complete data pipeline)
- **PROHIBITED**: Skipping related entity extraction (e.g., notes without attachments)
- **PROHIBITED**: Inconsistent extractor patterns (must inherit from BaseExtractor)

## Success Validation Criteria

### Complete Migration Functionality

- **MUST** execute `tightbeam migrate` without errors
- **MUST** populate all entity tables with data: clients, invoices, quotes, notes, attachments, jobs, properties, requests
- **MUST** download all binary attachments with metadata tracking
- **MUST** display comprehensive migration summary with counts and timing

### CLI Command Validation

- **MUST** support all subcommands: `tightbeam migrate [all|quotes|notes|attachments]`
- **MUST** support OAuth commands: `tightbeam oauth [setup|status|refresh]`
- **MUST** display Rich-formatted output with progress tracking
- **MUST** handle errors gracefully with user-friendly messages

### Architecture Validation

- **MUST** instantiate all extractors without runtime errors
- **MUST** demonstrate Protocol-based dependency injection
- **MUST** pass UP035 linting rule compliance (no typing.Dict usage)
- **MUST** validate BaseExtractor inheritance pattern across all extractors
