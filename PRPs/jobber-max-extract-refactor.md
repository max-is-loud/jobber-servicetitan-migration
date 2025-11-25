# Implementation Plan: Jobber Max Extract Refactor

## Overview

This plan details the comprehensive refactoring of Tightbeam's Jobber export implementation into a professional-grade ETL pipeline. The refactor implements a two-pass architecture:
- **Pass 1**: GraphQL metadata extraction with cost-aware pagination
- **Pass 2**: Binary file downloader with hash-based storage

The goal is complete data coverage, predictable rate limiting, resumable operations, and ServiceTitan-ready staging.

---

## Requirements Summary

**From PRD:** `/home/max/projects/tightbeam-v2/max-refactor-prd.md`

### Core Requirements
1. **Complete Data Coverage**: Extract ALL accessible entities from Jobber account via GraphQL
2. **Preserve Relationships**: Mirror Jobber's relational structure with foreign keys
3. **Notes & Attachments**: Include metadata for all parent entities
4. **Separation of Concerns**: Metadata (Pass 1) vs binaries (Pass 2)
5. **Jobber Cost-Aware**:
   - Cursor-based pagination with tunable page sizes
   - Rate limiting: ~4-6 req/s (under 8.3 req/s ceiling)
   - Handle GraphQL cost throttling
6. **Resumable & Idempotent**: Restart-safe at any point
7. **ServiceTitan-Friendly**: Maintain Jobber-like structure (no ST mapping yet)
8. **Observability**: Structured logs, dry-run modes

### Constraints
- **Rate Limits**: 2500 req/5 min + GraphQL cost limits (max 10,000 points, restore 500/sec)
- **Cost Calculation**:
  - Fields = 1 point each (except edges/nodes/node = 0)
  - Connections without `first` = assume 100× multiplier (e.g., 5 fields × 100 = 500 points)
  - **ALWAYS use `first: N`** to avoid 100× penalty
- **Page Size Recommendations**: 25-50 items for heavy objects
- **Migration Philosophy**: Fetch ALL fields needed for full-fidelity export; split complex queries rather than dropping fields

---

## Research Findings

### Existing Codebase Patterns (from codebase-analyst agent)

#### Architecture Overview
```
src/
├── extractors/           # BaseExtractor[T] + entity-specific extractors
│   └── map_mode/         # Lightweight discovery extractors
├── clients/              # JobberClient with GraphQL queries
├── repositories/         # SQLite operations (raw SQL, no ORM)
├── mappers/              # GraphQL → dataclass transformation
├── models/               # Dataclass entities (Client, Invoice, etc.)
├── rate_limiting/        # Token bucket + backoff + metrics
├── coordinators/         # Migration orchestration
├── config/               # ConfigManager + validation models
└── cli/                  # Typer commands
```

#### Key Patterns to Follow

**1. Template Method Pattern (BaseExtractor)**
```python
class BaseExtractor(ABC, Generic[T]):
    @abstractmethod
    def _fetch_page(self, cursor: Optional[str]) -> dict[str, Any]

    @abstractmethod
    def _extract_edges_and_page_info(self, response) -> tuple[List[dict], dict]

    @abstractmethod
    def _map_entity(self, node: dict) -> T

    @abstractmethod
    def _save_entities(self, entities: List[T]) -> None

    # Concrete template method
    def extract_all(self) -> dict[str, Any]:
        # Orchestrates pagination, logging, error handling
```

**2. Dependency Injection via ServiceFactory**
```python
# src/cli/services/factories.py
jobber_client = ServiceFactory.create_rate_limited_jobber_client(
    auth_provider, repository, config_manager, "moderate"
)
# Returns JobberClient wrapped with:
# - TokenBucketRateLimiter
# - ExponentialBackoffStrategy
# - MetricsCollector
```

**3. GraphQL Query Best Practices**
```python
def _get_clients_query(self) -> str:
    page_size = self._get_pagination_size("clients")  # From config
    nested_notes_size = self._get_pagination_size("nested_notes")  # Default: 10
    return f"""
    query GetClients($cursor: String) {{
      clients(first: {page_size}, after: $cursor) {{  # CRITICAL: Always use 'first'
        edges {{
          node {{
            id
            firstName
            notes(first: {nested_notes_size}) {{  # CRITICAL: Limit nested queries
              edges {{ node {{ id message }} }}
              pageInfo {{ hasNextPage endCursor }}
            }}
          }}
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """
```

**4. Database Patterns**
```python
# Repository pattern with parameterized queries
def save_clients(self, clients: List[Client]) -> None:
    cursor = self._connection.cursor()
    cursor.executemany(
        """INSERT OR REPLACE INTO clients (id, first_name, ...)
           VALUES (?, ?, ...)""",
        [(c.id, c.first_name, ...) for c in clients]
    )
    self._connection.commit()  # Commit after each batch
```

**5. Configuration Management**
```yaml
# config/settings.yaml
rate_limits:
  moderate:  # DEFAULT
    capacity: 600
    refill_rate: 600     # 10 req/s
    initial_tokens: 150
    safety_margin: 0.1
pagination:
  clients: 51
  jobs: 30
  nested_notes: 10      # CRITICAL: max 100 to control cost
  default: 30
```

### Jobber API Insights (from RAG knowledge base)

**Rate Limiting Architecture:**
1. **DDoS Protection**: 2500 req/5 min (8.3 req/s ceiling)
2. **GraphQL Cost Throttling**: Leaky bucket algorithm
   - Max available: 10,000 points
   - Restore rate: 500 points/sec
   - Query rejected if `requestedQueryCost` > `currentlyAvailable`

