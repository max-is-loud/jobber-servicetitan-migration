# Implementation Plan: Multi-Pass Jobber Extraction System

## Overview
Implement a staged extraction strategy that separates lightweight discovery (Pass 1: Map) from full data retrieval (Pass 2: Extract) with optional reconciliation (Pass 3). This provides predictable effort estimation, early risk surfacing, targeted retries, and better completeness monitoring compared to the current single-pass approach.

## Requirements Summary
- **Predictable effort**: Get counts and relationship density before committing to long runs
- **Early risk surfacing**: Identify heavy entities (clients with many attachments/notes) and adjust rate limits before deep fetch
- **Targeted retries**: Re-run only expensive objects instead of entire migration
- **Better monitoring**: Compare expected vs. retrieved counts to flag gaps quickly
- **Resumability**: Persist map snapshots and allow extraction to resume from checkpoints
- **Completeness accounting**: Map totals vs. extracted totals vs. binary success rates

## Research Findings

### Best Practices from Jobber API Documentation

**Rate Limiting (Leaky Bucket Algorithm):**
- Maximum available: 10,000 points
- Restore rate: 500 points/second
- DDoS protection: 2,500 requests per 5 minutes per app/account combination
- Query cost calculation: Fields cost 1 point each (except edges/nodes/node which cost 0)
- Connection fields: cost = `first` × field_count
- Without `first` argument: assumes max 100 nodes → 100× cost multiplier

**Cost Optimization Strategies:**
1. **Always use `first` argument** on connections to avoid 100× penalty
2. **Pagination recommended**: Cursor-based (Relay framework)
3. **Avoid deeply nested queries**: Cost increases exponentially
4. **Use delays between queries** to allow point restoration
5. **Cache common results** to reduce redundant queries

**Implications for Multi-Pass:**
- **Pass 1 (Map mode)**: Use minimal field selection → Low cost per query
  - Request only: `totalCount`, `pageInfo`, `id`, `updatedAt`
  - Small `first` values (20-50) for sampling
  - Estimated cost: ~5-10 points per query (vs. 100-500 for full queries)
  - Can run with aggressive optimization level (480 req/min)

- **Pass 2 (Extract mode)**: Full field selection → High cost per query
  - Current queries already optimized
  - Use moderate optimization level (360 req/min)
  - Adaptive concurrency based on Pass 1 density data

### Reference Implementations from Codebase

**Extractor Pattern** (`src/extractors/base_extractor.py:1-794`):
- Template Method pattern with abstract hooks
- Cursor-based pagination with `hasNextPage`/`endCursor`
- Batch processing with configurable delays
- Per-object existence checking for resume
- Related entity extraction (notes, attachments)
- Error recovery with exponential backoff

**Coordinator Pattern** (`src/coordinators/base_migration_coordinator.py:1-794`):
- Rich UI integration (progress bars, error panels)
- Template Method for migration workflow
- Dependency injection of shared services
- Resume support via cursor checkpoints
- Report generation with statistics

**Repository Pattern** (`src/repositories/repository.py`):
- Batch insert with `executemany`
- `INSERT OR REPLACE` for upsert semantics
- Transaction per batch (commit after page)
- Parameterized queries for security
- Migration state tracking per entity type

### Technology Decisions

**Database Extensions:**
- SQLite (existing) - Add 5 new tables for inventory/queue tracking
- No new dependencies required
- Leverage existing `migration_state` pattern

**CLI Framework:**
- Typer (existing) - Add 3 new subcommands
- Follow existing argument patterns
- Maintain backward compatibility with `migrate start`

**Rate Limiting:**
- Reuse existing `TokenBucketRateLimiter`
- Add mode-specific optimization profiles
- Maintain shared rate limiter across all extractors

**Query Optimization:**
- Create lightweight query variants for map mode
- Minimize field selection to reduce cost
- Use small `first` values (20-50) for density sampling

## Implementation Tasks

### Phase 1: Foundation (Data Model & Schema)

#### Task 1.1: Define Domain Models
**Description**: Create domain models for inventory, snapshots, and queue items
- **Files to create**:
  - `src/models/entity_inventory.py` - Entity inventory model
  - `src/models/map_snapshot.py` - Map snapshot model
  - `src/models/extract_queue_item.py` - Extract queue item model
  - `src/models/attachment_queue_item.py` - Attachment queue item model
- **Pattern to follow**: Existing models in `src/models/` (Client, Invoice, etc.)
- **Dependencies**: None
- **Estimated effort**: 2-3 hours

```python
# Example: src/models/entity_inventory.py
@dataclass
class EntityInventory:
    entity_type: str
    entity_id: str
    updated_at: Optional[str]
    discovered_at: str
    estimated_relations: dict  # {"notes": 5, "attachments": 2}
    map_snapshot_id: str
```

#### Task 1.2: Extend Repository with New Schema
**Description**: Add 5 new tables to repository schema initialization
- **Files to modify**:
  - `src/repositories/repository.py:init_schema()` (add table creation)
- **New tables**:
  ```sql
  CREATE TABLE entity_inventory (
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      updated_at TEXT,
      discovered_at TEXT NOT NULL,
      estimated_relations_json TEXT,
      map_snapshot_id TEXT NOT NULL,
      PRIMARY KEY (entity_type, entity_id, map_snapshot_id)
  );

  CREATE TABLE relation_inventory (
      parent_type TEXT NOT NULL,
      parent_id TEXT NOT NULL,
      relation_type TEXT NOT NULL,
      count INTEGER NOT NULL,
      cursor_hint TEXT,
      map_snapshot_id TEXT NOT NULL,
      PRIMARY KEY (parent_type, parent_id, relation_type, map_snapshot_id)
  );

  CREATE TABLE map_snapshot (
      id TEXT PRIMARY KEY,
      label TEXT,
      created_at TEXT NOT NULL,
      entities_included TEXT,  -- JSON: ["clients", "invoices"]
      pass1_cutoff TEXT NOT NULL
  );

  CREATE TABLE extract_queue (
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      status TEXT NOT NULL,  -- pending, in_progress, done, failed
      last_error TEXT,
      attempt_count INTEGER DEFAULT 0,
      map_snapshot_id TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (entity_type, entity_id, map_snapshot_id)
  );

  CREATE TABLE attachment_queue (
      parent_type TEXT NOT NULL,
      parent_id TEXT NOT NULL,
      attachment_id TEXT NOT NULL,
      status TEXT NOT NULL,
      last_error TEXT,
      attempt_count INTEGER DEFAULT 0,
      map_snapshot_id TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (attachment_id, map_snapshot_id)
  );
  ```
