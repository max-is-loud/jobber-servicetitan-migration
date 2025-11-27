# TightBeam Database Schema

This document describes the SQLite database schema used by TightBeam v2.

## Overview

The database is organized into three logical groups:

1. **Entity Tables** - Migrated data from Jobber API
2. **Multi-Pass Tables** - Map/Extract workflow tracking
3. **System Tables** - Migration state and monitoring

## Entity Tables

These tables store the actual migrated data from Jobber.

### clients

Stores client/customer records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber client ID |
| first_name | TEXT | Client first name |
| last_name | TEXT | Client last name |
| company_name | TEXT | Company name (nullable) |
| email | TEXT | Email address (nullable) |
| phone_number | TEXT | Phone number (nullable) |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### properties

Stores property/service location records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber property ID |
| client_id | TEXT | Foreign key to clients |
| street1 | TEXT | Address line 1 (nullable) |
| street2 | TEXT | Address line 2 (nullable) |
| city | TEXT | City (nullable) |
| province | TEXT | Province/state (nullable) |
| postal_code | TEXT | Postal/ZIP code (nullable) |
| country | TEXT | Country (nullable) |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### jobs

Stores job/work order records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber job ID |
| client_id | TEXT | Foreign key to clients |
| property_id | TEXT | Foreign key to properties |
| job_number | TEXT | Human-readable job number |
| title | TEXT | Job title |
| description | TEXT | Job description (nullable) |
| status | TEXT | Job status |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |
| start_at | TEXT | Scheduled start (nullable) |
| end_at | TEXT | Scheduled end (nullable) |

### invoices

Stores invoice records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber invoice ID |
| client_id | TEXT | Foreign key to clients |
| job_id | TEXT | Foreign key to jobs (nullable) |
| invoice_number | TEXT | Human-readable invoice number |
| subject | TEXT | Invoice subject/title |
| message | TEXT | Invoice message (nullable) |
| status | TEXT | Invoice status |
| total | REAL | Total amount |
| tax | REAL | Tax amount |
| issued_at | TEXT | ISO8601 issue date |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### quotes

Stores quote/estimate records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber quote ID |
| client_id | TEXT | Foreign key to clients |
| quote_number | TEXT | Human-readable quote number |
| message | TEXT | Quote message (nullable) |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### requests

Stores service request records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber request ID |
| client_id | TEXT | Foreign key to clients |
| property_id | TEXT | Foreign key to properties (nullable) |
| title | TEXT | Request title |
| description | TEXT | Request description (nullable) |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### visits

Stores visit/appointment records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber visit ID |
| job_id | TEXT | Foreign key to jobs |
| title | TEXT | Visit title |
| start_at | TEXT | ISO8601 scheduled start |
| end_at | TEXT | ISO8601 scheduled end |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### users

Stores user/team member records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber user ID |
| first_name | TEXT | User first name |
| last_name | TEXT | User last name |
| email | TEXT | Email address |
| account_role | TEXT | Role in account (nullable) |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### expenses

Stores expense records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber expense ID |
| description | TEXT | Expense description |
| total | REAL | Total amount |
| category | TEXT | Expense category (nullable) |
| incurred_at | TEXT | ISO8601 expense date |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### notes

Stores note records attached to various entities.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber note ID |
| parent_type | TEXT | Parent entity type |
| parent_id | TEXT | Parent entity ID |
| body | TEXT | Note content |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |
| author_id | TEXT | Foreign key to users (nullable) |

### attachments

Stores file attachment records.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber attachment ID |
| parent_type | TEXT | Parent entity type |
| parent_id | TEXT | Parent entity ID |
| file_name | TEXT | Original filename |
| file_url | TEXT | Jobber API URL |
| local_path | TEXT | Local filesystem path (nullable) |
| file_size | INTEGER | File size in bytes (nullable) |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### products_services

Stores product and service catalog items.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber item ID |
| name | TEXT | Product/service name |
| description | TEXT | Description (nullable) |
| unit_cost | REAL | Cost per unit |
| type | TEXT | "PRODUCT" or "SERVICE" |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### tax_rates

Stores tax rate configurations.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber tax rate ID |
| name | TEXT | Tax rate name |
| rate | REAL | Tax rate percentage |
| compound | INTEGER | 1 if compound tax, 0 otherwise |
| recoverable | INTEGER | 1 if recoverable, 0 otherwise |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

### timesheet_entries