**Response Format:**
```json
{
  "extensions": {
    "cost": {
      "requestedQueryCost": 142,
      "actualQueryCost": 47,
      "throttleStatus": {
        "maximumAvailable": 10000,
        "currentlyAvailable": 9953,
        "restoreRate": 500
      }
    }
  }
}
```

**Critical Cost Rules:**
- **WITHOUT `first` argument**: Assumes 100 nodes → 100× multiplier
  ```graphql
  # BAD: requestedQueryCost = 500 (5 fields × 100 assumed nodes)
  quotes {
    edges { node { id cost quoteNumber quoteStatus title } }
  }

  # GOOD: requestedQueryCost = 50 (5 fields × 10 nodes)
  quotes(first: 10) {
    edges { node { id cost quoteNumber quoteStatus title } }
  }
  ```
- **Nested queries**: Cost multiplies exponentially
  ```graphql
  # Very expensive: jobs × visits per job
  jobs {  # Assume 100
    nodes {
      visits {  # Assume 100 per job → 10,000 total
        nodes { id }
      }
    }
  }
  ```

---

## Implementation Tasks

### Phase 1: Foundation & Schema

#### Task 1.1: Define Entity Manifest
**Description**: Create machine-readable schema manifest for all Jobber entities to prevent hallucinations
**Files to create**:
- `schema/jobber_entity_manifest.yaml` - YAML entity definitions
- `docs/jobber_entity_manifest.md` - Human-readable reference

**Implementation**:
1. Run GraphQL introspection query against Jobber API
2. Extract entity types, fields, relationships
3. Document per-entity:
   - Primary key (typically `id`)
   - Foreign keys (e.g., `clientId`, `jobId`)
   - Timestamps (`createdAt`, `updatedAt`)
   - Status/enum fields
   - Required fields for migration
4. Create validation script to compare manifest vs live schema

**Dependencies**: None
**Estimated Effort**: 2-3 hours

#### Task 1.2: Update SQLite Schema
**Description**: Extend schema to support notes, attachments, and multi-pass tracking
**Files to modify**:
- `src/repositories/repository.py:104-500` - Add new table definitions

**New Tables**:
```sql
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    parent_type TEXT NOT NULL,  -- 'client', 'job', 'invoice', etc.
    parent_id TEXT NOT NULL,
    body TEXT,
    author_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (author_id) REFERENCES users(id)
);

CREATE TABLE note_attachments (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    remote_url TEXT,
    filename_original TEXT,
    content_type TEXT,
    size_bytes INTEGER,
    local_path TEXT,
    hash TEXT,
    download_status TEXT DEFAULT 'pending',  -- pending/downloading/completed/error
    download_error TEXT,
    downloaded_at TEXT
);

CREATE TABLE entity_sync_state (
    entity_type TEXT PRIMARY KEY,
    last_cursor TEXT,
    total_fetched INTEGER DEFAULT 0,
    last_sync_at TEXT,
    sync_status TEXT DEFAULT 'pending'  -- pending/in_progress/completed/error
);
```

**Dependencies**: Task 1.1 (entity manifest)
**Estimated Effort**: 1-2 hours

#### Task 1.3: Create Domain Models
**Description**: Add dataclasses for Notes and Attachments
**Files to create**:
- `src/models/note.py` - Note dataclass
- `src/models/note_attachment.py` - NoteAttachment dataclass

**Pattern to follow**:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Note:
    id: str
    parent_type: str
    parent_id: str
    body: Optional[str]
    author_id: Optional[str]
    created_at: str
    updated_at: Optional[str]
```

**Dependencies**: Task 1.2 (schema)
**Estimated Effort**: 30 minutes

---

### Phase 2: Notes Extraction (Top-Level Query Strategy)

#### Task 2.1: Design Notes Extraction Strategy
**Description**: Determine optimal strategy for extracting notes (top-level vs nested)

**Research Questions**:
1. Does Jobber expose a top-level `notes` query (paginated)?
2. If not, can we query notes per parent entity type?
3. What's the cost difference: nested vs top-level?

**Strategy Options**:
- **Option A (Preferred)**: Top-level `notes(first: 50)` query with parent filtering
- **Option B (Fallback)**: Nested extraction with `notes(first: 10)` per parent entity
- **Option C (Hybrid)**: Nested for discovery, top-level for bulk fetch

**Deliverable**: Document decision in `docs/notes_extraction_strategy.md`
**Dependencies**: Task 1.1 (entity manifest)
**Estimated Effort**: 1 hour (research + documentation)

#### Task 2.2: Implement Notes Fetching
**Description**: Add notes query to JobberClient
**Files to modify**:
- `src/clients/jobber_client.py` - Add `fetch_notes()` and `_get_notes_query()`

**Implementation** (based on strategy from Task 2.1):
```python
def _get_notes_query(self) -> str:
    page_size = self._get_pagination_size("notes")  # Add to config
    return f"""
    query GetNotes($cursor: String) {{
      notes(first: {page_size}, after: $cursor) {{
        edges {{
          node {{
            ... on ClientNote {{ id message createdAt client {{ id }} }}
            ... on JobNote {{ id message createdAt job {{ id }} }}
            ... on InvoiceNote {{ id message createdAt invoice {{ id }} }}
          }}
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """

def fetch_notes(self, cursor: Optional[str] = None) -> dict[str, Any]:
    return self._execute_query(self._get_notes_query(), {"cursor": cursor})
