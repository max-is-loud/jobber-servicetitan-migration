# Product Requirements Document (PRD): Enhanced Jobber Data Coverage
*Feature Branch – Implements Missing Legacy Export Coverage*

---

## 1. Purpose & Feature Goals

This feature branch closes gaps between Tightbeam-v2 and the original legacy Jobber export scripts, ensuring all data previously backed up is now retrieved, normalized, and persisted in a modular, OO, and testable fashion. This includes Quotes, Notes, Attachments (from Notes), and additional metadata fields for existing entities (e.g. line items, due dates).

---

## 2. Scope

**In-Scope:**
- Quotes/Estimates entity extraction, mapping, and persistence
- Client Notes extraction, mapping, and persistence
- Note Attachments: download and storage with file metadata captured in SQLite
- Expanded Invoice field support (e.g., due dates, line items, subtotals)
- Multi-contact support for Clients (all emails and phone numbers)

**Out of Scope:**
- ServiceTitan integration
- Other Jobber entities (e.g., Tasks, Jobs, Custom Fields unless found in scripts)
- Full binary file deduplication/deep file analysis

---

## 3. Architecture & Design Patterns

### 3.1 Modular OO Extractors
Each new entity or feature will be implemented as a dedicated Extractor module/class, following Tightbeam-v2 conventions:
- `QuotesExtractor` (for Estimates/Quotes)
- `NotesExtractor` (for Client Notes)
- `AttachmentDownloader`/`NoteAttachmentExtractor` (for binary files)
- `InvoiceExtractor` (expanding on existing implementation for new fields)
- `ClientExtractor` (expanding contact list support)

Each Extractor will implement a common interface (e.g., `BaseExtractor`).

### 3.2 Model & Schema Enhancements
- Add `quotes` table, with quote number, title, timestamps, total/subtotal, disclaimer, and line items (normalized as child table or JSONB)
- Add `notes` table, with note ID, client/job reference, created_at, message
- Add `attachments` table, with note reference, file name, content type, original URL, and local file path
- Expand `invoices` table with due date, subtotal, and line items (child table or JSONB)
- Expand `clients` table with additional emails/phones (related table or serialized array)

---

## 4. Data Flow & Sequence

1. CLI (`typer`) exposes subcommands (e.g., `fetch-jobber quotes`, `fetch-jobber notes`)
2. Coordinator instantiates the required Extractors via dependency injection
3. Each Extractor:
    - Paginates through Jobber data via GraphQL
    - Maps API data to local domain models
    - Persists results via corresponding Repository
    - For notes with attachments: triggers binary download and metadata capture

---

## 5. Technical Requirements

- GraphQL queries to fetch all available fields (including nested line items, all contacts, attachments)
- Reliable download and local storage of all note attachments (preserving original filenames, handling file overwrites/conflicts)
- SQLite schema migrations to support new/expanded tables
- Batch insert/update for performance
- Robust error handling and retry/backoff for failed downloads or API throttling
- Logging and reporting for all new entity types and attachments

---

## 6. Success Criteria

- All Quotes/Estimates from Jobber are present in SQLite, with line items and relevant metadata
- All Notes are present in SQLite, with correct client/job linkage
- All binary files attached to Notes are downloaded and tracked in the `attachments` table
- Invoice and Client tables have complete metadata and child objects as in legacy export
- CLI reports accurate record counts for each new entity

---

## 7. Milestones & Timeline

| Date    | Deliverable                                 |
| ------- | ------------------------------------------- |
| Day 1   | Schema and model design for new entities    |
| Day 3   | QuotesExtractor, NotesExtractor prototyping |
| Day 5   | AttachmentDownloader integration            |
| Day 7   | Expanded Invoice/Client extractor           |
| Day 9   | Batch insert and error handling             |
| Day 10  | CLI integration and reporting               |
| Day 12  | Manual validation and code review           |
| Day 13  | Merge to develop                            |

---

## 8. Documentation
- Update all relevant `/docs` entries (see main PRD Appendix)
- Document new schema, CLI usage, error and logging strategies, attachment storage layout, and batch operation behavior

---

## 9. Out of Scope
- No ServiceTitan push/mapping in this branch
- No UI or third-party integrations
- No deduplication/deep scanning of attachments

---

