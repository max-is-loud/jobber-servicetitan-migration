# Note Extraction Optimization Analysis

## Executive Summary

The current note extraction implementation can be optimized to reduce API costs by **60-70%** and eliminate thousands of API calls by leveraging nested GraphQL queries with proper pagination parameters.

## Current Implementation

### How It Works Now

1. **Parent Entity Queries** (clients, invoices, jobs, quotes, requests)
   - Include nested `notes { edges { node { id } } }` query
   - **Critical Issue**: No `first` argument specified
   - API assumes maximum 100 notes per parent entity in cost calculation

2. **Deferred Note Processing**
   - Collect note IDs from parent entities
   - Fetch each note individually using `fetch_note_by_id()`
   - 1 API call per note

### Current Query Cost Analysis

**Example: Fetching 1 client with 10 notes**

```graphql
# Parent query (current)
clients(first: 42) {
  edges {
    node {
      id
      firstName
      lastName
      # ... other fields (8 fields)
      notes {              # No 'first' argument!
        edges {
          node {
            ... on ClientNote {
              id           # Only fetching ID
            }
          }
        }
      }
    }
  }
}
```

**Cost breakdown:**
- Per client: 8 fields + notes connection
- Notes cost (no `first` arg): **100 notes assumed × 1 field = 100 points**
- For 42 clients: 42 × 100 = **4,200 points just for note IDs**
- Individual note fetches: 10 notes × 6 points = **60 points**
- **Total per client: ~160 points for 10 notes**

### Problems

1. **Wasteful Cost Calculation**: API assumes 100 notes even if client has 2 notes
2. **Excessive API Calls**: 1 API call per note (could be 1000s of calls)
3. **Rate Limit Risk**: Individual calls consume restore rate inefficiently
4. **Slow Performance**: Sequential API calls add latency

## Optimization Strategies

### Strategy 1: Nested Query with Full Data (RECOMMENDED)

Fetch complete note data in parent entity queries with proper pagination.

#### Implementation

```graphql
# Optimized client query
clients(first: 42) {
  edges {
    node {
      id
      firstName
      lastName
      # ... other fields
      notes(first: 10) {              # Add pagination limit
        edges {
          node {
            ... on ClientNote {
              id                        # Fetch all fields now
              message
              createdAt
              updatedAt
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
```

#### Cost Analysis

**Same scenario: 1 client with 10 notes**

- Per client: 8 fields
- Notes cost: `first: 10` × 5 fields = **50 points**
- No individual fetches needed
- **Total: ~60 points (vs 160 points current)**
- **Savings: 100 points per client (62% reduction)**

#### Benefits

✅ **Massive cost reduction**: 60-70% fewer query points
✅ **Eliminates individual API calls**: From 1000s to 0
✅ **Predictable costs**: `first` argument provides exact cost
✅ **Better rate limit utilization**: Single query vs many small ones
✅ **Faster performance**: No sequential API call overhead

#### Edge Cases Handled

1. **Clients with >10 notes**: Implement pagination if needed
   - Use `pageInfo.hasNextPage` to detect more notes
   - Follow-up query with `after: cursor` for remaining notes
   - Still more efficient than current approach

2. **Clients with 0 notes**: No cost penalty (0 × 5 = 0)

3. **Large note messages**: Field cost is per field, not per character

### Strategy 2: Remove Nested Notes Entirely (Alternative)

Remove notes from parent queries and batch-fetch notes separately.

#### Pros
- Simplifies parent queries
- Isolates note extraction logic

#### Cons
- Loses relationship context
- Still requires individual fetches (no batch node query in Jobber API)
- **Not recommended** - Same cost as current approach

## Recommended Implementation Plan

### Phase 1: Update Parent Entity Queries

**Files to modify:**
- `src/clients/jobber_client.py`

**Changes:**

1. Add `first` argument to all nested notes queries
2. Fetch full note fields instead of just `id`
3. Extract pagination size from config or use reasonable default (10-20)