- **Dependencies**: Task 1.1
- **Estimated effort**: 2 hours

#### Task 1.3: Add Repository Methods for Inventory/Queue Management
**Description**: Implement CRUD operations for new tables
- **Files to modify**:
  - `src/repositories/repository.py` (add new methods)
- **New methods**:
  - `save_map_snapshot(snapshot: MapSnapshot) -> None`
  - `get_map_snapshot(snapshot_id: str) -> Optional[MapSnapshot]`
  - `list_map_snapshots() -> List[MapSnapshot]`
  - `save_entity_inventory(inventory: List[EntityInventory]) -> None`
  - `get_entity_inventory(snapshot_id: str, entity_type: str) -> List[EntityInventory]`
  - `save_relation_inventory(inventory: List[RelationInventory]) -> None`
  - `create_extract_queue(snapshot_id: str, entity_type: str) -> None`
  - `get_extract_queue(snapshot_id: str, entity_type: str, status: str) -> List[ExtractQueueItem]`
  - `update_queue_status(queue_item: ExtractQueueItem) -> None`
  - `create_attachment_queue(snapshot_id: str, attachments: List[Attachment]) -> None`
  - `get_attachment_queue(snapshot_id: str, status: str) -> List[AttachmentQueueItem]`
- **Pattern to follow**: Existing repository methods (batch operations, parameterized queries)
- **Dependencies**: Task 1.2
- **Estimated effort**: 4-5 hours

### Phase 2: Map Mode Implementation

#### Task 2.1: Create Map Mode Query Variants
**Description**: Add lightweight query methods to JobberClient for map mode
- **Files to modify**:
  - `src/clients/jobber_client.py` (add new methods)
- **New methods** (one per entity type):
  - `fetch_clients_map(cursor: Optional[str] = None) -> dict`
  - `fetch_invoices_map(cursor: Optional[str] = None) -> dict`
  - `fetch_quotes_map(cursor: Optional[str] = None) -> dict`
  - `fetch_jobs_map(cursor: Optional[str] = None) -> dict`
  - ... (14 total, one per entity type)
- **Query structure** (example for clients):
  ```python
  query = """
  query GetClientsMap($after: String) {
    clients(first: 50, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id
          updatedAt
          notes { totalCount }
          noteAttachments { totalCount }
        }
      }
    }
  }
  """
  ```
- **Key differences from full queries**:
  - Include `totalCount` at connection level
  - Minimal fields: `id`, `updatedAt` only
  - Include relation `totalCount` fields (notes, attachments, line items, etc.)
  - No binaries, no large text fields
  - Small `first` value (20-50) to keep cost low
- **Dependencies**: None
- **Estimated effort**: 3-4 hours

#### Task 2.2: Create Map Mode Extractors
**Description**: Implement map mode extractors extending BaseExtractor
- **Files to create** (one per entity type):
  - `src/extractors/map_mode/clients_map_extractor.py`
  - `src/extractors/map_mode/invoices_map_extractor.py`
  - `src/extractors/map_mode/quotes_map_extractor.py`
  - `src/extractors/map_mode/jobs_map_extractor.py`
  - ... (14 total)
- **Pattern to follow**: `src/extractors/clients_extractor.py` (extend BaseExtractor)
- **Overrides**:
  - `_fetch_page()` → Call map mode query variant
  - `_map_entity()` → Create EntityInventory instead of full entity
  - `_save_entities()` → Save to entity_inventory table
  - `_extract_related_entities()` → Extract relation counts only
- **Example implementation**:
  ```python
  class ClientsMapExtractor(BaseExtractor[EntityInventory]):
      def __init__(self, jobber_client, repository, logger, map_snapshot_id):
          super().__init__(
              entity_type=EntityInventory,
              entity_name="client",
              jobber_client=jobber_client,
              repository=repository,
              logger=logger
          )
          self._map_snapshot_id = map_snapshot_id

      def _fetch_page(self, cursor=None) -> dict:
          return self._jobber_client.fetch_clients_map(cursor)

      def _map_entity(self, node) -> EntityInventory:
          return EntityInventory(
              entity_type="clients",
              entity_id=node["id"],
              updated_at=node.get("updatedAt"),
              discovered_at=datetime.now().isoformat(),
              estimated_relations={
                  "notes": node.get("notes", {}).get("totalCount", 0),
                  "attachments": node.get("noteAttachments", {}).get("totalCount", 0)
              },
              map_snapshot_id=self._map_snapshot_id
          )

      def _save_entities(self, entities: List[EntityInventory]) -> None:
          self._repository.save_entity_inventory(entities)
  ```
- **Dependencies**: Task 2.1, Task 1.3
- **Estimated effort**: 6-8 hours (repetitive but straightforward)

#### Task 2.3: Create Map Mode Coordinator
**Description**: Implement coordinator for map pass orchestration
- **Files to create**:
  - `src/coordinators/map_mode_coordinator.py`
- **Pattern to follow**: `src/coordinators/base_migration_coordinator.py`
- **Key responsibilities**:
  1. Create map snapshot with timestamp/label
  2. Initialize map mode extractors for selected entity types
  3. Orchestrate extraction with Rich progress display
  4. Collect totals and relation counts
  5. Identify "heavy" entities (high relation counts)
  6. Generate map report with:
     - Per-type totals
     - Top-N heaviest parents by relation count
     - Estimated API cost/time for full extraction
     - Density analysis (avg relations per entity)
  7. Save snapshot and report
