# Requirements: Fix Jobber Notes Extraction

## Problem Statement

The current notes extraction implementation fails because Jobber's GraphQL API does not support the `node(id:)` interface for fetching individual notes by ID.

**Current Error:**
```
GraphQL errors in response: Field 'node' doesn't exist on type 'Query'; Variable $id is declared by GetNoteById but not used
```

## Current Implementation Issues

1. **Deferred Loading Pattern Fails**: The codebase implements a two-phase approach:
   - Phase 1: Collect note IDs during parent entity extraction → `note_references` table
   - Phase 2: Bulk fetch notes using `node(id:)` interface → **FAILS**

2. **API Limitation**: Jobber only provides notes as nested fields on parent entities (clients, jobs, quotes, etc.)

3. **Large Note Counts**: Some entities have 100+ notes, requiring pagination to fetch all notes

## Requirements

### Functional Requirements

1. **Complete Note Extraction**: Extract ALL notes from all parent entities, regardless of count
2. **Handle Pagination**: Support entities with more than 100 notes per entity
3. **Avoid API Throttling**: Keep request costs low to avoid rate limiting
4. **Preserve Relationships**: Maintain parent-child relationships (note → client/job/quote/etc.)
5. **Extract Attachments**: Include attachment metadata from notes

### Technical Requirements

1. **Use Inline Extraction**: Fetch notes as nested fields in parent entity queries
2. **Pagination Strategy**: Implement pagination for notes field when `hasNextPage` is true
3. **Backward Compatibility**: Preserve existing note reference collection infrastructure
4. **Performance**: Minimize API requests while ensuring completeness
5. **Resume Support**: Support resumable extraction if interrupted

### Constraints

1. **API Limitations**:
   - No top-level `notes` query
   - No `node(id:)` interface for notes
   - Notes only available via parent entity nested fields
   - Maximum 100 notes per page in nested queries

2. **Existing Infrastructure**:
   - `note_references` table already exists
   - `NoteReferenceCollector` already integrated
   - Base extractor has note collection logic

## Success Criteria

- [ ] All notes extracted from all parent entities
- [ ] Entities with 100+ notes fully extracted via pagination
- [ ] No API throttling errors
- [ ] Note-to-parent relationships preserved
- [ ] Attachment metadata collected
- [ ] Existing tests pass
- [ ] Performance acceptable (estimate: ~5-10 min for 5000 notes)

## Research Questions

1. How do other developers handle Jobber notes extraction?
2. What is the optimal pagination strategy for nested notes?
3. Can we batch-fetch notes in any way?
4. What are the API cost implications of inline extraction?
5. How should we handle note pagination concurrently with parent pagination?
