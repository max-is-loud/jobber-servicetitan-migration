# Implementation Plan: GraphQL Streaming Performance Optimization

## Overview

Optimize the GraphQL streaming performance in tightbeam by implementing a three-pronged approach:
1. **Defer attachment metadata fetching** to download pass (quick win)
2. **Implement parallel page fetching** with rate-aware concurrency control
3. **Fine-tune rate limiting** based on actual query costs

This plan addresses the current slow streaming performance (~5-6 seconds per page) by reducing query costs and enabling concurrent request processing, targeting a **3-5x performance improvement**.

## Problem Statement

### Current Performance Issues

The invoice streaming process is currently very slow due to:

1. **Expensive Nested Queries**: Fetching full attachment metadata during stream pass
   - `noteAttachments(first: 10)` × 7 fields × 20 invoices = ~1,400 points per query
   - This metadata is fetched again in the download pass anyway (redundant)

2. **Sequential Page Processing**: Pages fetched one at a time
   - Rate limiter allows 11 req/min (one every 5.5 seconds)
   - With 2,600 point queries, effective rate is ~5.2 seconds per page minimum
   - No parallelism = underutilized API capacity

3. **Suboptimal Rate Limiting**: Conservative settings don't match actual usage
   - Settings tuned for worst-case (45 clients with unlimited lineItems)
   - After pagination fixes, actual costs are much lower
   - Jobber's 10,000 point bucket capacity is underutilized

### Performance Metrics

**Current State:**
- Query cost: ~2,600 points per page (20 invoices)
- Request rate: 11 req/min (one every 5.5 sec)
- Parallelism: 1 (sequential)
- **Throughput: ~220 invoices/minute**

**Target State:**
- Query cost: ~1,300 points per page (50% reduction via deferred attachments)
- Request rate: 20 req/min (one every 3 sec)
- Parallelism: 3 concurrent requests
- **Throughput: ~800-1200 invoices/minute (3.6-5.5x improvement)**

## Goals

### Primary Goals
1. Reduce query cost by 50% by deferring attachment metadata to download pass
2. Implement async parallel page fetching with 3x concurrency
3. Achieve 3-5x throughput improvement for invoice streaming
4. Maintain rate limit compliance (no throttling errors)

### Secondary Goals
1. Make parallel fetching configurable (enable/disable, concurrency level)
2. Add performance metrics logging (throughput, query costs, bucket status)
3. Extend optimization to all entity types (clients, quotes, jobs, etc.)
4. Ensure backward compatibility with existing streaming behavior

## Non-Goals