- **Example workflow**:
  ```python
  def run_map_pass(self, entity_types: List[str], label: Optional[str]) -> MapReport:
      # Create snapshot
      snapshot = self._create_snapshot(entity_types, label)

      # Run map extractors
      for entity_type in entity_types:
          extractor = self._create_map_extractor(entity_type, snapshot.id)
          result = extractor.extract()
          # Collect statistics

      # Analyze density
      hotspots = self._identify_hotspots(snapshot.id)

      # Generate report
      report = self._generate_map_report(snapshot, hotspots)

      return report
  ```
- **Dependencies**: Task 2.2
- **Estimated effort**: 5-6 hours

#### Task 2.4: Add Map Report Generator
**Description**: Create report generator for map pass results
- **Files to create**:
  - `src/reports/map_report_generator.py`
- **Pattern to follow**: `src/reports/migration_report_generator.py`
- **Report contents** (Markdown + JSON):
  - Summary statistics:
    - Total entities discovered per type
    - Total relation items per type
    - Map pass duration
  - Density analysis:
    - Average relations per entity type
    - Standard deviation
    - Top 10 heaviest entities (most notes/attachments)
  - Estimated extraction metrics:
    - Projected API cost (based on query costs)
    - Estimated runtime (based on current rate limits)
    - Suggested pagination sizes per entity type
  - Recommendations:
    - Entities requiring throttled extraction
    - Suggested concurrency levels
    - Potential issues flagged
- **Dependencies**: Task 2.3
- **Estimated effort**: 3-4 hours

### Phase 3: Extract Mode Implementation

#### Task 3.1: Create Extract Mode Coordinator
**Description**: Implement coordinator for hydration pass using map data
- **Files to create**:
  - `src/coordinators/extract_mode_coordinator.py`
- **Pattern to follow**: `src/coordinators/base_migration_coordinator.py`
- **Key responsibilities**:
  1. Load selected map snapshot
  2. Create extract queues from entity inventory
  3. Initialize existing extractors (reuse full extraction logic)
  4. Process queue items with status tracking
  5. Compare extracted counts vs. map totals
  6. Flag discrepancies for reconciliation
  7. Decouple attachment downloads to separate queue
  8. Generate extract report with completeness metrics
- **Queue processing workflow**:
  ```python
  def run_extract_pass(self, snapshot_id: str, entity_types: List[str], resume: bool) -> ExtractReport:
      # Load snapshot
      snapshot = self._repository.get_map_snapshot(snapshot_id)

      # Create/resume queues
      for entity_type in entity_types:
          if not resume:
              self._repository.create_extract_queue(snapshot_id, entity_type)

      # Process queues
      for entity_type in entity_types:
          queue_items = self._repository.get_extract_queue(
              snapshot_id, entity_type, status="pending"
          )

          extractor = self._create_extractor(entity_type)

          for item in queue_items:
              try:
                  # Mark in_progress
                  item.status = "in_progress"
                  self._repository.update_queue_status(item)

                  # Extract entity
                  entity = extractor.extract_single(item.entity_id)

                  # Mark done
                  item.status = "done"
                  self._repository.update_queue_status(item)
              except Exception as e:
                  # Mark failed
                  item.status = "failed"
                  item.last_error = str(e)
                  item.attempt_count += 1
                  self._repository.update_queue_status(item)

      # Validate completeness
      discrepancies = self._validate_completeness(snapshot_id)

      return self._generate_extract_report(snapshot, discrepancies)
  ```
- **Dependencies**: Task 1.3, existing extractors
- **Estimated effort**: 6-8 hours

#### Task 3.2: Modify Existing Extractors for Single-Entity Extraction
**Description**: Add single-entity extraction method to existing extractors
- **Files to modify**:
  - `src/extractors/base_extractor.py` (add method)
  - All 14 existing extractors (inherit new method)
- **New method**:
  ```python
  def extract_single(self, entity_id: str) -> T:
      """Extract a single entity by ID (for queue-based extraction).

      Args:
          entity_id: The entity ID to extract

      Returns:
          The extracted and mapped entity

      Raises:
          JobberApiError: If API call fails
          MappingError: If entity mapping fails
      """
      # Fetch single entity by ID
      response = self._fetch_single(entity_id)

      # Map and save
      entity = self._map_entity(response)
      self._save_entities([entity])

      # Extract and save related entities
      related = self._extract_related_entities(response, entity)
      self._save_related_entities(related)

      return entity
  ```
- **Pattern**: Similar to existing `extract()` method but for single entity
- **Dependencies**: None (modifies existing code)
- **Estimated effort**: 4-5 hours

#### Task 3.3: Decouple Attachment Downloads to Queue
**Description**: Separate attachment downloads from parent entity extraction
- **Files to modify**:
  - `src/extractors/base_extractor.py` (modify related entity extraction)
  - `src/coordinators/extract_mode_coordinator.py` (add attachment queue processing)
- **Changes**:
  1. During entity extraction, add attachments to `attachment_queue` instead of downloading immediately
  2. Process attachment queue separately after entities are extracted
  3. Track download status per attachment
  4. Enable retry of failed downloads without re-fetching parent
- **Workflow**:
  ```python
  # In extractor: Queue attachments
  def _extract_related_entities(self, node, primary_entity):
      attachments = self._extract_attachments_from_node(node)

      # Queue for later download instead of downloading now
      self._repository.create_attachment_queue(
          self._map_snapshot_id,
          attachments
      )

      return RelatedEntities(notes=notes, attachments=attachments)

  # In coordinator: Process attachment queue
  def _download_queued_attachments(self, snapshot_id: str):
      downloader = AttachmentDownloader(...)

      queue_items = self._repository.get_attachment_queue(snapshot_id, "pending")

      for item in queue_items:
          try:
              downloader.download_attachment(item.attachment)
              item.status = "done"
          except Exception as e:
              item.status = "failed"
              item.last_error = str(e)

          self._repository.update_queue_status(item)
  ```
