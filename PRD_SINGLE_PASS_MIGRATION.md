# PRD: Single-Pass Stream-and-Normalize Migration Architecture

**Status:** Pre-Alpha
**Version:** 2.0
**Breaking Changes:** Yes - Complete architectural rewrite

## Overview

Replace TightBeam's current two-pass migration with a single-pass stream-and-normalize architecture. Stream raw entity data to SQLite staging tables during pagination, then normalize offline. This eliminates 98% of API calls and reduces migration time from 48 hours to 20 minutes.

## Problem Statement

The current architecture fetches the same data twice:

**Current Flow:**
1. **Map Pass:** Paginate all entities (~510 API calls for 15,297 jobs) → Save only IDs
2. **Extract Pass:** Fetch each entity individually (~15,297 API calls) → Save full data

**Total:** ~15,807 API calls, ~48 hours

**Why This Is Broken:**
- We already have the full entity data during map pass - we just throw it away
- Extract pass re-fetches data we've already seen
- 97% of API calls are redundant
- Network failures require complete restart
- Can't process offline even though we have all the data

### Real-World Impact

Production migration (57,754 entities):
- **Current:** 59,150 API calls, 48+ hours
- **Proposed:** 1,396 API calls, 20 minutes
- **Improvement:** 98% fewer calls, 99% faster

## Solution: Stream-and-Normalize

### Architecture

```
┌─────────────────────────────────────────────────┐
│  Single Migration Command                       │
└────────────┬────────────────────────────────────┘
             │
             ├─> Phase 1: STREAM (~15 min)
             │   ├─> Paginate entities (1,396 API calls)
             │   ├─> Save raw JSON to staging table
             │   └─> Track progress, enable resume
             │
             └─> Phase 2: NORMALIZE (~5 min, offline)
                 ├─> Read JSON from staging table
                 ├─> Parse & map to domain models
                 ├─> Save to final entity tables
                 └─> Extract relations (notes, attachments)
```

**Key Insight:** We already paginate through all entities. Just save the full data instead of discarding it.

### Performance Comparison

| Metric | Current | Proposed | Improvement |
|--------|---------|----------|-------------|
| **API Calls** | 59,150 | 1,396 | **98% fewer** |
| **Time** | 48 hours | 20 minutes | **99% faster** |
| **Memory** | Variable | <500MB | Predictable |
| **Network Dependent** | Both passes | Stream only | Normalize offline |
| **Resume Granularity** | Per entity | Per phase | Simpler |

## Database Schema

### New Table: `raw_entity_staging`

```sql
CREATE TABLE raw_entity_staging (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    normalized BOOLEAN DEFAULT 0,
    PRIMARY KEY (entity_type, entity_id)
);

CREATE INDEX idx_staging_type ON raw_entity_staging(entity_type);
CREATE INDEX idx_staging_normalized ON raw_entity_staging(normalized)
    WHERE normalized = 0;
```

**Why This Works:**
- Store complete GraphQL response as JSON
- `normalized` flag tracks processing state
- Can resume normalization after crashes
- Vacuum table after successful migration to reclaim space

**Storage:** ~150MB for 50K entities (3KB avg per entity)

### Remove Legacy Tables

**Delete (no longer needed):**
- `map_snapshots` - No separate map/extract phases
- `entity_inventory` - Staging table replaces this
- `extract_queue` - Process directly from staging

**Simplification:** Single source of truth (staging table) instead of 3 separate tracking tables.

## CLI Commands

### Primary Command: `tightbeam migrate`

```bash
# Stream and normalize in one command (default)
tightbeam migrate --entities clients,jobs,invoices

# Resume after crash (auto-detects incomplete work)
tightbeam migrate --entities clients,jobs --resume

# Stream only, defer normalization
tightbeam migrate --entities clients,jobs --stream-only

# Normalize previously streamed data
tightbeam migrate --entities clients,jobs --normalize-only
```

**Removed Commands:**
- `migrate map` - No longer needed
- `migrate extract` - Replaced by `migrate`
- `migrate all` - Just `migrate` now

**Simplified:** One command does everything by default.

## Component Architecture

### 1. MigrationCoordinator (Simplified)

**Location:** `src/coordinators/migration_coordinator.py`

```python
class MigrationCoordinator:
    """Single-pass stream-and-normalize migration."""

    def run_migration(
        self,
        entity_types: List[str],
        resume: bool = False,
        stream_only: bool = False,
        normalize_only: bool = False,
    ) -> MigrationResult:
        """Execute complete migration workflow."""

        if not normalize_only:
            # Stream phase
            self._stream_entities(entity_types, resume)

        if not stream_only:
            # Normalize phase
            self._normalize_entities(entity_types, resume)

        return self._generate_report()
```

