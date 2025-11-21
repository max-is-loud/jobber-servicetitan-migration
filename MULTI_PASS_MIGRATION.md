# Multi-Pass Migration Guide

## Overview

TightBeam v2 implements a **multi-pass migration strategy** that separates lightweight discovery (Map Pass) from full data retrieval (Extract Pass). This approach provides:

- **Predictable effort estimation** - Know entity counts and relationship density before extraction
- **Early risk surfacing** - Identify heavy entities with many relations upfront
- **Targeted retries** - Re-run only failed entities without full pipeline restart
- **Better completeness monitoring** - Compare expected vs. retrieved counts

## Architecture

The multi-pass system consists of three coordinated passes:

### Pass 1: Map Mode (Discovery)
Builds a lightweight inventory of entities and relation counts without fetching full payloads.

**What it fetches:**
- Entity counts per type (clients, invoices, jobs, etc.)
- Minimal identifiers (id, updatedAt, createdAt)
- Relation counts per entity (notes, attachments, line items, visits)
- Creates a snapshot for extract pass targeting

**What it avoids:**
- Full field selection
- Binary data (attachments)
- Large text fields
- Nested relation payloads

**Output:**
- `MapSnapshot` record with unique ID and timestamp
- `EntityInventory` records with relation count estimates
- Map report (JSON and Markdown) with entity totals and hotspots

### Pass 2: Extract Mode (Full Retrieval)
Hydrates complete records using queues seeded from a map snapshot.

**What it fetches:**
- All fields for each entity type
- Related collections (notes, line items, visits, tasks)
- Binary downloads queued separately

**Execution model:**
- Creates work queues from `EntityInventory` records
- Tracks per-entity status: `pending` → `in_progress` → `done`/`failed`
- Supports resume: skips `done` entities, retries `failed` ones
- Separate attachment queue for isolated retry

**Output:**
- Complete entity records in destination tables
- `ExtractQueueItem` status tracking
- `AttachmentQueueItem` for binary downloads
- Extract report with completeness validation

### Pass 3: Reconcile Mode (Optional - Not Yet Implemented)
Planned for closing gaps and handling data drift between passes.

**Planned capabilities:**
- Re-run discovery for types with discrepancies
- Verify attachment download success
- Produce delta queues for missing entities
- Final completeness report

## CLI Commands

### Map Command

Run discovery pass to build entity inventory:

```bash
# Map all entity types
uv run tightbeam migrate map

# Map specific entity types
uv run tightbeam migrate map --entity clients --entity invoices

# Add a label for easy reference
uv run tightbeam migrate map --snapshot-label "pre-migration-2025"

# Specify report directory
uv run tightbeam migrate map --report-dir ./my-reports
```

**Options:**
- `--entity, --entities TEXT`: Entity types to include (repeat for multiple). Defaults to all supported types.
- `--snapshot-label TEXT`: Optional human-friendly label for the snapshot
- `--report-dir PATH`: Directory for reports (default: `reports/`)

**Supported entity types:**
- `clients`
- `expenses`
- `invoices`
- `jobs`
- `productsAndServices`
- `properties`
- `quotes`
- `requests`
- `taxRates`
- `timesheetEntries`
- `users`
- `visits`

**Global migrate options** (available for both map and extract):
- `--db PATH`: SQLite database path
- `--verbose`: Enable verbose logging
- `--adaptive`: Enable adaptive performance optimization (auto-tune page size and delays)
- `--optimization-level TEXT`: Rate limiting level (conservative/moderate/aggressive)
- `--enable-cost-monitoring`: Track GraphQL costs and rate limits

### Extract Command

Run full extraction pass using a map snapshot:

```bash
# Extract using a specific snapshot ID
uv run tightbeam migrate extract --snapshot-id <snapshot-uuid>

# Extract specific entity types from snapshot
uv run tightbeam migrate extract --snapshot-id <id> --entity clients --entity invoices

# Resume extraction from existing queues
uv run tightbeam migrate extract --snapshot-id <id> --resume

# Specify report directory
uv run tightbeam migrate extract --snapshot-id <id> --report-dir ./my-reports
```

