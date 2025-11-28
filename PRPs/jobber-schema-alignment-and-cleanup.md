# Implementation Plan: Jobber Schema Alignment and Database Cleanup

## Overview
Comprehensive analysis and update of the Tightbeam data pipeline to ensure alignment between:
1. Jobber's actual GraphQL schema (from introspection_results.json)
2. Our GraphQL queries
3. Our entity mappers and transformers
4. Our database schema
5. Removal of deprecated/unused tables

This plan focuses on collecting all real, actual fields available in Jobber data, updating queries to match the current schema, and cleaning up the database.

## Requirements Summary
- Analyze introspection_results.json to understand all available Jobber fields
- Map the complete data flow: GraphQL → Mappers → Database
- Identify field mismatches and missing fields
- Update GraphQL queries to use correct field names
- Update database schema to capture all useful fields
- Remove deprecated/unused database tables
- Clean up database initialization queries

## Research Findings

### Current State Analysis

#### 1. GraphQL Schema Structure (introspection_results.json)
- **26 types total**: 21 OBJECT types, 4 UNION types, 1 SCALAR type
- **Key entities with field counts**:
  - Client: 42 fields (we currently query ~7)
  - Invoice: 35 fields (we currently query ~15)
  - Quote: 30 fields (we currently query ~12)
  - Job: 42 fields (we currently query ~12)
  - Property: 14 fields (we currently query ~5)
  - Request: 23 fields (we currently query ~10)
  - Visit: 30 fields (we currently query ~10)
  - User: 21 fields (we currently query ~6)
  - Expense: 11 fields (we currently query ~8)
  - TimeSheetEntry: 18 fields (we currently query ~10)
  - ProductOrService: 16 fields (we currently query ~8)

#### 2. Current Database Schema (18 tables)
**Core Entity Tables** (14):
- clients, invoices, quotes, jobs, properties, requests, users
- products_services, tax_rates, visits, timesheet_entries, expenses
- notes (polymorphic), attachments

**System Tables** (4):
- oauth_tokens (authentication)
- migration_state (resume tracking)
- note_references (deferred note loading)
- graphql_costs (API cost tracking)

**Additional System Tables** (discovered in repository.py):
- map_snapshot (multi-pass migration)
- entity_inventory (entity counting)
- relation_inventory (relationship tracking)
- extract_queue (entity extraction queue)
- attachment_queue (attachment download queue)

**Total: 22 tables** (not 18 as initially thought)

#### 3. Data Pipeline Architecture
```
Jobber GraphQL API
    ↓ JobberClient (src/clients/jobber_client.py)
GraphQL Response (JSON)
    ↓ EntityMapper (src/mappers/entity_mapper.py)
Domain Models (dataclasses in src/models/)
    ↓ Repository (src/repositories/repository.py)
SQLite Database
```

#### 4. Known Issues from Recent Commits

From git log analysis:
- **b708937**: Updated entity mappers for corrected GraphQL field names
- **4211901**: Added GraphQL schema introspection and restored missing query fields
- **c304d68**: Fixed GraphQL queries to match current Jobber API schema

**Field name corrections made**:
- `status` fields were incorrectly prefixed (e.g., `invoiceStatus` → `status`)
- Attachment URL field: `downloadUrl` → `url`
- Property coordinates: Added but with uncertainty

### Reference Implementations

#### Pattern: Two-Query Mode System
1. **Map Mode** (lightweight discovery): 5-10 GraphQL points
   - Fetches: id, updatedAt, totalCount for nested relationships
   - Purpose: Discover what exists, what changed

2. **Full Extraction Mode**: 100-500 GraphQL points
   - Fetches: All entity fields + nested relationships
   - Purpose: Complete data extraction

#### Pattern: Deferred Note Loading
- Phase 1: Collect note IDs during entity extraction
- Phase 2: Bulk fetch notes by ID using polymorphic query
- Benefit: 60-70% cost reduction

#### Pattern: Adaptive Pagination
- Dynamic page size adjustment based on GraphQL cost throttling
- Default sizes: clients=50, nested_notes=10, etc.
- Auto-adjusts when hitting rate limits

### Technology Decisions

1. **Introspection Analysis**: Python script to parse introspection_results.json
2. **Field Mapping Audit**: Automated comparison of available vs. used fields
3. **Schema Updates**: SQLite ALTER TABLE for backward-compatible additions
4. **Deprecated Table Removal**: Manual verification + DROP TABLE statements
5. **Query Updates**: Direct string updates in jobber_client.py

## Implementation Tasks

### Phase 1: Discovery and Analysis

#### Task 1.1: Parse Introspection Results
**Description**: Create a comprehensive field inventory from introspection_results.json

**Files to create**:
- `scripts/analyze_introspection.py` - Parse JSON and generate field reports

**Script output**:
- Field inventory by entity (CSV/JSON)
- Field type mapping
- Nested relationship structure
- Complex type definitions (InvoiceAmounts, QuoteAmounts, etc.)

**Acceptance criteria**:
- Complete list of all 26 types with field details
- Identification of scalar vs. object vs. union types
- Documentation of nested structures

**Estimated effort**: 2 hours

---

#### Task 1.2: Audit Current GraphQL Queries
**Description**: Extract all fields currently queried from jobber_client.py

**Files to analyze**:
- `src/clients/jobber_client.py` (lines 46-669: full queries)
- `src/clients/jobber_client.py` (lines 2766-3194: map queries)
- `src/clients/jobber_client.py` (lines 672-777: note-by-id query)