```python
# In _get_clients_query()
notes(first: 10) {
  edges {
    node {
      ... on ClientNote {
        id
        message
        createdAt
        updatedAt
      }
    }
  }
  pageInfo {
    hasNextPage
    endCursor
  }
}
```

### Phase 2: Update Extractors to Use Nested Note Data

**Files to modify:**
- `src/extractors/clients_extractor.py` (to be created per task #9b40a52c)
- `src/extractors/invoices_extractor.py` (to be created per task #44c435d7)
- Other parent extractors

**Changes:**

1. Extract notes from parent entity response during mapping
2. Save notes immediately with parent entity
3. Deprecate `extract_deferred_notes()` pattern for primary note extraction

### Phase 3: Handle Paginated Notes (if needed)

For entities with >10 notes:

1. Detect `pageInfo.hasNextPage = true`
2. Track pagination cursor for follow-up queries
3. Implement follow-up note fetching for high-note-count entities

**Configuration option:**
```yaml
pagination:
  nested_notes: 10  # How many notes to fetch per parent
  notes_threshold: 50  # Max notes before switching to deferred pattern
```

## Cost Projections

### Real-World Scenario

**Migration with:**
- 1,000 clients
- Average 5 notes per client
- 5,000 total notes

#### Current Implementation Cost

1. Client queries: 1,000 clients × 100 (assumed notes) = **100,000 points**
2. Individual note fetches: 5,000 notes × 6 points = **30,000 points**
3. **Total: 130,000 points**

At 500 points/second restore rate:
- Time to restore full capacity: 260 seconds (4.3 minutes)
- Risk of throttling: **Very High**

#### Optimized Implementation Cost

1. Client queries with nested notes: 1,000 clients × 25 (5 notes × 5 fields) = **25,000 points**
2. Individual note fetches: **0 points**
3. **Total: 25,000 points**

At 500 points/second restore rate:
- Time to restore full capacity: 50 seconds
- Risk of throttling: **Low**

**Savings: 105,000 points (81% reduction)**

## Jobber API Rate Limit Context

From `https://developer.getjobber.com/docs/using_jobbers_api/api_rate_limits/`:

### Query Cost Rules
- All fields: 1 point (except `edges`, `nodes`, `node` = 0 points)
- Connection cost: `first` arg × number of fields
- **Without `first`/`last`: assumes 100 nodes maximum**
- Nested queries multiply costs

### Rate Limits
- **Maximum available**: 10,000 points
- **Restore rate**: 500 points/second
- **DDoS protection**: 2,500 requests per 5 minutes

### Best Practices (from Jobber docs)
> "In order to avoid expensive connection queries, you should always try to supply a `first`, or `last` argument and paginate if needed. These arguments can also be applied to nested connection types inside of your original query, so it is highly recommended to use them in the case of nested queries to avoid an unnecessarily high query cost."

> "It is recommended to avoid using deeply nested queries whenever possible as the query cost can increase exponentially based on the number of nodes."

**Our optimization aligns perfectly with Jobber's recommendations.**

## Next Steps

1. ✅ Research completed - Document created
2. ⬜ Update parent entity GraphQL queries with `first` argument on nested notes
3. ⬜ Modify entity mappers to extract nested note data
4. ⬜ Test with real Jobber data to validate cost savings
5. ⬜ Add configuration options for nested note pagination size
6. ⬜ Update documentation
7. ⬜ Deprecate individual note fetching pattern

## Related Tasks

- Task #9b40a52c: Create ClientsExtractor class
- Task #44c435d7: Create InvoicesExtractor class
- Task #f5f3becb: Refactor coordinator to use extractors consistently

**Recommendation**: Implement this optimization as part of the ClientsExtractor and InvoicesExtractor creation tasks to ensure consistency across the codebase.

## References

- Jobber API Rate Limits: https://developer.getjobber.com/docs/using_jobbers_api/api_rate_limits/
- Current implementation: `src/extractors/notes_extractor.py:85-212`
- Current queries: `src/clients/jobber_client.py:46-587`
- Configuration: `config/settings.yaml:17-30`