**Options:**
- `--snapshot-id TEXT`: **Required** - Map snapshot ID to extract from
- `--entity, --entities TEXT`: Entity types to extract (defaults to all types in snapshot)
- `--resume`: Resume from existing extract queues instead of recreating them
- `--report-dir PATH`: Directory for reports (default: `reports/`)

## Workflow Examples

### Basic Multi-Pass Migration

```bash
# Step 1: Run map pass to discover entities
uv run tightbeam migrate map --snapshot-label "initial-discovery"

# Review the map report in reports/map-<timestamp>.md
# Note the snapshot ID from the report

# Step 2: Run extract pass using the snapshot ID
uv run tightbeam migrate extract --snapshot-id <snapshot-id-from-map>

# Step 3: Review extract report for completeness
# Check reports/extract-<timestamp>.md for any discrepancies
```

### Selective Entity Migration

```bash
# Map only clients and invoices
uv run tightbeam migrate map --entity clients --entity invoices

# Extract only clients from the snapshot
uv run tightbeam migrate extract --snapshot-id <id> --entity clients
```

### Resuming Failed Extraction

```bash
# If extraction fails or is interrupted, resume with the same snapshot
uv run tightbeam migrate extract --snapshot-id <id> --resume

# The --resume flag skips entities marked as 'done' and retries 'failed' ones
```

### Using Adaptive Optimization

```bash
# Enable adaptive tuning for both passes
uv run tightbeam migrate --adaptive map

uv run tightbeam migrate --adaptive extract --snapshot-id <id>

# Adaptive mode automatically adjusts:
# - Page sizes based on throttling
# - Request delays to stay under rate limits
# - Emits summary at end showing adjustments made
```

## Database Schema

The multi-pass system adds four new tables to the SQLite database:

### map_snapshot

Tracks map pass execution metadata.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | UUID for the snapshot |
| created_at | TEXT | ISO8601 timestamp when created |
| pass1_cutoff | TEXT | ISO8601 cutoff time for snapshot |
| label | TEXT | Optional human-friendly label |
| entities_included | TEXT | JSON array of entity types |

### entity_inventory

Stores discovered entities from map pass.

| Column | Type | Description |
|--------|------|-------------|
| entity_type | TEXT | Entity type (e.g., "clients") |
| entity_id | TEXT | Jobber API identifier |
| discovered_at | TEXT | ISO8601 discovery timestamp |
| map_snapshot_id | TEXT | Foreign key to map_snapshot |
| updated_at | TEXT | Last update from API (nullable) |
| estimated_relations_json | TEXT | JSON with relation counts |

**Primary Key:** `(entity_type, entity_id, map_snapshot_id)`

**estimated_relations_json example:**
```json
{"notes": 5, "attachments": 2, "line_items": 10, "visits": 3}
```

### extract_queue_item

Tracks extraction status per entity.

| Column | Type | Description |
|--------|------|-------------|
| entity_type | TEXT | Entity type to extract |
| entity_id | TEXT | Entity identifier |
| status | TEXT | pending/in_progress/done/failed |
| map_snapshot_id | TEXT | Foreign key to map_snapshot |
| updated_at | TEXT | ISO8601 last update timestamp |
| last_error | TEXT | Error message (nullable) |
| attempt_count | INTEGER | Number of attempts |

**Primary Key:** `(entity_type, entity_id, map_snapshot_id)`

**Status flow:** `pending` → `in_progress` → `done` (success) or `failed` (retry)

### attachment_queue_item

Tracks binary download status separately from entity extraction.

| Column | Type | Description |
|--------|------|-------------|
| attachment_id | TEXT | Attachment identifier |
| parent_type | TEXT | Parent entity type |
| parent_id | TEXT | Parent entity ID |
| status | TEXT | pending/in_progress/done/failed |
| map_snapshot_id | TEXT | Foreign key to map_snapshot |
| updated_at | TEXT | ISO8601 last update timestamp |
| last_error | TEXT | Error message (nullable) |
| attempt_count | INTEGER | Number of download attempts |

**Primary Key:** `(attachment_id, map_snapshot_id)`