Stores timesheet/time tracking entries.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Jobber timesheet entry ID |
| user_id | TEXT | Foreign key to users |
| job_id | TEXT | Foreign key to jobs (nullable) |
| description | TEXT | Work description (nullable) |
| start_at | TEXT | ISO8601 start time |
| end_at | TEXT | ISO8601 end time |
| total_time | REAL | Total hours worked |
| created_at | TEXT | ISO8601 creation timestamp |
| updated_at | TEXT | ISO8601 last update timestamp |

## Multi-Pass Workflow Tables

These tables support the multi-pass map/extract migration strategy.

### map_snapshot

Tracks map pass execution metadata for multi-pass migrations.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | UUID snapshot identifier |
| created_at | TEXT NOT NULL | ISO8601 creation timestamp |
| pass1_cutoff | TEXT NOT NULL | ISO8601 cutoff time for snapshot |
| label | TEXT | Optional human-friendly label |
| entities_included | TEXT | JSON array of entity types |

**Purpose:** Enables multiple extract passes from the same map data and comparison over time.

**Example entities_included:**
```json
["clients", "invoices", "quotes", "jobs"]
```

**Indexes:**
- Primary key on `id`
- Index on `created_at` for chronological queries

### entity_inventory

Stores discovered entities from map pass with lightweight metadata.

| Column | Type | Description |
|--------|------|-------------|
| entity_type | TEXT NOT NULL | Entity type (e.g., "clients") |
| entity_id | TEXT NOT NULL | Jobber API identifier |
| discovered_at | TEXT NOT NULL | ISO8601 discovery timestamp |
| map_snapshot_id | TEXT NOT NULL | Foreign key to map_snapshot |
| updated_at | TEXT | Last update from API (nullable) |
| estimated_relations_json | TEXT | JSON with relation counts |

**Primary Key:** `(entity_type, entity_id, map_snapshot_id)`

**Purpose:** Provides inventory for extract pass planning and cost estimation.

**Example estimated_relations_json:**
```json
{"notes": 5, "attachments": 2, "line_items": 10, "visits": 3}
```

**Indexes:**
- Primary key on `(entity_type, entity_id, map_snapshot_id)`
- Index on `map_snapshot_id` for snapshot queries
- Index on `entity_type` for per-type aggregation

### extract_queue_item

Tracks extraction status per entity for resumable extraction.

| Column | Type | Description |
|--------|------|-------------|
| entity_type | TEXT NOT NULL | Entity type to extract |
| entity_id | TEXT NOT NULL | Entity identifier |
| status | TEXT NOT NULL | pending/in_progress/done/failed |
| map_snapshot_id | TEXT NOT NULL | Foreign key to map_snapshot |
| updated_at | TEXT NOT NULL | ISO8601 last update timestamp |
| last_error | TEXT | Error message if failed (nullable) |
| attempt_count | INTEGER | Number of extraction attempts |

**Primary Key:** `(entity_type, entity_id, map_snapshot_id)`

**Purpose:** Enables resumable extraction with per-entity status tracking.

**Status flow:** `pending` → `in_progress` → `done` (success) or `failed` (retry)

**Indexes:**
- Primary key on `(entity_type, entity_id, map_snapshot_id)`
- Index on `(map_snapshot_id, status)` for queue queries
- Index on `status` for status filtering

### attachment_queue_item

Tracks binary download status separately from entity extraction.

| Column | Type | Description |
|--------|------|-------------|
| attachment_id | TEXT NOT NULL | Attachment identifier |
| parent_type | TEXT NOT NULL | Parent entity type |
| parent_id | TEXT NOT NULL | Parent entity ID |
| status | TEXT NOT NULL | pending/in_progress/done/failed |
| map_snapshot_id | TEXT NOT NULL | Foreign key to map_snapshot |
| updated_at | TEXT NOT NULL | ISO8601 last update timestamp |
| last_error | TEXT | Error message if failed (nullable) |
| attempt_count | INTEGER | Number of download attempts |

**Primary Key:** `(attachment_id, map_snapshot_id)`

**Purpose:** Decouples attachment downloads from entity extraction for isolated retry.

**Status flow:** `pending` → `in_progress` → `done` (success) or `failed` (retry)

**Indexes:**
- Primary key on `(attachment_id, map_snapshot_id)`
- Index on `(map_snapshot_id, status)` for queue queries
- Index on `(parent_type, parent_id)` for parent lookups

## System Tables

These tables track migration state and performance monitoring.

### migration_state

Tracks migration execution state for resume functionality.

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PRIMARY KEY | State key identifier |
| value | TEXT | State value (JSON or scalar) |

