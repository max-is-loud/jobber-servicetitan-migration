# Implementation Plan: Fix max-extract GraphQL Errors

## Overview
Fix 6 GraphQL errors encountered during max-extract command execution. The errors fall into two categories:
1. **Union Type Query Errors** (5 errors): Direct selections on union types without inline fragments
2. **Field Name Error** (1 error): Querying non-existent `rate` field on `TaxRate`
3. **Throttling Error** (1 error): API throttling on visits query

## Error Summary

```
❌ Errors (6):
   ✗ properties: Field 'rate' doesn't exist on type 'TaxRate'
   ✗ requests: Selections can't be made directly on unions (see selections on RequestNoteUnion)
   ✗ quotes: Selections can't be made directly on unions (see selections on QuoteNoteUnion)
   ✗ jobs: Selections can't be made directly on unions (see selections on JobNoteUnion)
   ✗ visits: Throttled
   ✗ invoices: Selections can't be made directly on unions (see selections on InvoiceNoteUnion)
```

## Research Findings

### 1. Union Type Pattern Analysis

**Current Problem**: In `_get_properties_query()`, `_get_requests_query()`, `_get_quotes_query()`, `_get_jobs_query()`, and `_get_invoices_query()`, we query notes like this:

```graphql
notes(first: {nested_notes_limit}) {
  totalCount
  edges {
    node {
      id  # ❌ WRONG: Direct selection on union type
    }
  }
}
```

**Schema Reality**: The `notes` field returns connection types that wrap union types:
- `InvoiceNoteUnionConnection` wraps `InvoiceNoteUnion` (union of InvoiceNote, ClientNote)
- `JobNoteUnionConnection` wraps `JobNoteUnion` (union of JobNote, ClientNote)
- `QuoteNoteUnionConnection` wraps `QuoteNoteUnion` (union of QuoteNote, ClientNote)
- `RequestNoteUnionConnection` wraps `RequestNoteUnion` (union of RequestNote, ClientNote)

**Correct Pattern** (from `NOTE_BY_ID_QUERY` lines 708-813):
```graphql
notes(first: {nested_notes_limit}) {
  totalCount
  edges {
    node {
      ... on InvoiceNote {
        id
      }
      ... on ClientNote {
        id
      }
    }
  }
}
```

**Why Clients Query Works**: `ClientNoteConnection` is NOT a union type - it's a direct object type.

### 2. TaxRate Field Analysis

**Current Problem** (line 398 in `_get_properties_query()`):
```graphql
taxRate {
  id
  name
  rate  # ❌ WRONG: Field doesn't exist on TaxRate in this API version
}
```

