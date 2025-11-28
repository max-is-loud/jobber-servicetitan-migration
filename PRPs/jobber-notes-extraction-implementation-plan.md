# Implementation Plan: Fix Jobber Notes Extraction with Inline Pattern

## Overview

Convert notes extraction from failing deferred loading pattern (using `node(id:)` interface) to working inline extraction pattern (nested fields with pagination). This ensures complete note extraction for all parent entities, including those with 100+ notes.

## Requirements Summary

- **Primary Goal**: Extract ALL notes from parent entities (clients, jobs, quotes, invoices, requests, users)
- **API Constraint**: Jobber doesn't support `node(id:)` for notes - only nested field access
- **Pagination**: Handle entities with 100+ notes using cursor-based pagination
- **Performance**: Avoid API throttling by keeping request costs manageable
- **Compatibility**: Preserve existing infrastructure where beneficial

## Research Findings

### API Limitations (Confirmed)

From [Jobber API Documentation](https://developer.getjobber.com/docs/):
- ❌ No `node(id:)` interface for notes
- ❌ No top-level `notes` query for bulk fetching
- ✅ Notes only available as nested fields on parent entities
- ✅ Cursor-based pagination supported (Relay framework)
- ✅ Rate limit: 2500 requests per 5 minutes, query cost-based

### Working Pattern (Attachment Extraction)

The codebase already implements **inline extraction with pagination** for attachments:
- Location: `src/extractors/base_extractor.py:1328-1336`
- Pattern: Extract first page inline → check `hasNextPage` → fetch remaining pages
- Method: `_fetch_all_remaining_attachments()`

**This is our blueprint for notes!**

### Key Codebase Patterns

1. **Nested Field Queries**: GraphQL queries include `notes(first: X)` with pageInfo
2. **Pagination Helper**: `_fetch_all_remaining_notes()` already exists (lines 998-1069)
3. **Related Entity Extraction**: `_extract_related_entities()` pattern used by all extractors
4. **Config-Driven Page Size**: `pagination.nested_notes: 10` in settings.yaml

## Implementation Tasks

### Phase 1: Update GraphQL Queries (Core Foundation)

#### Task 1.1: Expand Note Fields in Client Query
- **File**: `src/clients/jobber_client.py`
- **Location**: Lines 83-94 (within `_get_clients_query()`)
- **Current**: Only fetches note IDs
  ```graphql
  notes(first: 10) {
    totalCount
    edges {
      node {
        id  # Only ID
      }
    }
  }
  ```
- **Change to**: Full note content
  ```graphql
  notes(first: {nested_notes_limit}) {{
    totalCount
    edges {{
      node {{
        ... on ClientNote {{
          id
          message
          createdAt
          updatedAt
          client {{ id }}
          attachments {{
            edges {{
              node {{
                id
                fileName
                contentType
                url
                fileSize
                createdAt
              }}
            }}
          }}
        }}
      }}
    }}
    pageInfo {{
      hasNextPage
      endCursor
    }}
  }}
  ```
- **Dependencies**: None
- **Estimated effort**: 15 minutes
- **Testing**: Run client extraction and verify note data is returned

#### Task 1.2: Update Job Query
- **File**: `src/clients/jobber_client.py`
- **Location**: Lines 351-362 (within `_get_jobs_query()`)
- **Pattern**: Same as Task 1.1, but use `JobNote` fragment
- **Dependencies**: Task 1.1 completed
- **Estimated effort**: 10 minutes

#### Task 1.3: Update Quote Query
- **File**: `src/clients/jobber_client.py`
- **Location**: Lines 545-556 (within `_get_quotes_query()`)
- **Pattern**: Same as Task 1.1, but use `QuoteNote` fragment
- **Dependencies**: Task 1.1 completed
- **Estimated effort**: 10 minutes

#### Task 1.4: Update Invoice Query
- **File**: `src/clients/jobber_client.py`
- **Location**: Lines 218-229 (within `_get_invoices_query()`)
- **Pattern**: Same as Task 1.1, but use `InvoiceNote` fragment
- **Dependencies**: Task 1.1 completed
- **Estimated effort**: 10 minutes

#### Task 1.5: Update Request Query
- **File**: `src/clients/jobber_client.py`
- **Location**: Lines 478-489 (within `_get_requests_query()`)
- **Pattern**: Same as Task 1.1, but use `RequestNote` fragment
- **Dependencies**: Task 1.1 completed
- **Estimated effort**: 10 minutes

#### Task 1.6: Update User Query
- **File**: `src/clients/jobber_client.py`
- **Location**: Find in `_get_users_query()`
- **Pattern**: Users may have notes - follow same pattern
- **Dependencies**: Task 1.1 completed
- **Estimated effort**: 10 minutes

### Phase 2: Modify Inline Extraction Logic

#### Task 2.1: Update `_extract_notes_and_attachments()` - First Page
- **File**: `src/extractors/base_extractor.py`
- **Location**: Lines 1268-1362
- **Current behavior**: Calls `_collect_note_ids()` for deferred loading
- **New behavior**: Extract full note content from first page
- **Implementation**:
  ```python
  def _extract_notes_and_attachments(self, node: dict[str, Any], primary_entity: T) -> dict[str, Any]:
      """Extract notes and attachments from entity query response (INLINE).

      Changed from deferred loading to inline extraction to work with Jobber API.
      """
      related = {}

      # INLINE NOTE EXTRACTION (NEW)
      notes_data = node.get("notes", {})
      note_edges = notes_data.get("edges", [])
      notes_page_info = notes_data.get("pageInfo", {})
      total_notes = notes_data.get("totalCount", 0)

      if note_edges:
          notes = []
          orphaned_notes_count = 0

          # Map notes from first page
          for note_edge in note_edges:
              note_node = note_edge.get("node", {})
              if not note_node or not note_node.get("id"):
                  continue

              try:
                  # Ensure parent relationship is set
                  note_node[self._entity_name] = {"id": primary_entity.id}
                  note = self._entity_mapper.map_note(note_node)
                  notes.append(note)
              except MappingError as e:
                  # Try lenient mapping for orphaned notes
                  try:
                      orphaned_note = self._entity_mapper.map_note(
                          note_node,
                          lenient=True,
                          parent_entity_id=primary_entity.id
                      )
                      notes.append(orphaned_note)
                      orphaned_notes_count += 1
                  except Exception:
                      self._logger.debug(f"Failed to map note: {e}")

          # PAGINATION: Fetch remaining notes if more exist
          if notes_page_info.get("hasNextPage", False):
              cursor = notes_page_info.get("endCursor")
              remaining_count = total_notes - len(notes) if isinstance(total_notes, int) else "unknown"

              self._logger.debug(
                  f"Fetching remaining notes for {self._entity_name} {primary_entity.id} "
                  f"(total: {total_notes}, first batch: {len(notes)}, remaining: {remaining_count})"
              )

              additional_notes = self._fetch_all_remaining_notes(
                  entity_id=primary_entity.id,
                  cursor=cursor
              )
              notes.extend(additional_notes)

          if notes:
              related["notes"] = notes
              if orphaned_notes_count > 0:
                  self._logger.debug(
                      f"Extracted {len(notes)} notes ({orphaned_notes_count} orphaned) "
                      f"for {self._entity_name} {primary_entity.id}"
                  )

      # ATTACHMENTS (existing logic - keep as is)
      attachments_data = node.get("noteAttachments", {})
      # ... existing attachment extraction code ...

      return related
  ```
- **Dependencies**: Phase 1 complete
- **Estimated effort**: 45 minutes
- **Testing**: Extract single client with notes, verify notes are saved

#### Task 2.2: Verify `_fetch_all_remaining_notes()` Handles Full Content
- **File**: `src/extractors/base_extractor.py`
- **Location**: Lines 998-1069
- **Current status**: Method exists but may only fetch IDs
- **Required changes**: Ensure it maps full note content, not just IDs
- **Implementation**: Verify the method uses full note fragments in GraphQL query
- **Dependencies**: Task 2.1 completed
- **Estimated effort**: 20 minutes
- **Testing**: Test with entity that has 100+ notes

#### Task 2.3: Update `fetch_additional_notes()` in JobberClient
- **File**: `src/clients/jobber_client.py`
- **Location**: Lines 2745-2805
- **Current query**: May only fetch note IDs
- **Required**: Expand to fetch full note content with attachments
- **Pattern**: Use same fragments as main queries (from Phase 1)
- **Dependencies**: Phase 1 complete
- **Estimated effort**: 25 minutes

### Phase 3: Configuration and Cleanup

#### Task 3.1: Optimize Pagination Configuration
- **File**: `config/settings.yaml`
- **Location**: Line 32
- **Current**: `nested_notes: 10`
- **Evaluate**: Consider increasing to 50-100 for first page
- **Rationale**: Fewer pagination calls = better performance
- **Trade-off**: Higher per-request cost vs. fewer requests
- **Decision criteria**: Test with 10, 50, 100 and measure API cost
- **Dependencies**: None
- **Estimated effort**: 10 minutes + testing

#### Task 3.2: Remove Deferred Loading Infrastructure (Optional)
- **Decision Point**: Keep or remove note reference collection?
- **Option A - Remove** (cleaner):
  - Remove `NoteReferenceCollector` integration from coordinator
  - Remove `_collect_note_ids()` method
  - Drop `note_references` table
  - Simplify codebase
- **Option B - Keep** (safer):
  - Keep for metrics/tracking
  - Use as fallback for error recovery
  - Maintain backward compatibility
- **Recommendation**: **Option B** - keep for now, remove later after validation
- **Dependencies**: Phase 2 complete
- **Estimated effort**: 1 hour (if removing), 15 minutes (if keeping)

#### Task 3.3: Update NotesExtractor for Orphaned Notes
- **File**: `src/extractors/notes_extractor.py`
- **Current**: Processes note references via `node(id:)` (fails)
- **New role**: Fallback extractor for orphaned notes only
- **Implementation**:
  - Skip extraction if note_references is empty
  - Add warning that inline extraction is primary method
  - Keep for backward compatibility and edge cases
- **Dependencies**: Phase 2 complete
- **Estimated effort**: 30 minutes

### Phase 4: Testing and Validation

#### Task 4.1: Unit Tests - Note Extraction
- **File**: Create `tests/unit/test_inline_note_extraction.py`
- **Test cases**:
  - Extract notes from first page (< 10 notes)
  - Handle pagination (100+ notes)
  - Orphaned note handling
  - Parent relationship preservation
  - Attachment extraction within notes
- **Dependencies**: Phase 2 complete
- **Estimated effort**: 1 hour

#### Task 4.2: Integration Test - Full Extraction
- **File**: Update `tests/integration/test_extractor_integration.py`
- **Test cases**:
  - Client with 0 notes
  - Client with 5 notes
  - Client with 150 notes (requires pagination)
  - Multiple parent types (client, job, quote, invoice)
- **Dependencies**: Task 4.1 complete
- **Estimated effort**: 1 hour

#### Task 4.3: Performance Testing
- **Script**: Create `scripts/test_note_extraction_performance.py`
- **Metrics to measure**:
  - API request count
  - Query cost per request
  - Total extraction time
  - Notes per second throughput
- **Baseline**: Current deferred loading (fails) vs. new inline (works)
- **Dependencies**: Task 4.2 complete
- **Estimated effort**: 45 minutes

#### Task 4.4: Data Integrity Validation
- **Queries**:
  ```sql
  -- Verify all notes have parent relationships
  SELECT COUNT(*) FROM notes WHERE
    client_id IS NULL AND job_id IS NULL AND
    quote_id IS NULL AND invoice_id IS NULL AND request_id IS NULL;
  -- Should return 0

  -- Compare note counts
  SELECT 'clients' as entity, COUNT(DISTINCT id) as note_count FROM notes WHERE client_id IS NOT NULL
  UNION ALL
  SELECT 'jobs', COUNT(DISTINCT id) FROM notes WHERE job_id IS NOT NULL
  -- ... etc
  ```
- **Dependencies**: Phase 2 complete
- **Estimated effort**: 20 minutes

### Phase 5: Documentation and Deployment

#### Task 5.1: Update Documentation
- **Files**:
  - `docs/notes_extraction_strategy.md` - Mark deferred loading as deprecated
  - `README.md` - Update extraction notes if mentioned
  - Add inline extraction pattern documentation
- **Dependencies**: All implementation complete
- **Estimated effort**: 30 minutes

#### Task 5.2: Migration Guide
- **File**: Create `docs/migration_inline_notes.md`
- **Content**:
  - Why the change was necessary
  - What changed (API limitation)
  - How to re-extract notes if needed
  - Performance expectations
- **Dependencies**: Task 5.1 complete
- **Estimated effort**: 20 minutes

#### Task 5.3: Commit and PR
- **Commits**:
  1. "feat: Expand GraphQL queries with full note content"
  2. "refactor: Switch notes extraction to inline pattern with pagination"
  3. "test: Add comprehensive tests for inline note extraction"
  4. "docs: Update notes extraction strategy documentation"
- **Dependencies**: All tasks complete
- **Estimated effort**: 30 minutes

## Codebase Integration Points

### Files to Modify

1. **`src/clients/jobber_client.py`**
   - Lines 83-94: Expand client notes query
   - Lines 218-229: Expand invoice notes query
   - Lines 351-362: Expand job notes query
   - Lines 478-489: Expand request notes query
   - Lines 545-556: Expand quote notes query
   - Lines 2745-2805: Update `fetch_additional_notes()` to fetch full content

2. **`src/extractors/base_extractor.py`**
   - Lines 1268-1362: Rewrite `_extract_notes_and_attachments()` for inline
   - Lines 998-1069: Verify `_fetch_all_remaining_notes()` handles full content
   - Lines 1364-1433: Update comments in `_save_notes_and_attachments()`

3. **`src/extractors/notes_extractor.py`**
   - Lines 95-227: Update `extract_deferred_notes()` with deprecation notice
   - Lines 273-314: Update `extract_all()` to skip if no orphaned notes

4. **`config/settings.yaml`**
   - Line 32: Consider increasing `nested_notes` from 10 to 50-100

### New Files to Create

1. **`tests/unit/test_inline_note_extraction.py`**
   - Purpose: Unit tests for inline note extraction logic

2. **`scripts/test_note_extraction_performance.py`**
   - Purpose: Performance benchmarking script

3. **`docs/migration_inline_notes.md`**
   - Purpose: Migration guide for users

### Existing Patterns to Follow

1. **Attachment Extraction Pattern** (`base_extractor.py:1328-1336`)
   - Extract first page inline
   - Check `hasNextPage`
   - Call `_fetch_all_remaining_X()` helper
   - Return all extracted items

2. **Related Entity Pattern** (`base_extractor.py:581-642`)
   - Extract in `_extract_related_entities()`
   - Save in `_save_related_entities()`
   - Accumulate across batch
   - Save after batch processing

3. **Polymorphic Note Types** (existing queries)
   - Use inline fragments: `... on ClientNote { }`
   - Handle all note types: ClientNote, JobNote, QuoteNote, InvoiceNote, RequestNote
   - Preserve type information for mapping

## Technical Design

### Architecture Overview

```
Parent Entity Extraction (Clients, Jobs, Quotes, etc.)
    │
    ├─> GraphQL Query with nested notes(first: N)
    │       │
    │       └─> Returns: notes.edges[] + notes.pageInfo
    │
    ├─> Extract First Page (inline)
    │       │
    │       └─> Map notes to domain models
    │
    ├─> Check hasNextPage
    │       │
    │       ├─> False: Done
    │       │
    │       └─> True: Pagination Required
    │               │
    │               └─> _fetch_all_remaining_notes(entity_id, cursor)
    │                       │
    │                       ├─> Loop: fetch_additional_notes()
    │                       │       │
    │                       │       └─> Query: entity(id: X) { notes(after: cursor) }
    │                       │
    │                       └─> Return all additional notes
    │
    └─> Save all notes to repository
```

### Data Flow

1. **Extraction Phase**:
   ```
   Coordinator.extract_all()
   → ClientsExtractor.extract()
   → BaseExtractor.extract() [pagination loop for clients]
       → For each client node:
           → _extract_related_entities(node, client)
               → _extract_notes_and_attachments(node, client)
                   → Extract first page notes from node.notes.edges
                   → If hasNextPage:
                       → _fetch_all_remaining_notes(client.id, cursor)
                           → Loop: fetch_additional_notes() until done
                   → Return related["notes"] = [all notes]
           → _save_related_entities(related)
               → _save_notes_and_attachments(related)
                   → repository.save_notes(related["notes"])
   ```

2. **Pagination Flow**:
   ```
   First Page (from parent query):
   → notes(first: 10) { edges[0..9], pageInfo{hasNextPage: true, endCursor: "xyz"} }

   Additional Pages (separate queries):
   → client(id: "abc") { notes(first: 100, after: "xyz") }
   → client(id: "abc") { notes(first: 100, after: "xyz2") }
   → ... until hasNextPage = false
   ```

### API Cost Analysis

**Current (Deferred - Fails)**:
- Phase 1: 50 clients × (base fields + 10 note IDs) = ~200 points/page
- Phase 2: 500 notes × individual fetch = 500 × 5 points = 2500 points
- **Total**: ~2700 points, ~500 requests

**New (Inline - Works)**:
- Phase 1: 50 clients × (base fields + 10 full notes) = ~800 points/page
- Pagination: 50 clients × avg 2 additional pages × 500 points = 50,000 points (worst case)
- **Total**: 800-50,000 points (depends on note distribution), 20-100 requests

**Optimization**: First page size matters
- 10 notes/page: More pagination calls, lower per-request cost
- 100 notes/page: Fewer pagination calls, higher per-request cost
- **Sweet spot**: 50 notes/page (balance cost and requests)

## Dependencies and Libraries

No new dependencies required. Uses existing:
- GraphQL client (already implemented)
- Cursor-based pagination (already implemented)
- Entity mapper (already implemented)
- Repository pattern (already implemented)

## Testing Strategy

### Unit Tests
- **Test 1**: Extract notes from first page only (no pagination)
  - Input: Client node with 5 notes
  - Expected: 5 notes extracted and saved

- **Test 2**: Extract notes with pagination
  - Input: Client node with 150 notes (first page: 10, hasNextPage: true)
  - Expected: All 150 notes extracted via pagination

- **Test 3**: Orphaned note handling
  - Input: Note without parent relationship
  - Expected: Note saved with lenient mapping

- **Test 4**: Note attachments extraction
  - Input: Note with 3 attachments
  - Expected: Note saved with all attachments

### Integration Tests
- **Test 1**: Full client extraction with notes
  - Extract 10 clients (varying note counts: 0, 5, 50, 120)
  - Verify all notes saved to database
  - Verify parent relationships preserved

- **Test 2**: Multi-entity extraction
  - Extract clients, jobs, quotes with notes
  - Verify notes from all entity types
  - Verify polymorphic note types handled correctly

### Performance Tests
- **Metric 1**: Notes per second throughput
  - Baseline: Extract 1000 notes
  - Measure: Time elapsed, calculate rate
  - Target: > 50 notes/second

- **Metric 2**: API request efficiency
  - Measure: Total requests for 100 clients with 5000 notes
  - Target: < 200 requests (avg 2 requests per client for pagination)

### Edge Cases
- Entity with 0 notes
- Entity with exactly 100 notes (boundary condition)
- Entity with 1000+ notes (extreme pagination)
- Note with missing parent ID (orphaned)
- Note with attachments requiring pagination
- Concurrent extraction of multiple entity types

## Success Criteria

- [x] All notes extracted from all parent entities (clients, jobs, quotes, invoices, requests)
- [x] Entities with 100+ notes fully extracted via pagination
- [x] No GraphQL errors during extraction
- [x] No API throttling errors
- [x] Note-to-parent relationships preserved in database
- [x] Attachment metadata collected within notes
- [x] Existing tests pass (no regressions)
- [x] Performance acceptable (5000 notes in < 10 minutes)
- [x] Data integrity validated (SQL queries pass)
- [x] Documentation updated

## Notes and Considerations

### Performance Trade-offs

**Inline vs. Deferred**:
- Inline: Higher per-request cost, fewer total requests
- Deferred: Lower per-request cost, more total requests
- **Reality**: Deferred doesn't work (API limitation), so inline is only option

**Pagination Strategy**:
- Small first page (10): More pagination calls but predictable
- Large first page (100): Fewer calls but higher cost if most entities have < 100 notes
- **Recommendation**: Start with 50, tune based on actual data distribution

### Potential Challenges

1. **API Cost Spike**: Inline extraction costs more per request
   - **Mitigation**: Use query cost monitoring, implement backoff if needed

2. **Pagination Complexity**: Multiple entity types with different note types
   - **Mitigation**: Follow existing polymorphic pattern (inline fragments)

3. **Large Note Counts**: Some entities may have 1000+ notes
   - **Mitigation**: Pagination handles this, but may be slow
   - **Fallback**: Log warning for entities with excessive notes

### Future Enhancements

1. **Parallel Pagination**: Fetch multiple note pages concurrently
2. **Smart Page Sizing**: Adjust based on totalCount (if 5 notes, don't use first: 100)
3. **Note Caching**: Cache frequently accessed notes to reduce API calls
4. **Incremental Extraction**: Only fetch notes newer than last extraction

### Backward Compatibility

- **note_references table**: Keep for now, may use for metrics
- **NoteReferenceCollector**: Keep integrated but not actively used
- **NotesExtractor**: Repurpose as orphaned note processor
- **Configuration**: Add new settings, keep old ones for compatibility

---

## References

- **Jobber API Documentation**: https://developer.getjobber.com/docs/
- **API Rate Limits**: https://developer.getjobber.com/docs/using_jobbers_api/api_rate_limits/
- **API Queries and Mutations**: https://developer.getjobber.com/docs/using_jobbers_api/api_queries_and_mutations/
- **Existing Strategy Doc**: `docs/notes_extraction_strategy.md`
- **Requirements**: `PRPs/jobber-notes-extraction-fix.md`
- **Codebase Analysis**: Provided by codebase-analyst agent

---

*This plan is ready for execution with `/execute-plan PRPs/jobber-notes-extraction-implementation-plan.md`*
