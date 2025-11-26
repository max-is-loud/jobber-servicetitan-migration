# Phase 2 Async Parallel Fetching - Completion Requirements

**Date:** 2025-11-24
**Status:** 🔴 CRITICAL GAPS - NOT PRODUCTION READY
**Audit By:** Jenny (Senior Software Engineering Auditor)
**Priority:** HIGH - Blocks 3-5x performance improvement goal

---

## Executive Summary

### Current State
- ✅ **Phase 1 Complete:** Deferred attachments working, 2x improvement achieved
- ⚠️ **Phase 2 Infrastructure Built:** Async HTTP client, rate limiter, configuration
- 🔴 **Phase 2 Core Missing:** No actual parallel fetching implementation
- ❌ **Phase 3 Not Started:** No integration or testing

### Performance Impact
| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Query Cost | 1,300 pts | 1,300 pts | ✅ Achieved |
| Throughput | ~400 inv/min | 1,200 inv/min | 🔴 3x missing |
| Improvement | 2x | 5-6x | 🔴 3x missing |

**Root Cause:** AsyncParallelStreamExtractor implements sequential processing instead of actual parallel fetching.

---

## Critical Issues (Must Fix)

### C-1: No Actual Parallel Fetching 🔴 CRITICAL

**File:** `src/extractors/async_parallel_stream_extractor.py`
**Lines:** 178-206

**Problem:**
Current implementation processes pages **sequentially** in a while loop:
```python
async def _parallel_fetch_pages(self, http_client, initial_cursor):
    current_cursor = initial_cursor
    while current_cursor:
        # Fetches ONE page at a time - NO PARALLELISM
        page_result = await self._fetch_and_save_page(http_client, current_cursor)
        # ...wait for completion before next page
```

**Required Implementation:**
Use `asyncio.gather()` to fetch multiple pages concurrently:

```python
async def _parallel_fetch_pages(self, http_client, initial_cursor):
    """Fetch remaining pages with true parallel execution."""

    # Strategy: Build a cursor queue from initial discovery
    cursor_queue = [initial_cursor]
    all_cursors_discovered = False

    while cursor_queue or not all_cursors_discovered:
        # Take batch of cursors up to max_concurrent
        batch = cursor_queue[:self._max_concurrent]
        cursor_queue = cursor_queue[self._max_concurrent:]

        if not batch:
            break

        # Fetch multiple pages in parallel using asyncio.gather
        tasks = [
            self._fetch_and_save_page(http_client, cursor)
            for cursor in batch
        ]

        # Wait for all tasks in batch to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results: extract new cursors, handle errors
        for result in results:
            if isinstance(result, Exception):
                self._logger.error(f"Page fetch failed: {result}")
                self._metrics["failed_requests"] += 1
                continue

            if result:
                _, page_info, _ = self._extract_edges_and_page_info(result)
                if page_info.get("hasNextPage"):
                    new_cursor = page_info.get("endCursor")
                    cursor_queue.append(new_cursor)
                else:
                    # No more pages after this one
                    all_cursors_discovered = True
```

**Reference:** Original spec lines 848-920 in `PRPs/graphql-streaming-optimization-plan.md`

