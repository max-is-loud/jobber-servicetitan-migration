# Notes Extraction Strategy

**Date**: 2025-11-24
**Context**: Jobber Max Extract Refactor - Phase 2
**Decision**: Hybrid extraction using deferred loading pattern

---

## Research Findings

### Jobber API Constraints

After analyzing the Jobber GraphQL API and existing codebase (src/clients/jobber_client.py:285-296), the following limitations were discovered:

1. **No Top-Level Notes Query**: Jobber does not provide a bulk `notes(first: N)` query for pagination
2. **Access Patterns**:
   - **Nested**: Notes available via parent entity connections (e.g., `client.notes(first: 10)`)
   - **Individual**: Single note fetch via `node(id:)` interface with polymorphic fragments
3. **Attachments**: No standalone `noteAttachments` query - must be fetched with parent entities

### Existing Implementation Pattern

The codebase already implements a **deferred loading pattern**:

```python
# From JobberClient comments (line 285-291):
# 1. Collect note IDs during parent entity extraction
# 2. Fetch individual notes using node(id:) interface (see NOTE_BY_ID_QUERY)
# This avoids nested query complexity that triggers API rate limiting.
```

**Existing NOTE_BY_ID_QUERY** (line 696-739):
```graphql
query GetNoteById($id: ID!) {
  node(id: $id) {
    ... on ClientNote {
      id
      message
      createdAt
      client { id }
    }
    ... on JobNote {
      id
      message
      createdAt
      job { id }
    }
    ... on QuoteNote { ... }
    ... on InvoiceNote { ... }
    ... on RequestNote { ... }
  }
}
```

---

## Extraction Strategy: Hybrid Approach

### Option A: Nested Extraction (During Parent Fetch) ❌

**How it works**:
```graphql
clients(first: 50) {
  edges {
    node {
      id
      notes(first: 10) {  # Fetch notes inline
        edges { node { id message } }
      }
    }
  }
}
```

**Pros**:
- Single pass for parent + notes
- Simpler orchestration

**Cons**:
- ❌ High GraphQL cost (exponential multiplication)
- ❌ Limited to 10 notes per parent (hard cap to control cost)
- ❌ Incomplete extraction if client has >10 notes
- ❌ Cannot paginate nested notes without additional queries

**Cost Example**:
- 50 clients × 10 notes × 3 fields = 1,500 points per page
- Triggers throttling on large accounts

---

### Option B: Top-Level Bulk Query ❌

**Availability**: **NOT SUPPORTED** by Jobber API

Jobber does not expose a top-level paginated notes query like:
```graphql
notes(first: 100) {  # DOES NOT EXIST
  edges { node { id message } }
}
```

---

### Option C: Deferred Loading via node(id:) ✅ **SELECTED**

**How it works** (Two-phase approach):

#### Phase 1: Collect Note IDs
During parent entity extraction, collect note IDs from nested queries:

```graphql
clients(first: 50) {
  edges {
    node {
      id
      notes(first: 10) {
        totalCount  # Know how many notes exist
        edges { node { id } }  # Just IDs, not full content
        pageInfo { hasNextPage }  # Check if more exist
      }
    }
  }
}
```

Store in temporary table:
```sql
CREATE TABLE note_references (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  note_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
```

#### Phase 2: Bulk Fetch Full Notes
Iterate collected note IDs and fetch individually:

```python
for note_id in collected_note_ids:
    response = fetch_note_by_id(note_id)  # Uses node(id:) interface
    note = map_note(response)
    save_note(note)
```

**Pros**:
- ✅ **Complete coverage**: Can fetch ALL notes (not limited to 10)
- ✅ **Lower GraphQL cost**: Parent queries only fetch IDs (1 field)
- ✅ **Parallelizable**: Individual note fetches can run concurrently
- ✅ **Resume-friendly**: Can checkpoint per note ID
- ✅ **Handles pagination**: Use `pageInfo.hasNextPage` to fetch additional note IDs if >10 exist

**Cons**:
- ⚠️ Requires two passes (parent entities → notes)
- ⚠️ More orchestration complexity
- ⚠️ Higher total request count (but lower cost per request)

**Cost Comparison**:

| Approach | Requests | Cost per Request | Total Cost |
|----------|----------|------------------|------------|
| Nested (full) | 1 | 1,500 points | 1,500 |
| Deferred (IDs only) | 1 + 500 notes | 100 + (500 × 5) | 2,600 |

Despite higher request count, deferred loading:
- Stays under rate limit (4-6 req/s ceiling)
- Reduces per-request cost (100 vs 1,500)
- Enables complete extraction (no 10-note limit)

---

## Implementation Plan

### Step 1: Extend Parent Entity Queries
Modify existing queries to include:
```graphql
notes(first: 100) {  # Max limit to reduce passes
  totalCount
  edges { node { id } }  # ID only
  pageInfo { hasNextPage endCursor }
}
```

**Example**: `_get_clients_query()` in JobberClient