- **Dependencies**: Task 3.1
- **Estimated effort**: 4-5 hours

#### Task 3.4: Add Completeness Validation
**Description**: Implement validation to compare map totals vs. extracted counts
- **Files to create**:
  - `src/validators/completeness_validator.py`
- **Validation checks**:
  1. **Per-type totals**: Extracted count matches mapped `totalCount`
  2. **Per-object relations**: Related-item counts match map expectations
  3. **Attachment success**: Downloaded binaries match queued attachments
  4. **Failed items**: List entities with errors for retry
  5. **Data drift**: Flag entities updated after `pass1_cutoff`
- **Output**:
  ```python
  @dataclass
  class CompletenessReport:
      snapshot_id: str
      entity_discrepancies: List[EntityDiscrepancy]  # Expected vs. actual
      relation_discrepancies: List[RelationDiscrepancy]
      attachment_failures: List[AttachmentFailure]
      drift_detected: List[DriftWarning]  # updatedAt > cutoff
      success_rate: float
  ```
- **Dependencies**: Task 3.1
- **Estimated effort**: 3-4 hours

#### Task 3.5: Add Extract Report Generator
**Description**: Create report generator for extract pass results
- **Files to create**:
  - `src/reports/extract_report_generator.py`
- **Pattern to follow**: `src/reports/migration_report_generator.py`
- **Report contents** (Markdown + JSON):
  - Summary statistics:
    - Entities extracted per type
    - Queue status breakdown (done/failed/pending)
    - Extraction duration
  - Completeness metrics:
    - Map totals vs. extracted totals
    - Success rates per entity type
    - Attachment download success rate
  - Discrepancy details:
    - Missing entities
    - Relation count mismatches
    - Failed entities with error messages
  - Retry recommendations:
    - Failed queue items
    - Suggested actions
- **Dependencies**: Task 3.4
- **Estimated effort**: 3-4 hours

### Phase 4: CLI Integration

#### Task 4.1: Add `tightbeam migrate map` Command
**Description**: Implement CLI command for map pass
- **Files to modify**:
  - `src/cli/migrate.py` (add new command)
- **Command signature**:
  ```python
  @migrate_app.command("map")
  def map_command(
      ctx: typer.Context,
      entities: Annotated[Optional[List[str]], typer.Option(
          help="Entity types to map (default: all)"
      )] = None,
      snapshot_label: Annotated[Optional[str], typer.Option(
          help="Label for this map snapshot"
      )] = None,
      optimization_level: Annotated[str, typer.Option(
          help="Rate limit optimization (conservative|moderate|aggressive)"
      )] = "aggressive",  # Map mode can be aggressive
  ) -> None:
      """Run discovery pass to map entity counts and relationships."""
  ```
- **Workflow**:
  1. Validate entity types
  2. Create rate-limited JobberClient (aggressive optimization)
  3. Initialize MapModeCoordinator
  4. Run map pass
  5. Display Rich progress bars
  6. Generate and save report
  7. Print summary and next steps
- **Dependencies**: Task 2.3, Task 2.4
- **Estimated effort**: 3-4 hours

#### Task 4.2: Add `tightbeam migrate extract` Command
**Description**: Implement CLI command for extract pass
- **Files to modify**:
  - `src/cli/migrate.py` (add new command)
- **Command signature**:
  ```python
  @migrate_app.command("extract")
  def extract_command(
      ctx: typer.Context,
      from_map: Annotated[str, typer.Option(
          help="Map snapshot ID or label to use"
      )],
      entities: Annotated[Optional[List[str]], typer.Option(
          help="Entity types to extract (default: all in snapshot)"
      )] = None,
      resume: Annotated[bool, typer.Option(
          help="Resume from failed/pending queue items"
      )] = False,
      optimization_level: Annotated[str, typer.Option(
          help="Rate limit optimization (conservative|moderate|aggressive)"
      )] = "moderate",  # Extract mode uses moderate
      skip_attachments: Annotated[bool, typer.Option(
          help="Skip attachment downloads"
      )] = False,
  ) -> None:
      """Run full extraction using a map snapshot."""
  ```
- **Workflow**:
  1. Load map snapshot (by ID or label)
  2. Validate entity types against snapshot
  3. Create rate-limited JobberClient (moderate optimization)
  4. Initialize ExtractModeCoordinator
  5. Run extract pass
  6. Display Rich progress bars with queue status
  7. Process attachment queue (unless skipped)
  8. Validate completeness
  9. Generate and save report
  10. Print discrepancies and retry recommendations
- **Dependencies**: Task 3.1, Task 3.4, Task 3.5
- **Estimated effort**: 4-5 hours

#### Task 4.3: Add `tightbeam migrate reconcile` Command
**Description**: Implement CLI command for reconciliation pass
- **Files to modify**:
  - `src/cli/migrate.py` (add new command)
- **Command signature**:
  ```python
  @migrate_app.command("reconcile")
  def reconcile_command(
      ctx: typer.Context,
      from_map: Annotated[str, typer.Option(
          help="Map snapshot ID or label to reconcile"
      )],
      entities: Annotated[Optional[List[str]], typer.Option(
          help="Entity types to reconcile (default: all with discrepancies)"
      )] = None,
  ) -> None:
      """Re-run discovery for types with discrepancies and queue deltas."""
  ```
- **Workflow**:
  1. Load original map snapshot
  2. Re-run map mode for specified entity types
  3. Compare new map with old map
  4. Generate delta queue for missing/changed entities
  5. Run targeted extraction for deltas only
  6. Retry failed attachments
  7. Generate final completeness report
- **Dependencies**: Task 3.1, Task 4.1, Task 4.2
- **Estimated effort**: 4-5 hours

#### Task 4.4: Maintain Backward Compatibility for `migrate start`
**Description**: Ensure existing `migrate start` command continues to work
- **Files to modify**:
  - `src/cli/migrate.py` (update existing command)