**Purpose:** Stores checkpoints for resumable migrations and configuration state.

**Common keys:**
- `last_migration_timestamp` - ISO8601 timestamp of last successful migration
- `resume_cursor_<entity_type>` - Pagination cursor for entity type

### migration_summary

Stores detailed migration execution summaries.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | Summary record ID |
| started_at | TEXT NOT NULL | ISO8601 migration start time |
| completed_at | TEXT | ISO8601 completion time (nullable) |
| entity_type | TEXT | Entity type migrated (nullable) |
| entities_processed | INTEGER | Count of entities processed |
| entities_failed | INTEGER | Count of failures |
| total_errors | INTEGER | Total error count |
| status | TEXT | Migration status |
| error_details | TEXT | JSON array of error details (nullable) |

**Purpose:** Provides audit trail and performance metrics for migrations.

**Indexes:**
- Primary key on `id`
- Index on `started_at` for chronological queries
- Index on `entity_type` for per-type analysis

### graphql_cost

Tracks GraphQL query costs and rate limiting for performance analysis.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | Cost record ID |
| query_name | TEXT | GraphQL operation name |
| timestamp | TEXT NOT NULL | ISO8601 query timestamp |
| actual_cost | INTEGER | Actual query cost |
| requested_cost | INTEGER | Requested cost estimate |
| throttle_status | TEXT | Throttle status returned |
| requested_query_cost | INTEGER | Cost requested from API |
| actual_query_cost | INTEGER | Actual cost charged |
| current_available | INTEGER | Available cost after query |
| maximum_available | INTEGER | Maximum bucket size |
| restore_rate | INTEGER | Cost restore rate per second |

**Purpose:** Enables performance tuning and rate limit optimization analysis.

**Indexes:**
- Primary key on `id`
- Index on `timestamp` for time-series queries
- Index on `query_name` for per-operation analysis

## Relationships

### Primary Relationships

```
clients (1) ──→ (many) properties
clients (1) ──→ (many) jobs
clients (1) ──→ (many) invoices
clients (1) ──→ (many) quotes
clients (1) ──→ (many) requests
jobs (1) ──→ (many) visits
jobs (1) ──→ (many) invoices (optional)
properties (1) ──→ (many) jobs
users (1) ──→ (many) timesheet_entries
```

### Attachment Relationships

```
* (many entities) ──→ (many) notes
* (many entities) ──→ (many) attachments
notes (1) ──→ (many) attachments
```

Notes and attachments use polymorphic relationships via `parent_type` and `parent_id` columns.

### Multi-Pass Relationships

```
map_snapshot (1) ──→ (many) entity_inventory
map_snapshot (1) ──→ (many) extract_queue_item
map_snapshot (1) ──→ (many) attachment_queue_item
```

## Data Types

All tables use SQLite's flexible typing with the following conventions:

- **TEXT** - Strings, ISO8601 timestamps, JSON
- **INTEGER** - Counts, flags, autoincrement IDs
- **REAL** - Monetary amounts, percentages, hours

### ISO8601 Timestamps

All timestamp columns use ISO8601 format with timezone:
```
2025-01-20T12:34:56.789Z
```

### JSON Columns

JSON data is stored as TEXT for SQLite compatibility:
- `entities_included` in `map_snapshot`
- `estimated_relations_json` in `entity_inventory`
- `error_details` in `migration_summary`

Query with SQLite JSON functions:
```sql
SELECT entity_id, json_extract(estimated_relations_json, '$.notes') as note_count
FROM entity_inventory
WHERE json_extract(estimated_relations_json, '$.notes') > 10;
```

## Indexes

### Performance Indexes

Key indexes for query performance:

```sql
-- Multi-pass workflow queries
CREATE INDEX idx_entity_inventory_snapshot ON entity_inventory(map_snapshot_id);
CREATE INDEX idx_extract_queue_status ON extract_queue_item(map_snapshot_id, status);
CREATE INDEX idx_attachment_queue_status ON attachment_queue_item(map_snapshot_id, status);

-- Entity relationship queries
CREATE INDEX idx_properties_client ON properties(client_id);
CREATE INDEX idx_jobs_client ON jobs(client_id);
CREATE INDEX idx_invoices_client ON invoices(client_id);
CREATE INDEX idx_notes_parent ON notes(parent_type, parent_id);
CREATE INDEX idx_attachments_parent ON attachments(parent_type, parent_id);

-- Time-series queries
CREATE INDEX idx_migration_summary_started ON migration_summary(started_at);
CREATE INDEX idx_graphql_cost_timestamp ON graphql_cost(timestamp);
```