```

**Dependencies**: Task 2.1 (strategy)
**Estimated Effort**: 2-3 hours

#### Task 2.3: Implement Notes Extractor
**Description**: Create NotesExtractor following BaseExtractor pattern
**Files to create**:
- `src/extractors/notes_extractor.py`

**Pattern**:
```python
class NotesExtractor(BaseExtractor[Note]):
    def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
        return self._jobber_client.fetch_notes(cursor)

    def _extract_edges_and_page_info(self, response):
        notes_data = response.get("data", {}).get("notes", {})
        return notes_data.get("edges", []), notes_data.get("pageInfo", {})

    def _map_entity(self, node: dict[str, Any]) -> Note:
        return self._entity_mapper.map_note(node)

    def _save_entities(self, entities: List[Note]) -> None:
        self._repository.save_notes(entities)
```

**Dependencies**: Task 2.2 (notes fetching)
**Estimated Effort**: 1-2 hours

#### Task 2.4: Implement Notes Mapper
**Description**: Add GraphQL → Note transformation
**Files to modify**:
- `src/mappers/entity_mapper.py` - Add `map_note()` method

**Implementation**:
```python
def map_note(self, node: dict[str, Any]) -> Note:
    # Handle polymorphic notes (ClientNote, JobNote, etc.)
    typename = node.get("__typename", "")
    parent_type = typename.replace("Note", "").lower() if typename else "unknown"

    # Extract parent ID from nested object
    parent_id = None
    for key in ["client", "job", "invoice", "quote"]:
        if key in node and node[key]:
            parent_id = node[key].get("id")
            break

    return Note(
        id=node["id"],
        parent_type=parent_type,
        parent_id=parent_id or "",
        body=node.get("message"),
        author_id=node.get("author", {}).get("id"),
        created_at=node.get("createdAt", ""),
        updated_at=node.get("updatedAt")
    )