- **Options**:
  1. **Keep existing behavior** (single-pass) as default
  2. **Add flag** `--use-multi-pass` to opt into new behavior
  3. **Auto-upgrade** to run `map` + `extract` in one flow with flag
- **Recommended approach**: Add optional flag
  ```python
  @migrate_app.command("start")
  def start_command(
      ctx: typer.Context,
      # ... existing parameters ...
      use_multi_pass: Annotated[bool, typer.Option(
          help="Use multi-pass map+extract strategy"
      )] = False,
  ) -> None:
      """Start migration (single-pass or multi-pass)."""
      if use_multi_pass:
          # Run map + extract in sequence
          map_result = run_map_pass(...)
          run_extract_pass(from_map=map_result.snapshot_id, ...)
      else:
          # Existing single-pass behavior
          run_single_pass_migration(...)
  ```
- **Dependencies**: Task 4.1, Task 4.2
- **Estimated effort**: 2-3 hours

### Phase 5: Testing & Documentation

#### Task 5.1: Unit Tests for Map Mode
**Description**: Write unit tests for map mode extractors and coordinator
- **Files to create**:
  - `tests/test_map_mode_extractors.py`
  - `tests/test_map_mode_coordinator.py`
  - `tests/test_map_report_generator.py`
- **Test cases**:
  - Map mode query construction (minimal fields)
  - Entity inventory creation and persistence
  - Relation count extraction
  - Snapshot creation and retrieval
  - Hotspot identification
  - Report generation
- **Pattern to follow**: `tests/test_extractors.py` (mock JobberClient, Repository)
- **Dependencies**: Tasks 2.1-2.4
- **Estimated effort**: 4-5 hours

#### Task 5.2: Unit Tests for Extract Mode
**Description**: Write unit tests for extract mode coordinator and queue processing
- **Files to create**:
  - `tests/test_extract_mode_coordinator.py`
  - `tests/test_completeness_validator.py`
  - `tests/test_extract_report_generator.py`
- **Test cases**:
  - Queue creation from inventory
  - Queue item status transitions
  - Single-entity extraction
  - Attachment queue processing
  - Completeness validation logic
  - Discrepancy detection
  - Report generation
- **Pattern to follow**: `tests/test_extractors.py`
- **Dependencies**: Tasks 3.1-3.5
- **Estimated effort**: 5-6 hours

#### Task 5.3: Integration Tests for Multi-Pass Flow
**Description**: Write end-to-end integration tests for map → extract → reconcile
- **Files to create**:
  - `tests/integration/test_multi_pass_flow.py`
- **Test scenarios**:
  1. **Happy path**: Map → Extract → All complete
  2. **Resume scenario**: Map → Extract (interrupted) → Extract (resume)
  3. **Discrepancy scenario**: Map → Extract → Reconcile
  4. **Attachment retry**: Extract (failed attachments) → Retry
  5. **Data drift**: Map → (delay) → Extract → Drift warning
- **Test fixtures**:
  - Mock GraphQL responses for map and extract queries
  - Sample map snapshots with various densities
  - Pre-populated queues with different statuses
- **Dependencies**: Tasks 4.1-4.3
- **Estimated effort**: 6-8 hours

#### Task 5.4: CLI Integration Tests
**Description**: Test CLI commands with various argument combinations
- **Files to create**:
  - `tests/cli/test_migrate_map_command.py`
  - `tests/cli/test_migrate_extract_command.py`
  - `tests/cli/test_migrate_reconcile_command.py`
- **Test cases**:
  - Argument parsing and validation
  - Help text generation
  - Error handling (invalid snapshot IDs, etc.)
  - Output formatting
  - Backward compatibility with `migrate start`
- **Dependencies**: Tasks 4.1-4.4
- **Estimated effort**: 3-4 hours

#### Task 5.5: Update Documentation
**Description**: Document multi-pass workflow and new commands
- **Files to modify**:
  - `README.md` (add multi-pass overview)
  - `docs/MIGRATION_COORDINATOR_DOCUMENTATION.md` (add map/extract modes)
  - `docs/DATABASE_SCHEMA.md` (document new tables)
- **Files to create**:
  - `docs/MULTI_PASS_MIGRATION.md` - Comprehensive guide
- **Documentation contents**:
  - Overview of multi-pass strategy
  - When to use single-pass vs. multi-pass
  - Step-by-step workflow examples
  - CLI command reference
  - Troubleshooting guide
  - Performance tuning recommendations
  - Schema documentation for new tables
- **Dependencies**: All implementation tasks
- **Estimated effort**: 4-5 hours

## Codebase Integration Points

### Files to Modify

#### Core Infrastructure
- `src/repositories/repository.py` - Add 5 new tables and 15+ new methods
  - **Changes**: Extend `init_schema()`, add inventory/queue CRUD methods
  - **Lines**: ~300-400 lines added

- `src/clients/jobber_client.py` - Add 14 map mode query methods
  - **Changes**: Add lightweight query variants for each entity type
  - **Lines**: ~200-300 lines added

- `src/extractors/base_extractor.py` - Add single-entity extraction method
  - **Changes**: New `extract_single(entity_id)` method
  - **Lines**: ~50-60 lines added

#### CLI Layer
- `src/cli/migrate.py` - Add 3 new commands and update existing command
  - **Changes**: Add `map`, `extract`, `reconcile` commands; update `start`
  - **Lines**: ~150-200 lines added

### New Files to Create

#### Domain Models (4 files)
```
src/models/
  entity_inventory.py          (~50 lines)
  map_snapshot.py              (~60 lines)
  extract_queue_item.py        (~70 lines)
  attachment_queue_item.py     (~70 lines)
```

#### Map Mode Extractors (14 files)
```
src/extractors/map_mode/
  __init__.py
  clients_map_extractor.py     (~150 lines each)
  invoices_map_extractor.py
  quotes_map_extractor.py
  jobs_map_extractor.py
  properties_map_extractor.py
  requests_map_extractor.py
  users_map_extractor.py
  visits_map_extractor.py
  timesheet_entries_map_extractor.py
  expenses_map_extractor.py
  products_services_map_extractor.py
  tax_rates_map_extractor.py
  notes_map_extractor.py
```

