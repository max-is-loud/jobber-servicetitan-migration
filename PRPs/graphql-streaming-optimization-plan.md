# Implementation Plan: GraphQL Streaming Performance Optimization

## Overview

This plan implements async parallel streaming for tightbeam to achieve **3-5x performance improvement** through three phases:
1. **Phase 1** (Quick Win - 1 hour): Defer attachment metadata to download pass
2. **Phase 2** (Medium - 4-6 hours): Implement async parallel page fetching
3. **Phase 3** (Testing - 2-3 hours): Integration, testing, and validation

**Expected Outcome**: Throughput improvement from 220 invoices/min → 800-1200 invoices/min

---

## Requirements Summary

From PRP `/home/max/projects/tightbeam-v2/PRPs/graphql-streaming-optimization.md`:

### Primary Goals
- ✅ Reduce query cost by 50% (2,600 → 1,300 points) via deferred attachments
- ✅ Implement async parallel fetching with 3x concurrency
- ✅ Achieve 3-5x throughput improvement
- ✅ Maintain rate limit compliance (no throttling)

### Secondary Goals
- ✅ Configurable parallel fetching (enable/disable, concurrency level)
- ✅ Performance metrics logging
- ✅ Extend to all entity types
- ✅ Backward compatibility

### Non-Goals
- ❌ GraphQL query batching (API doesn't support)
- ❌ Persisted queries/APQ (not applicable)
- ❌ Client-side caching (one-time extraction)

---

## Research Findings

### Codebase Analysis

From `codebase-analyst` agent investigation:

**Key Findings**:
1. **Zero async code exists** - Greenfield async implementation
2. **Pure synchronous architecture** - Uses `requests`, not `aiohttp`
3. **Thread-safe rate limiter** - Can reuse `TokenBucketRateLimiter`
4. **Dependency injection pattern** - Must maintain for consistency
5. **Template method pattern** - BaseExtractor orchestrates extraction flow
6. **Configuration-driven** - All limits from `ConfigManagerImpl`
7. **SQLite with WAL mode** - Supports concurrent reads, serialized writes
8. **Rich UI for progress** - Thread-safe, works with async

**Critical Patterns to Follow**:
- Dependency injection via constructor
- Template method with abstract hooks
- Configuration from `ConfigManager`
- Error isolation (continue on individual failures)
- Progress callbacks for UI updates
- Comprehensive metrics tracking
- Cursor persistence for resume capability

**Files to Reference**:
- `/home/max/projects/tightbeam-v2/src/extractors/base_extractor.py` - Template pattern
- `/home/max/projects/tightbeam-v2/src/extractors/stream_extractor.py` - Sequential streaming
- `/home/max/projects/tightbeam-v2/src/clients/jobber_client.py` - Query building
- `/home/max/projects/tightbeam-v2/src/rate_limiting/token_bucket.py` - Rate limiting
- `/home/max/projects/tightbeam-v2/src/cli/services/factories.py` - DI setup

### Technology Decisions

**1. HTTP Library: `aiohttp` (chosen)**
- **Rationale**: Mature, widely adopted, excellent connection pooling
- **Alternative**: `httpx` (less mature for async)
- **Dependencies**: Add `aiohttp>=3.9.0` to `pyproject.toml`

**2. Database: Write Queue Pattern** (chosen)
- **Rationale**: Avoids `aiosqlite` complexity, reuses existing Repository
- **Implementation**: `asyncio.Queue` for serializing writes
- **Alternative**: `aiosqlite` (requires refactoring all queries)

**3. Rate Limiting: Shared Semaphore + Token Bucket**
- **Rationale**: API-level rate limiting (not per-entity-type)
- **Implementation**: One semaphore controls concurrent requests
- **Reuse**: Existing `TokenBucketRateLimiter` with async adapter

**4. Progress Tracking: Thread-Safe Updates**
- **Rationale**: Rich Progress already thread-safe
- **Implementation**: Update from async tasks using sync calls
- **Alternative**: `asyncio.Queue` (unnecessary complexity)

**5. Testing: `pytest-asyncio`**
- **Rationale**: Standard for async testing
- **Dependencies**: Add `pytest-asyncio>=0.23.0` to dev dependencies

---

## Implementation Tasks

### Phase 1: Defer Attachment Metadata (Quick Win - 1 hour)

#### Task 1.1: Add Query Mode Parameter to JobberClient
**Priority**: HIGH
**Effort**: 30 minutes
**Files to Modify**:
- `src/clients/jobber_client.py`

**Implementation**:

```python
# Add mode parameter to existing query methods
def _get_invoices_query(self, mode: str = "stream") -> str:
    """
    Get GraphQL query for invoices.

    Args:
        mode: 'stream' (minimal attachments) or 'extract' (full metadata)

    Returns:
        Formatted GraphQL query string
    """
    page_size = self._get_pagination_size("invoices")
    nested_notes_limit = self._get_pagination_size("nested_notes")

    # Conditional attachment fields based on mode
    if mode == "stream":
        # Stream mode: Only totalCount (1 point per invoice)
        attachments_fields = "totalCount"
    else:
        # Extract mode: Full metadata (70 points per invoice)
        attachments_fields = f"""
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
              edges {{ node {{ description quantity unitPrice }} }}
              pageInfo {{ hasNextPage endCursor }}
            }}
            notes(first: {nested_notes_limit}) {{
              totalCount
              edges {{ node {{ ... on InvoiceNote {{ id message createdAt }} }} }}
              pageInfo {{ hasNextPage endCursor }}
            }}
            noteAttachments(first: {nested_notes_limit}) {{
              {attachments_fields}
            }}
            createdAt
            updatedAt
          }}
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """

# Update fetch_invoices method signature
def fetch_invoices(
    self,
    cursor: Optional[str] = None,
    mode: str = "stream"
) -> dict[str, Any]:
    """
    Fetch invoices from Jobber API.

    Args:
        cursor: Pagination cursor
        mode: Query mode ('stream' or 'extract')

    Returns:
        GraphQL response dictionary
    """
    query = self._get_invoices_query(mode)
    # ... existing implementation
```

**Apply Same Pattern To**:
- `_get_clients_query()` and `fetch_clients()`
- `_get_quotes_query()` and `fetch_quotes()`
- `_get_jobs_query()` and `fetch_jobs()`
- `_get_requests_query()` and `fetch_requests()`

**Acceptance Criteria**:
- ✅ `mode="stream"` returns only `noteAttachments { totalCount }`
- ✅ `mode="extract"` returns full attachment metadata (backward compatible)
- ✅ Query cost reduced by ~1,300 points in stream mode
- ✅ Existing tests pass with `mode="extract"` as default

**Testing**:
```bash
# Verify query building
uv run pytest tests/unit/clients/test_jobber_client.py -k query

# Check integration
uv run pytest tests/integration/test_extractor_integration.py
```

---

#### Task 1.2: Update StreamExtractor to Use Stream Mode
**Priority**: HIGH
**Effort**: 15 minutes
**Files to Modify**:
- `src/extractors/stream_extractor.py`

**Implementation**:

```python
# In StreamExtractor class

def stream(self, resume: bool = False) -> Dict[str, Any]:
    """Stream entities with minimal attachment metadata."""

    # ... existing cursor resume logic ...

    while True:
        try:
            # Pass mode='stream' to minimize query cost
            response = self._fetch_method(cursor, mode="stream")

            # ... rest of existing logic unchanged ...
```

**Existing Code Reference** (`stream_extractor.py:91-195`):
- Cursor-based pagination loop
- Response parsing and entity extraction
- Progress callbacks
- Error handling with retry
- Cursor persistence

**Acceptance Criteria**:
- ✅ StreamExtractor uses `mode="stream"` for all fetches
- ✅ Existing extract behavior unchanged (uses default `mode="extract"`)
- ✅ Tests pass for both stream and extract modes

**Testing**:
```bash
# Test stream mode
uv run pytest tests/unit/extractors/test_stream_extractor.py

# Verify no regressions
uv run pytest tests/integration/test_multi_pass_flow_integration.py
```

---

#### Task 1.3: Update Rate Limit Configuration
**Priority**: HIGH
**Effort**: 15 minutes
**Files to Modify**:
- `config/settings.yaml`

**Changes**:

```yaml
# Update based on new 1,300 point query cost
# Previous: 2,600 points @ 11 req/min (one every 5.5 sec)
# New: 1,300 points @ 20 req/min (one every 3 sec)

rate_limits:
  capacity: 30           # Increased from 20 for better burst
  refill_rate: 20        # Increased from 10 (20 req/min = 1 every 3 sec)
  initial_tokens: 10     # Increased from 5 for faster startup
```

**Rationale**:
- Query cost: 1,300 points
- Restore rate: 500 points/sec
- Time to restore per query: 1,300 ÷ 500 = 2.6 seconds
- Safe rate: 20 req/min (one every 3 seconds)
- 10% safety margin built in

**Acceptance Criteria**:
- ✅ No throttling errors during streaming
- ✅ `throttleStatus.currentlyAvailable` stays positive
- ✅ Performance improvement measurable (~2x faster)

**Validation**:
```bash
# Stream invoices and monitor rate limits
uv run tightbeam migrate --verbose stream --entity invoices

# Check for throttling messages in output
# Should see steady progress without retries
```

---

### Phase 2: Async Parallel Fetching (Medium - 4-6 hours)

#### Task 2.1: Add Dependencies to pyproject.toml
**Priority**: CRITICAL (Prerequisite)
**Effort**: 5 minutes
**Files to Modify**:
- `pyproject.toml`

**Changes**:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "aiohttp>=3.9.0",      # Async HTTP client
]