## Schema Versioning

The schema version is tracked in `migration_state`:

```sql
SELECT value FROM migration_state WHERE key = 'schema_version';
```

Current schema version: **2.0** (multi-pass support added)

## Migration Path

### From v1.x (Single-Pass)

The v2.0 schema is backward compatible with v1.x. New multi-pass tables are added without modifying existing entity tables.

Existing migrations continue to work:
```bash
# v1.x style (still supported)
uv run tightbeam migrate all

# v2.0 style (recommended)
uv run tightbeam migrate map
uv run tightbeam migrate extract --snapshot-id <id>
```

### Future Schema Changes

Schema changes will be versioned and migrations provided to upgrade existing databases without data loss.

## Backup and Maintenance

### Backing Up

SQLite databases can be backed up with simple file copy:

```bash
# Backup database
cp tightbeam.db tightbeam.db.backup

# Or use SQLite backup command
sqlite3 tightbeam.db ".backup tightbeam.db.backup"
```

### Pruning Old Snapshots

Clean up old map snapshots to reduce database size:

```sql
-- List snapshots
SELECT id, created_at, label, entities_included
FROM map_snapshot
ORDER BY created_at DESC;

-- Delete old snapshot and related data (use with caution!)
DELETE FROM entity_inventory WHERE map_snapshot_id = '<snapshot-id>';
DELETE FROM extract_queue_item WHERE map_snapshot_id = '<snapshot-id>';
DELETE FROM attachment_queue_item WHERE map_snapshot_id = '<snapshot-id>';
DELETE FROM map_snapshot WHERE id = '<snapshot-id>';
```

**Warning:** Deleting snapshots will prevent resuming extractions from those snapshots.

### Vacuum

Reclaim space after deletions:

```bash
sqlite3 tightbeam.db "VACUUM;"
```

## Useful Queries

### Entity Statistics

```sql
-- Count entities by type
SELECT 'clients' as type, COUNT(*) as count FROM clients
UNION ALL
SELECT 'invoices', COUNT(*) FROM invoices
UNION ALL
SELECT 'jobs', COUNT(*) FROM jobs
ORDER BY count DESC;

-- Clients with most jobs
SELECT c.first_name, c.last_name, COUNT(j.id) as job_count
FROM clients c
LEFT JOIN jobs j ON c.id = j.client_id
GROUP BY c.id
ORDER BY job_count DESC
LIMIT 10;
```

### Multi-Pass Analytics

```sql
-- Compare map vs extracted counts
SELECT
  ei.entity_type,
  COUNT(DISTINCT ei.entity_id) as mapped_count,
  SUM(CASE WHEN eq.status = 'done' THEN 1 ELSE 0 END) as extracted_count,
  SUM(CASE WHEN eq.status = 'failed' THEN 1 ELSE 0 END) as failed_count
FROM entity_inventory ei
LEFT JOIN extract_queue_item eq
  ON ei.entity_type = eq.entity_type
  AND ei.entity_id = eq.entity_id
  AND ei.map_snapshot_id = eq.map_snapshot_id
WHERE ei.map_snapshot_id = '<snapshot-id>'
GROUP BY ei.entity_type;

-- Find entities with most relations
SELECT entity_type, entity_id, estimated_relations_json
FROM entity_inventory
WHERE map_snapshot_id = '<snapshot-id>'
ORDER BY LENGTH(estimated_relations_json) DESC
LIMIT 20;
```

### Performance Analysis

```sql
-- GraphQL query cost summary
SELECT
  query_name,
  COUNT(*) as query_count,
  AVG(actual_cost) as avg_cost,
  MAX(actual_cost) as max_cost,
  SUM(CASE WHEN throttle_status = 'throttled' THEN 1 ELSE 0 END) as throttle_count
FROM graphql_cost
GROUP BY query_name
ORDER BY avg_cost DESC;

-- Migration performance over time
SELECT
  DATE(started_at) as date,
  entity_type,
  SUM(entities_processed) as total_processed,
  SUM(entities_failed) as total_failed,
  AVG(entities_processed * 1.0 /
    (JULIANDAY(completed_at) - JULIANDAY(started_at)) / 86400) as avg_rate
FROM migration_summary
WHERE completed_at IS NOT NULL
GROUP BY DATE(started_at), entity_type
ORDER BY date DESC;
```

---

**Database Schema Documentation** - Complete reference for TightBeam v2 SQLite database