**Script to create**:
- `scripts/audit_queries.py` - Parse query strings and extract field names

**Output**:
- Per-entity field usage report
- Comparison: Available vs. Queried fields
- Missing high-value fields (e.g., Client.balance, Invoice.amounts)

**Acceptance criteria**:
- CSV/JSON report of current field usage by entity
- Gap analysis highlighting unused fields

**Estimated effort**: 2 hours

---

#### Task 1.3: Audit Entity Mappers
**Description**: Verify all mapper transformations handle queried fields correctly

**Files to analyze**:
- `src/mappers/entity_mapper.py` (all map_* methods)
- `src/mappers/mapper_utils.py` (transformation utilities)

**Checks**:
- ✅ Does mapper extract all queried fields?
- ✅ Are field name transformations correct? (camelCase → snake_case)
- ✅ Are data type conversions appropriate? (Money → cents, ISO8601 → string)
- ❌ Any fields queried but not mapped?
- ❌ Any fields mapped but not stored in database?

**Output**:
- Mapper audit report (markdown)
- List of unmapped fields
- List of transformation errors

**Acceptance criteria**:
- Complete mapper coverage verification
- Documentation of transformation logic

**Estimated effort**: 2 hours

---

#### Task 1.4: Audit Database Schema
**Description**: Compare database schema against entity mappers

**Files to analyze**:
- `src/repositories/repository.py` (lines 134-580: CREATE TABLE statements)
- `src/models/*.py` (dataclass definitions)

**Analysis**:
- For each entity: mapper output → database columns
- Identify missing columns for mapped fields
- Identify unused columns (no longer mapped)
- Check data types match (INTEGER for cents, TEXT for JSON, etc.)

**Output**:
- Schema coverage report
- Missing column list (with proposed types)
- Deprecated column list (for removal consideration)

**Acceptance criteria**:
- Complete schema audit documentation
- SQL statements for schema updates

**Estimated effort**: 3 hours

---

#### Task 1.5: Identify Deprecated Tables
**Description**: Find tables that are no longer used by the codebase

**Method**:
1. List all tables from repository.py init_schema()
2. For each table, grep codebase for references
3. Check if table is populated by any extractor
4. Verify table is queried by any feature

**Tables to investigate**:
- `relation_inventory` - Relationship tracking (multi-pass feature?)
- `extract_queue` - Entity extraction queue (still used?)
- Potentially others based on git history

**Output**:
- Deprecation report with usage analysis
- Recommendation: KEEP, DEPRECATE, or REMOVE
- Migration script for safe removal

**Acceptance criteria**:
- Usage report for all 22 tables
- Safe removal plan for deprecated tables

**Estimated effort**: 3 hours

---

### Phase 2: GraphQL Query Updates

#### Task 2.1: Update Client Query
**Description**: Add missing high-value fields to client query

**Fields to add** (based on introspection):
- `balance` (Float) - Outstanding balance
- `companyName` (String) - Company name if business client
- `billingAddress` (ClientAddress) - Billing address object
- `isArchivable` (Boolean) - Archive status

**Files to modify**:
- `src/clients/jobber_client.py` (lines 46-114: _get_clients_query)
- `src/clients/jobber_client.py` (lines 2766-2791: _get_clients_map_query)

**Considerations**:
- ClientAddress is nested object (10 fields)
- May need to flatten address fields in mapper
- Balance is financial data (store as cents?)

**Acceptance criteria**:
- Updated query with new fields
- Cost impact analysis (<10% increase acceptable)

**Estimated effort**: 1 hour

---

#### Task 2.2: Update Invoice Query
**Description**: Add amounts object and missing fields

**Fields to add**:
- `amounts { total subtotal tax discount deposits }` (InvoiceAmounts object)
- `dueDate` (ISO8601DateTime) - Already in DB, ensure queried
- `invoiceNet` (Int) - Net amount
- `client { id companyName }` - Ensure client relationship

**Current issue**:
- We query individual amount fields but InvoiceAmounts object provides structured data
- Missing subtotal breakdown

**Files to modify**:
- `src/clients/jobber_client.py` (lines 116-189: _get_invoices_query)
- `src/mappers/entity_mapper.py` (lines 95-160: map_invoice)

**Acceptance criteria**:
- Amounts object properly queried and mapped
- All financial fields stored as cents

**Estimated effort**: 1.5 hours

---

#### Task 2.3: Update Quote Query
**Description**: Add amounts object and line item details

**Fields to add**:
- `amounts { total subtotal tax discount }` (QuoteAmounts object)
- Line item expansion (currently we get basic fields)

**Current state**:
- We store line_items as JSON but may be missing fields
- QuoteAmounts object provides consistent financial structure

**Files to modify**:
- `src/clients/jobber_client.py` (lines 191-269: _get_quotes_query)
- `src/mappers/entity_mapper.py` (lines 162-240: map_quote)

**Acceptance criteria**:
- Structured amounts object
- Complete line item data

**Estimated effort**: 1.5 hours

---

#### Task 2.4: Update Job Query
**Description**: Add billing, completion, and relationship fields

**Fields to add**:
- `billingType` (BillingStrategy) - Billing strategy
- `completedAt` (ISO8601DateTime) - Completion timestamp
- `instructions` (String) - Job instructions
- `arrivalWindow` (ArrivalWindow) - Scheduling window
- `invoicedTotal` (Float) - Amount invoiced

**Files to modify**:
- `src/clients/jobber_client.py` (lines 286-352: _get_jobs_query)
- `src/mappers/entity_mapper.py` (lines 411-482: map_job)