[project.optional-dependencies]
dev = [
    # ... existing dev dependencies ...
    "pytest-asyncio>=0.23.0",  # Async test support
]
```

**Install**:
```bash
uv sync
```

**Acceptance Criteria**:
- ✅ `aiohttp` installed and importable
- ✅ `pytest-asyncio` available for tests

---

#### Task 2.2: Create Async HTTP Client Wrapper
**Priority**: HIGH
**Effort**: 2 hours
**Files to Create**:
- `src/clients/async_http_client.py`

**Implementation**:

```python
"""Async HTTP client for parallel GraphQL requests."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aiohttp

from ..exceptions import JobberApiError
from ..interfaces import Logger


class AsyncHttpClient:
    """
    Async HTTP client with connection pooling and error handling.

    Manages aiohttp ClientSession lifecycle and provides async POST
    method for GraphQL requests with proper resource cleanup.
    """

    def __init__(
        self,
        logger: Logger,
        timeout: int = 60,
        max_connections: int = 10,
    ) -> None:
        """
        Initialize async HTTP client.

        Args:
            logger: Logger for error reporting
            timeout: Request timeout in seconds
            max_connections: Max concurrent connections in pool
        """
        self.logger = logger
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.connector = aiohttp.TCPConnector(limit=max_connections)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> AsyncHttpClient:
        """Create session on async context entry."""
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            connector=self.connector,
        )
        self.logger.debug("AsyncHttpClient session created")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close session on async context exit."""
        if self.session:
            await self.session.close()
            self.logger.debug("AsyncHttpClient session closed")

    async def post(
        self,
        url: str,
        json: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Execute async POST request with error handling.

        Args:
            url: GraphQL API endpoint
            json: Request payload (query + variables)
            headers: HTTP headers

        Returns:
            Response JSON dictionary

        Raises:
            JobberApiError: If request fails
        """
        if not self.session:
            raise JobberApiError("AsyncHttpClient not initialized (use async context)")

        try:
            async with self.session.post(
                url=url,
                json=json,
                headers=headers,
            ) as response:
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientResponseError as e:
            self.logger.error(f"HTTP {e.status}: {e.message}")
            raise JobberApiError(f"HTTP request failed: {e}") from e

        except aiohttp.ClientError as e:
            self.logger.error(f"Client error: {e}")
            raise JobberApiError(f"HTTP request failed: {e}") from e

        except asyncio.TimeoutError as e:
            self.logger.error(f"Request timeout after {self.timeout.total}s")
            raise JobberApiError("Request timeout") from e
```

**Acceptance Criteria**:
- ✅ Async context manager properly manages session lifecycle
- ✅ Connection pooling limits concurrent connections
- ✅ Comprehensive error handling with specific exceptions
- ✅ Logging for debugging
- ✅ Type hints for maintainability

**Testing** (create `tests/unit/clients/test_async_http_client.py`):

```python
"""Tests for AsyncHttpClient."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.clients.async_http_client import AsyncHttpClient
from src.exceptions import JobberApiError


@pytest.mark.asyncio
async def test_context_manager_creates_session():
    """Session created on async context entry."""
    logger = Mock()

    async with AsyncHttpClient(logger) as client:
        assert client.session is not None


@pytest.mark.asyncio
async def test_context_manager_closes_session():
    """Session closed on async context exit."""
    logger = Mock()

    async with AsyncHttpClient(logger) as client:
        session = client.session

    assert session.closed


@pytest.mark.asyncio
async def test_post_success():
    """POST request returns JSON response."""
    logger = Mock()
    mock_response = {"data": {"test": "value"}}

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=mock_response
        )
        mock_post.return_value.__aenter__.return_value.raise_for_status = Mock()

        async with AsyncHttpClient(logger) as client:
            result = await client.post(
                url="https://api.example.com",
                json={"query": "test"},
                headers={"Authorization": "Bearer token"},
            )

        assert result == mock_response