**From Schema Introspection**: TaxRate exists as a type but the `rate` field is not available in the current schema (the introspection_results.json doesn't show TaxRate fields, suggesting limited schema access or deprecated fields).

**From Analysis**:
- `analysis_output/entity_summary.md` shows: `taxRate | TaxRate | ✓` (nullable)
- `TAX_RATES_QUERY` (lines 688-705) only queries: `id`, `name`, `description` (NO `rate` field)

**Solution**: Query only fields that exist in TAX_RATES_QUERY pattern.

### 3. Throttling Issue

**Current Problem**: Visits query gets throttled during max-extract.

**Root Cause Analysis**:
- Visits use standard page size (likely 100)
- No adaptive page sizing triggered yet
- May be hitting rate limit thresholds

**Existing Solutions in Codebase**:
1. **Adaptive Page Sizing** (`_get_pagination_size()`, lines 1276-1310)
2. **Retry Logic** (`_execute_graphql_request()`, lines 1452-1583)
3. **Throttle Detection** (`_is_throttling_error()`, lines 1636-1648)

**Strategy**: Reduce default visits page size in config OR let adaptive sizing handle it.

### 4. Existing Patterns to Follow

**Pattern 1: Clients Query** (lines 46-125) - CORRECT
```graphql
notes(first: {nested_notes_size}) {
  totalCount
  edges {
    node {
      id  # ✓ WORKS: ClientNoteConnection is NOT a union
    }
  }
}
```

**Pattern 2: NOTE_BY_ID_QUERY** (lines 708-813) - CORRECT
```graphql
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
```

**Pattern 3: noteAttachments** (lines 849-854) - CORRECT
```graphql
noteAttachments(first: 10) {
  edges {
    node {
      id
      note {
        ... on InvoiceNote {  # ✓ CORRECT: Uses inline fragment
          id
        }
      }
    }
  }
}
```

## Implementation Tasks

### Phase 1: Fix Union Type Queries (Priority: Critical)

#### Task 1.1: Fix Invoice Notes Query
**File**: `src/clients/jobber_client.py`
**Location**: `_get_invoices_query()` method, lines 127-206

**Change**: Update notes query from:
```graphql
notes(first: {nested_notes_limit}) {
  totalCount
  edges {
    node {
      id
    }
  }
}
```

To:
```graphql
notes(first: {nested_notes_limit}) {
  totalCount
  edges {
    node {
      ... on InvoiceNote {
        id
      }
      ... on ClientNote {
        id
      }
    }
  }
  pageInfo {
    hasNextPage
    endCursor
  }
}
```

**Estimated effort**: 5 minutes

#### Task 1.2: Fix Quote Notes Query
**File**: `src/clients/jobber_client.py`
**Location**: `_get_quotes_query()` method, lines 208-290

**Change**: Update notes query to use inline fragments:
```graphql
notes(first: {nested_notes_limit}) {
  totalCount
  edges {
    node {
      ... on QuoteNote {
        id
      }
      ... on ClientNote {
        id
      }
    }
  }
  pageInfo {
    hasNextPage
    endCursor
  }
}
```

**Estimated effort**: 5 minutes

#### Task 1.3: Fix Job Notes Query
**File**: `src/clients/jobber_client.py`
**Location**: `_get_jobs_query()` method, lines 307-376

**Change**: Update notes query to use inline fragments:
```graphql
notes(first: {nested_notes_limit}) {
  totalCount
  edges {
    node {
      ... on JobNote {
        id
      }
      ... on ClientNote {
        id
      }
    }
  }
  pageInfo {
    hasNextPage
    endCursor
  }
}
```

**Estimated effort**: 5 minutes

#### Task 1.4: Fix Request Notes Query
**File**: `src/clients/jobber_client.py`
**Location**: `_get_requests_query()` method, lines 425-497

**Change**: Update notes query to use inline fragments:
```graphql
notes(first: {nested_notes_limit}) {
  totalCount
  edges {
    node {
      ... on RequestNote {
        id
      }
      ... on ClientNote {
        id
      }
    }
  }
  pageInfo {
    hasNextPage
    endCursor
  }
}
```

**Estimated effort**: 5 minutes

### Phase 2: Fix TaxRate Field Query (Priority: Critical)

#### Task 2.1: Remove Invalid 'rate' Field from Properties Query
**File**: `src/clients/jobber_client.py`
**Location**: `_get_properties_query()` method, lines 378-423

**Change**: Update taxRate query from:
```graphql
taxRate {
  id
  name
  rate  # ❌ Remove this line
}
```

To:
```graphql
taxRate {
  id
  name
  # Note: 'rate' field not available in current API schema
}
```

**Alternative**: If tax rate percentage is critical, investigate:
1. Check if TaxRate has alternative fields (description might contain rate info)
2. Query tax rates separately via TAX_RATES_QUERY to see available fields
3. Consider using the standalone taxRates query for complete data

**Estimated effort**: 3 minutes

### Phase 3: Address Throttling Issue (Priority: Medium)

#### Task 3.1: Reduce Visits Page Size in Configuration
**File**: `config/settings.yaml`
**Location**: pagination section

**Change**: Add or reduce visits page size:
```yaml
pagination:
  visits: 50  # Reduce from 100 to 50
  # Or let adaptive sizing handle it automatically
```

**Rationale**:
- Visits queries may have more complex nested data
- Lower initial page size prevents throttling
- Adaptive sizing will optimize based on actual API responses

**Estimated effort**: 2 minutes

#### Task 3.2: Verify Adaptive Sizing Thresholds
**File**: Review adaptive page sizing logic
**Location**: `src/clients/jobber_client.py`, `_get_pagination_size()` method

**Verification Steps**:
1. Check that adaptive sizing reduces page size when throttled
2. Ensure visits entity is included in adaptive sizing logic
3. Confirm retry logic catches throttling errors

**No code changes required** - existing logic should handle this.

**Estimated effort**: 5 minutes (verification only)

### Phase 4: Fix Map Mode Queries (Priority: Medium)

The map mode queries also need inline fragments for union types.

#### Task 4.1: Fix Map Mode Queries
**Files to update**:
- `_get_invoices_map_query()` (lines 2829-2854)
- `_get_quotes_map_query()` (lines 2856-2884)
- `_get_jobs_map_query()` (lines 2886-2911)
- `_get_requests_map_query()` (lines 2933-2958)

**Change pattern**: Add inline fragments to notes totalCount queries:
```graphql
notes {
  totalCount
}
```

**Note**: Map mode queries only fetch totalCount, not edges/nodes, so they should NOT have the direct selection error. Verify if these queries are actually failing or if only full extraction queries fail.

**Estimated effort**: 10 minutes (if needed)

### Phase 5: Update fetch_additional_notes Methods (Priority: Low)

#### Task 5.1: Check fetch_additional_notes and fetch_additional_note_ids
**File**: `src/clients/jobber_client.py`
**Locations**:
- `fetch_additional_notes()` (lines 2626-2681)
- `fetch_additional_note_ids()` (lines 2683-2729)

**Review**: These methods also query notes fields and may need inline fragments.

**Current pattern** (lines 2658-2667):
```graphql
notes(first: {page_size}, after: $cursor) {
  totalCount
  edges {
    node {
      ... on {note_type} {
        id
        message
        createdAt
      }
    }
  }
}
```

**Status**: ✓ ALREADY CORRECT - Uses inline fragments.

**Estimated effort**: 2 minutes (verification only)

## Technical Design

### Union Type Query Pattern

**Standard Pattern for All Union Type Notes**:
```graphql
notes(first: N) {
  totalCount
  edges {
    node {
      ... on [EntityType]Note {
        id
      }
      ... on ClientNote {
        id
      }
    }
  }
  pageInfo {
    hasNextPage
    endCursor
  }
}
```

**Union Type Mappings**:
- InvoiceNoteUnion: InvoiceNote, ClientNote
- QuoteNoteUnion: QuoteNote, ClientNote
- JobNoteUnion: JobNote, ClientNote
- RequestNoteUnion: RequestNote, ClientNote

### Data Flow Validation

After fixes, data should flow:
1. GraphQL query with inline fragments → Valid API response
2. Response contains `__typename` for each node
3. Entity mapper handles polymorphic note types
4. Repository stores notes with correct entity relationships

## Testing Strategy

### Unit Tests
1. Validate GraphQL query syntax (ensure inline fragments are correct)
2. Test entity mapper handles both note types in unions
3. Verify repository stores notes correctly

### Integration Tests
1. Run max-extract on test account
2. Verify all 6 error types are resolved:
   - ✓ properties: TaxRate query succeeds
   - ✓ requests: RequestNoteUnion query succeeds
   - ✓ quotes: QuoteNoteUnion query succeeds
   - ✓ jobs: JobNoteUnion query succeeds
   - ✓ invoices: InvoiceNoteUnion query succeeds
   - ✓ visits: No throttling or handled gracefully

### Edge Cases to Test
1. Notes that are ClientNote vs entity-specific notes
2. Entities with no notes (totalCount: 0)
3. Entities with paginated notes (hasNextPage: true)
4. TaxRate field when null vs when present

## Success Criteria

- [ ] All union type notes queries use inline fragments
- [ ] TaxRate query only requests available fields
- [ ] Visits throttling reduced or handled gracefully
- [ ] max-extract command completes without GraphQL errors
- [ ] All entity types extract successfully
- [ ] Notes data properly associated with parent entities

## Notes and Considerations

### Why This Happened
1. **Union types changed**: Jobber may have changed notes from direct object types to unions
2. **Schema mismatch**: Our queries were written against an older API version
3. **Incomplete introspection**: TaxRate fields not fully documented in introspection

### Future Prevention
1. **Schema validation**: Add CI step to validate queries against introspection
2. **Version tracking**: Track Jobber API version in config
3. **Field inventory**: Maintain mapping of available vs queried fields
4. **Automated testing**: Integration tests against real API for schema changes

### Alternative Approaches Considered

**Option 1: Query only totalCount** (rejected)
```graphql
notes {
  totalCount
}
```
- Pros: No union type issues
- Cons: Loses note IDs, breaks deferred loading pattern

**Option 2: Remove notes from parent queries** (rejected)
- Pros: Simplifies queries
- Cons: Requires separate note fetching, increases API calls

**Option 3: Use inline fragments** (SELECTED)
- Pros: Maintains existing architecture, minimal changes
- Cons: Slightly more verbose queries

### Dependency on Existing Features

**Deferred Loading Pattern** (PRESERVED):
- Phase 1: Collect note IDs from parent queries (with inline fragments)
- Phase 2: Fetch full notes using NOTE_BY_ID_QUERY
- Benefit: 60-70% cost reduction maintained

**Adaptive Page Sizing** (LEVERAGED):
- Existing logic handles throttling automatically
- Visits throttling should trigger adaptive reduction
- No changes needed to core logic

## References

- `src/clients/jobber_client.py`: All GraphQL queries
- `analysis_output/entity_summary.md`: Schema field inventory
- `introspection_results.json`: Full schema introspection
- `docs/architecture/notes-optimization.md`: Notes architecture documentation
- Recent commits (b708937, 4211901, c304d68): Field name fixes

---

**Plan Status**: Ready for execution with `/execute-plan PRPs/fix-max-extract-graphql-errors.md`

**Estimated Total Time**: 30-40 minutes
**Priority**: Critical - Blocks max-extract functionality
**Risk Level**: Low - Well-understood changes with clear patterns