**Acceptance criteria**:
- Enhanced job data with billing and completion tracking
- Instructions field for job context

**Estimated effort**: 1.5 hours

---

#### Task 2.5: Update Property Query
**Description**: Add property details and tax information

**Fields to add**:
- `name` (String) - Property name/identifier
- `taxRate { id name rate }` - Tax rate relationship
- `isBillingAddress` (Boolean) - Billing address flag
- `routingOrder` (Int) - Service routing order

**Current issue**:
- We have address fields but missing property metadata
- Tax rate relationship not captured

**Files to modify**:
- `src/clients/jobber_client.py` (lines 354-391: _get_properties_query)
- `src/mappers/entity_mapper.py` (lines 484-546: map_property)

**Acceptance criteria**:
- Property name and metadata captured
- Tax rate relationship stored

**Estimated effort**: 1 hour

---

#### Task 2.6: Update Request Query
**Description**: Verify field names and add conversion tracking

**Fields to verify**:
- ✅ Status field (confirm it's not `requestStatus`)
- Add conversion relationships if missing

**Investigation needed**:
- Recent commit mentioned `requestStatus` correction
- Verify current query uses correct field name

**Files to check**:
- `src/clients/jobber_client.py` (lines 393-465: _get_requests_query)
- `src/mappers/entity_mapper.py` (lines 548-619: map_request)

**Acceptance criteria**:
- Correct field names confirmed
- Conversion tracking fields added if useful

**Estimated effort**: 1 hour

---

#### Task 2.7: Update Visit Query
**Description**: Add completion tracking and assignment details

**Fields to add**:
- `completedAt` (ISO8601DateTime) - Completion timestamp
- `completedBy` (String) - Who completed visit
- `allDay` (Boolean) - All-day event flag
- `clientConfirmed` (Boolean) - Client confirmation status

**Files to modify**:
- `src/clients/jobber_client.py` (lines 540-579: _get_visits_query)
- `src/mappers/entity_mapper.py` (lines 755-833: map_visit)

**Acceptance criteria**:
- Completion tracking fields added
- Client confirmation status captured

**Estimated effort**: 1 hour

---

#### Task 2.8: Update User Query
**Description**: Add admin flags and scheduling availability

**Fields to add**:
- `isAccountAdmin` (Boolean) - Admin flag
- `isAccountOwner` (Boolean) - Owner flag
- `availableForScheduling` (Boolean) - Scheduling availability
- `assignedColor` (String) - Calendar color

**Files to modify**:
- `src/clients/jobber_client.py` (lines 471-501: USERS_QUERY)
- `src/mappers/entity_mapper.py` (lines 621-691: map_user)

**Acceptance criteria**:
- Admin and owner flags stored
- Scheduling metadata captured

**Estimated effort**: 1 hour

---

#### Task 2.9: Add Missing Note Type Fragments
**Description**: Complete polymorphic note coverage

**Current issue**:
- NOTE_BY_ID_QUERY has fragments for: ClientNote, JobNote, QuoteNote, InvoiceNote, RequestNote
- Missing: PropertyNote, VisitNote (properties and visits can have notes)

**Files to modify**:
- `src/clients/jobber_client.py` (lines 672-777: NOTE_BY_ID_QUERY)

**Changes needed**:
```graphql
... on PropertyNote {
  id
  message
  property { id }
  createdAt
  updatedAt
  attachments { edges { node { ... } } }
}
... on VisitNote {
  id
  message
  visit { id }
  createdAt
  updatedAt
  attachments { edges { node { ... } } }
}
```

**Acceptance criteria**:
- All note types covered
- No query failures for property/visit notes

**Estimated effort**: 0.5 hours

---

### Phase 3: Entity Mapper Updates

#### Task 3.1: Update Client Mapper
**Description**: Handle new client fields

**New mappings needed**:
- `balance` → `balance_cents` (Float → int conversion)
- `companyName` → `company_name` (String)
- `billingAddress` → Flatten to `billing_street`, `billing_city`, etc.
- `isArchivable` → `is_archivable` (Boolean)

**Files to modify**:
- `src/mappers/entity_mapper.py` (lines 34-93: map_client)
- `src/models/client.py` (add new fields to dataclass)

**Considerations**:
- ClientAddress has 10 fields - decide which to store
- Balance should use cents for precision

**Acceptance criteria**:
- All new fields properly mapped
- Data type conversions correct

**Estimated effort**: 1.5 hours

---

#### Task 3.2: Update Invoice Mapper
**Description**: Use InvoiceAmounts object for structured financial data

**Current approach**:
- We extract individual amount fields

**New approach**:
- Extract from `amounts` object: `total`, `subtotal`, `tax`, `discount`, `deposits`
- Store each as cents (int)

**Files to modify**:
- `src/mappers/entity_mapper.py` (lines 95-160: map_invoice)
- `src/models/invoice.py` (update dataclass)

**Acceptance criteria**:
- InvoiceAmounts object properly parsed
- All financial fields as cents

**Estimated effort**: 1 hour

---

#### Task 3.3: Update Quote Mapper
**Description**: Use QuoteAmounts object

**Similar to invoice mapper**:
- Extract from `amounts` object
- Store as cents

**Files to modify**:
- `src/mappers/entity_mapper.py` (lines 162-240: map_quote)
- `src/models/quote.py` (update dataclass)

**Acceptance criteria**:
- QuoteAmounts object properly parsed
- Consistent with invoice mapper pattern

**Estimated effort**: 1 hour

---

#### Task 3.4: Update Job Mapper
**Description**: Add new job metadata fields

**New mappings**:
- `billingType` → `billing_type` (enum/string)
- `completedAt` → `completed_at` (ISO8601 → string)
- `instructions` → `instructions` (text)
- `invoicedTotal` → `invoiced_total_cents` (float → int)

**Files to modify**:
- `src/mappers/entity_mapper.py` (lines 411-482: map_job)
- `src/models/job.py` (update dataclass)

**Acceptance criteria**:
- Completion tracking fields mapped
- Instructions text stored

**Estimated effort**: 1 hour

---

#### Task 3.5: Update Property Mapper
**Description**: Add property metadata and tax relationship

**New mappings**:
- `name` → `name` (string)
- `taxRate.id` → `tax_rate_id` (foreign key)
- `isBillingAddress` → `is_billing_address` (boolean)
- `routingOrder` → `routing_order` (int)

**Files to modify**:
- `src/mappers/entity_mapper.py` (lines 484-546: map_property)
- `src/models/property.py` (update dataclass)

**Acceptance criteria**:
- Property name and metadata stored
- Tax rate foreign key captured

**Estimated effort**: 1 hour

---

#### Task 3.6: Update Visit Mapper
**Description**: Add completion and confirmation fields

**New mappings**:
- `completedAt` → `completed_at`
- `completedBy` → `completed_by`
- `allDay` → `all_day`
- `clientConfirmed` → `client_confirmed`

**Files to modify**:
- `src/mappers/entity_mapper.py` (lines 755-833: map_visit)
- `src/models/visit.py` (update dataclass)

**Acceptance criteria**:
- Completion tracking stored
- Client confirmation flag captured

**Estimated effort**: 1 hour

---

#### Task 3.7: Update User Mapper
**Description**: Add admin and scheduling fields

**New mappings**:
- `isAccountAdmin` → `is_account_admin`
- `isAccountOwner` → `is_account_owner`
- `availableForScheduling` → `available_for_scheduling`
- `assignedColor` → `assigned_color`

**Files to modify**:
- `src/mappers/entity_mapper.py` (lines 621-691: map_user)
- `src/models/user.py` (update dataclass)

**Acceptance criteria**:
- Admin flags stored
- Scheduling metadata captured

**Estimated effort**: 1 hour

---

### Phase 4: Database Schema Updates

#### Task 4.1: Add Client Table Columns
**Description**: Extend clients table for new fields

**Migration SQL**:
```sql
ALTER TABLE clients ADD COLUMN balance_cents INTEGER DEFAULT 0;
ALTER TABLE clients ADD COLUMN company_name TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN billing_street TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN billing_city TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN billing_state TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN billing_postal_code TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN billing_country TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN is_archivable INTEGER DEFAULT 0;  -- SQLite boolean
```

**Files to modify**:
- `src/repositories/repository.py` (_migrate_existing_tables method)
- `src/models/client.py` (dataclass fields)

**Acceptance criteria**:
- Backward-compatible ALTER TABLE statements
- Conditional column addition (check if exists first)

**Estimated effort**: 1 hour

---

#### Task 4.2: Add Invoice Table Columns
**Description**: Add missing financial breakdown fields

**Migration SQL**:
```sql
ALTER TABLE invoices ADD COLUMN tax_cents INTEGER DEFAULT 0;
ALTER TABLE invoices ADD COLUMN discount_cents INTEGER DEFAULT 0;
ALTER TABLE invoices ADD COLUMN deposits_cents INTEGER DEFAULT 0;
ALTER TABLE invoices ADD COLUMN invoice_net INTEGER DEFAULT 0;
```

**Files to modify**:
- `src/repositories/repository.py`
- `src/models/invoice.py`

**Acceptance criteria**:
- All InvoiceAmounts fields stored
- Consistent cents-based storage

**Estimated effort**: 1 hour

---

#### Task 4.3: Add Quote Table Columns
**Description**: Add QuoteAmounts fields

**Migration SQL**:
```sql
ALTER TABLE quotes ADD COLUMN tax_cents INTEGER DEFAULT 0;
ALTER TABLE quotes ADD COLUMN discount_cents INTEGER DEFAULT 0;
```

**Files to modify**:
- `src/repositories/repository.py`
- `src/models/quote.py`

**Acceptance criteria**:
- QuoteAmounts fields stored
- Consistent with invoice pattern

**Estimated effort**: 1 hour

---

#### Task 4.4: Add Job Table Columns
**Description**: Add job metadata and completion tracking

**Migration SQL**:
```sql
ALTER TABLE jobs ADD COLUMN billing_type TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN completed_at TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN instructions TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN invoiced_total_cents INTEGER DEFAULT 0;
```

**Files to modify**:
- `src/repositories/repository.py`
- `src/models/job.py`

**Acceptance criteria**:
- Completion tracking fields added
- Instructions text storage

**Estimated effort**: 1 hour

---

#### Task 4.5: Add Property Table Columns
**Description**: Add property metadata and tax relationship

**Migration SQL**:
```sql
ALTER TABLE properties ADD COLUMN name TEXT DEFAULT '';
ALTER TABLE properties ADD COLUMN tax_rate_id TEXT DEFAULT '';
ALTER TABLE properties ADD COLUMN is_billing_address INTEGER DEFAULT 0;
ALTER TABLE properties ADD COLUMN routing_order INTEGER DEFAULT 0;
```

**Files to modify**:
- `src/repositories/repository.py`
- `src/models/property.py`

**Acceptance criteria**:
- Property name and metadata stored
- Tax rate foreign key indexed

**Estimated effort**: 1 hour

---

#### Task 4.6: Add Visit Table Columns
**Description**: Add completion and confirmation tracking

**Migration SQL**:
```sql
ALTER TABLE visits ADD COLUMN completed_at TEXT DEFAULT '';
ALTER TABLE visits ADD COLUMN completed_by TEXT DEFAULT '';
ALTER TABLE visits ADD COLUMN all_day INTEGER DEFAULT 0;
ALTER TABLE visits ADD COLUMN client_confirmed INTEGER DEFAULT 0;
```

**Files to modify**:
- `src/repositories/repository.py`
- `src/models/visit.py`

**Acceptance criteria**:
- Completion tracking stored
- Client confirmation flag

**Estimated effort**: 1 hour

---

#### Task 4.7: Add User Table Columns
**Description**: Add admin and scheduling metadata

**Migration SQL**:
```sql
ALTER TABLE users ADD COLUMN is_account_admin INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN is_account_owner INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN available_for_scheduling INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN assigned_color TEXT DEFAULT '';
```

**Files to modify**:
- `src/repositories/repository.py`
- `src/models/user.py`

**Acceptance criteria**:
- Admin flags stored
- Scheduling metadata captured

**Estimated effort**: 1 hour

---

### Phase 5: Database Cleanup

#### Task 5.1: Analyze Table Usage
**Description**: Verify which tables are actively used

**Method**:
1. For each of 22 tables, search codebase for:
   - INSERT statements
   - SELECT statements
   - References in extractors
   - References in CLI commands

**Tables to verify**:
- ✅ Core entities (clients, invoices, etc.) - KEEP
- ✅ notes, attachments - KEEP
- ✅ oauth_tokens - KEEP (authentication)
- ✅ migration_state - KEEP (resume functionality)
- ✅ note_references - KEEP (deferred loading)
- ✅ graphql_costs - KEEP (cost tracking)
- ❓ map_snapshot - Verify multi-pass usage
- ❓ entity_inventory - Verify counting usage
- ❓ relation_inventory - Check relationship tracking
- ❓ extract_queue - Check extraction queue usage
- ❓ attachment_queue - Check attachment queue usage

**Output**:
- Usage report for each table
- Recommendation: KEEP or REMOVE

**Acceptance criteria**:
- Complete usage analysis
- Clear recommendations with justification

**Estimated effort**: 2 hours

---

#### Task 5.2: Review Multi-Pass Tables
**Description**: Verify map_snapshot, entity_inventory, relation_inventory usage

**Files to check**:
- Search for "map_snapshot" references
- Search for "entity_inventory" references
- Search for "relation_inventory" references

**Questions**:
- Are these used by the multi-pass migration strategy?
- Are they populated by current extractors?
- Are they queried by any commands?

**Acceptance criteria**:
- Clear understanding of multi-pass table purposes
- Decision: KEEP (if used) or REMOVE (if deprecated)

**Estimated effort**: 1 hour

---

#### Task 5.3: Review Queue Tables
**Description**: Verify extract_queue and attachment_queue usage

**Files to check**:
- Search for "extract_queue" references
- Search for "attachment_queue" references
- Check if extractors use queue pattern

**Questions**:
- Are queues still used for batch processing?
- Or are extractions now synchronous?

**Acceptance criteria**:
- Understanding of queue table purposes
- Decision: KEEP or REMOVE

**Estimated effort**: 1 hour

---

#### Task 5.4: Create Removal Migration (if needed)
**Description**: If tables are deprecated, create safe removal script

**Only if tables are confirmed unused**:
```sql
-- Backup first
.backup backup_before_cleanup.db

-- Drop unused tables
DROP TABLE IF EXISTS relation_inventory;
DROP TABLE IF EXISTS extract_queue;
-- etc.
```

**Safety checks**:
- Create database backup
- Test on copy first
- Document removed tables for rollback

**Files to modify**:
- Create `migrations/cleanup_unused_tables.sql`
- Update `docs/DATABASE_SCHEMA.md`

**Acceptance criteria**:
- Safe removal script with backup
- Documentation updated

**Estimated effort**: 1 hour

---

#### Task 5.5: Update Database Initialization
**Description**: Clean up init_schema() to remove unused table creation

**Files to modify**:
- `src/repositories/repository.py` (init_schema method)

**Changes**:
- Remove CREATE TABLE statements for deprecated tables
- Update comments to reflect current schema
- Ensure indexes are only for active tables

**Acceptance criteria**:
- init_schema() only creates used tables
- Clean, documented schema initialization

**Estimated effort**: 1 hour

---

### Phase 6: Testing and Validation

#### Task 6.1: Create Schema Validation Tests
**Description**: Test that all fields are correctly mapped from GraphQL to database

**Test cases**:
1. For each entity:
   - Mock GraphQL response with all fields
   - Run through mapper
   - Verify database insert
   - Verify all fields stored correctly

2. Data type validation:
   - Money fields → cents (integer)
   - Dates → ISO8601 strings
   - JSON fields → valid JSON
   - Foreign keys → valid references

**Files to create**:
- `tests/integration/test_complete_pipeline.py`
- `tests/unit/test_enhanced_mappers.py`

**Acceptance criteria**:
- All entities tested end-to-end
- All new fields verified

**Estimated effort**: 4 hours

---

#### Task 6.2: Test Database Migrations
**Description**: Verify ALTER TABLE statements work on existing databases

**Test scenarios**:
1. Fresh database → all tables created correctly
2. Existing database → migrations add columns without errors
3. Idempotent migrations → running twice doesn't break

**Test database states**:
- Empty database
- Database with v1 schema (before this change)
- Database with v2 schema (after this change)

**Acceptance criteria**:
- Migrations succeed on all database states
- No data loss
- Backward compatibility maintained

**Estimated effort**: 2 hours

---

#### Task 6.3: Test Query Cost Impact
**Description**: Verify updated queries don't exceed cost budgets

**Method**:
1. Run updated queries against Jobber API
2. Capture GraphQL cost from response headers
3. Compare to baseline costs

**Acceptable thresholds**:
- Client query: <120 points (baseline ~100)
- Invoice query: <150 points (baseline ~120)
- Job query: <150 points (baseline ~120)
- Other entities: <20% increase

**Acceptance criteria**:
- Cost increase under 20% for all queries
- No queries exceed 500 points

**Estimated effort**: 2 hours

---

#### Task 6.4: Integration Test: Full Extraction
**Description**: Run complete extraction with updated schema

**Test procedure**:
1. Create fresh test database
2. Run all extractors (clients, jobs, invoices, etc.)
3. Verify all entities extracted
4. Verify all new fields populated
5. Check database integrity

**Success metrics**:
- All extractors complete without errors
- New fields populated with data (not all NULL)
- Database passes integrity checks

**Acceptance criteria**:
- Successful full extraction
- New fields populated appropriately

**Estimated effort**: 3 hours

---

#### Task 6.5: Create Field Coverage Report
**Description**: Document which Jobber fields are now captured

**Report contents**:
1. For each entity:
   - Total fields available (from introspection)
   - Fields queried
   - Fields stored in database
   - Coverage percentage

2. High-value uncaptured fields (for future consideration)

**Output**:
- `docs/field_coverage_report.md`
- Summary statistics

**Acceptance criteria**:
- Complete coverage documentation
- Baseline for future enhancements

**Estimated effort**: 2 hours

---

## Codebase Integration Points

### Files to Modify

#### GraphQL Queries
- `src/clients/jobber_client.py`
  - Lines 46-669: Full extraction queries
  - Lines 2766-3194: Map mode queries
  - Lines 672-777: Note polymorphic query

#### Entity Mappers
- `src/mappers/entity_mapper.py`
  - Lines 34-93: map_client
  - Lines 95-160: map_invoice
  - Lines 162-240: map_quote
  - Lines 411-482: map_job
  - Lines 484-546: map_property
  - Lines 548-619: map_request
  - Lines 755-833: map_visit
  - Lines 621-691: map_user

#### Database Schema
- `src/repositories/repository.py`
  - Lines 63-133: _migrate_existing_tables
  - Lines 134-580: init_schema

#### Domain Models
- `src/models/client.py`
- `src/models/invoice.py`
- `src/models/quote.py`
- `src/models/job.py`
- `src/models/property.py`
- `src/models/visit.py`
- `src/models/user.py`

### New Files to Create

#### Analysis Scripts
- `scripts/analyze_introspection.py` - Parse introspection_results.json
- `scripts/audit_queries.py` - Extract queried fields from queries
- `scripts/compare_coverage.py` - Compare available vs. captured fields

#### Migration Scripts
- `migrations/cleanup_unused_tables.sql` - Safe table removal (if needed)

#### Tests
- `tests/integration/test_complete_pipeline.py` - End-to-end field mapping tests
- `tests/unit/test_enhanced_mappers.py` - Unit tests for new mapper logic

#### Documentation
- `docs/field_coverage_report.md` - Coverage analysis and statistics

### Existing Patterns to Follow

#### Pattern 1: Field Mapping Convention
```python
# GraphQL: camelCase → Database: snake_case
# GraphQL: Money/Float → Database: INTEGER (cents)
# GraphQL: ISO8601DateTime → Database: TEXT (ISO string)
# GraphQL: Boolean → Database: INTEGER (0/1)
# GraphQL: Object → Database: TEXT (JSON) or flattened fields
```

#### Pattern 2: Mapper Utilities
```python
# Use MapperUtils for transformations
MapperUtils.convert_to_cents(amount)  # Float → cents
MapperUtils.format_iso_datetime(dt)   # ISO8601 → string
MapperUtils.extract_primary_field(array, field, marker)  # Extract primary
MapperUtils.serialize_json_field(obj)  # Object → JSON
```

#### Pattern 3: Database Migration
```python
# Check column exists before adding
cursor.execute("PRAGMA table_info(table_name)")
columns = {row[1] for row in cursor.fetchall()}
if "column_name" not in columns:
    cursor.execute("ALTER TABLE table_name ADD COLUMN column_name TYPE DEFAULT value")
```

#### Pattern 4: Nested Object Handling
```python
# Option A: Flatten to multiple columns
billing_address = data.get("billingAddress", {})
billing_street = billing_address.get("street", "")
billing_city = billing_address.get("city", "")

# Option B: Store as JSON
line_items = data.get("lineItems", {}).get("edges", [])
line_items_json = json.dumps([edge["node"] for edge in line_items])
```

## Technical Design

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  Jobber GraphQL API                              │
│              (introspection_results.json)                        │
│                                                                   │
│  Client: 42 fields    Invoice: 35 fields    Job: 42 fields      │
│  Quote: 30 fields     Property: 14 fields   Visit: 30 fields    │
│  User: 21 fields      Expense: 11 fields    etc.                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    JobberClient Queries
                  (jobber_client.py)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   GraphQL Response (JSON)                        │
│                                                                   │
│  {                                                                │
│    "clients": {                                                   │
│      "edges": [                                                   │
│        { "node": {                                                │
│          "id": "...",                                             │
│          "firstName": "...",                                      │
│          "balance": 150.00,     ← NEW                            │
│          "companyName": "...",  ← NEW                            │
│          "billingAddress": {    ← NEW                            │
│            "street": "...",                                       │
│            "city": "..."                                          │
│          }                                                        │
│        }}                                                         │
│      ]                                                            │
│    }                                                              │
│  }                                                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                      EntityMapper
                  (entity_mapper.py)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Domain Model (Dataclass)                      │
│                                                                   │
│  Client(                                                          │
│    id="...",                                                      │
│    first_name="...",                                              │
│    last_name="...",                                               │
│    balance_cents=15000,           ← NEW (float → cents)          │
│    company_name="...",            ← NEW                          │
│    billing_street="...",          ← NEW (flattened)              │
│    billing_city="...",            ← NEW (flattened)              │
│    is_archivable=True             ← NEW (bool → int)             │
│  )                                                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                        Repository
                   (repository.py)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      SQLite Database                             │
│                                                                   │
│  CREATE TABLE clients (                                          │
│    id TEXT PRIMARY KEY,                                          │
│    first_name TEXT,                                              │
│    last_name TEXT,                                               │
│    email TEXT,                                                   │
│    phone TEXT,                                                   │
│    balance_cents INTEGER DEFAULT 0,      ← NEW                  │
│    company_name TEXT DEFAULT '',          ← NEW                  │
│    billing_street TEXT DEFAULT '',        ← NEW                  │
│    billing_city TEXT DEFAULT '',          ← NEW                  │
│    billing_state TEXT DEFAULT '',         ← NEW                  │
│    billing_postal_code TEXT DEFAULT '',   ← NEW                  │
│    is_archivable INTEGER DEFAULT 0,       ← NEW                  │
│    created_at TEXT,                                              │
│    updated_at TEXT                                               │
│  );                                                               │
│                                                                   │
│  [Similar enhancements for all 14 entity tables]                │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Example: Client Balance Field

```
1. GraphQL Query (jobber_client.py)
   query GetClients {
     clients(first: 50) {
       edges {
         node {
           balance     ← Add this field
         }
       }
     }
   }

2. GraphQL Response
   {
     "data": {
       "clients": {
         "edges": [
           { "node": { "balance": 150.00 } }
         ]
       }
     }
   }

3. Entity Mapper (entity_mapper.py)
   def map_client(self, data):
       balance = data.get("balance", 0.0)
       balance_cents = MapperUtils.convert_to_cents(balance)
       # 150.00 → 15000

       return Client(
           balance_cents=balance_cents
       )

4. Repository (repository.py)
   Migration:
   ALTER TABLE clients ADD COLUMN balance_cents INTEGER DEFAULT 0;

   Insert:
   INSERT INTO clients (balance_cents) VALUES (15000);

5. Database Storage
   clients table:
   | id  | first_name | balance_cents |
   |-----|------------|---------------|
   | 123 | John       | 15000         |
```

### Field Addition Decision Matrix

For each field in introspection_results.json, decide:

| Criteria | Action | Example |
|----------|--------|---------|
| **High business value** + Used in app | ✅ ADD | Client.balance, Invoice.amounts |
| **Metadata** + Useful for debugging | ✅ ADD | Job.completedAt, User.isAccountAdmin |
| **Relationship** + Improves data model | ✅ ADD | Property.taxRate, Request conversions |
| **Complex nested object** + Rarely needed | ⚠️ CONSIDER | Custom fields, complex line items |
| **Low value** + Rarely queried | ❌ SKIP | UI-specific fields, display helpers |
| **Deprecated** + Not in current API | ❌ SKIP | Old field names |

## Dependencies and Libraries

**Existing (no new dependencies)**:
- `sqlite3` - Database operations
- `json` - JSON serialization for nested fields
- `dataclasses` - Domain models
- `typing` - Type hints

**Development/Testing**:
- `pytest` - Testing framework (already in use)
- Python 3.14 standard library

## Testing Strategy

### Unit Tests
- **Mapper tests**: Mock GraphQL responses → verify dataclass output
- **Utility tests**: Test MapperUtils transformations
- **Model tests**: Verify dataclass field types

### Integration Tests
- **Pipeline tests**: GraphQL mock → Mapper → Repository → Database
- **Migration tests**: Verify ALTER TABLE statements on various database states
- **Field coverage tests**: Ensure all queried fields are stored

### Edge Cases to Cover
1. **NULL values**: Fields that may be null in GraphQL
2. **Missing nested objects**: Handle missing billingAddress gracefully
3. **Empty arrays**: lineItems = []
4. **Large JSON blobs**: Ensure JSON serialization doesn't break
5. **Backward compatibility**: Existing databases with old schema
6. **Idempotent migrations**: Running migrations multiple times

### Performance Tests
- **Query cost**: Verify new queries don't exceed budgets
- **Extraction speed**: Ensure new fields don't slow down extraction
- **Database size**: Monitor database size increase

## Success Criteria

### Phase 1: Discovery ✅
- [ ] Complete field inventory from introspection_results.json
- [ ] Query audit report showing current vs. available fields
- [ ] Mapper audit confirming correct transformations
- [ ] Schema audit identifying missing/deprecated columns
- [ ] Deprecated table usage analysis

### Phase 2: GraphQL Queries ✅
- [ ] All entity queries updated with high-value fields
- [ ] Note polymorphic query covers all note types
- [ ] Query cost increase <20% for all entities
- [ ] No breaking changes to existing extraction logic

### Phase 3: Mappers ✅
- [ ] All new fields properly mapped (camelCase → snake_case)
- [ ] Correct data type conversions (Money → cents, etc.)
- [ ] Nested objects handled (flattened or JSON)
- [ ] All mappers tested with real API responses

### Phase 4: Database Schema ✅
- [ ] All new columns added via migration
- [ ] Migrations are idempotent and backward-compatible
- [ ] Foreign key constraints maintained
- [ ] Indexes added for new foreign keys

### Phase 5: Cleanup ✅
- [ ] Unused tables identified and removed (if any)
- [ ] init_schema() only creates active tables
- [ ] Documentation updated to reflect current schema

### Phase 6: Testing ✅
- [ ] All unit tests passing
- [ ] Integration tests verify end-to-end pipeline
- [ ] Migration tests confirm backward compatibility
- [ ] Full extraction test successful with new schema
- [ ] Field coverage report generated

### Documentation ✅
- [ ] Field coverage report published
- [ ] DATABASE_SCHEMA.md updated
- [ ] Migration notes added to CHANGELOG
- [ ] Code comments updated for new fields

## Notes and Considerations

### Critical Considerations

1. **Backward Compatibility**:
   - All schema changes MUST be backward-compatible
   - Existing extraction code MUST continue working
   - Use ALTER TABLE ADD COLUMN with defaults

2. **Data Type Precision**:
   - ALWAYS store financial data as cents (INTEGER)
   - ISO8601 dates as TEXT strings
   - JSON for complex nested objects

3. **GraphQL Cost Management**:
   - Monitor cost increase from new fields
   - Keep nested query pagination limits
   - Don't exceed 500 points per query

4. **Testing Requirements**:
   - Test on real Jobber API (sandbox account)
   - Verify migrations on existing databases
   - Check for NULL handling edge cases

### Potential Challenges

1. **InvoiceAmounts/QuoteAmounts Objects**:
   - These are nested objects with multiple fields
   - Need to decide: flatten or store as JSON
   - **Recommendation**: Flatten (tax_cents, discount_cents, etc.)

2. **ClientAddress Nested Object**:
   - 10 fields in address object
   - **Recommendation**: Flatten to billing_street, billing_city, etc.

3. **Custom Fields**:
   - Jobber allows custom fields (variable structure)
   - **Recommendation**: Store as JSON blob, don't create columns

4. **Deprecated Tables**:
   - Need careful verification before removal
   - May be used by undocumented features
   - **Recommendation**: Mark deprecated first, remove in next version

5. **Query Cost Threshold**:
   - Adding fields increases query cost
   - Must balance completeness vs. cost
   - **Recommendation**: Priority 1 fields first, monitor cost

### Future Enhancements

1. **Schema Versioning**:
   - Track schema version in database
   - Enable version-specific migrations
   - Support multiple API versions

2. **Field Value Analysis**:
   - Analyze which fields are actually populated
   - Identify low-value fields (always NULL)
   - Guide future schema optimizations

3. **Automated Coverage Reporting**:
   - Generate coverage report during extraction
   - Alert on new fields in Jobber API
   - Track coverage percentage over time

4. **Selective Field Extraction**:
   - Allow users to choose which fields to extract
   - Reduce cost for minimal migrations
   - Configuration-based query building

---

**This plan is ready for execution with `/execute-plan PRPs/jobber-schema-alignment-and-cleanup.md`**

---

## Appendix: Field Priority Classification

### Priority 1: High Business Value (MUST ADD)

**Client**:
- `balance` - Outstanding balance (critical financial data)
- `companyName` - Business clients
- `billingAddress` - Billing information

**Invoice**:
- `amounts.tax` - Tax breakdown
- `amounts.discount` - Discount tracking
- `amounts.deposits` - Deposit tracking

**Job**:
- `completedAt` - Completion tracking
- `billingType` - Billing strategy
- `instructions` - Job context

**Quote**:
- `amounts.tax` - Tax breakdown
- `amounts.discount` - Discount tracking

**Property**:
- `name` - Property identification
- `taxRate` - Tax relationship

**User**:
- `isAccountAdmin` - Admin privileges
- `isAccountOwner` - Owner privileges

**Visit**:
- `completedAt` - Completion tracking
- `clientConfirmed` - Confirmation status

### Priority 2: Useful Metadata (SHOULD ADD)

**Client**:
- `isArchivable` - Archive status

**Job**:
- `invoicedTotal` - Invoicing tracking

**Property**:
- `isBillingAddress` - Billing flag
- `routingOrder` - Service routing

**User**:
- `availableForScheduling` - Scheduling availability
- `assignedColor` - Calendar color

**Visit**:
- `completedBy` - Who completed
- `allDay` - All-day event flag

### Priority 3: Lower Value (CONSIDER)

**Client**:
- `customFields` - Variable structure, store as JSON

**Job/Visit**:
- `arrivalWindow` - Scheduling window (complex object)

**Invoice/Quote**:
- `customFields` - Variable structure

### Priority 4: Skip (Not Needed Now)

- UI-specific fields (clientHubUri, jobberWebUri)
- Deeply nested relationship counts (can query on-demand)
- Display helper fields (friendly phone formats - derive from raw)