#### Coordinators (2 files)
```
src/coordinators/
  map_mode_coordinator.py      (~400 lines)
  extract_mode_coordinator.py  (~500 lines)
```

#### Report Generators (2 files)
```
src/reports/
  map_report_generator.py      (~300 lines)
  extract_report_generator.py  (~300 lines)
```

#### Validators (1 file)
```
src/validators/
  __init__.py
  completeness_validator.py    (~250 lines)
```

#### Tests (8 files)
```
tests/
  test_map_mode_extractors.py       (~300 lines)
  test_map_mode_coordinator.py      (~250 lines)
  test_extract_mode_coordinator.py  (~300 lines)
  test_completeness_validator.py    (~200 lines)
  test_map_report_generator.py      (~150 lines)
  test_extract_report_generator.py  (~150 lines)
tests/cli/
  test_migrate_map_command.py       (~200 lines)
  test_migrate_extract_command.py   (~250 lines)
  test_migrate_reconcile_command.py (~200 lines)
tests/integration/
  test_multi_pass_flow.py           (~400 lines)
```

#### Documentation (1 file)
```
docs/
  MULTI_PASS_MIGRATION.md      (~500 lines)
```

### Existing Patterns to Follow

#### 1. Extractor Pattern (from `base_extractor.py`)
```python
# Extend BaseExtractor for map mode
class ClientsMapExtractor(BaseExtractor[EntityInventory]):
    # Override template methods
    def _fetch_page(self, cursor) -> dict
    def _map_entity(self, node) -> EntityInventory
    def _save_entities(self, entities) -> None
```

#### 2. Coordinator Pattern (from `base_migration_coordinator.py`)
```python
# Extend BaseMigrationCoordinator for new modes
class MapModeCoordinator(BaseMigrationCoordinator):
    # Override migration workflow
    def migrate(self) -> MapReport
```

#### 3. Repository Pattern (from `repository.py`)
```python
# Batch operations with parameterized queries
def save_entity_inventory(self, inventory: List[EntityInventory]) -> None:
    cursor = self._connection.cursor()
    tuples = [(i.entity_type, i.entity_id, ...) for i in inventory]
    cursor.executemany(
        "INSERT OR REPLACE INTO entity_inventory (...) VALUES (?, ?, ...)",
        tuples
    )
    self._connection.commit()
```

#### 4. CLI Command Pattern (from `migrate.py`)
```python
# Typer command with type hints and help text
@migrate_app.command("map")
def map_command(
    ctx: typer.Context,
    entities: Annotated[Optional[List[str]], typer.Option(
        help="Entity types to map"
    )] = None,
) -> None:
    """Run discovery pass to map entity counts."""
```

#### 5. Rich UI Pattern (from `base_migration_coordinator.py`)
```python
# Progress bars and error panels
with Progress(...) as progress:
    task_id = progress.add_task("[cyan]Mapping clients...", total=None)
    # ... extraction logic ...
    progress.update(task_id, completed=count)

# Error handling
console.print(Panel(
    f"[red]Error:[/red] {error_message}",
    border_style="red",
    title="Extraction Failed"
))
```

## Technical Design

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ migrate map  │  │migrate extract│ │migrate reconcile│         │
│  └──────┬───────┘  └──────┬────────┘ └──────┬────────┘          │
└─────────┼──────────────────┼─────────────────┼───────────────────┘
          │                  │                 │
          ▼                  ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Coordinator Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │Map Mode      │  │Extract Mode  │  │Reconcile     │          │
│  │Coordinator   │  │Coordinator   │  │Coordinator   │          │
│  └──────┬───────┘  └──────┬────────┘ └──────┬────────┘          │
└─────────┼──────────────────┼─────────────────┼───────────────────┘
          │                  │                 │
          ▼                  ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Extractor Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │Map Mode      │  │Full Mode     │  │Single Entity │          │
│  │Extractors    │  │Extractors    │  │Extract       │          │
│  │(14 types)    │  │(14 types)    │  │              │          │
│  └──────┬───────┘  └──────┬────────┘ └──────┬────────┘          │
└─────────┼──────────────────┼─────────────────┼───────────────────┘
          │                  │                 │
          └──────────────────┴─────────────────┘
                             │
                             ▼
          ┌──────────────────────────────────────┐
          │         JobberClient (Shared)         │
          │   ┌──────────────────────────────┐   │
          │   │  RateLimitedHttpClient       │   │
          │   │  (TokenBucket + Backoff)     │   │
          │   └──────────────────────────────┘   │
          └──────────────────┬───────────────────┘
                             │
                             ▼
          ┌──────────────────────────────────────┐
          │        Jobber GraphQL API            │
          └──────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     Data Layer (SQLite)                          │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Map Phase Tables                                        │    │
│  │  - entity_inventory (type, id, relations, snapshot)    │    │
│  │  - relation_inventory (parent, relation, count)        │    │
│  │  - map_snapshot (id, label, timestamp, entities)       │    │
│  └────────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Extract Phase Tables                                    │    │
│  │  - extract_queue (type, id, status, error, snapshot)   │    │
│  │  - attachment_queue (id, status, error, snapshot)      │    │
│  └────────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Final Data Tables (Existing)                            │    │
│  │  - clients, invoices, quotes, jobs, properties, ...    │    │
│  │  - notes, attachments, visits, expenses, ...           │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

#### Pass 1: Map Mode
```
1. User runs: tightbeam migrate map --snapshot-label "2025-01-migration"

2. CLI creates MapModeCoordinator with:
   - Aggressive rate limiter (480 req/min)
   - Lightweight JobberClient queries

3. MapModeCoordinator:
   a. Creates map_snapshot record (ID, label, timestamp)
   b. For each entity type:
      - Creates MapModeExtractor
      - Runs lightweight extraction (id, updatedAt, relation counts)
      - Saves to entity_inventory table
      - Saves relation counts to relation_inventory table
   c. Analyzes density and identifies hotspots
   d. Generates map report with recommendations

4. Report saved to: reports/map-2025-01-migration.md
   - Total counts per entity type
   - Heaviest entities (most relations)
   - Estimated extraction time and cost
   - Suggested optimization levels

5. Snapshot ID returned: "snap_abc123xyz"
```

