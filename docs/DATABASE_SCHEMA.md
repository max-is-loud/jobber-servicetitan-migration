# Database Schema Documentation

Complete reference for the TightBeam SQLite database schema, automatically extracted from production code.

**Schema Source:** `src/repositories/repository.py::init_schema()`
**Total Tables:** 18
**Database Engine:** SQLite 3

## Table of Contents

- [Core Entity Tables](#core-entity-tables)
  - [clients](#clients)
  - [invoices](#invoices)
  - [quotes](#quotes)
  - [jobs](#jobs)
  - [properties](#properties)
  - [requests](#requests)
- [Resource Tables](#resource-tables)
  - [users](#users)
  - [products_services](#products_services)
  - [tax_rates](#tax_rates)
- [Content Tables](#content-tables)
  - [notes](#notes)
  - [attachments](#attachments)
- [Time & Expense Tables](#time--expense-tables)
  - [visits](#visits)
  - [timesheet_entries](#timesheet_entries)
  - [expenses](#expenses)
- [System Tables](#system-tables)
  - [oauth_tokens](#oauth_tokens)
  - [migration_state](#migration_state)
  - [note_references](#note_references)
  - [graphql_costs](#graphql_costs)
- [Entity Relationships](#entity-relationships)
- [Indexes](#indexes)
- [Common Queries](#common-queries)

---

## Core Entity Tables

### clients

Primary customer entity representing Jobber account clients.

```sql
CREATE TABLE clients (
    id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    created_at TEXT,
    additional_emails TEXT DEFAULT '[]',  -- JSON array
    additional_phones TEXT DEFAULT '[]'   -- JSON array
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber client ID (primary key) |
| first_name | TEXT | YES | Client's first name |
| last_name | TEXT | YES | Client's last name |
| email | TEXT | YES | Primary email address |
| phone | TEXT | YES | Primary phone number |
| created_at | TEXT | YES | ISO 8601 timestamp |
| additional_emails | TEXT | YES | JSON array of additional emails |
| additional_phones | TEXT | YES | JSON array of additional phones |

**Relationships:**
- Has many: invoices, quotes, jobs, properties, requests, visits

**Notes:**
- `additional_emails` and `additional_phones` added via migration (src/repositories/repository.py:62-65)
- Stores JSON arrays as TEXT

### invoices

Financial invoice entities linked to clients.

```sql
CREATE TABLE invoices (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    number TEXT,
    total_cents INTEGER,
    status TEXT,
    issued_at TEXT,
    due_date TEXT DEFAULT '',
    subtotal INTEGER DEFAULT 0,
    line_items TEXT DEFAULT '[]'  -- JSON array
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber invoice ID (primary key) |
| client_id | TEXT | NO | Foreign key to clients |
| number | TEXT | YES | Invoice number (e.g., "INV-001") |
| total_cents | INTEGER | YES | Total amount in cents |
| status | TEXT | YES | Invoice status (draft, sent, paid, etc.) |
| issued_at | TEXT | YES | ISO 8601 timestamp |
| due_date | TEXT | YES | ISO 8601 date |
| subtotal | INTEGER | YES | Subtotal before taxes in cents |
| line_items | TEXT | YES | JSON array of line items |

**Relationships:**
- Belongs to: clients

**Indexes:**
- `idx_invoices_client_id` on `client_id`

### quotes

Quote/estimate entities for potential work.

```sql
CREATE TABLE quotes (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    quote_number TEXT,
    title TEXT,
    total INTEGER,
    subtotal INTEGER,
    disclaimer TEXT,
    line_items TEXT,  -- JSON array
    created_at TEXT,
    transitioned_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber quote ID (primary key) |
| client_id | TEXT | NO | Foreign key to clients |
| quote_number | TEXT | YES | Quote identifier (e.g., "Q-001") |
| title | TEXT | YES | Quote title/description |
| total | INTEGER | YES | Total amount in cents |
| subtotal | INTEGER | YES | Subtotal before taxes in cents |
| disclaimer | TEXT | YES | Terms and conditions text |
| line_items | TEXT | YES | JSON array of quote line items |
| created_at | TEXT | YES | ISO 8601 timestamp |
| transitioned_at | TEXT | YES | When quote was accepted/declined |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Belongs to: clients
- May convert to: jobs (via jobs.quote_id), requests (via requests.converted_to_quote_id)

**Indexes:**
- `idx_quotes_client_id` on `client_id`

### jobs

Work order entities representing scheduled service work.

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    property_id TEXT REFERENCES properties(id) ON DELETE SET NULL,
    quote_id TEXT REFERENCES quotes(id) ON DELETE SET NULL,
    job_number TEXT,
    title TEXT,
    description TEXT,
    status TEXT,
    scheduled_start_at TEXT,
    scheduled_end_at TEXT,
    completed_at TEXT,
    total INTEGER,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber job ID (primary key) |
| client_id | TEXT | NO | Foreign key to clients (CASCADE delete) |
| property_id | TEXT | YES | Foreign key to properties (SET NULL on delete) |
| quote_id | TEXT | YES | Foreign key to quotes if converted from quote |
| job_number | TEXT | YES | Job identifier (e.g., "J-001") |
| title | TEXT | YES | Job title |
| description | TEXT | YES | Job description/scope |
| status | TEXT | YES | Job status (pending, in_progress, complete, etc.) |
| scheduled_start_at | TEXT | YES | Scheduled start timestamp |
| scheduled_end_at | TEXT | YES | Scheduled end timestamp |
| completed_at | TEXT | YES | Actual completion timestamp |
| total | INTEGER | YES | Total job value in cents |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Belongs to: clients, properties (optional), quotes (optional)
- Has many: expenses, visits, timesheet_entries

**Indexes:**
- `idx_jobs_client_id` on `client_id`
- `idx_jobs_property_id` on `property_id`
- `idx_jobs_quote_id` on `quote_id`

**Cascade Behavior:**
- If client deleted: job is deleted (CASCADE)
- If property deleted: property_id set to NULL
- If quote deleted: quote_id set to NULL

### properties

Service location entities representing client addresses.

```sql
CREATE TABLE properties (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT,
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    state_province TEXT,
    postal_code TEXT,
    country TEXT,
    latitude TEXT,
    longitude TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber property ID (primary key) |
| client_id | TEXT | NO | Foreign key to clients (CASCADE delete) |
| name | TEXT | YES | Property name/label |
| address_line1 | TEXT | YES | Street address line 1 |
| address_line2 | TEXT | YES | Street address line 2 (apt, unit, etc.) |
| city | TEXT | YES | City name |
| state_province | TEXT | YES | State or province |
| postal_code | TEXT | YES | ZIP/postal code |
| country | TEXT | YES | Country name |
| latitude | TEXT | YES | GPS latitude (stored as text) |
| longitude | TEXT | YES | GPS longitude (stored as text) |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Belongs to: clients
- Has many: jobs, requests, visits

**Indexes:**
- `idx_properties_client_id` on `client_id`

### requests

Service request entities representing customer inquiries.

```sql
CREATE TABLE requests (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    property_id TEXT REFERENCES properties(id) ON DELETE SET NULL,
    title TEXT,
    description TEXT,
    status TEXT,
    priority TEXT,
    source TEXT,
    assigned_to TEXT,
    converted_to_quote_id TEXT REFERENCES quotes(id) ON DELETE SET NULL,
    converted_to_job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber request ID (primary key) |
| client_id | TEXT | NO | Foreign key to clients (CASCADE delete) |
| property_id | TEXT | YES | Foreign key to properties |
| title | TEXT | YES | Request title |
| description | TEXT | YES | Request details |
| status | TEXT | YES | Request status (new, converted, cancelled) |
| priority | TEXT | YES | Priority level (low, medium, high) |
| source | TEXT | YES | How request originated (phone, email, web) |
| assigned_to | TEXT | YES | Assigned user name/ID |
| converted_to_quote_id | TEXT | YES | Quote ID if converted |
| converted_to_job_id | TEXT | YES | Job ID if converted directly |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Belongs to: clients, properties (optional)
- May convert to: quotes, jobs

**Indexes:**
- `idx_requests_client_id` on `client_id`
- `idx_requests_property_id` on `property_id`
- `idx_requests_converted_to_quote_id` on `converted_to_quote_id`
- `idx_requests_converted_to_job_id` on `converted_to_job_id`

---

## Resource Tables

### users

Team member entities for staff/technician management.

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    role TEXT,
    is_account_admin TEXT,
    is_account_owner TEXT,
    status TEXT,
    phone TEXT,
    timezone TEXT,
    created_at TEXT,
    last_login_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber user ID (primary key) |
| first_name | TEXT | YES | User's first name |
| last_name | TEXT | YES | User's last name |
| email | TEXT | YES | Email address |
| role | TEXT | YES | User role (admin, technician, office) |
| is_account_admin | TEXT | YES | Boolean stored as text ("true"/"false") |
| is_account_owner | TEXT | YES | Boolean stored as text |
| status | TEXT | YES | Account status (active, inactive) |
| phone | TEXT | YES | Phone number |
| timezone | TEXT | YES | User's timezone |
| created_at | TEXT | YES | Creation timestamp |
| last_login_at | TEXT | YES | Last login timestamp |

**Relationships:**
- Has many: timesheet_entries (as user, approver, or payer)
- Referenced by: visits (assigned_user_id)

**Notes:**
- Booleans stored as TEXT ("true"/"false") due to SQLite limitations

### products_services

Service catalog items and products.

```sql
CREATE TABLE products_services (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    category TEXT,
    default_unit_cost_cents INTEGER,
    internal_unit_cost_cents INTEGER,
    markup_percentage TEXT,
    duration_minutes INTEGER,
    taxable TEXT,
    visible TEXT,
    online_booking_enabled TEXT,
    online_booking_sort_order INTEGER,
    active TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber product/service ID (primary key) |
| name | TEXT | YES | Product/service name |
| description | TEXT | YES | Detailed description |
| category | TEXT | YES | Category classification |
| default_unit_cost_cents | INTEGER | YES | Default price in cents |
| internal_unit_cost_cents | INTEGER | YES | Internal cost in cents |
| markup_percentage | TEXT | YES | Markup % stored as text |
| duration_minutes | INTEGER | YES | Expected service duration |
| taxable | TEXT | YES | Boolean stored as text |
| visible | TEXT | YES | Boolean - show to customers |
| online_booking_enabled | TEXT | YES | Boolean - allow online booking |
| online_booking_sort_order | INTEGER | YES | Display order online |
| active | TEXT | YES | Boolean - currently offered |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Notes:**
- Used in line items for quotes, invoices, and jobs

### tax_rates

Regional tax configuration.

```sql
CREATE TABLE tax_rates (
    id TEXT PRIMARY KEY,
    name TEXT,
    rate_percentage TEXT,
    region TEXT,
    compound TEXT,
    active TEXT,
    description TEXT,
    tax_number TEXT,
    display_order INTEGER,
    default_for_region TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber tax rate ID (primary key) |
| name | TEXT | YES | Tax name (e.g., "GST", "PST", "VAT") |
| rate_percentage | TEXT | YES | Tax rate as percentage text |
| region | TEXT | YES | Geographic region |
| compound | TEXT | YES | Boolean - compound tax |
| active | TEXT | YES | Boolean - currently in use |
| description | TEXT | YES | Tax description |
| tax_number | TEXT | YES | Government tax number |
| display_order | INTEGER | YES | Display order in UI |
| default_for_region | TEXT | YES | Boolean - default for region |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

---

## Content Tables

### notes

Polymorphic note entities that can attach to any parent entity.

```sql
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    message TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber note ID (primary key) |
| entity_type | TEXT | NO | Parent entity type (Client, Invoice, Job, etc.) |
| entity_id | TEXT | NO | Parent entity ID |
| message | TEXT | YES | Note content |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Polymorphic belongs to: clients, invoices, jobs, quotes, etc. (via entity_type + entity_id)
- Has many: attachments

**Indexes:**
- `idx_notes_entity` composite index on `(entity_type, entity_id)`

**Notes:**
- Uses polymorphic association pattern
- Single notes table for all entity types
- Jobber GraphQL returns typed notes (ClientNote, InvoiceNote, etc.)

### attachments

File attachments linked to notes.

```sql
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES notes(id),
    file_name TEXT,
    content_type TEXT,
    original_url TEXT,
    local_file_path TEXT,
    file_size INTEGER,
    created_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber attachment ID (primary key) |
| note_id | TEXT | NO | Foreign key to notes |
| file_name | TEXT | YES | Original filename |
| content_type | TEXT | YES | MIME type (e.g., "image/jpeg") |
| original_url | TEXT | YES | Jobber CDN URL |
| local_file_path | TEXT | YES | Local filesystem path after download |
| file_size | INTEGER | YES | File size in bytes |
| created_at | TEXT | YES | Upload timestamp |

**Relationships:**
- Belongs to: notes

**Indexes:**
- `idx_attachments_note_id` on `note_id`

**Notes:**
- `local_file_path` populated by AttachmentDownloader extractor
- Files downloaded to `attachments/` directory by default

---

## Time & Expense Tables

### visits

Scheduled service visits/appointments.

```sql
CREATE TABLE visits (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    property_id TEXT REFERENCES properties(id) ON DELETE SET NULL,
    assigned_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    title TEXT,
    instructions TEXT,
    status TEXT,
    all_day TEXT,
    duration_minutes INTEGER,
    start_at TEXT,
    end_at TEXT,
    completed_at TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber visit ID (primary key) |
| job_id | TEXT | NO | Foreign key to jobs (CASCADE delete) |
| client_id | TEXT | NO | Foreign key to clients (CASCADE delete) |
| property_id | TEXT | YES | Foreign key to properties |
| assigned_user_id | TEXT | YES | Foreign key to users (assigned technician) |
| title | TEXT | YES | Visit title |
| instructions | TEXT | YES | Special instructions |
| status | TEXT | YES | Visit status (scheduled, in_progress, complete) |
| all_day | TEXT | YES | Boolean - all-day event |
| duration_minutes | INTEGER | YES | Scheduled duration |
| start_at | TEXT | YES | Scheduled start timestamp |
| end_at | TEXT | YES | Scheduled end timestamp |
| completed_at | TEXT | YES | Actual completion timestamp |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Belongs to: jobs, clients, properties (optional), users (optional)
- Has many: timesheet_entries

**Indexes:**
- `idx_visits_job_id` on `job_id`
- `idx_visits_client_id` on `client_id`
- `idx_visits_property_id` on `property_id`
- `idx_visits_assigned_user_id` on `assigned_user_id`

### timesheet_entries

Time tracking records for work performed.

```sql
CREATE TABLE timesheet_entries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    visit_id TEXT REFERENCES visits(id) ON DELETE SET NULL,
    approved_by_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    paid_by_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    label TEXT,
    note TEXT,
    labour_rate TEXT,
    final_duration_seconds INTEGER,
    visit_duration_total_seconds INTEGER,
    approved TEXT,
    ticking TEXT,
    start_at TEXT,
    end_at TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber timesheet entry ID (primary key) |
| user_id | TEXT | NO | Foreign key to users (worker) |
| job_id | TEXT | NO | Foreign key to jobs |
| visit_id | TEXT | YES | Foreign key to visits |
| approved_by_id | TEXT | YES | Foreign key to users (approver) |
| paid_by_id | TEXT | YES | Foreign key to users (payer) |
| label | TEXT | YES | Entry label/category |
| note | TEXT | YES | Additional notes |
| labour_rate | TEXT | YES | Hourly rate (stored as text) |
| final_duration_seconds | INTEGER | YES | Final worked duration |
| visit_duration_total_seconds | INTEGER | YES | Total visit duration |
| approved | TEXT | YES | Boolean - approval status |
| ticking | TEXT | YES | Boolean - currently running |
| start_at | TEXT | YES | Start timestamp |
| end_at | TEXT | YES | End timestamp |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Belongs to: users (worker), jobs, visits (optional)
- References: users (as approver), users (as payer)

**Indexes:**
- `idx_timesheet_entries_user_id` on `user_id`
- `idx_timesheet_entries_job_id` on `job_id`
- `idx_timesheet_entries_visit_id` on `visit_id`
- `idx_timesheet_entries_approved_by_id` on `approved_by_id`
- `idx_timesheet_entries_paid_by_id` on `paid_by_id`

### expenses

Job-related expense tracking.

```sql
CREATE TABLE expenses (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    amount_cents INTEGER,
    description TEXT,
    category TEXT,
    receipt_url TEXT,
    vendor TEXT,
    expense_date TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | TEXT | NO | Jobber expense ID (primary key) |
| job_id | TEXT | NO | Foreign key to jobs (CASCADE delete) |
| amount_cents | INTEGER | YES | Expense amount in cents |
| description | TEXT | YES | Expense description |
| category | TEXT | YES | Expense category |
| receipt_url | TEXT | YES | URL to receipt image/document |
| vendor | TEXT | YES | Vendor name |
| expense_date | TEXT | YES | Date expense occurred |
| created_at | TEXT | YES | Creation timestamp |
| updated_at | TEXT | YES | Last modification timestamp |

**Relationships:**
- Belongs to: jobs

**Indexes:**
- `idx_expenses_job_id` on `job_id`

---

## System Tables

### oauth_tokens

OAuth2 token storage for Jobber API authentication.

```sql
CREATE TABLE oauth_tokens (
    id INTEGER PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | INTEGER | NO | Auto-increment primary key |
| access_token | TEXT | NO | JWT access token |
| refresh_token | TEXT | NO | Refresh token for renewal |
| expires_at | TEXT | NO | Token expiration timestamp |
| created_at | TEXT | NO | Token creation timestamp |

**Notes:**
- Typically contains single row (latest token)
- Managed by OAuth2Manager (src/auth/oauth2_manager.py)
- Tokens refreshed automatically before expiration

### migration_state

Cursor-based resumption state for entity migrations.

```sql
CREATE TABLE migration_state (
    entity_type TEXT PRIMARY KEY,
    last_cursor TEXT,
    updated_at TEXT NOT NULL
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| entity_type | TEXT | NO | Entity type name (primary key) |
| last_cursor | TEXT | YES | GraphQL cursor position |
| updated_at | TEXT | NO | Last update timestamp |

**Entity Types:**
- clients
- invoices
- quotes
- jobs
- properties
- requests
- users
- notes
- attachments
- visits
- timesheet_entries
- expenses
- products_services
- tax_rates

**Notes:**
- Enables `--resume` functionality
- Stores GraphQL pagination cursor per entity type
- Managed by Repository.save_migration_state() and Repository.get_migration_state()

### note_references

Temporary storage for deferred note loading during large migrations.

```sql
CREATE TABLE note_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | INTEGER | NO | Auto-increment primary key |
| note_id | TEXT | NO | Jobber note ID to fetch |
| entity_type | TEXT | NO | Parent entity type |
| entity_id | TEXT | NO | Parent entity ID |
| created_at | TEXT | YES | Reference creation timestamp (auto) |

**Indexes:**
- `idx_note_references_entity` composite index on `(entity_type, entity_id)`

**Notes:**
- Used by NoteReferenceCollector during client/invoice migrations
- Allows deferred note fetching to avoid nested query costs
- See docs/architecture/notes-optimization.md for optimization strategy

### graphql_costs

GraphQL query cost tracking for monitoring and optimization.

```sql
CREATE TABLE graphql_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_type TEXT NOT NULL,
    batch_size INTEGER NOT NULL,
    requested_cost INTEGER NOT NULL,
    actual_cost INTEGER NOT NULL,
    cost_difference INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
)
```

**Columns:**
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | INTEGER | NO | Auto-increment primary key |
| query_type | TEXT | NO | Query identifier (e.g., "clients", "invoices") |
| batch_size | INTEGER | NO | Number of entities in batch |
| requested_cost | INTEGER | NO | Estimated cost before query |
| actual_cost | INTEGER | NO | Actual cost from GraphQL response |
| cost_difference | INTEGER | NO | Difference (actual - requested) |
| timestamp | REAL | NO | Unix timestamp |
| created_at | TEXT | YES | Creation timestamp (auto) |

**Notes:**
- Populated by MetricsCollector when cost monitoring enabled
- Helps identify query optimization opportunities
- Used for rate limit tuning and efficiency analysis

---

## Entity Relationships

### Relationship Diagram (ERD)

```
clients (1) ──< (N) invoices
        │
        ├──< (N) quotes
        │        │
        │        └──> (1) jobs (converted from quote)
        │
        ├──< (N) properties
        │        │
        │        └──< (N) jobs
        │                 │
        │                 ├──< (N) visits
        │                 │        │
        │                 │        └──< (N) timesheet_entries
        │                 │
        │                 └──< (N) expenses
        │
        └──< (N) requests
                 │
                 ├──> (1) quotes (converted to)
                 └──> (1) jobs (converted to)

users (1) ──< (N) timesheet_entries (as worker)
      │
      ├──< (N) timesheet_entries (as approver)
      │
      ├──< (N) timesheet_entries (as payer)
      │
      └──< (N) visits (as assigned user)

notes (N) ──> (1) ANY_ENTITY (polymorphic: entity_type + entity_id)
      │
      └──< (N) attachments
```

### Cascade Behaviors

**ON DELETE CASCADE** (child deleted when parent deleted):
- clients → jobs
- clients → properties
- clients → requests
- clients → visits
- jobs → expenses
- jobs → visits
- jobs → timesheet_entries
- users → timesheet_entries

**ON DELETE SET NULL** (foreign key nulled when parent deleted):
- properties → jobs.property_id
- quotes → jobs.quote_id
- quotes → requests.converted_to_quote_id
- jobs → requests.converted_to_job_id
- users → visits.assigned_user_id
- visits → timesheet_entries.visit_id
- users → timesheet_entries.approved_by_id
- users → timesheet_entries.paid_by_id

---

## Indexes

All indexes defined in `src/repositories/repository.py:402-447`.

### Foreign Key Indexes

```sql
-- Core entities
CREATE INDEX idx_invoices_client_id ON invoices(client_id);
CREATE INDEX idx_quotes_client_id ON quotes(client_id);
CREATE INDEX idx_properties_client_id ON properties(client_id);
CREATE INDEX idx_jobs_client_id ON jobs(client_id);
CREATE INDEX idx_jobs_property_id ON jobs(property_id);
CREATE INDEX idx_jobs_quote_id ON jobs(quote_id);

-- Requests
CREATE INDEX idx_requests_client_id ON requests(client_id);
CREATE INDEX idx_requests_property_id ON requests(property_id);
CREATE INDEX idx_requests_converted_to_quote_id ON requests(converted_to_quote_id);
CREATE INDEX idx_requests_converted_to_job_id ON requests(converted_to_job_id);

-- Time & expense
CREATE INDEX idx_expenses_job_id ON expenses(job_id);
CREATE INDEX idx_visits_job_id ON visits(job_id);
CREATE INDEX idx_visits_client_id ON visits(client_id);
CREATE INDEX idx_visits_property_id ON visits(property_id);
CREATE INDEX idx_visits_assigned_user_id ON visits(assigned_user_id);
CREATE INDEX idx_timesheet_entries_user_id ON timesheet_entries(user_id);
CREATE INDEX idx_timesheet_entries_job_id ON timesheet_entries(job_id);
CREATE INDEX idx_timesheet_entries_visit_id ON timesheet_entries(visit_id);
CREATE INDEX idx_timesheet_entries_approved_by_id ON timesheet_entries(approved_by_id);
CREATE INDEX idx_timesheet_entries_paid_by_id ON timesheet_entries(paid_by_id);

-- Content
CREATE INDEX idx_notes_entity ON notes(entity_type, entity_id);
CREATE INDEX idx_attachments_note_id ON attachments(note_id);
CREATE INDEX idx_note_references_entity ON note_references(entity_type, entity_id);
```

### Performance Notes

- All foreign keys have corresponding indexes for join performance
- Composite index on notes enables fast polymorphic lookups
- Indexes created with `IF NOT EXISTS` for safe re-initialization

---

## Common Queries

### Get client with all related data

```sql
-- Client with invoices and quotes
SELECT
    c.*,
    COUNT(DISTINCT i.id) as invoice_count,
    COUNT(DISTINCT q.id) as quote_count,
    SUM(i.total_cents) as total_invoiced
FROM clients c
LEFT JOIN invoices i ON c.id = i.client_id
LEFT JOIN quotes q ON c.id = q.client_id
WHERE c.id = 'client_123'
GROUP BY c.id;
```

### Get job with all visits and expenses

```sql
SELECT
    j.id,
    j.title,
    j.status,
    j.total,
    COUNT(DISTINCT v.id) as visit_count,
    COUNT(DISTINCT e.id) as expense_count,
    SUM(e.amount_cents) as total_expenses
FROM jobs j
LEFT JOIN visits v ON j.id = v.job_id
LEFT JOIN expenses e ON j.id = e.job_id
WHERE j.id = 'job_456'
GROUP BY j.id;
```

### Get notes for any entity

```sql
-- Notes for a specific client
SELECT n.*, a.file_name, a.local_file_path
FROM notes n
LEFT JOIN attachments a ON n.id = a.note_id
WHERE n.entity_type = 'Client'
  AND n.entity_id = 'client_123'
ORDER BY n.created_at DESC;
```

### Migration state check

```sql
-- Check migration progress for all entities
SELECT
    entity_type,
    last_cursor,
    updated_at,
    CASE
        WHEN last_cursor IS NULL THEN 'Not started'
        ELSE 'In progress'
    END as status
FROM migration_state
ORDER BY updated_at DESC;
```

### Find incomplete work

```sql
-- Jobs without completion date
SELECT j.*, c.first_name, c.last_name
FROM jobs j
JOIN clients c ON j.client_id = c.id
WHERE j.completed_at IS NULL
  AND j.status != 'cancelled'
ORDER BY j.scheduled_start_at;
```

### Time tracking summary

```sql
-- Timesheet summary by user
SELECT
    u.first_name || ' ' || u.last_name as user_name,
    COUNT(t.id) as entry_count,
    SUM(t.final_duration_seconds) / 3600.0 as total_hours,
    COUNT(CASE WHEN t.approved = 'true' THEN 1 END) as approved_count
FROM users u
LEFT JOIN timesheet_entries t ON u.id = t.user_id
WHERE t.created_at >= date('now', '-30 days')
GROUP BY u.id
ORDER BY total_hours DESC;
```

### Revenue analysis

```sql
-- Monthly invoice revenue
SELECT
    strftime('%Y-%m', issued_at) as month,
    COUNT(*) as invoice_count,
    SUM(total_cents) / 100.0 as total_revenue,
    COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count
FROM invoices
GROUP BY month
ORDER BY month DESC;
```

---

## Schema Migrations

### Current Version

No formal versioning system yet. Schema evolves via:
1. `Repository.init_schema()` - Creates tables if not exist
2. `Repository._migrate_existing_tables()` - Adds columns to existing tables

### Migration History

**clients table:**
- Added `additional_emails` column (TEXT, default '[]')
- Added `additional_phones` column (TEXT, default '[]')

**invoices table:**
- Added `due_date` column (TEXT, default '')
- Added `subtotal` column (INTEGER, default 0)
- Added `line_items` column (TEXT, default '[]')

**Source:** `src/repositories/repository.py:44-83`

### Future Enhancements

Planned schema changes documented in:
- `docs/architecture/notes-optimization.md` - Optimized note extraction
- Task system: Consider adding `entities_count` to migration_state table

---

**Last Updated:** 2025-01-17
**Schema Source:** `src/repositories/repository.py` (commit 4026f5c)
**Database Version:** SQLite 3
**Total Tables:** 18