**Acceptance Criteria:**
- [ ] Uses `asyncio.gather()` to fetch N pages concurrently (N = max_concurrent)
- [ ] Manages cursor queue to discover and fetch subsequent pages
- [ ] Isolates errors per page (one failure doesn't stop others)
- [ ] Respects max_concurrent setting (3-4 concurrent pages)
- [ ] Achieves **3x throughput improvement** over sequential with max_concurrent=3

---

### C-2: Missing Semaphore Concurrency Control 🔴 CRITICAL

**File:** `src/extractors/async_parallel_stream_extractor.py`
**Lines:** 47-98 (constructor), 208-251 (fetch method)

**Problem:**
No semaphore to limit concurrent requests. If parallel fetching were implemented, this would cause unbounded concurrency and rate limit violations.

**Required Implementation:**

1. **Add semaphore to constructor:**
```python
def __init__(self, jobber_client, repository, logger, entity_type,
             rate_limiter, config_manager=None, max_concurrent=3,
             progress_callback=None):
    # ... existing init code ...

    # Add semaphore for concurrency control
    self._semaphore = asyncio.Semaphore(max_concurrent)
```

2. **Wrap requests with semaphore:**
```python
async def _fetch_and_save_page(self, http_client, cursor):
    """Fetch page with semaphore and rate limiting."""

    # Acquire semaphore slot (blocks if max_concurrent reached)
    async with self._semaphore:
        # Then acquire rate limit token
        if not await self._rate_limiter.acquire_async(timeout=60.0):
            self._logger.warning("Rate limiter timeout")
            return None

        # Now safe to fetch
        page_data = await self._fetch_page(http_client, cursor)
        # ... rest of implementation
```

**Reference:** Original spec lines 774-775, 804-805

**Acceptance Criteria:**
- [ ] Semaphore initialized with max_concurrent value
- [ ] All page fetches wrapped with `async with self._semaphore:`
- [ ] Concurrent requests never exceed max_concurrent
- [ ] Rate limiter still functions correctly
- [ ] No rate limit violations under load

---

### C-3: Missing Nested Relations Fetching 🔴 CRITICAL

**File:** `src/extractors/async_parallel_stream_extractor.py`
**Problem:** Doesn't fetch complete notes/attachments when entities have >10 items

**Reference Implementation:**
`src/extractors/stream_extractor.py:220-377` - `_fetch_complete_nested_relations()`

**Required Implementation:**
Port the nested relations logic from StreamExtractor to async version:

```python
async def _fetch_complete_nested_relations(
    self,
    raw_nodes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Async version of nested relations fetching.

    Fetches all pages of notes and attachments when totalCount > page size.
    Uses parallel fetching for multiple entities' nested relations.
    """

    nodes_needing_fetch = []

    # Identify which nodes need additional fetching
    for node in raw_nodes:
        needs_fetch = False

        # Check notes pagination
        if "notes" in node:
            notes_conn = node["notes"]
            if notes_conn.get("pageInfo", {}).get("hasNextPage"):
                needs_fetch = True

        # Check attachments pagination
        if "noteAttachments" in node:
            attach_conn = node["noteAttachments"]
            if attach_conn.get("pageInfo", {}).get("hasNextPage"):
                needs_fetch = True

        if needs_fetch:
            nodes_needing_fetch.append(node)

    # Fetch additional pages for all nodes concurrently
    if nodes_needing_fetch:
        tasks = [
            self._fetch_node_nested_pages(node)
            for node in nodes_needing_fetch
        ]
        completed_nodes = await asyncio.gather(*tasks, return_exceptions=True)

        # Update raw_nodes with completed data
        # ... merge logic here

    return raw_nodes
```

**Acceptance Criteria:**
- [ ] Detects when notes/attachments have `hasNextPage: true`
- [ ] Fetches all remaining pages for notes and attachments
- [ ] Uses async/parallel fetching for multiple entities
- [ ] Data completeness matches StreamExtractor output
- [ ] Integration test comparing outputs passes

---

### C-4: No ServiceFactory Integration 🔴 CRITICAL

**File:** `src/cli/services/factories.py`
**Missing Method:** `create_async_parallel_stream_extractor()`

**Required Implementation:**

```python
def create_async_parallel_stream_extractor(
    self,
    entity_type: str,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> AsyncParallelStreamExtractor:
    """
    Create AsyncParallelStreamExtractor with all dependencies.

    Args:
        entity_type: Entity type to stream (e.g., "clients", "invoices")
        progress_callback: Optional progress callback

    Returns:
        Configured AsyncParallelStreamExtractor instance
    """
    from ..extractors.async_parallel_stream_extractor import AsyncParallelStreamExtractor

    # Get max_concurrent from config (with entity-specific override)
    max_concurrent = self.config_manager.get_max_concurrent(entity_type)

    return AsyncParallelStreamExtractor(
        jobber_client=self.jobber_client,
        repository=self.repository,
        logger=self.logger,
        entity_type=entity_type,
        rate_limiter=self.rate_limiter,  # Share same rate limiter!
        config_manager=self.config_manager,
        max_concurrent=max_concurrent,
        progress_callback=progress_callback,
    )
```

**Key Points:**
- Shares the same `rate_limiter` instance across all extractors
- Reads `max_concurrent` from config with entity-specific overrides
- Follows existing DI pattern (same as `create_stream_extractor`)

**Reference:** Original spec lines 1188-1232

**Acceptance Criteria:**
- [ ] Method exists in ServiceFactory
- [ ] Returns configured AsyncParallelStreamExtractor
- [ ] Shares rate limiter instance (critical for correctness)
- [ ] Respects entity-specific max_concurrent overrides
- [ ] Follows existing factory patterns

---

### C-5: No CLI Command Integration 🔴 CRITICAL

**File:** `src/cli/migrate.py`
**Function:** `stream()` command

**Required Implementation:**
Add conditional logic to use async extractor when enabled:

```python
@app.command()
def stream(
    entity_type: str = typer.Argument(..., help="Entity type to stream"),
    resume: bool = typer.Option(False, "--resume", help="Resume from saved cursor"),
    # ... other options
):
    """Stream entities to staging table using optimized pagination."""

    try:
        factory = create_service_factory()

        # Check if parallel fetching is enabled
        if factory.config_manager.is_parallel_fetching_enabled():
            logger.info(
                f"Using async parallel streaming for {entity_type} "
                f"(max_concurrent={factory.config_manager.get_max_concurrent(entity_type)})"
            )

            # Create async extractor
            extractor = factory.create_async_parallel_stream_extractor(
                entity_type=entity_type,
                progress_callback=progress.update_progress,
            )

            # Run async streaming
            import asyncio
            result = asyncio.run(extractor.stream(resume=resume))

        else:
            logger.info(f"Using sequential streaming for {entity_type}")

            # Create sequential extractor (existing code)
            extractor = factory.create_stream_extractor(
                entity_type=entity_type,
                progress_callback=progress.update_progress,
            )

            # Run sequential streaming
            result = extractor.stream(resume=resume)

        # Display results
        logger.info(
            f"Streamed {result['total_streamed']} {entity_type} "
            f"in {result['duration']:.1f}s "
            f"({result.get('throughput', 0):.1f} entities/sec)"
        )

    except Exception as e:
        logger.error(f"Stream failed: {e}")
        raise typer.Exit(1)
```

**Reference:** Original spec lines 1256-1310

**Acceptance Criteria:**
- [ ] Checks `is_parallel_fetching_enabled()` from config
- [ ] Uses async extractor when enabled, sequential when disabled
- [ ] Properly runs async code with `asyncio.run()`
- [ ] Maintains backward compatibility (sequential still works)
- [ ] Logs which mode is being used
- [ ] Reports metrics (throughput, duration) for both modes

---

## Important Gaps (Should Fix)

### I-1: Limited Entity Type Support ⚠️ HIGH

**File:** `src/extractors/async_parallel_stream_extractor.py`
**Lines:** 39-45

**Problem:**
Only 5 of 12 entity types supported:
- ✅ clients, invoices, quotes, jobs, requests
- ❌ properties, users, expenses, visits, timesheetEntries, productsAndServices, taxRates

**Required Implementation:**
Add remaining 7 entity types to `_RESPONSE_PATHS`:

```python
_RESPONSE_PATHS = {
    # Existing
    "clients": ["data", "clients"],
    "invoices": ["data", "invoices"],
    "quotes": ["data", "quotes"],
    "jobs": ["data", "jobs"],
    "requests": ["data", "requests"],

    # Add these
    "properties": ["data", "properties"],
    "users": ["data", "users"],
    "expenses": ["data", "expenses"],
    "visits": ["data", "visits"],
    "timesheetEntries": ["data", "timesheetEntries"],
    "productsAndServices": ["data", "productsAndServices"],
    "taxRates": ["data", "taxRates"],
}
```

Also update `_build_query()` to support all entity types.

**Acceptance Criteria:**
- [ ] All 12 entity types supported
- [ ] Each type has correct response path
- [ ] Each type has query builder mapping
- [ ] Tested with at least invoices, clients, jobs (high priority)

---

### I-2: No Test Coverage ⚠️ HIGH

**Missing Files:**
- `tests/unit/clients/test_async_http_client.py` - Already exists ✅
- `tests/unit/extractors/test_async_parallel_stream_extractor.py` - Need to create
- `tests/integration/test_async_parallel_streaming.py` - Need to create

**Required Tests:**

#### Unit Tests for AsyncParallelStreamExtractor

```python
# tests/unit/extractors/test_async_parallel_stream_extractor.py

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from src.extractors.async_parallel_stream_extractor import AsyncParallelStreamExtractor


@pytest.mark.asyncio
async def test_parallel_fetching_multiple_pages():
    """Test that multiple pages are fetched in parallel."""
    # Mock dependencies
    # ... setup

    # Should fetch up to max_concurrent pages in parallel
    # Verify asyncio.gather was called
    # Verify concurrent execution (time-based)


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """Test that semaphore prevents exceeding max_concurrent."""
    # Create extractor with max_concurrent=3
    # Attempt to fetch 10 pages
    # Verify never more than 3 concurrent requests


@pytest.mark.asyncio
async def test_rate_limiter_integration():
    """Test rate limiter is properly awaited."""
    # Mock rate limiter
    # Verify acquire_async is called for each request


@pytest.mark.asyncio
async def test_nested_relations_fetching():
    """Test complete nested notes/attachments fetching."""
    # Create entity with >10 notes (hasNextPage: true)
    # Verify all pages fetched
    # Compare with StreamExtractor output


@pytest.mark.asyncio
async def test_error_isolation():
    """Test one failed page doesn't stop others."""
    # Mock one page to fail
    # Verify other pages complete successfully
    # Verify failed_requests metric incremented
```

#### Integration Tests

```python
# tests/integration/test_async_parallel_streaming.py

@pytest.mark.integration
@pytest.mark.asyncio
async def test_parallel_vs_sequential_throughput():
    """
    Compare async parallel vs sequential streaming performance.

    Expected: Parallel should be ~3x faster with max_concurrent=3
    """
    # Stream 100 invoices using sequential
    # Stream 100 invoices using parallel
    # Assert parallel is 2.5-3.5x faster


@pytest.mark.integration
@pytest.mark.asyncio
async def test_data_integrity():
    """
    Verify async parallel produces identical data to sequential.

    Critical: Data completeness must match exactly.
    """
    # Stream same entity set with both extractors
    # Compare raw_entities tables
    # Assert byte-for-byte identical (order-independent)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rate_limit_compliance():
    """
    Verify parallel fetching respects rate limits.

    Should not exceed configured refill_rate even with concurrency.
    """
    # Monitor actual request rate
    # Verify stays within limits
    # Verify no throttling errors
```

**Reference:** Original spec lines 467-539, 982-1086, 1337-1497

**Acceptance Criteria:**
- [ ] Unit test coverage >80% for AsyncParallelStreamExtractor
- [ ] Integration tests verify 3x performance improvement
- [ ] Integration tests verify data integrity
- [ ] All tests pass consistently

---

### I-3: Incomplete Metrics Tracking ⚠️ MEDIUM

**File:** `src/extractors/async_parallel_stream_extractor.py`
**Lines:** 90-97

**Missing Metrics:**
```python
self._metrics = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_entities": 0,
    "start_time": 0.0,
    "end_time": 0.0,

    # Add these
    "parallel_batches": 0,       # Number of parallel batches executed
    "avg_batch_time": 0.0,       # Average time per batch
    "max_concurrent_used": 0,    # Peak concurrent requests
    "rate_limit_waits": 0,       # Times waited for rate limit
}
```

**Acceptance Criteria:**
- [ ] Track parallel batches executed
- [ ] Track average batch completion time
- [ ] Track peak concurrent requests used
- [ ] Log comprehensive performance summary at end

---

## Implementation Plan

### Phase 2 Completion Checklist

**Critical Path (Must Complete):**
- [ ] **C-1:** Implement true parallel fetching with `asyncio.gather()`
- [ ] **C-2:** Add semaphore concurrency control
- [ ] **C-3:** Port nested relations fetching logic
- [ ] **C-4:** Add `create_async_parallel_stream_extractor()` to ServiceFactory
- [ ] **C-5:** Integrate into CLI `stream` command with config check
- [ ] **I-2:** Add integration tests (parallel vs sequential, data integrity)

**Important (Should Complete):**
- [ ] **I-1:** Add remaining 7 entity types
- [ ] **I-2:** Add comprehensive unit tests
- [ ] **I-3:** Enhance metrics tracking

**Optional (Nice to Have):**
- [ ] Add logging to AsyncHttpClient
- [ ] Add performance monitoring dashboard
- [ ] Optimize cursor queue management

### Estimated Effort
- **Critical Issues (C-1 to C-5):** 4-6 hours
- **Important Gaps (I-1 to I-3):** 2-3 hours
- **Total:** 6-9 hours

### Testing Strategy
1. **Unit Tests:** Verify each component works correctly in isolation
2. **Integration Tests:** Verify end-to-end with actual API calls (use test account)
3. **Performance Validation:** Measure actual throughput improvement
4. **Data Integrity:** Compare parallel vs sequential outputs

---

## Acceptance Criteria (Phase 2 Complete)

### Functional Requirements
- [ ] Async parallel streaming works for all 12 entity types
- [ ] Produces identical data to sequential StreamExtractor
- [ ] Respects rate limits (no throttling errors)
- [ ] Handles errors gracefully (one page failure doesn't stop others)
- [ ] CLI command switches between parallel/sequential based on config
- [ ] Backward compatible (sequential mode still works)

### Performance Requirements
- [ ] **3x throughput improvement** with max_concurrent=3 (vs sequential)
- [ ] **5-6x total improvement** combining Phase 1 (2x) and Phase 2 (3x)
- [ ] 10k invoices complete in ~8 minutes (target: <10 min)
- [ ] No rate limit violations during parallel execution

### Quality Requirements
- [ ] Unit test coverage >80% for new code
- [ ] All integration tests pass
- [ ] No data loss or corruption
- [ ] Comprehensive logging and metrics
- [ ] Documentation updated

---

## Files Reference

### Files to Modify (Critical)
1. `src/extractors/async_parallel_stream_extractor.py` - Fix parallel fetching, add semaphore, nested relations
2. `src/cli/services/factories.py` - Add factory method
3. `src/cli/migrate.py` - Add CLI integration

### Files to Create (Testing)
4. `tests/unit/extractors/test_async_parallel_stream_extractor.py` - Unit tests
5. `tests/integration/test_async_parallel_streaming.py` - Integration tests

### Files Already Complete ✅
- `src/clients/jobber_client.py` - Query mode parameter (Phase 1)
- `src/extractors/stream_extractor.py` - Stream mode usage (Phase 1)
- `config/settings.yaml` - Rate limits and parallel config
- `src/clients/async_http_client.py` - Async HTTP wrapper
- `src/rate_limiting/token_bucket.py` - Async rate limiting
- `src/config/config_manager.py` - Parallel fetching config methods
- `src/config/config_models.py` - ParallelFetchingConfig model

### Reference Specifications
- `PRPs/graphql-streaming-optimization-plan.md` - Original implementation plan
- `PRPs/graphql-streaming-optimization.md` - Performance analysis

---

## Architecture Notes

### Parallel Fetching Strategy

**Cursor Queue Pattern:**
```
1. Fetch first page → get cursor A
2. Fetch cursor A → get cursors B, C, D (if multiple pages remain)
3. Fetch B, C, D in parallel → get cursors E, F, G, H, I
4. Fetch E, F, G, H, I in parallel (up to max_concurrent)
5. Continue until no more cursors
```

**Key Insight:** GraphQL cursor-based pagination DOES support fetching non-sequential pages in parallel, as long as you have the cursor values. The first page gives you cursor for page 2, which you can use to fetch page 2 and discover cursor for page 3, etc.

### Rate Limiting Design

**Two-Level Control:**
1. **Semaphore (Concurrency):** Limits max concurrent requests (e.g., 3)
2. **Rate Limiter (Throughput):** Limits requests per minute (e.g., 20/min)

Both must be respected:
```python
async with self._semaphore:           # Wait for concurrency slot
    await self._rate_limiter.acquire() # Wait for rate limit token
    await fetch_page()                 # Now safe to fetch
```

### Error Handling

**Error Isolation:**
- Use `asyncio.gather(..., return_exceptions=True)`
- Check each result for exceptions
- Log failures but continue with successful pages
- Track metrics: `successful_requests`, `failed_requests`

---

## Questions for Clarification

### Architectural
1. **Cursor Discovery:** Can we fetch page N+2 before page N+1 completes? (Assumption: Yes, if we have the cursor)
2. **Database Writes:** Is `loop.run_in_executor()` + SQLite WAL sufficient for concurrent writes? (Assumption: Yes)

### Priority
1. Which entity types are highest priority? (Likely: invoices, clients, jobs based on volume)
2. Is 3x improvement acceptable, or must we achieve 5x? (3x from parallel + 2x from Phase 1 = 6x total)

---

## Success Metrics

### Before (Phase 1 Only)
- Query Cost: 1,300 points ✅
- Throughput: ~400 invoices/min
- 10k invoices: ~25 minutes
- Improvement: 2x

### After (Phase 1 + Phase 2 Complete)
- Query Cost: 1,300 points ✅
- Throughput: 1,200 invoices/min ⚡
- 10k invoices: ~8 minutes ⚡
- Improvement: **5-6x** ⚡

### Validation Test
```bash
# Sequential (baseline)
time tightbeam stream invoices

# Parallel (enable in config first)
time tightbeam stream invoices

# Compare: parallel should be ~3x faster
```

---

## Contact & Support

**Original Implementation Plan:** `PRPs/graphql-streaming-optimization-plan.md`
**Audit Report:** Jenny's findings (in memory)
**Archon Project ID:** `6343aa4b-cf77-410a-aa96-b68833a2d10e`

**Key Archon Tasks:**
- Task 7: Implement AsyncParallelStreamExtractor (currently marked "done" but incomplete)
- Task 9: Update ServiceFactory (not started)
- Task 10: Update Stream Command (not started)
- Task 11: Add Integration Tests (not started)

---

## Appendix: Code Snippets

### Example: Proper Parallel Fetching Pattern

```python
async def _parallel_fetch_pages(self, http_client, initial_cursor):
    """Fetch pages in parallel using cursor queue."""

    cursor_queue = [initial_cursor]

    while cursor_queue:
        # Take batch up to max_concurrent
        batch = cursor_queue[:self._max_concurrent]
        cursor_queue = cursor_queue[self._max_concurrent:]

        # Fetch batch in parallel
        tasks = [self._fetch_and_save_page(http_client, c) for c in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and discover new cursors
        for result in results:
            if isinstance(result, Exception):
                continue

            if result:
                _, page_info, _ = self._extract_edges_and_page_info(result)
                if page_info.get("hasNextPage"):
                    cursor_queue.append(page_info.get("endCursor"))
```

### Example: Proper Semaphore Usage

```python
async def _fetch_and_save_page(self, http_client, cursor):
    """Fetch page with proper concurrency control."""

    # First acquire semaphore slot
    async with self._semaphore:
        # Then acquire rate limit token
        if not await self._rate_limiter.acquire_async(timeout=60.0):
            return None

        # Now safe to fetch (both limits respected)
        page_data = await self._fetch_page(http_client, cursor)

        # Save data
        edges, _, _ = self._extract_edges_and_page_info(page_data)
        if edges:
            await self._save_entities_async(edges)

        return page_data
```

---

**END OF REPORT**