**Status flow:** `pending` → `in_progress` → `done` (success) or `failed` (retry)

## Reports

Both map and extract passes generate detailed reports in JSON and Markdown formats.

### Map Report Format

**Location:** `reports/map-<timestamp>.json` and `.md`

**Contents:**
- Snapshot ID and metadata
- Per-entity type totals
- Top entities by relation density (hotspots)
- Estimated extraction effort
- Timestamp and configuration used

**Example sections:**
- **Entity Totals** - Count per type
- **Relation Density** - Entities with most notes/attachments
- **Hotspots** - Top 10 heaviest entities for extraction planning

### Extract Report Format

**Location:** `reports/extract-<timestamp>.json` and `.md`

**Contents:**
- Snapshot ID used for extraction
- Per-entity type extraction status
- Completeness validation (expected vs. actual)
- Failed entities list for retry
- Attachment download statistics
- Timestamp and configuration used

**Example sections:**
- **Extraction Summary** - Success/failure counts
- **Completeness Check** - Map totals vs. extracted totals
- **Failed Entities** - IDs and error messages
- **Attachment Status** - Download success/failure counts

## Performance & Optimization

### Adaptive Optimization

Use `--adaptive` flag to enable automatic tuning:

```bash
uv run tightbeam migrate --adaptive map
```

**What it does:**
- Monitors API throttling events
- Adjusts page size dynamically (reduces on throttle)
- Adjusts request delays to stay under rate limits
- Does NOT persist changes to config file during map mode
- Emits summary showing adjustments made

**Summary output example:**
```
Adaptive Tuning Summary:
  Throttle events: 3
  Page size: 50 → 35 (30% reduction)
  Request delay: 0.25s → 0.35s (40% increase)
```

### Rate Limiting Levels

Use `--optimization-level` to control request rate:

```bash
uv run tightbeam migrate --optimization-level aggressive map
```

**Levels:**
- `conservative` (4 req/s): 52% safety margin, safest for production
- `moderate` (6 req/s): 28% safety margin, **default recommended**
- `aggressive` (8 req/s): 4% safety margin, requires monitoring

### Cost Monitoring

Track GraphQL query costs and rate limit usage:

```bash
uv run tightbeam migrate --enable-cost-monitoring --cost-monitoring-verbose map
```

**Provides:**
- Detailed query cost analysis
- Rate limit accuracy tracking
- Performance insights for tuning

## Migration from Single-Pass

If you have existing migrations using `migrate all`:

### Backward Compatibility

The `migrate all` command still works for single-pass migrations:

```bash
# Traditional single-pass migration
uv run tightbeam migrate all

# With resume support
uv run tightbeam migrate all --resume
```

### Migration Benefits

Switching to multi-pass provides:

1. **Visibility** - See entity counts before long extraction
2. **Control** - Choose which entities to extract
3. **Resilience** - Resume from failures without restarting
4. **Efficiency** - Retry only failed entities

### Recommended Transition

```bash
# Old workflow
uv run tightbeam migrate all

# New workflow - equivalent but more controllable
uv run tightbeam migrate map
uv run tightbeam migrate extract --snapshot-id <id>
```

## Best Practices

### 1. Always Label Important Snapshots

```bash
uv run tightbeam migrate map --snapshot-label "Q1-2025-migration"
```

Labels make snapshots easier to identify and reference later.

### 2. Review Map Reports Before Extraction

Check `reports/map-<timestamp>.md` to:
- Confirm entity counts match expectations
- Identify heavy entities (many relations)
- Adjust extraction strategy if needed

### 3. Use Resume for Long Migrations

```bash
# If interrupted, resume with the same snapshot
uv run tightbeam migrate extract --snapshot-id <id> --resume
```

This skips completed entities and retries failures.

### 4. Enable Adaptive Mode for Unknown Workloads

```bash
uv run tightbeam migrate --adaptive map
```

Let the optimizer tune performance automatically.

### 5. Monitor Extract Reports for Completeness

After extraction, check `reports/extract-<timestamp>.md`:
- Verify extracted counts match map totals
- Review failed entities list
- Check attachment download success rate