### Step 2: Store Note References During Extraction
```python
# In ClientsExtractor._save_entities()
for client in clients:
    for note_id in client.note_ids:
        repository.save_note_reference(
            note_id=note_id,
            entity_type="client",
            entity_id=client.id
        )
```

### Step 3: Create NotesExtractor
```python
class NotesExtractor:
    def extract_all(self):
        # Get all note IDs from note_references table
        note_ids = repository.get_pending_note_ids()

        for note_id in note_ids:
            # Fetch full note via node(id:) interface
            response = jobber_client.fetch_note_by_id(note_id)
            note = mapper.map_note(response)
            repository.save_note(note)
            repository.mark_note_reference_processed(note_id)
```

### Step 4: Handle Pagination for Notes >100
If `notes.pageInfo.hasNextPage == true`:
```python
# Fetch additional note IDs
def fetch_additional_note_ids(entity_type, entity_id, cursor):
    # Use entity-specific query with cursor
    response = fetch_entity_notes_page(entity_type, entity_id, cursor)
    # Extract and store additional note IDs
```

---

## Attachment Handling

**Strategy**: Extract attachment metadata during parent entity queries

Attachments (`noteAttachments`) are available as nested fields on parent entities:

```graphql
clients(first: 50) {
  edges {
    node {
      noteAttachments(first: 100) {
        edges {
          node {
            id
            note { id }
            fileName
            contentType
            fileSize
            url  # Remote download URL
          }
        }
      }
    }
  }
}
```

**Implementation**:
1. Extract attachment metadata during parent entity fetch (Pass 1)
2. Store in `attachments` table with `download_status='pending'`
3. Binary downloads handled in separate pass (Pass 2 - out of scope for notes extraction)

---

## Migration Coordinator Integration

**Execution Order**:
```python
ENTITY_ORDER = [
    "users",        # No dependencies
    "clients",      # Extract + collect note IDs
    "properties",   # Extract + collect note IDs
    "requests",     # Extract + collect note IDs
    "quotes",       # Extract + collect note IDs
    "jobs",         # Extract + collect note IDs
    "visits",       # Extract + collect note IDs
    "invoices",     # Extract + collect note IDs
    "notes",        # ← Bulk fetch after parent entities
]
```

**Note**: `notes` extraction runs AFTER all parent entities to ensure all note IDs are collected.

---

## Validation & Testing

### Unit Tests
- Test note ID collection during parent extraction
- Test individual note fetching via `node(id:)`
- Test polymorphic note mapping (ClientNote, JobNote, etc.)
- Test pagination for entities with >100 notes

### Integration Tests
- End-to-end: parent entities → note IDs → full notes
- Verify no duplicate notes
- Verify all note IDs from `note_references` are fetched

### Data Integrity Checks
```sql
-- Ensure all collected note IDs are fetched
SELECT COUNT(*) FROM note_references nr
LEFT JOIN notes n ON nr.note_id = n.id
WHERE n.id IS NULL;  -- Should return 0
```

---

## Performance Estimates

**Assumptions**:
- 1,000 clients with avg 5 notes each = 5,000 notes
- Request rate: 5 req/s
- Page size: 50 clients/page

**Phase 1 (Collect Note IDs)**:
- 20 pages × 0.2s = 4 seconds

**Phase 2 (Fetch Full Notes)**:
- 5,000 notes ÷ 5 req/s = 1,000 seconds (~17 minutes)

**Optimizations**:
- Batch note fetches (if Jobber supports multi-ID query)
- Parallel fetching (5-10 concurrent requests)
- Can reduce to ~3-5 minutes with concurrency

---

## Alternative Considered: GraphQL Aliases

**Idea**: Use GraphQL aliases to fetch multiple notes in one query:
```graphql
{
  note1: node(id: "123") { ... on ClientNote { id message } }
  note2: node(id: "456") { ... on ClientNote { id message } }
  note3: node(id: "789") { ... on ClientNote { id message } }
}
```

**Decision**: **Not recommended**
- Complex query construction
- Still limited by request cost (all notes counted)
- No benefit over sequential individual fetches
- Harder to implement resume logic

---

## Decision Summary

**Selected Strategy**: **Option C - Deferred Loading via node(id:)**

**Rationale**:
1. Only viable option for complete note extraction (Jobber API limitation)
2. Lower per-request cost prevents throttling
3. Enables parallel/concurrent fetching
4. Already implemented pattern in codebase (`NOTE_BY_ID_QUERY`)
5. Resume-friendly with checkpoint tracking

**Trade-offs Accepted**:
- Higher request count (acceptable within rate limits)
- Two-pass extraction (necessary for completeness)
- More complex orchestration (mitigated by existing patterns)

---

## References

- Jobber API Docs: https://developer.getjobber.com/docs/
- Existing Implementation: `src/clients/jobber_client.py:285-296, 696-739`
- Note Model: `src/models/note.py`
- Repository: `src/repositories/repository.py` (note_references table)