```

**Dependencies**: Task 2.3 (extractor)
**Estimated Effort**: 1 hour

#### Task 2.5: Add Notes Repository Methods
**Description**: Implement database operations for notes
**Files to modify**:
- `src/repositories/repository.py` - Add `save_notes()` and `get_notes_by_parent()`

**Implementation**:
```python
def save_notes(self, notes: List[Note]) -> None:
    cursor = self._connection.cursor()
    cursor.executemany(
        """INSERT OR REPLACE INTO notes
           (id, parent_type, parent_id, body, author_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(n.id, n.parent_type, n.parent_id, n.body, n.author_id,
          n.created_at, n.updated_at) for n in notes]
    )
    self._connection.commit()

def get_notes_by_parent(self, parent_type: str, parent_id: str) -> List[Note]:
    cursor = self._connection.cursor()
    cursor.execute(
        "SELECT * FROM notes WHERE parent_type = ? AND parent_id = ?",
        (parent_type, parent_id)
    )
    # Map rows to Note objects
```

**Dependencies**: Task 2.4 (mapper)
**Estimated Effort**: 1 hour

---

### Phase 3: Attachments Metadata Extraction

#### Task 3.1: Implement Attachments Fetching
**Description**: Add attachment metadata query to JobberClient
**Files to modify**:
- `src/clients/jobber_client.py` - Add `fetch_note_attachments()` if available as top-level query

**Strategy**:
- Check if `noteAttachments` exists as top-level query
- Fallback: Extract from nested `note.attachments` during notes extraction

**Implementation** (if top-level available):
```python
def _get_note_attachments_query(self) -> str:
    page_size = self._get_pagination_size("attachments")
    return f"""
    query GetNoteAttachments($cursor: String) {{
      noteAttachments(first: {page_size}, after: $cursor) {{
        edges {{
          node {{
            id
            note {{ id }}
            url
            fileName
            contentType
            fileSize
          }}
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """
```

**Dependencies**: Task 2.2 (notes extraction complete)
**Estimated Effort**: 2 hours

#### Task 3.2: Implement Attachments Extractor
**Description**: Create NoteAttachmentsExtractor
**Files to create**:
- `src/extractors/note_attachments_extractor.py`

**Pattern**: Follow BaseExtractor[NoteAttachment] template
**Dependencies**: Task 3.1
**Estimated Effort**: 1-2 hours

#### Task 3.3: Implement Attachments Mapper
**Description**: Add GraphQL → NoteAttachment transformation
**Files to modify**:
- `src/mappers/entity_mapper.py` - Add `map_note_attachment()` method

**Implementation**:
```python
def map_note_attachment(self, node: dict[str, Any]) -> NoteAttachment:
    return NoteAttachment(
        id=node["id"],
        note_id=node.get("note", {}).get("id", ""),
        remote_url=node.get("url", ""),
        filename_original=node.get("fileName", ""),
        content_type=node.get("contentType"),
        size_bytes=node.get("fileSize"),
        local_path=None,  # Populated in Pass 2
        hash=None,
        download_status="pending",
        download_error=None,
        downloaded_at=None
    )
```

**Dependencies**: Task 3.2
**Estimated Effort**: 30 minutes

#### Task 3.4: Add Attachments Repository Methods
**Description**: Database operations for attachments
**Files to modify**:
- `src/repositories/repository.py` - Add `save_note_attachments()`, `get_pending_attachments()`

**Implementation**:
```python
def save_note_attachments(self, attachments: List[NoteAttachment]) -> None:
    cursor = self._connection.cursor()
    cursor.executemany(
        """INSERT OR REPLACE INTO note_attachments
           (id, note_id, remote_url, filename_original, content_type,
            size_bytes, local_path, hash, download_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(a.id, a.note_id, a.remote_url, a.filename_original, a.content_type,
          a.size_bytes, a.local_path, a.hash, a.download_status)
         for a in attachments]
    )
    self._connection.commit()

def get_pending_attachments(self, limit: int = 100) -> List[NoteAttachment]:
    cursor = self._connection.cursor()
    cursor.execute(
        """SELECT * FROM note_attachments
           WHERE download_status IN ('pending', 'error')
           LIMIT ?""",
        (limit,)
    )
    # Map rows to NoteAttachment objects
```

**Dependencies**: Task 3.3
**Estimated Effort**: 1 hour

---

### Phase 4: Enhanced Entity Extraction

#### Task 4.1: Review & Extend Existing Entity Queries
**Description**: Audit current queries for completeness and cost optimization
**Files to modify**:
- `src/clients/jobber_client.py` - Update all `_get_{entity}_query()` methods

**Checklist per entity**:
- [ ] Uses `first: {page_size}` on all connections
- [ ] Nested queries use configurable limits (e.g., `nested_notes: 10`)
- [ ] Includes all fields from entity manifest
- [ ] Foreign keys properly extracted
- [ ] Timestamps included (createdAt, updatedAt)

**Entities to audit**:
- clients ✓ (already has `clients(first: 51)`)
- invoices
- quotes
- jobs
- visits
- properties
- requests ✓ (recently updated with batch caching)
- users
- expenses
- timesheets
- products_services
- tax_rates

**Dependencies**: Task 1.1 (entity manifest)
**Estimated Effort**: 3-4 hours

#### Task 4.2: Add Missing Entity Extractors
**Description**: Create extractors for Priority 2 entities
**Files to create** (if not existing):
- `src/extractors/tasks_extractor.py`
- `src/extractors/reminders_extractor.py`
- `src/extractors/timesheet_entries_extractor.py` ✓ (exists)
- `src/extractors/schedules_extractor.py`
- `src/extractors/events_extractor.py`

**Pattern**: Follow BaseExtractor[T] template
**Dependencies**: Task 4.1 (queries updated)
**Estimated Effort**: 2-3 hours (15-20 min per extractor)

#### Task 4.3: Update Entity Mappers
**Description**: Ensure all entity mappers handle full field set
**Files to modify**:
- `src/mappers/entity_mapper.py` - Review all `map_{entity}()` methods

**Verify**:
- All fields from manifest are mapped
- Foreign keys correctly extracted
- JSON fields properly serialized
- Timestamps normalized to ISO format

**Dependencies**: Task 4.2
**Estimated Effort**: 2 hours

---

### Phase 5: Cost Monitoring & Optimization

#### Task 5.1: Implement Cost Tracking Enhancements
**Description**: Capture and analyze actual vs requested costs
**Files to modify**:
- `src/rate_limiting/metrics_collector.py` - Add GraphQL cost tracking

**New Metrics**:
```python
def record_graphql_cost(
    self,
    query_type: str,
    batch_size: int,
    requested_cost: int,
    actual_cost: int,
    throttle_status: dict
) -> None:
    """Record GraphQL cost metrics for optimization."""
    cursor = self._repository._connection.cursor()
    cursor.execute(
        """INSERT INTO graphql_costs
           (query_type, batch_size, requested_cost, actual_cost,
            cost_difference, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (query_type, batch_size, requested_cost, actual_cost,
         requested_cost - actual_cost, time.time())
    )
```

**Dependencies**: Task 1.2 (graphql_costs table exists)
**Estimated Effort**: 1 hour

#### Task 5.2: Add Cost Extraction to HTTP Client
**Description**: Parse `extensions.cost` from GraphQL responses
**Files to modify**:
- `src/clients/jobber_client.py` - Extract cost data from responses
- `src/clients/http_client.py` - Pass cost data to metrics collector

**Implementation**:
```python
def _execute_query(self, query: str, variables: dict) -> dict[str, Any]:
    response = self._http_client.post(GRAPHQL_ENDPOINT, json={"query": query, "variables": variables})
    data = response.json()

    # Extract cost metadata
    cost_data = data.get("extensions", {}).get("cost", {})
    if cost_data and self._metrics_collector:
        self._metrics_collector.record_graphql_cost(
            query_type=self._extract_query_name(query),
            batch_size=variables.get("first", 0),
            requested_cost=cost_data.get("requestedQueryCost", 0),
            actual_cost=cost_data.get("actualQueryCost", 0),
            throttle_status=cost_data.get("throttleStatus", {})
        )

    return data
```

**Dependencies**: Task 5.1
**Estimated Effort**: 1-2 hours

#### Task 5.3: Implement Adaptive Page Sizing
**Description**: Dynamically adjust page sizes based on cost feedback
**Files to modify**:
- `src/config/config_manager.py` - Add cost-adaptive pagination

**Strategy**:
1. Start with configured page size (e.g., 51 for clients)
2. If `requestedQueryCost` > 8000 (80% of max), reduce page size by 20%
3. If `currentlyAvailable` < 2000, add delay before next request
4. Track adjustments in metrics

**Implementation**:
```python
def get_adaptive_page_size(
    self,
    entity_type: str,
    current_cost: int,
    available_points: int
) -> int:
    base_size = self.get_pagination_size(entity_type)

    # If cost is high, reduce page size
    if current_cost > 8000:
        return max(10, int(base_size * 0.8))

    # If points are low, be more conservative
    if available_points < 2000:
        return max(10, int(base_size * 0.5))

    return base_size
```

**Dependencies**: Task 5.2
**Estimated Effort**: 2 hours

---

### Phase 6: Binary Attachment Downloader (Pass 2)

#### Task 6.1: Design Attachment Storage Strategy
**Description**: Define file naming, directory structure, and hash algorithm
**Deliverable**: Document in `docs/attachment_storage_strategy.md`

**Strategy**:
```
attachments/
├── {sha256_hash}.{original_extension}
└── manifest.json  # Optional: mapping of hash → metadata
```

**Hash Calculation**:
```python
def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
```

**Dependencies**: None
**Estimated Effort**: 30 minutes

#### Task 6.2: Implement Attachment Downloader
**Description**: Create binary file downloader with retry logic
**Files to create**:
- `src/downloaders/attachment_downloader.py`

**Implementation**:
```python
import hashlib
import requests
from pathlib import Path
from typing import Optional

class AttachmentDownloader:
    def __init__(
        self,
        repository: Repository,
        storage_path: Path,
        logger: Logger,
        max_retries: int = 3
    ):
        self._repository = repository
        self._storage_path = storage_path
        self._logger = logger
        self._max_retries = max_retries

    def download_all_pending(self, batch_size: int = 100) -> dict:
        """Download all pending attachments in batches."""
        stats = {"success": 0, "failed": 0, "skipped": 0}

        while True:
            batch = self._repository.get_pending_attachments(batch_size)
            if not batch:
                break

            for attachment in batch:
                result = self._download_attachment(attachment)
                stats[result] += 1

        return stats

    def _download_attachment(self, attachment: NoteAttachment) -> str:
        """Download single attachment with retry."""
        for attempt in range(self._max_retries):
            try:
                # Stream download
                response = requests.get(attachment.remote_url, stream=True, timeout=30)
                response.raise_for_status()

                # Compute hash
                content = response.content
                file_hash = hashlib.sha256(content).hexdigest()

                # Determine extension
                ext = Path(attachment.filename_original).suffix or ".bin"
                filename = f"{file_hash}{ext}"
                filepath = self._storage_path / filename

                # Write file
                filepath.write_bytes(content)

                # Update database
                self._repository.update_attachment_download(
                    attachment.id,
                    local_path=str(filepath),
                    hash=file_hash,
                    status="completed"
                )

                self._logger.info(f"Downloaded: {attachment.filename_original} → {filename}")
                return "success"

            except Exception as e:
                if attempt == self._max_retries - 1:
                    # Final failure
                    self._repository.update_attachment_download(
                        attachment.id,
                        status="error",
                        error=str(e)
                    )
                    self._logger.error(f"Failed: {attachment.filename_original}: {e}")
                    return "failed"
                time.sleep(2 ** attempt)  # Exponential backoff

        return "failed"
```

**Dependencies**: Task 6.1 (storage strategy)
**Estimated Effort**: 3-4 hours

#### Task 6.3: Add CLI Command for Pass 2
**Description**: Create `tight jobber download-attachments` command
**Files to modify**:
- `src/cli/migrate.py` - Add `download_attachments` command

**Implementation**:
```python
@migrate_app.command()
def download_attachments(
    ctx: typer.Context,
    output_dir: Path = typer.Option(Path("./attachments"), help="Output directory"),
    batch_size: int = typer.Option(100, help="Attachments per batch"),
    concurrency: int = typer.Option(5, help="Concurrent downloads")
) -> None:
    """Download binary attachments from note_attachments table."""
    logger = create_logger(ctx.obj["verbose"])
    repository = create_repository(ctx.obj["db"])

    downloader = AttachmentDownloader(
        repository=repository,
        storage_path=output_dir,
        logger=logger
    )

    logger.info(f"Starting attachment download to {output_dir}")
    stats = downloader.download_all_pending(batch_size)

    logger.success(f"Download complete: {stats['success']} succeeded, {stats['failed']} failed")
```

**Dependencies**: Task 6.2
**Estimated Effort**: 1 hour

#### Task 6.4: Implement Repository Update Methods
**Description**: Add methods to update attachment download status
**Files to modify**:
- `src/repositories/repository.py`

**Implementation**:
```python
def update_attachment_download(
    self,
    attachment_id: str,
    local_path: Optional[str] = None,
    hash: Optional[str] = None,
    status: Optional[str] = None,
    error: Optional[str] = None
) -> None:
    cursor = self._connection.cursor()
    cursor.execute(
        """UPDATE note_attachments
           SET local_path = COALESCE(?, local_path),
               hash = COALESCE(?, hash),
               download_status = COALESCE(?, download_status),
               download_error = COALESCE(?, download_error),
               downloaded_at = CASE WHEN ? = 'completed' THEN datetime('now') ELSE downloaded_at END
           WHERE id = ?""",
        (local_path, hash, status, error, status, attachment_id)
    )
    self._connection.commit()
```

**Dependencies**: Task 6.2
**Estimated Effort**: 30 minutes

---

### Phase 7: Orchestration & Resume Support

#### Task 7.1: Implement Entity Sync State Tracking
**Description**: Track progress per entity type for resume capability
**Files to modify**:
- `src/repositories/repository.py` - Add sync state methods

**Implementation**:
```python
def save_sync_state(
    self,
    entity_type: str,
    cursor: Optional[str],
    total_fetched: int,
    status: str = "in_progress"
) -> None:
    cursor_obj = self._connection.cursor()
    cursor_obj.execute(
        """INSERT OR REPLACE INTO entity_sync_state
           (entity_type, last_cursor, total_fetched, last_sync_at, sync_status)
           VALUES (?, ?, ?, datetime('now'), ?)""",
        (entity_type, cursor, total_fetched, status)
    )
    self._connection.commit()

def get_sync_state(self, entity_type: str) -> Optional[dict]:
    cursor = self._connection.cursor()
    cursor.execute(
        "SELECT * FROM entity_sync_state WHERE entity_type = ?",
        (entity_type,)
    )
    row = cursor.fetchone()
    return dict(row) if row else None
```

**Dependencies**: Task 1.2 (entity_sync_state table)
**Estimated Effort**: 1 hour

#### Task 7.2: Update BaseExtractor for Resume Support
**Description**: Modify template method to support resume from cursor
**Files to modify**:
- `src/extractors/base_extractor.py`

**Changes**:
```python
def extract_all(self, resume: bool = False) -> dict[str, Any]:
    """Extract all entities with optional resume."""
    # Check for existing progress
    cursor = None
    total_fetched = 0
    if resume:
        state = self._repository.get_sync_state(self._entity_type)
        if state:
            cursor = state.get("last_cursor")
            total_fetched = state.get("total_fetched", 0)
            self._logger.info(f"Resuming from cursor: {cursor}, fetched: {total_fetched}")

    # Mark as in progress
    self._repository.save_sync_state(self._entity_type, cursor, total_fetched, "in_progress")

    while True:
        response = self._fetch_page(cursor)
        edges, page_info = self._extract_edges_and_page_info(response)
        entities = [self._map_entity(e['node']) for e in edges]
        self._save_entities(entities)

        total_fetched += len(entities)
        cursor = page_info.get('endCursor')

        # Checkpoint progress
        self._repository.save_sync_state(self._entity_type, cursor, total_fetched)

        if not page_info.get('hasNextPage'):
            break

    # Mark as completed
    self._repository.save_sync_state(self._entity_type, None, total_fetched, "completed")
    return {"total": total_fetched}
```

**Dependencies**: Task 7.1
**Estimated Effort**: 1-2 hours

#### Task 7.3: Create Migration Coordinator
**Description**: Orchestrate multi-entity extraction pipeline
**Files to create**:
- `src/coordinators/max_extract_coordinator.py`

**Implementation**:
```python
class MaxExtractCoordinator:
    """Orchestrates Pass 1 (metadata) extraction."""

    ENTITY_ORDER = [
        "users",        # Extract first (no dependencies)
        "clients",
        "properties",
        "requests",
        "quotes",
        "jobs",
        "visits",
        "invoices",
        "expenses",
        "timesheets",
        "notes",        # After parent entities
        "note_attachments"  # After notes
    ]

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        entity_mapper: EntityMapper
    ):
        self._jobber_client = jobber_client
        self._repository = repository
        self._logger = logger
        self._entity_mapper = entity_mapper
        self._extractors = self._build_extractors()

    def extract_all(self, entities: List[str] = None, resume: bool = False) -> dict:
        """Extract specified entities (or all if None)."""
        entities_to_extract = entities or self.ENTITY_ORDER

        results = {}
        for entity_type in entities_to_extract:
            extractor = self._extractors.get(entity_type)
            if not extractor:
                self._logger.warning(f"No extractor for: {entity_type}")
                continue

            self._logger.info(f"Extracting: {entity_type}")
            result = extractor.extract_all(resume=resume)
            results[entity_type] = result

        return results

    def _build_extractors(self) -> dict:
        """Factory method to create all extractors."""
        return {
            "clients": ClientsExtractor(self._jobber_client, self._entity_mapper, self._repository, self._logger),
            "invoices": InvoicesExtractor(...),
            # ... (one per entity)
        }
```

**Dependencies**: Task 7.2 (resume support in extractors)
**Estimated Effort**: 2-3 hours

#### Task 7.4: Add CLI Command for Pass 1
**Description**: Create `tight jobber max-extract` command
**Files to modify**:
- `src/cli/migrate.py` - Add `max_extract` command

**Implementation**:
```python
@migrate_app.command(name="max-extract")
def max_extract(
    ctx: typer.Context,
    entities: List[str] = typer.Option(None, help="Entities to extract (default: all)"),
    resume: bool = typer.Option(False, help="Resume from last checkpoint"),
    dry_run: bool = typer.Option(False, help="Dry run (no DB writes)")
) -> None:
    """Extract all Jobber data (Pass 1: metadata)."""
    logger = create_logger(ctx.obj["verbose"])
    repository = create_repository(ctx.obj["db"])
    jobber_client = create_rate_limited_jobber_client(...)
    entity_mapper = create_entity_mapper()

    coordinator = MaxExtractCoordinator(jobber_client, repository, logger, entity_mapper)

    logger.info("Starting Max Extract (Pass 1)")
    results = coordinator.extract_all(entities=entities, resume=resume)

    # Print summary
    for entity, result in results.items():
        logger.success(f"{entity}: {result['total']} records")
```

**Dependencies**: Task 7.3
**Estimated Effort**: 1 hour

---

### Phase 8: Testing & Validation

#### Task 8.1: Unit Tests for Notes & Attachments
**Description**: Test notes/attachments extraction logic
**Files to create**:
- `tests/unit/test_notes_extractor.py`
- `tests/unit/test_note_attachments_extractor.py`
- `tests/unit/test_attachment_downloader.py`

**Pattern**:
```python
class TestNotesExtractor:
    def setup_method(self):
        self.mock_client = Mock(spec=JobberClient)
        self.mock_mapper = Mock(spec=EntityMapper)
        self.mock_repository = Mock(spec=Repository)
        self.mock_logger = Mock(spec=Logger)

        self.extractor = NotesExtractor(
            jobber_client=self.mock_client,
            entity_mapper=self.mock_mapper,
            repository=self.mock_repository,
            logger=self.mock_logger
        )

    def test_fetch_page_calls_jobber_client(self):
        self.mock_client.fetch_notes.return_value = {"data": {"notes": {}}}
        result = self.extractor._fetch_page(cursor="abc123")
        self.mock_client.fetch_notes.assert_called_once_with("abc123")
```

**Dependencies**: Tasks 2.3, 3.2, 6.2
**Estimated Effort**: 3-4 hours

#### Task 8.2: Integration Tests for Full Pipeline
**Description**: End-to-end test of max-extract flow
**Files to create**:
- `tests/integration/test_max_extract_coordinator.py`

**Test Scenarios**:
1. Full extraction of all entities
2. Resume from checkpoint
3. Cost tracking and metrics
4. Attachment download

**Dependencies**: Task 7.3 (coordinator)
**Estimated Effort**: 2-3 hours

#### Task 8.3: Validation Scripts
**Description**: Verify data completeness and relationships
**Files to create**:
- `scripts/validate_extraction.py` - Check for orphaned records, null FKs

**Checks**:
```python
def validate_foreign_keys(repository: Repository) -> List[str]:
    """Check for orphaned foreign key references."""
    issues = []

    # Check clients referenced by invoices exist
    cursor = repository._connection.cursor()
    cursor.execute("""
        SELECT i.id FROM invoices i
        LEFT JOIN clients c ON i.client_id = c.id
        WHERE c.id IS NULL
    """)
    orphans = cursor.fetchall()
    if orphans:
        issues.append(f"{len(orphans)} invoices with missing clients")

    # Check notes have valid parent entities
    # ... (similar checks)

    return issues
```

**Dependencies**: Task 7.4 (extraction complete)
**Estimated Effort**: 2 hours

---

### Phase 9: Documentation & Hardening

#### Task 9.1: Update Configuration Documentation
**Description**: Document new pagination settings and rate limits
**Files to modify**:
- `docs/configuration.md` - Add notes/attachments pagination
- `config/settings.yaml` - Add new entity types

**New Config**:
```yaml
pagination:
  # ... existing ...
  notes: 50
  note_attachments: 50
  tasks: 30
  reminders: 30
  schedules: 30
```

**Dependencies**: None
**Estimated Effort**: 1 hour

#### Task 9.2: Create Migration Guide
**Description**: Document migration workflow for users
**Files to create**:
- `docs/max_extract_guide.md`

**Content**:
```markdown
# Max Extract Guide

## Overview
Two-pass extraction for complete Jobber data migration.

## Pass 1: Metadata Extraction
```bash
tight jobber max-extract --db jobber_export.db

# Resume if interrupted
tight jobber max-extract --db jobber_export.db --resume

# Extract specific entities
tight jobber max-extract --db jobber_export.db --entities clients,invoices
```

## Pass 2: Binary Downloads
```bash
tight jobber download-attachments --db jobber_export.db --output-dir ./attachments
```

## Monitoring Progress
```bash
# Check sync state
sqlite3 jobber_export.db "SELECT * FROM entity_sync_state"

# View cost metrics
sqlite3 jobber_export.db "SELECT * FROM graphql_costs ORDER BY timestamp DESC LIMIT 10"
```
```

**Dependencies**: Tasks 7.4, 6.3
**Estimated Effort**: 2 hours

#### Task 9.3: Error Handling Review
**Description**: Ensure robust error handling across all new code
**Files to review**:
- All new extractors
- Attachment downloader
- Coordinator

**Checklist**:
- [ ] Network errors caught and retried
- [ ] GraphQL errors logged with context
- [ ] Rate limit errors trigger backoff
- [ ] Database errors rollback transactions
- [ ] User-friendly error messages

**Dependencies**: All prior tasks
**Estimated Effort**: 2-3 hours

#### Task 9.4: Performance Testing
**Description**: Test extraction against large Jobber account
**Deliverable**: Performance report with metrics

**Metrics to Capture**:
- Total runtime (per entity, overall)
- Average requests/second
- GraphQL cost utilization (requested vs available)
- Database write throughput
- Memory usage

**Dependencies**: Task 8.2 (integration tests)
**Estimated Effort**: 2-3 hours

---

## Codebase Integration Points

### Files to Modify

**Core Infrastructure:**
- `src/repositories/repository.py:104-500` - Schema updates, new methods
- `src/clients/jobber_client.py:46-500` - Notes/attachments queries
- `src/mappers/entity_mapper.py` - Notes/attachments mappers
- `src/extractors/base_extractor.py` - Resume support
- `src/cli/migrate.py` - New CLI commands
- `config/settings.yaml:18-32` - Pagination config

**New Files to Create:**
- `src/models/note.py`
- `src/models/note_attachment.py`
- `src/extractors/notes_extractor.py`
- `src/extractors/note_attachments_extractor.py`
- `src/extractors/{tasks,reminders,schedules}_extractor.py`
- `src/downloaders/attachment_downloader.py`
- `src/coordinators/max_extract_coordinator.py`
- `schema/jobber_entity_manifest.yaml`
- `docs/jobber_entity_manifest.md`
- `docs/notes_extraction_strategy.md`
- `docs/attachment_storage_strategy.md`
- `docs/max_extract_guide.md`

### Existing Patterns to Follow

**1. Extractor Pattern:**
```python
# Inherit from BaseExtractor[T]
# Implement 4 abstract methods
# Get pagination, error handling, logging for free
```

**2. ServiceFactory Wiring:**
```python
# Use ServiceFactory for dependency injection
# Don't manually instantiate with complex dependencies
```

**3. GraphQL Cost Optimization:**
```python
# ALWAYS use first: N on connections
# Limit nested queries (default: 10)
# Extract cost metadata from responses
```

**4. Database Operations:**
```python
# Use INSERT OR REPLACE for upserts
# Commit after each batch
# Parameterized queries everywhere
```

**5. Configuration Access:**
```python
# Use ConfigManager.get_pagination_size(entity)
# Fallback to default if entity not configured
```

---

## Technical Design

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  Pass 1: Metadata ETL                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  CLI Command: tight jobber max-extract                 │
│         ↓                                               │
│  MaxExtractCoordinator                                 │
│         ↓                                               │
│  ┌──────────────────────────────────────┐              │
│  │  For each entity (clients, jobs...): │              │
│  │  1. Check sync state (resume?)       │              │
│  │  2. Fetch page (cursor-based)        │              │
│  │  3. Extract cost metadata            │              │
│  │  4. Map GraphQL → dataclass          │              │
│  │  5. Save to SQLite                   │              │
│  │  6. Update sync state                │              │
│  └──────────────────────────────────────┘              │
│         ↓                                               │
│  SQLite Database                                        │
│  ├─ clients, jobs, invoices... (data)                  │
│  ├─ notes (polymorphic parent refs)                    │
│  ├─ note_attachments (metadata only)                   │
│  ├─ entity_sync_state (resume cursors)                 │
│  └─ graphql_costs (optimization metrics)               │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│              Pass 2: Binary Downloader                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  CLI Command: tight jobber download-attachments        │
│         ↓                                               │
│  AttachmentDownloader                                  │
│         ↓                                               │
│  ┌──────────────────────────────────────┐              │
│  │  For each pending attachment:        │              │
│  │  1. GET remote_url (stream)          │              │
│  │  2. Compute SHA256 hash              │              │
│  │  3. Write to {hash}.{ext}            │              │
│  │  4. Update note_attachments table    │              │
│  └──────────────────────────────────────┘              │
│         ↓                                               │
│  File System: attachments/                             │
│  └─ {sha256}.pdf, {sha256}.jpg...                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User invokes**: `tight jobber max-extract --resume`
2. **Coordinator**: Iterates through ENTITY_ORDER list
3. **Per Entity**:
   - Extractor checks `entity_sync_state` for resume cursor
   - Fetches page via `JobberClient.fetch_{entity}(cursor)`
   - RateLimitedHttpClient waits for token bucket
   - Response includes `extensions.cost` metadata
   - MetricsCollector records cost → `graphql_costs` table
   - Mapper transforms GraphQL → dataclass
   - Repository saves batch with `INSERT OR REPLACE`
   - Sync state updated with new cursor
4. **After all entities**: Summary logged
5. **User invokes**: `tight jobber download-attachments`
6. **Downloader**:
   - Queries `note_attachments` WHERE `download_status = 'pending'`
   - Downloads in batches of 100
   - Computes hash, writes file, updates table

### API Endpoints (GraphQL)

**Pass 1 Queries**:
```graphql
# Existing (to be audited)
clients(first: Int, after: String)
invoices(first: Int, after: String)
jobs(first: Int, after: String)
# ... (all entity types)

# New
notes(first: Int, after: String)  # If available as top-level
noteAttachments(first: Int, after: String)  # If available
```

**Pass 2**:
- Binary downloads via `noteAttachment.url` (HTTP GET)

---

## Dependencies and Libraries

**Existing (No New Dependencies)**:
- `requests` - HTTP client for GraphQL + binary downloads
- `sqlite3` - Database operations
- `typer` - CLI commands
- `rich` - Terminal UI
- `pytest` - Testing
- `pyyaml` - Configuration

**Optional (If Needed)**:
- `httpx` - Async HTTP client for concurrent downloads (Phase 10 optimization)

---

## Testing Strategy

### Unit Tests
- **Extractors**: Mock JobberClient, test pagination logic
- **Mappers**: Test GraphQL → dataclass transformation
- **Repository**: Test SQL operations with in-memory DB
- **Downloader**: Mock requests, test hash calculation

### Integration Tests
- **Full Pipeline**: Test max-extract with mock Jobber API
- **Resume Logic**: Interrupt extraction, verify resume works
- **Cost Tracking**: Verify metrics recorded correctly

### Edge Cases
- Empty result sets (no notes, no attachments)
- Rate limit errors (429 responses)
- GraphQL cost throttle errors
- Network failures during download
- Orphaned foreign keys

### Manual Testing
- Run against real Jobber test account
- Verify data completeness
- Check attachment files integrity
- Measure performance metrics

---

## Success Criteria

- [ ] All Priority 1 entities extracted (clients, properties, requests, quotes, jobs, visits, invoices, line items, payments)
- [ ] All Priority 2 entities extracted (tasks, timesheets, schedules, users)
- [ ] Notes extracted with correct parent references
- [ ] Attachment metadata captured in database
- [ ] Binary files downloaded and hashed
- [ ] Resume from checkpoint works for all entities
- [ ] GraphQL cost < 80% of available points throughout extraction
- [ ] Request rate < 6 req/s (within safety margin)
- [ ] Foreign key relationships validated (no orphans)
- [ ] Integration tests pass with >90% coverage
- [ ] Documentation complete and accurate

---

## Notes and Considerations

### Implementation Challenges

1. **Notes Extraction Strategy**:
   - **Risk**: Jobber may not expose top-level `notes` query
   - **Mitigation**: Implement fallback to nested extraction from parent entities
   - **Decision Point**: Task 2.1 research phase

2. **GraphQL Cost Unpredictability**:
   - **Risk**: Actual cost may vary significantly from requested
   - **Mitigation**: Implement adaptive page sizing (Task 5.3)
   - **Monitoring**: Track cost variance in `graphql_costs` table

3. **Attachment URL Expiry**:
   - **Risk**: Download URLs may have limited lifetime
   - **Mitigation**: Run Pass 2 soon after Pass 1
   - **Documentation**: Warn users in migration guide

4. **Large Account Performance**:
   - **Risk**: Extraction may take many hours
   - **Mitigation**: Resume support + progress logging
   - **Future**: Optional concurrent extraction (Phase 10)

### Future Enhancements (Out of Scope)

- Incremental sync (delta extraction)
- Parallel entity extraction
- Webhook-based real-time updates
- ServiceTitan schema mapping
- Web dashboard for monitoring
- Compression for attachments

---

**This plan is ready for execution with `/execute-plan PRPs/jobber-max-extract-refactor.md`**

**Project ID**: `140568ba-dfac-44fe-83a6-54da06275d9c` (Archon MCP)