**Replaced:** MapModeCoordinator + ExtractModeCoordinator with single unified coordinator.

### 2. StreamExtractor

**Location:** `src/extractors/stream_extractor.py`

```python
class StreamExtractor:
    """Stream raw entity data to staging table."""

    def stream(self, entity_type: str) -> StreamResult:
        """Paginate and save raw JSON."""
        cursor = self._get_resume_cursor(entity_type)

        while has_next_page:
            # Fetch page (reuse existing queries)
            response = self._client.fetch_page(cursor)

            # Extract nodes
            nodes = response['data'][entity_type]['edges']

            # Save raw JSON
            self._repo.save_raw_entities(
                entity_type=entity_type,
                raw_nodes=nodes
            )

            cursor = page_info['endCursor']
```

**Reuses:** All existing GraphQL queries from current extractors, just saves full response instead of mapping immediately.

### 3. NormalizeExtractor

**Location:** `src/extractors/normalize_extractor.py`

```python
class NormalizeExtractor:
    """Normalize staged entities to final tables."""

    def normalize(self, entity_type: str) -> NormalizeResult:
        """Process all un-normalized entities."""

        while True:
            # Load batch from staging
            batch = self._repo.get_unnormalized_batch(
                entity_type=entity_type,
                limit=100
            )
            if not batch:
                break

            # Map to domain models (reuse existing mappers)
            entities = [
                self._mapper.map_entity(json.loads(raw))
                for raw in batch
            ]

            # Save to final tables
            self._repo.save_entities(entities)

            # Mark as normalized
            self._repo.mark_normalized([e.id for e in entities])
```

**Reuses:** All existing EntityMapper logic, just reads from staging instead of API.

### 4. Repository Methods

**Location:** `src/repositories/repository.py`

```python
# New methods
def save_raw_entities(entity_type: str, raw_nodes: List[dict]) -> None
def get_unnormalized_batch(entity_type: str, limit: int) -> List[str]
def mark_normalized(entity_ids: List[str]) -> None
def get_stream_progress(entity_type: str) -> StreamProgress
def vacuum_staging() -> None

# Removed methods
def save_entity_inventory() - No longer needed
def create_extract_queue() - No longer needed
def get_extract_queue() - No longer needed
```

## Implementation Plan

### Phase 1: Database Foundation (~30 minutes)

1. Create `raw_entity_staging` table
2. Add repository methods for staging operations
3. Drop legacy tables (map_snapshots, entity_inventory, extract_queue)

**Files:**
- `src/repositories/migrations/004_single_pass_schema.sql`
- `src/repositories/repository.py`

### Phase 2: Stream Infrastructure (~1.5 hours)