### 6. Keep Snapshots Manageable

Periodically clean up old snapshots to reduce database size. The system stores all snapshots for historical tracking.

## Troubleshooting

### Finding Snapshot IDs

Snapshot IDs are printed at the end of map runs and included in map reports:

```bash
# Run map and note the snapshot ID from output
uv run tightbeam migrate map

# Or check the latest map report
ls -lt reports/map-*.md | head -1
```

### Extraction Failures

If entities fail during extraction:

1. Check extract report for error messages
2. Review failed entities list
3. Re-run with `--resume` to retry only failures:
   ```bash
   uv run tightbeam migrate extract --snapshot-id <id> --resume
   ```

### Throttling Issues

If experiencing API throttling:

1. Use more conservative rate limiting:
   ```bash
   uv run tightbeam migrate --optimization-level conservative extract --snapshot-id <id>
   ```

2. Enable adaptive optimization:
   ```bash
   uv run tightbeam migrate --adaptive extract --snapshot-id <id>
   ```

3. Enable cost monitoring to track API usage:
   ```bash
   uv run tightbeam migrate --enable-cost-monitoring --cost-monitoring-verbose extract --snapshot-id <id>
   ```

### Missing Entities

If extracted counts don't match map totals:

1. Check extract report completeness section
2. Look for failed entities in the report
3. Verify no entities were updated/deleted between map and extract passes
4. Consider running reconcile pass (when implemented)

### Database Locked Errors

If you encounter database lock errors:

1. Ensure no other TightBeam processes are running
2. Check for abandoned connections
3. Close any SQLite browsers/viewers
4. Restart the extraction with `--resume`

## Advanced Usage

### Querying Map Data Directly

You can query the SQLite database to analyze map results:

```sql
-- Get entity counts per type
SELECT entity_type, COUNT(*) as count
FROM entity_inventory
WHERE map_snapshot_id = '<snapshot-id>'
GROUP BY entity_type;

-- Find heaviest entities by relation counts
SELECT entity_type, entity_id, estimated_relations_json
FROM entity_inventory
WHERE map_snapshot_id = '<snapshot-id>'
ORDER BY LENGTH(estimated_relations_json) DESC
LIMIT 10;

-- Check extraction queue status
SELECT entity_type, status, COUNT(*) as count
FROM extract_queue_item
WHERE map_snapshot_id = '<snapshot-id>'
GROUP BY entity_type, status;
```

### Custom Entity Selection

Extract different entity subsets from the same snapshot:

```bash
# First, extract high-priority entities
uv run tightbeam migrate extract --snapshot-id <id> --entity clients --entity invoices

# Later, extract remaining entities
uv run tightbeam migrate extract --snapshot-id <id> --entity jobs --entity quotes
```

### Multiple Snapshots for Comparison

Create multiple snapshots over time to track data growth:

```bash
# Initial snapshot
uv run tightbeam migrate map --snapshot-label "baseline-2025-01"

# Later snapshot
uv run tightbeam migrate map --snapshot-label "baseline-2025-02"

# Compare snapshots in database
SELECT entity_type, COUNT(*) as count, map_snapshot_id
FROM entity_inventory
WHERE map_snapshot_id IN ('<id1>', '<id2>')
GROUP BY entity_type, map_snapshot_id;
```

## Future Enhancements

### Reconcile Pass (Planned)

The optional third pass will:
- Re-run discovery for types with discrepancies
- Generate delta queues for missing entities
- Verify attachment download completeness
- Produce final completeness report

**Planned CLI:**
```bash
uv run tightbeam migrate reconcile --snapshot-id <id>
```

### Incremental Sync (Planned)

Update migrations to fetch only changed data:

```bash
# Fetch only entities updated since last migration
uv run tightbeam migrate update

# Or use explicit date filter
uv run tightbeam migrate map --since 2025-01-01
```

## Support

For issues, questions, or feature requests:

1. Check this documentation
2. Review map/extract reports for detailed diagnostics
3. Enable verbose logging: `--verbose` flag
4. Create an issue on the project repository

---

**Multi-Pass Migration System** - Predictable, resilient, and controllable data migration