@pytest.mark.asyncio
async def test_post_raises_on_http_error():
    """POST raises JobberApiError on HTTP errors."""
    logger = Mock()

    with patch("aiohttp.ClientSession.post") as mock_post:
        from aiohttp import ClientResponseError
        mock_post.return_value.__aenter__.return_value.raise_for_status = Mock(
            side_effect=ClientResponseError(None, None, status=429)
        )

        async with AsyncHttpClient(logger) as client:
            with pytest.raises(JobberApiError, match="HTTP request failed"):
                await client.post(
                    url="https://api.example.com",
                    json={"query": "test"},
                    headers={},
                )
```

---

#### Task 2.3: Add Async Support to TokenBucketRateLimiter
**Priority**: HIGH
**Effort**: 1 hour
**Files to Modify**:
- `src/rate_limiting/token_bucket.py`

**Implementation**:

```python
# Add at top of file
import asyncio

# Add async method to existing TokenBucketRateLimiter class

async def acquire_async(
    self,
    cost: float = 1.0,
    timeout: Optional[float] = None,
) -> bool:
    """
    Async token acquisition - blocks until tokens available or timeout.

    Args:
        cost: Number of tokens to acquire
        timeout: Max wait time in seconds (None = wait forever)

    Returns:
        True if tokens acquired, False if timeout

    Raises:
        asyncio.TimeoutError: If timeout reached
    """
    import time
    start_time = time.time()

    while True:
        # Try to consume tokens (thread-safe)
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

        # Async sleep (non-blocking, yields to event loop)
        await asyncio.sleep(wait_time)
```

**Existing Code**: `token_bucket.py` is thread-safe (uses `threading.Lock`)
- Can safely call `consume()` from async tasks
- Existing synchronous methods still work

**Acceptance Criteria**:
- ✅ Async method properly awaits token availability
- ✅ Non-blocking (uses `asyncio.sleep` not `time.sleep`)
- ✅ Thread-safe (reuses existing lock)
- ✅ Timeout support
- ✅ Backward compatible (existing sync methods unchanged)

**Testing** (add to `tests/unit/rate_limiting/test_token_bucket.py`):

```python
@pytest.mark.asyncio
async def test_acquire_async_returns_true_when_tokens_available():
    """acquire_async succeeds when tokens available."""
    limiter = TokenBucketRateLimiter(capacity=10, refill_rate=100, initial_tokens=10)

    result = await limiter.acquire_async(cost=5.0)

    assert result is True
    assert limiter.get_available_tokens() == 5.0


@pytest.mark.asyncio
async def test_acquire_async_waits_for_tokens():
    """acquire_async waits for token refill."""
    limiter = TokenBucketRateLimiter(capacity=10, refill_rate=10, initial_tokens=1)

    # First acquire consumes token
    await limiter.acquire_async(cost=1.0)

    # Second acquire waits for refill
    import time
    start = time.time()
    result = await limiter.acquire_async(cost=1.0)
    elapsed = time.time() - start

    assert result is True
    assert elapsed >= 0.1  # Waited for refill (1 token / 10 rate = 0.1s)


@pytest.mark.asyncio
async def test_acquire_async_respects_timeout():
    """acquire_async returns False on timeout."""
    limiter = TokenBucketRateLimiter(capacity=10, refill_rate=1, initial_tokens=0)

    # Try to acquire with short timeout (should fail)
    result = await limiter.acquire_async(cost=10.0, timeout=0.1)

    assert result is False