- GraphQL query batching (Jobber API doesn't support batching)
- Persisted queries / APQ (not supported by Jobber, limited value for dynamic cursors)
- Client-side caching (streaming is one-time data extraction)
- Attachment content optimization or deduplication

## Solution Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│ Stream Pass Optimization Strategy                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Phase 1: Defer Attachment Metadata (Quick Win)             │
│  ┌────────────────────────────────────────────────┐         │
│  │ Change: noteAttachments(first: 10) { 7 fields }│         │
│  │ To:     noteAttachments { totalCount }         │         │
│  │                                                 │         │
│  │ Savings: 1,400 points → 20 points per query    │         │
│  │ New cost: 2,600 → 1,300 points                 │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
│  Phase 2: Parallel Page Fetching (Big Win)                  │
│  ┌────────────────────────────────────────────────┐         │
│  │ Current: Sequential (1 page at a time)         │         │
│  │          Page 1 → wait 5.5s → Page 2           │         │
│  │                                                 │         │
│  │ New: Async parallel (3 pages at a time)        │         │
│  │      Page 1 ┐                                   │         │
│  │      Page 2 ├─ concurrent → results in ~3s     │         │
│  │      Page 3 ┘                                   │         │
│  │                                                 │         │
│  │ Rate limiting: Semaphore + TokenBucket         │         │
│  │ - Semaphore(3): Max 3 concurrent requests      │         │
│  │ - TokenBucket: Rate limit compliance           │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
│  Phase 3: Rate Limit Tuning (Refinement)                    │
│  ┌────────────────────────────────────────────────┐         │
│  │ Adjust based on new query costs:               │         │
│  │ - 1,300 pts/query ÷ 500 pts/sec = 2.6 sec     │         │
│  │ - Safe rate: 20 req/min (one every 3 sec)     │         │
│  │ - With 3 concurrent: 60 effective req/min     │         │
│  └────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### Detailed Technical Design

#### Phase 1: Defer Attachment Metadata

**GraphQL Query Modification:**

```graphql
# BEFORE (stream pass):
noteAttachments(first: 10) {
  totalCount
  edges {
    node {
      id                  # 1 field
      note { id }         # 1 field (nested)
      fileName            # 1 field
      contentType         # 1 field
      url                 # 1 field
      fileSize            # 1 field
      createdAt           # 1 field
    }
  }
  pageInfo {
    hasNextPage
    endCursor
  }
}
# Cost: 10 attachments × 7 fields = 70 points per invoice
# Total: 20 invoices × 70 = 1,400 points

# AFTER (stream pass):
noteAttachments {
  totalCount              # 1 field total
}
# Cost: 1 point per invoice
# Total: 20 invoices × 1 = 20 points

# Savings: 1,380 points per query (53% reduction!)
```

**Migration Strategy:**
- Stream pass: Fetch only `totalCount` for attachments
- Download pass: Fetch full metadata when actually downloading
- No data loss: All attachment metadata still captured, just in different pass

#### Phase 2: Async Parallel Fetching

**Architecture:**

```python
┌──────────────────────────────────────────────────┐
│ AsyncParallelStreamExtractor                     │
├──────────────────────────────────────────────────┤
│                                                   │
│  Components:                                      │
│  ┌─────────────────────────────────────────┐    │
│  │ Concurrency Control                      │    │
│  │ - asyncio.Semaphore(max_concurrent=3)    │    │
│  │ - Limits parallel requests               │    │
│  └─────────────────────────────────────────┘    │
│                                                   │
│  ┌─────────────────────────────────────────┐    │
│  │ Rate Limiting Integration                │    │
│  │ - TokenBucketRateLimiter wrapper         │    │
│  │ - Async-safe token acquisition           │    │
│  │ - Respects existing rate limits          │    │
│  └─────────────────────────────────────────┘    │
│                                                   │
│  ┌─────────────────────────────────────────┐    │
│  │ Async HTTP Client                        │    │
│  │ - aiohttp for async requests             │    │
│  │ - Connection pooling                     │    │
│  │ - Automatic retry with backoff           │    │
│  └─────────────────────────────────────────┘    │
│                                                   │
│  Flow:                                            │
│  1. Generate next N cursors (N=concurrency)      │
│  2. Create N async tasks                         │
│  3. Each task:                                    │
│     a. Acquire semaphore slot                    │
│     b. Acquire rate limit token (blocks if empty)│
│     c. Execute async HTTP request                │
│     d. Process response                          │
│     e. Release semaphore                         │
│  4. asyncio.gather() waits for all tasks         │
│  5. Repeat until no more pages                   │
│                                                   │
└──────────────────────────────────────────────────┘
```

**Implementation Details:**

```python
# New class: src/extractors/async_parallel_stream_extractor.py

import asyncio
import aiohttp
from typing import List, Optional, Dict, Any

class AsyncParallelStreamExtractor:
    """Async parallel streaming extractor with rate-aware concurrency."""

    def __init__(
        self,
        max_concurrent: int = 3,
        rate_limiter: TokenBucketRateLimiter = None,
        **kwargs
    ):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limiter = rate_limiter
        self.session: Optional[aiohttp.ClientSession] = None

    async def _fetch_page_async(
        self,
        cursor: Optional[str]
    ) -> Dict[str, Any]:
        """Fetch a single page with rate limiting."""
        async with self.semaphore:
            # Wait for rate limit token (async-safe)
            await self._acquire_rate_limit_token()

            # Execute async HTTP request
            async with self.session.post(
                url=self.api_url,
                json={"query": self.query, "variables": {"cursor": cursor}},
                headers=self.headers
            ) as response:
                return await response.json()

    async def stream_parallel(self) -> ExtractionSummary:
        """Stream entities with parallel page fetching."""
        async with aiohttp.ClientSession() as self.session:
            cursors = [None]  # Start with first page

            while cursors:
                # Fetch up to max_concurrent pages in parallel
                tasks = [
                    self._fetch_page_async(cursor)
                    for cursor in cursors[:self.max_concurrent]
                ]

                # Wait for all parallel requests
                responses = await asyncio.gather(*tasks)

                # Process responses and extract next cursors
                cursors = []
                for response in responses:
                    entities = self._process_response(response)
                    self._save_entities(entities)

                    # Add next cursor if has more pages
                    page_info = self._extract_page_info(response)
                    if page_info.get("hasNextPage"):
                        cursors.append(page_info["endCursor"])

        return self._build_summary()
```

**Rate Limiter Integration:**

```python
# Modify: src/rate_limiting/token_bucket.py

class TokenBucketRateLimiter:
    """Add async support for parallel fetching."""

    async def acquire_async(self, cost: float = 1.0) -> None:
        """Async version of token acquisition - blocks until available."""
        while not self.consume(cost):
            # Calculate wait time until enough tokens available
            wait_time = cost / self.refill_rate
            await asyncio.sleep(wait_time)
```

#### Phase 3: Rate Limit Tuning

**Updated Settings (config/settings.yaml):**

```yaml
# Based on new query costs after deferring attachments:
# - 20 invoices × ~65 fields (base + lineItems(10) + notes(10) + 20 for counts) = ~1,300 points/query
# - At 500 points/sec restore: 1,300 / 500 = 2.6 seconds per query
# - Safe rate: 20 requests/minute (one every 3 seconds)
# - With 3 concurrent requests: 60 effective req/min
rate_limits:
  capacity: 30           # Higher capacity for burst requests
  refill_rate: 20        # 20 requests per minute = 0.333 req/s (one every 3 sec)
  initial_tokens: 10     # Better startup with more initial tokens

pagination:
  invoices: 20           # Keep at 20 for consistent query costs
  nested_notes: 10       # Keep at 10 for notes

# New: Parallel fetching configuration
parallel_fetching:
  enabled: true          # Enable parallel fetching
  max_concurrent: 3      # Max 3 concurrent requests
  entities:              # Per-entity concurrency overrides
    invoices: 3
    clients: 2           # Clients have larger queries, limit to 2
    quotes: 3
    jobs: 3
```

## Implementation Tasks

### Phase 1: Defer Attachment Metadata (Quick Win - 1 hour)

#### Task 1.1: Create Stream-Mode Query Variants
**Priority:** HIGH
**Estimated Effort:** 30 minutes
**Files to Modify:**
- `src/clients/jobber_client.py`

**Changes:**

```python
# Add mode parameter to query builders
def _get_invoices_query(self, mode: str = "stream") -> str:
    """Get GraphQL query for invoices.

    Args:
        mode: 'stream' for minimal attachment metadata,
              'extract' for full metadata
    """
    page_size = self._get_pagination_size("invoices")
    nested_notes_limit = self._get_pagination_size("nested_notes")

    # Conditional attachment query based on mode
    if mode == "stream":
        attachments_query = """
            noteAttachments {
              totalCount
            }
        """
    else:  # extract mode
        attachments_query = f"""
            noteAttachments(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  id
                  note {{ ... on InvoiceNote {{ id }} }}
                  fileName
                  contentType
                  url
                  fileSize
                  createdAt
                }}
              }}
              pageInfo {{
                hasNextPage
                endCursor
              }}
            }}
        """

    return f"""
    query GetInvoices($cursor: String) {{
      invoices(first: {page_size}, after: $cursor) {{
        totalCount
        edges {{
          node {{
            id
            client {{ id }}
            invoiceNumber
            amounts {{ total subtotal }}
            invoiceStatus
            issuedDate
            dueDate
            lineItems(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  description
                  quantity
                  unitPrice
                }}
              }}
              pageInfo {{ hasNextPage endCursor }}
            }}
            notes(first: {nested_notes_limit}) {{
              totalCount
              edges {{
                node {{
                  ... on InvoiceNote {{
                    id
                    message
                    createdAt
                  }}
                }}
              }}
              pageInfo {{ hasNextPage endCursor }}
            }}
            {attachments_query}
            createdAt
            updatedAt
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
    """
```

**Acceptance Criteria:**
- ✅ Stream mode returns only `totalCount` for attachments
- ✅ Extract mode returns full attachment metadata (backward compatible)
- ✅ Query cost reduced by ~1,300 points in stream mode

---

#### Task 1.2: Update Stream Extractor to Use Stream Mode
**Priority:** HIGH
**Estimated Effort:** 15 minutes
**Files to Modify:**
- `src/extractors/stream_extractor.py`

**Changes:**

```python
# Modify fetch method to pass mode parameter
def _fetch_page(self, cursor: Optional[str] = None) -> dict[str, Any]:
    """Fetch a page using stream-optimized query."""
    # Pass mode='stream' to get minimal attachment metadata
    return self._jobber_client.fetch_invoices(cursor, mode="stream")
```

**Acceptance Criteria:**
- ✅ Stream extractor uses stream-mode queries
- ✅ Existing extract behavior unchanged
- ✅ Tests pass for both modes

---

#### Task 1.3: Update Rate Limit Settings
**Priority:** HIGH
**Estimated Effort:** 15 minutes
**Files to Modify:**
- `config/settings.yaml`

**Changes:**

```yaml
# Update rate limits based on new 1,300 point query cost
rate_limits:
  capacity: 30
  refill_rate: 20
  initial_tokens: 10
```

**Acceptance Criteria:**
- ✅ Settings reflect new query costs
- ✅ No throttling errors during streaming
- ✅ Performance improvement measurable (2x faster)

---

### Phase 2: Async Parallel Fetching (Medium Effort - 4-6 hours)

#### Task 2.1: Create Async HTTP Client Wrapper
**Priority:** MEDIUM
**Estimated Effort:** 2 hours
**Files to Create:**
- `src/clients/async_http_client.py`

**Implementation:**

```python
"""Async HTTP client for parallel GraphQL requests."""

import asyncio
import aiohttp
from typing import Dict, Any, Optional
from ..exceptions import JobberApiError
from ..interfaces import Logger

class AsyncHttpClient:
    """Async HTTP client with connection pooling and retry logic."""

    def __init__(
        self,
        logger: Logger,
        timeout: int = 60,
        max_connections: int = 10
    ):
        self.logger = logger
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.connector = aiohttp.TCPConnector(limit=max_connections)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Create session on context entry."""
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            connector=self.connector
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close session on context exit."""
        if self.session:
            await self.session.close()

    async def post(
        self,
        url: str,
        json: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Execute async POST request with error handling."""
        try:
            async with self.session.post(
                url=url,
                json=json,
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            raise JobberApiError(f"HTTP request failed: {e}") from e
```

**Acceptance Criteria:**
- ✅ Async HTTP client with connection pooling
- ✅ Proper error handling and logging
- ✅ Context manager for session lifecycle
- ✅ Unit tests for success and error cases

---

#### Task 2.2: Create Async Token Bucket Implementation
**Priority:** MEDIUM
**Estimated Effort:** 1 hour
**Files to Modify:**
- `src/rate_limiting/token_bucket.py`

**Changes:**

```python
# Add async methods to existing TokenBucketRateLimiter

async def acquire_async(self, cost: float = 1.0, timeout: Optional[float] = None) -> bool:
    """Async token acquisition - blocks until available or timeout.

    Args:
        cost: Number of tokens to acquire
        timeout: Max wait time in seconds (None = wait forever)

    Returns:
        True if acquired, False if timeout
    """
    start_time = time.time()

    while True:
        # Try to consume tokens
        if self.consume(cost):
            return True

        # Check timeout
        if timeout is not None:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return False

        # Calculate wait time until enough tokens available
        tokens_needed = cost - self.get_available_tokens()
        wait_time = tokens_needed / self.refill_rate

        # Don't wait longer than remaining timeout
        if timeout is not None:
            remaining = timeout - elapsed
            wait_time = min(wait_time, remaining)

        # Async sleep (non-blocking)
        await asyncio.sleep(wait_time)
```

**Acceptance Criteria:**
- ✅ Async token acquisition with timeout support
- ✅ Non-blocking waits using asyncio.sleep
- ✅ Thread-safe for concurrent async tasks
- ✅ Unit tests for various scenarios

---

#### Task 2.3: Implement AsyncParallelStreamExtractor
**Priority:** MEDIUM
**Estimated Effort:** 2 hours
**Files to Create:**
- `src/extractors/async_parallel_stream_extractor.py`

**Implementation:**

```python
"""Async parallel stream extractor with rate-aware concurrency."""

import asyncio
from typing import List, Optional, Dict, Any
from .stream_extractor import StreamExtractor
from ..clients.async_http_client import AsyncHttpClient
from ..rate_limiting.token_bucket import TokenBucketRateLimiter

class AsyncParallelStreamExtractor(StreamExtractor):
    """Stream extractor with parallel page fetching."""

    def __init__(
        self,
        max_concurrent: int = 3,
        enable_parallel: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.max_concurrent = max_concurrent
        self.enable_parallel = enable_parallel
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch_page_async(
        self,
        cursor: Optional[str]
    ) -> Dict[str, Any]:
        """Fetch page with concurrency control and rate limiting."""
        async with self.semaphore:
            # Acquire rate limit token (async)
            query_cost = self._estimate_query_cost()
            await self._rate_limiter.acquire_async(query_cost)

            # Execute async HTTP request
            response = await self._async_http_client.post(
                url=self._jobber_client.API_URL,
                json={
                    "query": self._get_query(),
                    "variables": {"cursor": cursor}
                },
                headers=self._jobber_client._get_headers()
            )

            return response

    async def _stream_parallel_async(self) -> ExtractionSummary:
        """Stream with parallel page fetching."""
        async with AsyncHttpClient(self._logger) as http_client:
            self._async_http_client = http_client

            cursors = [None]  # Start with first page
            total_entities = 0

            while cursors:
                # Fetch up to max_concurrent pages in parallel
                batch = cursors[:self.max_concurrent]
                tasks = [self._fetch_page_async(c) for c in batch]

                # Wait for all requests in batch
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                # Process responses
                next_cursors = []
                for response in responses:
                    if isinstance(response, Exception):
                        self._logger.error(f"Page fetch failed: {response}")
                        continue

                    # Extract and save entities
                    edges, page_info = self._extract_edges_and_page_info(response)
                    entities = [self._map_entity(e["node"]) for e in edges]
                    self._save_entities(entities)
                    total_entities += len(entities)

                    # Add next cursor if has more
                    if page_info.get("hasNextPage"):
                        next_cursors.append(page_info["endCursor"])

                # Update cursors for next batch
                cursors = next_cursors

        return self._build_summary(total_entities)

    def stream(self) -> ExtractionSummary:
        """Entry point - delegates to sync or async based on config."""
        if self.enable_parallel:
            # Run async version
            return asyncio.run(self._stream_parallel_async())
        else:
            # Fall back to sequential (backward compatible)
            return super().stream()
```

**Acceptance Criteria:**
- ✅ Parallel page fetching with configurable concurrency
- ✅ Rate limit integration (async token acquisition)
- ✅ Error handling for failed requests
- ✅ Backward compatible (can disable parallel mode)
- ✅ Maintains data integrity (no duplicate/missing entities)

---

#### Task 2.4: Add Configuration for Parallel Fetching
**Priority:** MEDIUM
**Estimated Effort:** 30 minutes
**Files to Modify:**
- `config/settings.yaml`
- `src/config/config_manager.py`

**Changes:**

```yaml
# settings.yaml - add parallel fetching config
parallel_fetching:
  enabled: true
  max_concurrent: 3
  entities:
    invoices: 3
    clients: 2
    quotes: 3
    jobs: 3
    default: 3
```

```python
# config_manager.py - add getters
def is_parallel_fetching_enabled(self) -> bool:
    """Check if parallel fetching is enabled."""
    return self.config.get("parallel_fetching", {}).get("enabled", False)

def get_max_concurrent(self, entity_type: str = "default") -> int:
    """Get max concurrent requests for entity type."""
    parallel_config = self.config.get("parallel_fetching", {})
    entities = parallel_config.get("entities", {})
    return entities.get(entity_type, entities.get("default", 1))
```

**Acceptance Criteria:**
- ✅ Configuration accessible via ConfigManager
- ✅ Per-entity concurrency overrides work
- ✅ Defaults to disabled for safety

---

### Phase 3: Integration & Testing (2-3 hours)

#### Task 3.1: Update Stream Command to Use Parallel Extractor
**Priority:** MEDIUM
**Estimated Effort:** 1 hour
**Files to Modify:**
- `src/cli/migrate.py`
- `src/cli/services/factories.py`

**Changes:**

```python
# factories.py - create async parallel extractor
@staticmethod
def create_async_parallel_stream_extractor(
    entity_type: str,
    config_manager: ConfigManagerImpl,
    **kwargs
) -> AsyncParallelStreamExtractor:
    """Create async parallel stream extractor with config."""
    max_concurrent = config_manager.get_max_concurrent(entity_type)
    enable_parallel = config_manager.is_parallel_fetching_enabled()

    # ... create extractor with parallel config
    return AsyncParallelStreamExtractor(
        max_concurrent=max_concurrent,
        enable_parallel=enable_parallel,
        **kwargs
    )

# migrate.py - use parallel extractor for stream command
if config_manager.is_parallel_fetching_enabled():
    extractor = ServiceFactory.create_async_parallel_stream_extractor(
        entity_type=entity,
        config_manager=config_manager,
        # ... other args
    )
else:
    # Fall back to regular stream extractor
    extractor = ServiceFactory.create_stream_extractor(...)
```

**Acceptance Criteria:**
- ✅ Stream command uses parallel extractor when enabled
- ✅ Falls back to sequential when disabled
- ✅ Configuration properly passed through

---

#### Task 3.2: Add Performance Metrics Logging
**Priority:** LOW
**Estimated Effort:** 1 hour
**Files to Modify:**
- `src/extractors/async_parallel_stream_extractor.py`
- `src/interfaces/logger.py`

**Changes:**

```python
# Add performance tracking
class AsyncParallelStreamExtractor:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.metrics = {
            "total_requests": 0,
            "parallel_batches": 0,
            "avg_batch_time": 0.0,
            "query_costs": [],
            "throttle_events": 0
        }

    async def _stream_parallel_async(self):
        # ... existing code ...

        # Track metrics
        batch_start = time.time()
        responses = await asyncio.gather(*tasks)
        batch_time = time.time() - batch_start

        self.metrics["parallel_batches"] += 1
        self.metrics["total_requests"] += len(tasks)
        self.metrics["avg_batch_time"] = (
            (self.metrics["avg_batch_time"] * (self.metrics["parallel_batches"] - 1) + batch_time)
            / self.metrics["parallel_batches"]
        )

        # Log metrics periodically
        if self.metrics["parallel_batches"] % 10 == 0:
            self._log_performance_metrics()

    def _log_performance_metrics(self):
        """Log performance statistics."""
        self._logger.info(
            f"Performance: {self.metrics['total_requests']} requests "
            f"in {self.metrics['parallel_batches']} batches, "
            f"avg {self.metrics['avg_batch_time']:.2f}s per batch, "
            f"throughput: {self.metrics['total_requests'] / (self.metrics['parallel_batches'] * self.metrics['avg_batch_time']):.1f} req/s"
        )
```

**Acceptance Criteria:**
- ✅ Performance metrics tracked during streaming
- ✅ Periodic logging of throughput stats
- ✅ Metrics included in final summary

---

#### Task 3.3: Add Tests for Parallel Extractor
**Priority:** HIGH
**Estimated Effort:** 1 hour
**Files to Create:**
- `tests/integration/test_async_parallel_streaming.py`
- `tests/unit/extractors/test_async_parallel_stream_extractor.py`

**Test Coverage:**

```python
# Integration tests
class TestAsyncParallelStreaming:
    async def test_parallel_fetching_respects_rate_limits(self):
        """Verify parallel requests don't exceed rate limits."""
        # Mock rate limiter, track token consumption
        # Assert no over-consumption

    async def test_parallel_fetching_handles_errors(self):
        """One failed request doesn't block others."""
        # Mock HTTP client to fail some requests
        # Assert other requests succeed

    async def test_parallel_vs_sequential_throughput(self):
        """Parallel is faster than sequential."""
        # Run both modes, compare times
        # Assert parallel is 2-3x faster

    async def test_data_integrity_with_parallel(self):
        """No duplicate or missing entities."""
        # Fetch with parallel and sequential
        # Assert same entities returned

# Unit tests
class TestAsyncParallelStreamExtractor:
    async def test_semaphore_limits_concurrency(self):
        """Max concurrent requests respected."""
        # Track concurrent requests
        # Assert never exceeds max_concurrent

    async def test_rate_limit_integration(self):
        """Rate limiter acquire called before requests."""
        # Mock rate limiter
        # Assert acquire_async called for each request

    async def test_fallback_to_sequential(self):
        """Disabled parallel falls back gracefully."""
        # Create with enable_parallel=False
        # Assert uses sequential method
```

**Acceptance Criteria:**
- ✅ All tests pass
- ✅ Code coverage >80% for new code
- ✅ Integration test validates end-to-end flow

---

## Performance Validation

### Success Metrics

After implementing all three phases, we should achieve:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Query Cost (invoices) | 2,600 pts | 1,300 pts | 50% reduction |
| Requests/Minute | 11 | 20 | 1.8x |
| Concurrent Requests | 1 | 3 | 3x |
| **Throughput (invoices/min)** | **220** | **800-1200** | **3.6-5.5x** |
| Time to stream 10k invoices | ~45 min | ~8-12 min | 4-6x faster |

### Test Plan

1. **Baseline Measurement**: Run current stream command, measure time
2. **Phase 1 Validation**: Apply attachment deferral, measure ~2x improvement
3. **Phase 2 Validation**: Enable parallel fetching, measure additional 2-3x improvement
4. **Stress Test**: Stream large dataset (10k+ invoices), verify no throttling
5. **Rate Limit Compliance**: Monitor `throttleStatus` in responses, ensure `currentlyAvailable` stays positive

## Rollout Strategy

### Phase 1 (Week 1)
- Implement attachment deferral (Tasks 1.1-1.3)
- Deploy with `parallel_fetching.enabled: false`
- Validate 2x performance improvement
- Monitor for regressions

### Phase 2 (Week 2)
- Implement async infrastructure (Tasks 2.1-2.2)
- Implement parallel extractor (Tasks 2.3-2.4)
- Deploy with `parallel_fetching.enabled: false` (feature flag off)
- Internal testing with flag on

### Phase 3 (Week 3)
- Integration and testing (Tasks 3.1-3.3)
- Gradual rollout: enable for 1 entity type first
- Monitor performance and stability
- Enable for all entity types if successful

### Rollback Plan
- Phase 1: Revert query changes, restore full attachment metadata
- Phase 2/3: Set `parallel_fetching.enabled: false` in config
- No data loss risk: all changes are backward compatible

## Dependencies

### External
- `aiohttp` library for async HTTP (add to pyproject.toml)
- Python 3.11+ for better asyncio performance (already required)

### Internal
- Existing `TokenBucketRateLimiter` must support async (Task 2.2)
- Config manager must load parallel fetching settings (Task 2.4)
- Stream extractor must be refactorable for async (Task 2.3)

## Risks and Mitigations

### Risk 1: Async Complexity
**Impact:** HIGH
**Likelihood:** MEDIUM
**Mitigation:**
- Make parallel fetching opt-in via config
- Maintain sequential fallback
- Extensive testing before rollout

### Risk 2: Rate Limit Violations
**Impact:** HIGH
**Likelihood:** LOW
**Mitigation:**
- Semaphore strictly enforces max concurrent
- Rate limiter blocks when bucket empty
- Monitor `throttleStatus` in responses
- Conservative initial settings (3 concurrent)

### Risk 3: Data Integrity Issues
**Impact:** CRITICAL
**Likelihood:** LOW
**Mitigation:**
- Comprehensive integration tests
- Verify entity counts match sequential mode
- Parallel-safe entity saving (existing repo methods)

### Risk 4: Increased Memory Usage
**Impact:** MEDIUM
**Likelihood:** MEDIUM
**Mitigation:**
- Connection pooling limits (max 10 connections)
- Batched processing (fetch N, process, repeat)
- Monitor memory during testing

## Open Questions

1. **Should we make attachment deferral configurable?**
   - Proposal: Always defer in stream mode, fetch full in extract mode
   - Reasoning: Clear separation of concerns, no configurability needed

2. **What's the optimal concurrency level?**
   - Start with 3 concurrent requests
   - Make configurable per entity type
   - Tune based on production metrics

3. **Should we extend to map mode too?**
   - No for initial implementation (map queries are cheap)
   - Consider if map becomes bottleneck later

4. **How to handle partial failures in parallel batches?**
   - Log error, continue with successful requests
   - Track failed cursors for potential retry
   - Include failure count in summary

## Related Documents

- [PRD: Binary Download Pass](/PRD_BINARY_DOWNLOAD_PASS.md) - Attachment download architecture
- [PRD: Single Pass Migration](/PRD_SINGLE_PASS_MIGRATION.md) - Overall migration architecture
- [API Rate Limits Documentation](https://developer.getjobber.com/docs/using_jobbers_api/api_rate_limits/) - Jobber's rate limit details
- [GraphQL Performance Best Practices](https://graphql.org/learn/performance/) - Official GraphQL optimization guide

## Appendix: Research References

### GraphQL Optimization Techniques
- [Performance | GraphQL](https://graphql.org/learn/performance/) - Official performance guide
- [Optimizing API performance with GraphQL](https://www.statsig.com/perspectives/optimizing-api-performance-with-graphql) - Batching and caching strategies
- [GraphQL Performance Optimization Techniques](https://talent500.com/blog/graphql-make-it-run-like-a-rocket-performance-optimization-techniques/) - Comprehensive optimization overview

### Parallel Request Processing
- [Batching Client GraphQL Queries | Apollo](https://www.apollographql.com/blog/batching-client-graphql-queries) - Query batching patterns
- [Optimizing Your GraphQL Request Waterfalls | Apollo](https://www.apollographql.com/blog/backend/performance/optimizing-your-graphql-request-waterfalls/) - Parallel request strategies
- [Query Batching - Apollo GraphQL Docs](https://www.apollographql.com/docs/graphos/routing/performance/query-batching) - Batching implementation

### Persisted Queries (Evaluated but Not Applicable)
- [Automatic Persisted Queries - Apollo Docs](https://www.apollographql.com/docs/apollo-server/performance/apq) - APQ overview
- Not applicable: Jobber API doesn't support APQ, queries are dynamic (cursor-based)