#### Pass 2: Extract Mode
```
1. User runs: tightbeam migrate extract --from-map "2025-01-migration"

2. CLI creates ExtractModeCoordinator with:
   - Moderate rate limiter (360 req/min)
   - Full-featured JobberClient queries

3. ExtractModeCoordinator:
   a. Loads map_snapshot "2025-01-migration"
   b. For each entity type in snapshot:
      - Creates extract_queue from entity_inventory
      - Initializes existing full extractor
      - Processes queue items one by one:
        * Mark status = "in_progress"
        * Extract single entity with all fields
        * Save to final tables (clients, invoices, etc.)
        * Queue attachments (don't download yet)
        * Mark status = "done" or "failed"
   c. After entities extracted, processes attachment_queue:
      - Downloads files in batches
      - Updates attachment status (done/failed)
   d. Validates completeness:
      - Compare entity counts (map vs. extracted)
      - Check relation counts match expectations
      - Identify discrepancies
   e. Generates extract report

4. Report saved to: reports/extract-2025-01-migration.md
   - Success rates per entity type
   - Completeness metrics
   - Failed entities with errors
   - Attachment download status
   - Retry recommendations
```

#### Pass 3: Reconcile (Optional)
```
1. User runs: tightbeam migrate reconcile --from-map "2025-01-migration"

2. ReconcileCoordinator:
   a. Loads original map_snapshot
   b. Re-runs map mode for types with discrepancies
   c. Compares new map with old map:
      - New entities (added since Pass 1)
      - Changed entities (updatedAt > cutoff)
   d. Creates delta queue with only missing/changed entities
   e. Runs targeted extraction for deltas
   f. Retries failed attachments from Pass 2
   g. Generates final completeness report

3. Report saved to: reports/reconcile-2025-01-migration.md
   - Delta entities processed
   - Final completeness status
   - Remaining failures (manual investigation needed)
```

### API Endpoints (GraphQL Queries)

#### Map Mode Query Example (Lightweight)
```graphql
query GetClientsMap($after: String) {
  clients(first: 50, after: $after) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        updatedAt
        notes { totalCount }
        noteAttachments { totalCount }
      }
    }
  }
}
```

**Cost Analysis:**
- `totalCount`: 1 point
- `pageInfo.hasNextPage`: 1 point
- `pageInfo.endCursor`: 1 point
- Per edge (50 edges):
  - `id`: 1 point
  - `updatedAt`: 1 point
  - `notes.totalCount`: 1 point
  - `noteAttachments.totalCount`: 1 point
  - Subtotal: 4 points × 50 = 200 points
- **Total: ~203 points per query**

#### Extract Mode Query Example (Full)
```graphql
query GetClients($after: String) {
  clients(first: 50, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        firstName
        lastName
        email
        phone
        createdAt
        updatedAt
        # ... 20+ more fields
        notes(first: 100) {
          edges {
            node {
              id
              message
              createdAt
              # ... 10+ more fields
            }
          }
        }
        noteAttachments(first: 100) {
          edges {
            node {
              id
              fileName
              contentType
              originalUrl
              # ... 8+ more fields
            }
          }
        }
      }
    }
  }
}
```

**Cost Analysis:**
- Per client: ~30 fields = 30 points
- Per client notes: 100 × 15 fields = 1,500 points
- Per client attachments: 100 × 12 fields = 1,200 points
- **Total: ~2,730 points per client**
- **For 50 clients: ~136,500 points** (would be throttled!)

**Current optimization**: Nested pagination limits reduce actual cost:
```yaml
# settings.yaml
pagination:
  nested_notes: 25     # Instead of 100
  nested_attachments: 25
```
- Revised cost: 50 clients × (30 + 25×15 + 25×12) = 50 × 705 = **35,250 points**
- Still expensive but within limits with delays

## Dependencies and Libraries

**No new dependencies required!** All functionality can be implemented using existing stack:

- **SQLite**: Built-in Python `sqlite3` module
- **Typer**: Already in use for CLI
- **Rich**: Already in use for UI
- **Requests**: Already in use for HTTP
- **PyYAML**: Already in use for config
- **Pytest**: Already in use for testing

## Testing Strategy

### Unit Tests

#### Map Mode Tests
- Map mode query construction (verify minimal field selection)
- Entity inventory creation from GraphQL response
- Relation count extraction and persistence
- Snapshot creation and labeling
- Hotspot identification logic
- Map report generation and formatting

#### Extract Mode Tests
- Queue creation from entity inventory
- Queue item status state transitions
- Single-entity extraction logic
- Attachment queue processing
- Completeness validation calculations
- Discrepancy detection and reporting

#### Repository Tests
- New table schema creation
- Inventory/snapshot CRUD operations
- Queue CRUD operations with status filtering
- Transaction handling
- Error handling for constraint violations

### Integration Tests

#### End-to-End Scenarios
1. **Complete flow**: Map → Extract → Validate → Success
2. **Resume flow**: Map → Extract (interrupted) → Extract (resume) → Success
3. **Discrepancy flow**: Map → Extract → Discrepancies detected → Reconcile → Success
4. **Attachment retry**: Extract → Attachment failures → Retry → Success
5. **Data drift**: Map → (time passes, data changes) → Extract → Drift warnings

#### CLI Integration Tests
- Command argument parsing and validation
- Help text generation for all commands
- Error handling (invalid snapshot IDs, missing entities, etc.)
- Report file creation and formatting
- Backward compatibility with `migrate start`

### Test Coverage Targets
- **Unit tests**: >90% coverage for core logic
- **Integration tests**: All happy paths and major error scenarios
- **CLI tests**: All command variations and argument combinations