```

---

#### Task 2.4: Implement AsyncParallelStreamExtractor
**Priority**: HIGH
**Effort**: 2-3 hours
**Files to Create**:
- `src/extractors/async_parallel_stream_extractor.py`

**Implementation**:

```python
"""Async parallel stream extractor with rate-aware concurrency."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from ..clients.async_http_client import AsyncHttpClient
from ..clients.jobber_client import JobberClient
from ..config import ConfigManagerImpl
from ..exceptions import JobberApiError
from ..interfaces import Logger
from ..rate_limiting.token_bucket import TokenBucketRateLimiter
from ..repositories import Repository


class AsyncParallelStreamExtractor:
    """
    Stream extractor with parallel page fetching.

    Fetches multiple pages concurrently while respecting:
    - API rate limits (via TokenBucketRateLimiter)
    - Concurrency limits (via asyncio.Semaphore)
    - Configuration settings (page size, delays)

    Features:
    - Async parallel HTTP requests
    - Rate-aware token acquisition
    - Error isolation (failed pages don't block others)
    - Progress callbacks
    - Comprehensive metrics
    """

    # Entity type mapping (reuse from StreamExtractor)
    _FETCH_METHOD_MAP = {
        "clients": "fetch_clients",
        "invoices": "fetch_invoices",
        "quotes": "fetch_quotes",
        "jobs": "fetch_jobs",
        "properties": "fetch_properties",
        "requests": "fetch_requests",
        "users": "fetch_users",
        "expenses": "fetch_expenses",
        "visits": "fetch_visits",
        "timesheetEntries": "fetch_timesheet_entries",
        "productsAndServices": "fetch_products_and_services",
        "taxRates": "fetch_tax_rates",
    }

    _RESPONSE_PATH_MAP = {
        "clients": ["data", "clients"],
        "invoices": ["data", "invoices"],
        "quotes": ["data", "quotes"],
        "jobs": ["data", "jobs"],
        "properties": ["data", "properties"],
        "requests": ["data", "requests"],
        "users": ["data", "users"],
        "expenses": ["data", "expenses"],
        "visits": ["data", "visits"],
        "timesheetEntries": ["data", "timesheetEntries"],
        "productsAndServices": ["data", "productsAndServices"],
        "taxRates": ["data", "taxRates"],
    }

    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        entity_type: str,
        rate_limiter: TokenBucketRateLimiter,
        config_manager: ConfigManagerImpl,
        max_concurrent: int = 3,
        enable_parallel: bool = True,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """
        Initialize async parallel stream extractor.

        Args:
            jobber_client: Client for GraphQL queries (provides query strings)
            repository: Repository for database writes
            logger: Logger for progress/errors
            entity_type: Entity type to stream
            rate_limiter: Shared rate limiter for token acquisition
            config_manager: Configuration manager
            max_concurrent: Max parallel requests
            enable_parallel: Enable/disable parallel mode
            progress_callback: Optional callback for progress updates
        """
        if entity_type not in self._FETCH_METHOD_MAP:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        self._jobber_client = jobber_client
        self._repo = repository
        self._logger = logger
        self._entity_type = entity_type
        self._rate_limiter = rate_limiter
        self._config_manager = config_manager
        self._max_concurrent = max_concurrent
        self._enable_parallel = enable_parallel
        self._progress_callback = progress_callback

        # Response path for extracting edges/pageInfo
        self._response_path = self._RESPONSE_PATH_MAP[entity_type]

        # Concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Performance metrics
        self._metrics = {
            "total_requests": 0,
            "parallel_batches": 0,
            "total_entities": 0,
            "avg_batch_time": 0.0,
            "errors": 0,
        }

    async def _fetch_page_async(
        self,
        cursor: Optional[str],
        async_http_client: AsyncHttpClient,
    ) -> Dict[str, Any]:
        """
        Fetch a single page with concurrency and rate limiting.

        Args:
            cursor: Pagination cursor
            async_http_client: Async HTTP client instance

        Returns:
            GraphQL response dictionary

        Raises:
            JobberApiError: If fetch fails
        """
        async with self._semaphore:
            # Acquire rate limit token (blocks if bucket empty)
            await self._rate_limiter.acquire_async(cost=1.0)

            # Get query from JobberClient (reuse existing query builders)
            fetch_method_name = self._FETCH_METHOD_MAP[self._entity_type]
            query_method_name = f"_get_{self._entity_type}_query"
            query_builder = getattr(self._jobber_client, query_method_name)
            query = query_builder(mode="stream")  # Use stream mode

            # Execute async HTTP request
            response = await async_http_client.post(
                url=self._jobber_client.API_URL,
                json={
                    "query": query,
                    "variables": {"cursor": cursor} if cursor else {},
                },
                headers=self._jobber_client._get_headers(),
            )

            self._metrics["total_requests"] += 1
            return response

    def _extract_edges_and_page_info(
        self, response: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Extract edges and pageInfo from GraphQL response.

        Args:
            response: GraphQL response

        Returns:
            Tuple of (edges, page_info)
        """
        # Navigate response path
        data = response
        for key in self._response_path:
            data = data.get(key, {})

        edges = data.get("edges", [])
        page_info = data.get("pageInfo", {})
        return edges, page_info

    async def _stream_parallel_async(self) -> Dict[str, Any]:
        """
        Stream entities with parallel page fetching.

        Returns:
            Stream results dictionary
        """
        start_time = time.time()
        cursors = [None]  # Start with first page

        async with AsyncHttpClient(self._logger) as http_client:
            while cursors:
                batch_start = time.time()

                # Fetch up to max_concurrent pages in parallel
                batch = cursors[: self._max_concurrent]
                tasks = [self._fetch_page_async(cursor, http_client) for cursor in batch]

                # Wait for all requests in batch (continue on exceptions)
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                # Process responses
                next_cursors = []
                batch_entities = 0

                for response in responses:
                    if isinstance(response, Exception):
                        self._logger.error(f"Page fetch failed: {response}")
                        self._metrics["errors"] += 1
                        continue

                    try:
                        # Extract entities from response
                        edges, page_info = self._extract_edges_and_page_info(response)

                        # Save raw JSON to staging table
                        for edge in edges:
                            node = edge.get("node", {})
                            self._repo.save_raw_entity(
                                entity_type=self._entity_type,
                                entity_id=node.get("id"),
                                raw_data=node,
                            )
                            batch_entities += 1

                        # Progress callback
                        if self._progress_callback:
                            self._progress_callback(len(edges))

                        # Add next cursor if has more pages
                        if page_info.get("hasNextPage"):
                            next_cursors.append(page_info.get("endCursor"))

                    except Exception as e:
                        self._logger.error(f"Failed to process response: {e}")
                        self._metrics["errors"] += 1

                # Update metrics
                batch_time = time.time() - batch_start
                self._metrics["parallel_batches"] += 1
                self._metrics["total_entities"] += batch_entities
                self._metrics["avg_batch_time"] = (
                    self._metrics["avg_batch_time"] * (self._metrics["parallel_batches"] - 1)
                    + batch_time
                ) / self._metrics["parallel_batches"]

                # Log progress every 10 batches
                if self._metrics["parallel_batches"] % 10 == 0:
                    self._log_performance()

                # Update cursors for next batch
                cursors = next_cursors

        duration = time.time() - start_time

        return {
            "entity_type": self._entity_type,
            "total_entities": self._metrics["total_entities"],
            "total_requests": self._metrics["total_requests"],
            "parallel_batches": self._metrics["parallel_batches"],
            "errors": self._metrics["errors"],
            "duration": duration,
            "throughput": self._metrics["total_entities"] / duration if duration > 0 else 0,
        }

    def _log_performance(self) -> None:
        """Log performance metrics."""
        throughput = self._metrics["total_requests"] / (
            self._metrics["parallel_batches"] * self._metrics["avg_batch_time"]
        )
        self._logger.info(
            f"Performance: {self._metrics['total_requests']} requests "
            f"in {self._metrics['parallel_batches']} batches, "
            f"avg {self._metrics['avg_batch_time']:.2f}s per batch, "
            f"throughput: {throughput:.1f} req/s, "
            f"entities: {self._metrics['total_entities']}"
        )

    def stream(self, resume: bool = False) -> Dict[str, Any]:
        """
        Entry point for streaming.

        Args:
            resume: Resume from saved cursor (not implemented for async yet)

        Returns:
            Stream results
        """
        if self._enable_parallel:
            # Run async version
            self._logger.info(
                f"Streaming {self._entity_type} with parallel fetching "
                f"(max_concurrent={self._max_concurrent})"
            )
            return asyncio.run(self._stream_parallel_async())
        else:
            # Fall back to sequential (import and delegate to StreamExtractor)
            self._logger.warning(
                "Parallel fetching disabled, falling back to sequential streaming"
            )
            raise NotImplementedError(
                "Sequential fallback not implemented yet - use StreamExtractor directly"
            )
```

**Acceptance Criteria**:
- ✅ Parallel page fetching with configurable concurrency
- ✅ Rate limit integration via async token acquisition
- ✅ Error handling - failed pages don't block others
- ✅ Reuses JobberClient query builders (DRY)
- ✅ Progress callbacks for UI updates
- ✅ Comprehensive metrics tracking
- ✅ Resource cleanup (async context managers)

**Testing** (create `tests/unit/extractors/test_async_parallel_stream_extractor.py`):

```python
"""Tests for AsyncParallelStreamExtractor."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.extractors.async_parallel_stream_extractor import AsyncParallelStreamExtractor


@pytest.mark.asyncio
async def test_parallel_fetching_respects_semaphore():
    """Max concurrent requests limited by semaphore."""
    # Track concurrent requests
    concurrent_count = 0
    max_concurrent_seen = 0

    async def mock_fetch(*args, **kwargs):
        nonlocal concurrent_count, max_concurrent_seen
        concurrent_count += 1
        max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
        await asyncio.sleep(0.1)  # Simulate network delay
        concurrent_count -= 1
        return {"data": {"invoices": {"edges": [], "pageInfo": {"hasNextPage": False}}}}

    # Create extractor with max_concurrent=3
    extractor = AsyncParallelStreamExtractor(
        jobber_client=Mock(),
        repository=Mock(),
        logger=Mock(),
        entity_type="invoices",
        rate_limiter=Mock(acquire_async=AsyncMock()),
        config_manager=Mock(),
        max_concurrent=3,
    )

    # Mock fetch to track concurrency
    with patch.object(extractor, "_fetch_page_async", side_effect=mock_fetch):
        # Trigger 10 concurrent fetches
        await extractor._stream_parallel_async()

    # Assert never exceeded max_concurrent
    assert max_concurrent_seen <= 3


@pytest.mark.asyncio
async def test_rate_limiter_called_before_requests():
    """Rate limiter acquire_async called for each request."""
    mock_rate_limiter = Mock()
    mock_rate_limiter.acquire_async = AsyncMock()

    extractor = AsyncParallelStreamExtractor(
        jobber_client=Mock(),
        repository=Mock(),
        logger=Mock(),
        entity_type="invoices",
        rate_limiter=mock_rate_limiter,
        config_manager=Mock(),
        max_concurrent=3,
    )

    # Mock HTTP response
    with patch("src.clients.async_http_client.AsyncHttpClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {
            "data": {"invoices": {"edges": [], "pageInfo": {"hasNextPage": False}}}
        }

        await extractor._stream_parallel_async()

    # Assert rate limiter was called
    assert mock_rate_limiter.acquire_async.call_count > 0


@pytest.mark.asyncio
async def test_error_handling_continues_on_failure():
    """Failed request doesn't stop other requests."""
    extractor = AsyncParallelStreamExtractor(
        jobber_client=Mock(),
        repository=Mock(),
        logger=Mock(),
        entity_type="invoices",
        rate_limiter=Mock(acquire_async=AsyncMock()),
        config_manager=Mock(),
        max_concurrent=3,
    )

    # Mock HTTP to fail on first request, succeed on others
    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Network error")
        return {"data": {"invoices": {"edges": [{"node": {"id": "1"}}], "pageInfo": {"hasNextPage": False}}}}

    with patch("src.clients.async_http_client.AsyncHttpClient.post", side_effect=mock_post):
        result = await extractor._stream_parallel_async()

    # Assert extraction continued despite error
    assert result["errors"] == 1
    assert result["total_entities"] > 0
```

---

#### Task 2.5: Add Parallel Fetching Configuration
**Priority**: MEDIUM
**Effort**: 30 minutes
**Files to Modify**:
- `config/settings.yaml`
- `src/config/config_manager.py`

**Changes to `settings.yaml`**:

```yaml
# ... existing rate_limits and pagination ...

# New: Parallel fetching configuration
parallel_fetching:
  enabled: true          # Enable async parallel fetching
  max_concurrent: 3      # Max concurrent requests
  entities:              # Per-entity concurrency overrides
    clients: 2           # Clients have expensive queries
    invoices: 3
    quotes: 3
    jobs: 3
    requests: 3
    default: 3           # Default for unlisted entities
```

**Changes to `config_manager.py`**:

```python
# Add methods to ConfigManagerImpl class

def is_parallel_fetching_enabled(self) -> bool:
    """
    Check if parallel fetching is enabled.

    Returns:
        True if enabled, False otherwise
    """
    return self.config.get("parallel_fetching", {}).get("enabled", False)


def get_max_concurrent(self, entity_type: str = "default") -> int:
    """
    Get max concurrent requests for entity type.

    Args:
        entity_type: Entity type (e.g., "invoices")

    Returns:
        Max concurrent requests for entity type
    """
    parallel_config = self.config.get("parallel_fetching", {})
    entities = parallel_config.get("entities", {})
    return entities.get(entity_type, entities.get("default", 1))
```

**Acceptance Criteria**:
- ✅ Configuration accessible via ConfigManager methods
- ✅ Per-entity concurrency overrides work
- ✅ Defaults to disabled for safety (opt-in feature)
- ✅ Backward compatible (missing config returns False/1)

**Testing** (add to `tests/unit/config/test_config_manager.py`):

```python
def test_is_parallel_fetching_enabled_returns_true_when_configured():
    """Returns True when parallel_fetching.enabled is True."""
    config = {"parallel_fetching": {"enabled": True}}
    manager = ConfigManagerImpl(config)

    assert manager.is_parallel_fetching_enabled() is True


def test_get_max_concurrent_returns_entity_specific_value():
    """Returns entity-specific concurrency limit."""
    config = {
        "parallel_fetching": {
            "entities": {"invoices": 5, "clients": 2, "default": 3}
        }
    }
    manager = ConfigManagerImpl(config)

    assert manager.get_max_concurrent("invoices") == 5
    assert manager.get_max_concurrent("clients") == 2
    assert manager.get_max_concurrent("jobs") == 3  # Falls back to default
```

---

### Phase 3: Integration & Testing (2-3 hours)

#### Task 3.1: Update ServiceFactory to Create Async Extractors
**Priority**: HIGH
**Effort**: 1 hour
**Files to Modify**:
- `src/cli/services/factories.py`

**Implementation**:

```python
# Add to ServiceFactory class

@staticmethod
def create_async_parallel_stream_extractor(
    entity_type: str,
    config_manager: ConfigManagerImpl,
    jobber_client: JobberClient,
    repository: Repository,
    logger: Logger,
    rate_limiter: TokenBucketRateLimiter,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> AsyncParallelStreamExtractor:
    """
    Create async parallel stream extractor with configuration.

    Args:
        entity_type: Entity type to stream
        config_manager: Configuration manager
        jobber_client: JobberClient instance (for query building)
        repository: Repository for database writes
        logger: Logger instance
        rate_limiter: Shared rate limiter
        progress_callback: Optional progress callback

    Returns:
        Configured AsyncParallelStreamExtractor
    """
    from ..extractors.async_parallel_stream_extractor import AsyncParallelStreamExtractor

    # Get configuration
    max_concurrent = config_manager.get_max_concurrent(entity_type)
    enable_parallel = config_manager.is_parallel_fetching_enabled()

    return AsyncParallelStreamExtractor(
        jobber_client=jobber_client,
        repository=repository,
        logger=logger,
        entity_type=entity_type,
        rate_limiter=rate_limiter,
        config_manager=config_manager,
        max_concurrent=max_concurrent,
        enable_parallel=enable_parallel,
        progress_callback=progress_callback,
    )
```

**Existing Pattern Reference** (`factories.py:98-181`):
- `create_rate_limited_jobber_client()` creates shared rate limiter
- All extractors get same `JobberClient` instance
- Dependency injection via constructor

**Acceptance Criteria**:
- ✅ Factory method creates properly configured async extractor
- ✅ Shares rate limiter from JobberClient setup
- ✅ Configuration properly passed through
- ✅ Follows existing factory patterns

---

#### Task 3.2: Update Stream Command to Use Async Extractor
**Priority**: HIGH
**Effort**: 30 minutes
**Files to Modify**:
- `src/cli/migrate.py`

**Implementation**:

```python
# In stream command handler

@app.command()
def stream(
    entity: str = typer.Argument(..., help="Entity type to stream"),
    resume: bool = typer.Option(False, help="Resume from saved cursor"),
    db: str = typer.Option("tightbeam.db", help="Database path"),
    verbose: bool = typer.Option(False, help="Enable verbose logging"),
):
    """Stream entities to staging table (single-pass migration)."""

    # ... existing setup (logger, config_manager, repository, etc.) ...

    # Create JobberClient with rate limiting
    jobber_client = ServiceFactory.create_rate_limited_jobber_client(
        auth_provider=auth_provider,
        repository=repository,
        config_manager=config_manager,
    )

    # Get rate limiter from JobberClient's HTTP client wrapper
    rate_limited_http = jobber_client._http_client
    rate_limiter = rate_limited_http._rate_limiter

    # Check if parallel fetching enabled
    if config_manager.is_parallel_fetching_enabled():
        logger.info("Parallel fetching enabled")

        # Create async parallel extractor
        extractor = ServiceFactory.create_async_parallel_stream_extractor(
            entity_type=entity,
            config_manager=config_manager,
            jobber_client=jobber_client,
            repository=repository,
            logger=logger,
            rate_limiter=rate_limiter,
        )
    else:
        logger.info("Parallel fetching disabled, using sequential streaming")

        # Fall back to existing StreamExtractor
        extractor = StreamExtractor(
            jobber_client=jobber_client,
            repository=repository,
            logger=logger,
            entity_type=entity,
            config_manager=config_manager,
        )

    # Execute streaming
    result = extractor.stream(resume=resume)

    # Display results
    # ... existing result display logic ...
```

**Acceptance Criteria**:
- ✅ Uses async extractor when `parallel_fetching.enabled: true`
- ✅ Falls back to StreamExtractor when disabled
- ✅ Configuration controls behavior (no code changes needed)
- ✅ Backward compatible (defaults to sequential)

**Validation**:
```bash
# Test with parallel enabled
uv run tightbeam migrate stream --entity invoices

# Test with parallel disabled (edit config)
# config/settings.yaml: parallel_fetching.enabled: false
uv run tightbeam migrate stream --entity invoices

# Verify both work correctly
```

---

#### Task 3.3: Add Integration Tests
**Priority**: HIGH
**Effort**: 1 hour
**Files to Create**:
- `tests/integration/test_async_parallel_streaming.py`

**Implementation**:

```python
"""Integration tests for async parallel streaming."""

import pytest
from unittest.mock import AsyncMock, Mock
import asyncio

from src.extractors.async_parallel_stream_extractor import AsyncParallelStreamExtractor
from src.rate_limiting.token_bucket import TokenBucketRateLimiter


@pytest.mark.asyncio
class TestAsyncParallelStreamingIntegration:
    """Integration tests for async parallel streaming."""

    async def test_parallel_vs_sequential_throughput(self):
        """Parallel streaming is faster than sequential."""
        # Mock slow HTTP responses
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(0.5)  # Simulate 500ms network latency
            return {
                "data": {
                    "invoices": {
                        "edges": [{"node": {"id": f"inv_{i}"}} for i in range(10)],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            }

        # Create extractors
        mock_repo = Mock()
        mock_repo.save_raw_entity = Mock()
        mock_logger = Mock()
        mock_client = Mock()
        rate_limiter = TokenBucketRateLimiter(capacity=100, refill_rate=1000)

        # Parallel extractor (3 concurrent)
        parallel_extractor = AsyncParallelStreamExtractor(
            jobber_client=mock_client,
            repository=mock_repo,
            logger=mock_logger,
            entity_type="invoices",
            rate_limiter=rate_limiter,
            config_manager=Mock(),
            max_concurrent=3,
            enable_parallel=True,
        )

        # Measure parallel execution time
        import time
        with patch("src.clients.async_http_client.AsyncHttpClient.post", side_effect=slow_response):
            start = time.time()
            result = await parallel_extractor._stream_parallel_async()
            parallel_time = time.time() - start

        # Assert parallel execution is faster
        # With 3 concurrent and 0.5s latency:
        # - Sequential would take ~1.5s (3 pages × 0.5s)
        # - Parallel should take ~0.5s (all 3 pages in parallel)
        assert parallel_time < 0.8  # Allow some overhead

    async def test_data_integrity_with_parallel(self):
        """Parallel fetching produces same data as sequential."""
        # Mock responses
        mock_responses = [
            {
                "data": {
                    "invoices": {
                        "edges": [{"node": {"id": f"inv_{i}"}} for i in range(10)],
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                    }
                }
            },
            {
                "data": {
                    "invoices": {
                        "edges": [{"node": {"id": f"inv_{i}"}} for i in range(10, 20)],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            },
        ]

        call_count = 0

        async def mock_response(*args, **kwargs):
            nonlocal call_count
            response = mock_responses[call_count]
            call_count += 1
            return response

        # Track saved entities
        saved_entities = []
        mock_repo = Mock()
        mock_repo.save_raw_entity = lambda **kwargs: saved_entities.append(kwargs)

        extractor = AsyncParallelStreamExtractor(
            jobber_client=Mock(),
            repository=mock_repo,
            logger=Mock(),
            entity_type="invoices",
            rate_limiter=TokenBucketRateLimiter(capacity=100, refill_rate=1000),
            config_manager=Mock(),
            max_concurrent=3,
        )

        with patch("src.clients.async_http_client.AsyncHttpClient.post", side_effect=mock_response):
            result = await extractor._stream_parallel_async()

        # Assert all entities saved
        assert len(saved_entities) == 20
        assert result["total_entities"] == 20
        assert result["errors"] == 0

        # Assert entity IDs are correct
        entity_ids = [e["entity_id"] for e in saved_entities]
        expected_ids = [f"inv_{i}" for i in range(20)]
        assert sorted(entity_ids) == sorted(expected_ids)

    async def test_rate_limit_compliance_under_load(self):
        """Parallel fetching respects rate limits."""
        # Track token consumption
        token_consumptions = []

        class TrackedRateLimiter(TokenBucketRateLimiter):
            async def acquire_async(self, cost=1.0, timeout=None):
                token_consumptions.append(self.get_available_tokens())
                return await super().acquire_async(cost, timeout)

        rate_limiter = TrackedRateLimiter(capacity=10, refill_rate=100)

        extractor = AsyncParallelStreamExtractor(
            jobber_client=Mock(),
            repository=Mock(),
            logger=Mock(),
            entity_type="invoices",
            rate_limiter=rate_limiter,
            config_manager=Mock(),
            max_concurrent=5,
        )

        # Mock responses
        async def mock_response(*args, **kwargs):
            return {
                "data": {
                    "invoices": {
                        "edges": [{"node": {"id": "1"}}],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            }

        with patch("src.clients.async_http_client.AsyncHttpClient.post", side_effect=mock_response):
            await extractor._stream_parallel_async()

        # Assert no over-consumption (tokens never went negative)
        assert all(tokens >= 0 for tokens in token_consumptions)
```

**Acceptance Criteria**:
- ✅ Parallel mode demonstrates measurable speedup
- ✅ Data integrity maintained (no duplicate/missing entities)
- ✅ Rate limits respected under concurrent load
- ✅ All tests pass

**Run Tests**:
```bash
# Run all integration tests
uv run pytest tests/integration/test_async_parallel_streaming.py -v

# Run with coverage
uv run pytest tests/integration/test_async_parallel_streaming.py --cov=src/extractors
```

---

#### Task 3.4: Add Performance Metrics Logging
**Priority**: LOW
**Effort**: 30 minutes
**Files to Modify**:
- `src/extractors/async_parallel_stream_extractor.py` (already has metrics)

**Enhancement**:

```python
# Add to AsyncParallelStreamExtractor._stream_parallel_async()

# At end of method, before return
self._logger.info("=" * 60)
self._logger.info("ASYNC PARALLEL STREAMING PERFORMANCE SUMMARY")
self._logger.info("=" * 60)
self._logger.info(f"Entity type: {self._entity_type}")
self._logger.info(f"Total entities: {self._metrics['total_entities']}")
self._logger.info(f"Total requests: {self._metrics['total_requests']}")
self._logger.info(f"Parallel batches: {self._metrics['parallel_batches']}")
self._logger.info(f"Avg batch time: {self._metrics['avg_batch_time']:.2f}s")
self._logger.info(f"Duration: {duration:.2f}s")
self._logger.info(f"Throughput: {result['throughput']:.1f} entities/sec")
self._logger.info(f"Errors: {self._metrics['errors']}")
self._logger.info(f"Max concurrent: {self._max_concurrent}")
self._logger.info("=" * 60)
```

**Acceptance Criteria**:
- ✅ Performance summary logged at end of streaming
- ✅ Key metrics displayed (throughput, errors, duration)
- ✅ Helps with debugging and optimization

---

## Performance Validation

### Success Metrics

After all phases implemented:

| Metric | Before | After (Phase 1) | After (Phase 2) | Total Improvement |
|--------|--------|-----------------|-----------------|-------------------|
| Query Cost | 2,600 pts | 1,300 pts | 1,300 pts | 50% reduction |
| Requests/Min | 11 | 20 | 60 (effective) | 5.5x |
| Concurrent Requests | 1 | 1 | 3 | 3x |
| **Throughput (inv/min)** | **220** | **400** | **1200** | **5.5x** |
| Time for 10k invoices | ~45 min | ~25 min | ~8 min | **5.6x faster** |

### Validation Steps

**Phase 1 Validation**:
```bash
# Measure before Phase 1
time uv run tightbeam migrate stream --entity invoices
# Expected: ~5-6 seconds per page

# Apply Phase 1 changes
# Measure after Phase 1
time uv run tightbeam migrate stream --entity invoices
# Expected: ~3 seconds per page (2x improvement)
```

**Phase 2 Validation**:
```bash
# Enable parallel fetching in config
# config/settings.yaml: parallel_fetching.enabled: true

# Measure with parallel enabled
time uv run tightbeam migrate --verbose stream --entity invoices

# Check logs for:
# - "Parallel fetching enabled"
# - Performance metrics (req/s, throughput)
# - No throttling errors

# Expected: ~1 second per page (3-4x improvement over Phase 1)
```

**Stress Test**:
```bash
# Stream large dataset (all invoices)
uv run tightbeam migrate stream --entity invoices

# Monitor for:
# - Consistent throughput (no degradation)
# - Zero throttling errors
# - Memory usage stays reasonable
# - All entities extracted
```

---

## Rollout Strategy

### Week 1: Phase 1 (Quick Win)
- **Day 1**: Implement Tasks 1.1-1.3
- **Day 2**: Test and validate 2x improvement
- **Day 3**: Monitor production usage
- **Milestone**: Deploy with `parallel_fetching.enabled: false`

### Week 2: Phase 2 (Async Infrastructure)
- **Day 1-2**: Implement Tasks 2.1-2.3 (dependencies, HTTP, rate limiter)
- **Day 3-4**: Implement Task 2.4 (async extractor)
- **Day 5**: Implement Task 2.5 (configuration)
- **Milestone**: Deploy with feature flag OFF (code ready, not enabled)

### Week 3: Phase 3 (Integration & Testing)
- **Day 1**: Implement Tasks 3.1-3.2 (factory, command integration)
- **Day 2**: Implement Tasks 3.3-3.4 (tests, metrics)
- **Day 3**: Internal testing with parallel ON
- **Day 4**: Gradual rollout (1 entity type first)
- **Day 5**: Enable for all entity types if successful
- **Milestone**: Full production deployment

### Rollback Plan
- **Phase 1**: Revert query changes (restore full attachment metadata)
- **Phase 2/3**: Set `parallel_fetching.enabled: false` in config
- **No data loss risk**: All changes backward compatible

---

## Dependencies

### External Dependencies
```toml
# Add to pyproject.toml
[project]
dependencies = [
    "aiohttp>=3.9.0",  # Async HTTP client
]

[project.optional-dependencies]
dev = [
    "pytest-asyncio>=0.23.0",  # Async test support
]
```

**Install**:
```bash
uv sync
```

### Internal Dependencies
- `TokenBucketRateLimiter` must support async (Task 2.3)
- `ConfigManager` must load parallel config (Task 2.5)
- `JobberClient` queries must accept mode parameter (Task 1.1)

---

## Risks and Mitigations

### Risk 1: Async Complexity
**Impact**: HIGH
**Likelihood**: MEDIUM
**Mitigation**:
- Make parallel fetching opt-in (feature flag)
- Maintain sequential fallback
- Extensive testing before rollout
- Gradual rollout (1 entity at a time)

### Risk 2: Rate Limit Violations
**Impact**: HIGH
**Likelihood**: LOW
**Mitigation**:
- Semaphore strictly enforces concurrency
- Rate limiter blocks when bucket empty
- Monitor `throttleStatus` in responses
- Conservative initial settings (3 concurrent)
- Increase gradually based on metrics

### Risk 3: Data Integrity Issues
**Impact**: CRITICAL
**Likelihood**: LOW
**Mitigation**:
- Comprehensive integration tests
- Verify entity counts match sequential mode
- Repository methods already thread-safe (WAL mode)
- Atomic writes to staging table

### Risk 4: Increased Memory Usage
**Impact**: MEDIUM
**Likelihood**: MEDIUM
**Mitigation**:
- Connection pooling limits (max 10 connections)
- Batched processing (fetch N, save, repeat)
- Monitor memory during testing
- Limit concurrent tasks with semaphore

---

## Codebase Integration Points

### Files to Modify
- `src/clients/jobber_client.py` - Add query mode parameter
- `src/extractors/stream_extractor.py` - Use stream mode
- `config/settings.yaml` - Update rate limits and add parallel config
- `src/rate_limiting/token_bucket.py` - Add async support
- `src/config/config_manager.py` - Add parallel config getters
- `src/cli/services/factories.py` - Add async extractor factory
- `src/cli/migrate.py` - Use async extractor in stream command

### New Files to Create
- `src/clients/async_http_client.py` - Async HTTP wrapper
- `src/extractors/async_parallel_stream_extractor.py` - Async extractor
- `tests/unit/clients/test_async_http_client.py` - HTTP client tests
- `tests/unit/extractors/test_async_parallel_stream_extractor.py` - Extractor unit tests
- `tests/integration/test_async_parallel_streaming.py` - Integration tests

### Existing Patterns to Follow
- **Dependency injection** via constructor (all services)
- **Template method pattern** (BaseExtractor)
- **Configuration-driven behavior** (ConfigManager)
- **Progress callbacks** (StreamExtractor)
- **Comprehensive error handling** (BaseExtractor)
- **Metrics tracking** (BaseExtractor._last_extraction_summary)
- **Cursor persistence** (StreamExtractor resume logic)

---

## Testing Strategy

### Unit Tests
- `AsyncHttpClient`: Session lifecycle, error handling
- `TokenBucketRateLimiter.acquire_async()`: Token acquisition, timeout
- `AsyncParallelStreamExtractor`: Semaphore, rate limiting, error isolation

### Integration Tests
- Parallel vs sequential throughput comparison
- Data integrity (no duplicates/missing entities)
- Rate limit compliance under concurrent load
- Error handling (partial failures)

### Manual Testing
```bash
# Test Phase 1 (deferred attachments)
uv run tightbeam migrate stream --entity invoices

# Test Phase 2 (parallel enabled)
# Edit config: parallel_fetching.enabled: true
uv run tightbeam migrate --verbose stream --entity invoices

# Verify metrics in logs
# Check for throttling errors (should be zero)
```

### Coverage Goals
- New code: >80% coverage
- Integration tests: Cover main scenarios
- All tests passing before merge

---

## Success Criteria

- ✅ Query cost reduced by 50% (Phase 1)
- ✅ Parallel fetching implemented and configurable (Phase 2)
- ✅ 3-5x throughput improvement measured (Phase 3)
- ✅ Zero throttling errors during testing
- ✅ All existing tests pass
- ✅ New tests achieve >80% coverage
- ✅ Backward compatible (can disable parallel mode)
- ✅ Performance metrics logged
- ✅ Documentation updated

---

## Next Steps

After creating this plan:

1. **Review and approve** plan with stakeholders
2. **Execute Phase 1** (1 hour, quick win)
3. **Validate Phase 1** performance improvement
4. **Execute Phase 2** (4-6 hours, async infrastructure)
5. **Execute Phase 3** (2-3 hours, integration & testing)
6. **Gradual rollout** with monitoring
7. **Document** results and lessons learned

---

*This implementation plan is ready for execution. Begin with Phase 1 for quick wins, then proceed to Phase 2 for maximum performance gains.*