1. Create `StreamExtractor` class
2. Adapt existing GraphQL queries (reuse, don't rewrite)
3. Implement resume logic using staging table
4. Add progress tracking

**Files:**
- `src/extractors/stream_extractor.py`
- Reuse queries from existing extractors

### Phase 3: Normalize Infrastructure (~1.5 hours)

1. Create `NormalizeExtractor` class
2. Batch processing from staging table
3. Reuse existing EntityMapper classes (no changes needed)
4. Mark entities as normalized

**Files:**
- `src/extractors/normalize_extractor.py`

### Phase 4: Unified Coordinator (~1 hour)

1. Create `MigrationCoordinator` (replace both map and extract coordinators)
2. Orchestrate stream → normalize workflow
3. Progress tracking for both phases
4. Generate unified migration report

**Files:**
- `src/coordinators/migration_coordinator.py`
- Delete: `map_mode_coordinator.py`, `extract_mode_coordinator.py`

### Phase 5: CLI Simplification (~30 minutes)

1. Replace `migrate map/extract/all` with single `migrate` command
2. Add `--stream-only`, `--normalize-only`, `--resume` flags
3. Update help text

**Files:**
- `src/cli/migrate.py` (significant simplification)

### Phase 6: Testing (~2 hours)

1. Integration test: Full stream → normalize workflow
2. Resume test: Crash and resume at each phase
3. Performance benchmark vs. current system
4. Data integrity validation

**Files:**
- `tests/integration/test_single_pass_migration.py`
- `tests/integration/test_resume.py`

**Total Estimated Effort:** 6-7 hours

## Data Flow

### Stream Phase

```
JobberClient.fetch_jobs(cursor)
    ↓
GraphQL API Response (full entity data)
    ↓
Extract nodes from response
    ↓
Serialize to JSON
    ↓
INSERT INTO raw_entity_staging (entity_type, entity_id, raw_json)
    ↓
Update progress tracking
    ↓
Next page until hasNextPage = false
```

### Normalize Phase

```
SELECT raw_json FROM raw_entity_staging
WHERE normalized = 0
LIMIT 100
    ↓
json.loads(raw_json) for each entity
    ↓
EntityMapper.map_job(data) - REUSE existing mappers
    ↓
Extract related entities (notes, attachments)
    ↓
Repository.save_jobs(entities)
Repository.save_notes(notes)
    ↓
UPDATE raw_entity_staging SET normalized = 1
    ↓
Next batch until no more un-normalized entities
```

## Success Metrics

### Performance

- **API Call Reduction:** ≥95% reduction vs. current
- **Time Reduction:** ≥90% reduction vs. current
- **Memory Usage:** ≤500MB peak
- **Storage:** ≤200MB final (after vacuum)

### Quality

- **Data Integrity:** 100% match vs. current system results
- **Test Coverage:** ≥80% for new stream/normalize code
- **Resume Reliability:** 100% success rate for crash recovery
- **Code Simplification:** Remove ≥40% of coordinator/extractor code

### User Experience

- **Command Simplicity:** One command (`migrate`) instead of three
- **Progress Clarity:** Clear separation of stream vs. normalize progress
- **Resume Simplicity:** Automatic detection, no manual intervention
- **Error Recovery:** Resume from any point without data loss

## Migration Examples

### Example 1: Full Migration

```bash
tightbeam migrate --entities clients,jobs,invoices,quotes,properties

# Output:
# ╭─ Streaming Phase ─────────────────────────╮
# │ Clients    ████████████████  9,807/9,807  │
# │ Jobs       ████████████████ 15,297/15,297 │
# │ Invoices   ████████████████  9,539/9,539  │
# │ Quotes     ████████████████  7,326/7,326  │
# │ Properties ████████████████ 10,095/10,095 │
# ╰─ Complete: 52,064 entities in 15m 23s ────╯
#
# ╭─ Normalize Phase ─────────────────────────╮
# │ Clients    ████████████████  9,807/9,807  │
# │ Jobs       ████████████████ 15,297/15,297 │
# │ Invoices   ████████████████  9,539/9,539  │
# │ Quotes     ████████████████  7,326/7,326  │
# │ Properties ████████████████ 10,095/10,095 │
# ╰─ Complete: 52,064 entities in 4m 12s ─────╯
#
# ✓ Migration complete: 52,064 entities in 19m 35s
# ✓ 1,396 API calls (98% reduction vs. legacy)
# ✓ Report: reports/migration-2024-01-15.md
```

### Example 2: Resume After Crash

```bash
tightbeam migrate --entities clients,jobs

# Crash during stream phase...
# ╭─ Streaming Phase ─────────────────────────╮
# │ Clients    ████████████████  9,807/9,807  │
# │ Jobs       ████████▌░░░░░░░  8,500/15,297 │
# ╰─ Error: Network timeout ──────────────────╯

# Resume (auto-detects progress)
tightbeam migrate --entities clients,jobs --resume

# Output:
# ✓ Found incomplete migration
# ✓ Skipping clients (9,807/9,807 already streamed)
# ╭─ Resuming Stream Phase ──────────────────────╮
# │ Jobs       ████████████████ 15,297/15,297    │
# ╰─ Complete: 6,797 new entities in 4m 22s ─────╯
#
# ╭─ Normalize Phase ────────────────────────────╮
# │ Clients    ████████████████  9,807/9,807     │
# │ Jobs       ████████████████ 15,297/15,297    │
# ╰─ Complete: 25,104 entities in 2m 54s ────────╯
```

### Example 3: Deferred Normalization

```bash
# Stream during daytime (uses API/network)
tightbeam migrate --entities clients,jobs --stream-only

# Output:
# ╭─ Streaming Phase ─────────────────────────╮
# │ Clients    ████████████████  9,807/9,807  │
# │ Jobs       ████████████████ 15,297/15,297 │
# ╰─ Complete: 25,104 entities in 8m 17s ─────╯
#
# ✓ Normalization deferred
# ℹ Run: tightbeam migrate --normalize-only

# Normalize overnight (offline, no API)
tightbeam migrate --normalize-only

# Output:
# ╭─ Normalize Phase ─────────────────────────╮
# │ Clients    ████████████████  9,807/9,807  │
# │ Jobs       ████████████████ 15,297/15,297 │
# ╰─ Complete: 25,104 entities in 2m 54s ─────╯
#
# ✓ 0 API calls (fully offline processing)
```

## Risks & Mitigations

### Risk 1: JSON Serialization Edge Cases

**Risk:** Complex/nested GraphQL responses may not serialize cleanly

**Mitigation:**
- Test with real Jobber responses early
- Add JSON validation before INSERT
- Preserve problematic raw responses for debugging
- Fallback: String escape special characters

### Risk 2: Storage Space on Constrained Systems

**Risk:** 150MB staging table may be prohibitive for some users

**Mitigation:**
- Document storage requirements upfront
- Provide `--low-storage` mode (process entity types sequentially, vacuum after each)
- Auto-vacuum after successful normalization
- Warn if <500MB disk space available

### Risk 3: Performance of JSON Parsing

**Risk:** Deserializing 50K JSON documents may be slow

**Mitigation:**
- Batch processing (100 entities at a time)
- Benchmark and optimize batch size
- Optional: Pre-parse validation during stream phase
- Expected: 1000+ entities/second (acceptable)

### Risk 4: Incomplete Normalization Detection

**Risk:** Hard to detect if normalization partially failed

**Mitigation:**
- Track `normalized` flag per entity
- Count checks: staged entities = normalized entities
- Resume automatically completes missed entities
- Report shows counts at each phase

## Code Simplification

### Removed Components

**Coordinators:**
- ❌ `MapModeCoordinator` (1,200 lines)
- ❌ `ExtractModeCoordinator` (1,500 lines)
- ✅ `MigrationCoordinator` (600 lines) **-53% code**

**Extractors:**
- ❌ `BaseMapExtractor` + 12 entity-specific map extractors
- ❌ `BaseExtractor._fetch_single()` + queue logic
- ✅ `StreamExtractor` + `NormalizeExtractor` **-60% code**

**Database Tables:**
- ❌ `map_snapshots`
- ❌ `entity_inventory`
- ❌ `extract_queue`
- ✅ `raw_entity_staging` **-66% tables**

**CLI Commands:**
- ❌ `migrate map`
- ❌ `migrate extract`
- ❌ `migrate all`
- ✅ `migrate` **-66% commands**

**Estimated Total:** Remove ~3,500 lines, add ~1,200 lines = **Net -65% code**

## Performance Analysis

### API Costs (Jobber Points)

**Current Two-Pass (Jobs):**
- Map: 510 queries × 5 points = 2,550 points
- Extract: 15,297 queries × 70 points = 1,070,790 points
- **Total: 1,073,340 points**

**Proposed Single-Pass (Jobs):**
- Stream: 510 queries × 1,802 points = 919,020 points
- Normalize: 0 points (no API)
- **Total: 919,020 points**

**Savings: 154,320 points (14% reduction)**

But the real win is **time savings:** 48 hours → 20 minutes

### Time Breakdown

**Stream Phase (15 min):**
- API calls: 1,396 queries × 1s delay = 1,396s
- JSON serialization: ~10s
- Database inserts: ~30s
- **Total: ~24 minutes (conservative)**

**Normalize Phase (5 min):**
- JSON deserialization: 50K entities / 5,000 per sec = 10s
- Entity mapping: 50K entities / 2,000 per sec = 25s
- Database saves: Batched, ~60s
- Related entities: ~120s
- **Total: ~3.5 minutes**

**Combined: ~27 minutes** (vs. 48+ hours current)

## Future Enhancements

**Post-Launch Optimizations:**

1. **Parallel Normalization**
   - Process multiple entity types concurrently
   - Thread pool for JSON parsing
   - Potential 5x normalization speedup

2. **Compression**
   - Compress raw JSON with gzip
   - Reduce storage by 70-80%
   - Trade CPU for disk space

3. **Incremental Streaming**
   - Only stream entities updated since last migration
   - Compare `updatedAt` timestamps
   - Delta migrations for ongoing sync

4. **Smart Vacuuming**
   - Auto-vacuum staging after normalization
   - Configurable retention (keep for debugging vs. reclaim space)
   - Per-entity-type vacuum for selective cleanup

---

**Document Version:** 2.0 (Pre-Alpha)
**Last Updated:** 2024-01-15
**Status:** Ready for Implementation
**Breaking Changes:** Yes - Complete rewrite, no backwards compatibility