### Edge Cases to Cover
- Empty entity types (0 results)
- Heavy entities (1000+ notes/attachments)
- API throttling during map mode
- Database constraint violations
- Invalid snapshot IDs
- Stale map snapshots (long lag between passes)
- Concurrent queue updates (if implemented)
- Failed attachment retries (max attempts)
- GraphQL schema changes (new fields)

## Success Criteria

### Functional Requirements
- [ ] Map mode produces snapshot with per-entity totals and relation counts for all 14 entity types
- [ ] Map report includes hotspots (top 10 heaviest entities) and runtime estimates
- [ ] Extract mode can target a specific snapshot by ID or label
- [ ] Extract mode tracks per-object status (pending/in_progress/done/failed)
- [ ] Extract mode can resume from interrupted state (skip done, requeue pending)
- [ ] Attachment downloads decoupled from parent entity extraction
- [ ] Attachment queue allows isolated retry without re-fetching parents
- [ ] Completeness validation compares map totals vs. extracted totals
- [ ] Discrepancies clearly enumerated in extract report with actionable recommendations
- [ ] Reconcile mode can process only failed/missing entities from snapshot

### Non-Functional Requirements
- [ ] Map mode query cost <10 points per entity (vs. ~2,700 for full queries)
- [ ] Map mode completes in <10 minutes for typical accounts (vs. hours for full extraction)
- [ ] Extract mode respects rate limits (no increase in throttling vs. baseline)
- [ ] Storage overhead <10% of final data size (inventory/queue tables lightweight)
- [ ] Backward compatibility: `migrate start` still works with existing behavior
- [ ] Reports clearly formatted and saved to `reports/` directory
- [ ] All 3 new commands have comprehensive help text and examples

### Testing Requirements
- [ ] Map mode tests cover query construction and inventory persistence
- [ ] Extract mode tests cover queue processing and status transitions
- [ ] Integration tests validate map → extract → reconcile flow
- [ ] CLI tests verify argument parsing and error handling
- [ ] Test coverage >80% overall, >90% on critical paths (extractors, coordinators)
- [ ] No regressions in existing single-pass migration tests

### Documentation Requirements
- [ ] `docs/MULTI_PASS_MIGRATION.md` created with comprehensive guide
- [ ] `README.md` updated with multi-pass overview and quick start
- [ ] `docs/MIGRATION_COORDINATOR_DOCUMENTATION.md` updated with new modes
- [ ] `docs/DATABASE_SCHEMA.md` updated with 5 new tables
- [ ] All new CLI commands have `--help` text with examples

## Notes and Considerations

### Important Notes

1. **Rate Limiting Optimization**:
   - Map mode can use "aggressive" optimization (480 req/min) due to low query cost
   - Extract mode should use "moderate" (360 req/min) or "conservative" (240 req/min)
   - Consider adding custom optimization profile for map mode (e.g., 600 req/min)

2. **Query Cost Awareness**:
   - Always include `first` argument on connection fields (avoid 100× penalty)
   - Map mode queries should request <10 points (vs. 2,730+ for full queries)
   - Monitor `extensions.cost.currentlyAvailable` in responses

3. **Storage Overhead**:
   - Inventory/queue tables are lightweight (ids + timestamps + counts)
   - Estimate: <5% of final data size
   - Consider purging old snapshots (retention policy)

4. **Resumability**:
   - Map mode can resume from cursor (like existing migration)
   - Extract mode resumes from queue status (more granular)
   - Snapshot timestamps prevent stale data issues

5. **Data Drift Handling**:
   - Record `pass1_cutoff` timestamp in snapshot
   - During extract, flag entities with `updatedAt > cutoff`
   - Reconcile pass can re-fetch changed entities

### Potential Challenges

1. **Stale Map Snapshots**:
   - **Risk**: Long lag between map and extract makes inventory stale
   - **Mitigation**: Enforce max age warning (e.g., 7 days); recommend fresh map
   - **Alternative**: Auto-refresh snapshot if age > threshold

2. **Missing `totalCount` Support**:
   - **Risk**: Some GraphQL connections may not expose `totalCount`
   - **Mitigation**: Fall back to small sample edges (first: 10) and estimate
   - **Marking**: Flag estimates vs. exact counts in inventory

3. **Complex UX**:
   - **Risk**: Three-step workflow (map/extract/reconcile) may confuse users
   - **Mitigation**: Simplify defaults; add `--use-multi-pass` flag to `migrate start`
   - **Documentation**: Provide clear examples and decision tree

4. **Storage Growth**:
   - **Risk**: Old snapshots accumulate over time
   - **Mitigation**: Implement `--prune-maps` option to delete old snapshots
   - **Retention**: Keep last N snapshots or snapshots <30 days old

5. **Concurrent Migrations**:
   - **Risk**: Running multiple migrations with different snapshots
   - **Mitigation**: Not supported in v1; document as limitation
   - **Future**: Add locking mechanism if needed

6. **GraphQL Schema Evolution**:
   - **Risk**: New fields added to API not in map mode queries
   - **Mitigation**: Document query maintenance process
   - **Future**: Auto-generate queries from schema introspection

### Future Enhancements

1. **Parallel Entity Extraction**:
   - Process multiple entity types concurrently (with shared rate limiter)
   - Requires thread-safe queue updates

2. **Adaptive Pagination**:
   - Adjust `first` values dynamically based on density and throttling
   - Use map mode density data to optimize page sizes

3. **Smart Retries**:
   - Exponential backoff for failed queue items
   - Auto-reduce concurrency after repeated throttling

4. **Snapshot Comparison UI**:
   - CLI command to compare two snapshots (diff counts)
   - Visualize data growth over time

5. **Export to Other Formats**:
   - CSV/XLSX export from completed extraction
   - Cloud storage upload (S3, GCS)

6. **Multi-Account Orchestration**:
   - Run migrations for multiple Jobber accounts in parallel
   - Centralized progress dashboard

---

*This plan is ready for execution with `/execute-plan PRPs/multi-pass-jobber-extraction.md`*
