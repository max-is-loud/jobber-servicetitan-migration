# Implementation Plan: Progress Tracking with Total Counts and Time Estimation

## Overview
Add comprehensive progress tracking to the extraction process by leveraging GraphQL's `totalCount` field to display accurate percentages, entity counts (X/Y format), and estimated time remaining (ETA) during extraction operations.

## Requirements Summary
- Display total count of entities available for extraction
- Show current progress as "X/Y entities" format
- Calculate and display accurate completion percentage
- Estimate and show time remaining (ETA)
- Maintain existing resume/skip functionality
- No impact on API rate limits or costs

## Research Findings

### Current State Analysis

**Key Discovery:** GraphQL responses ALREADY include `totalCount` for map mode queries but NOT for full extraction queries.

**Map Mode (already has totalCount):**
```graphql
query GetClientsMap($cursor: String) {
  clients(first: 50, after: $cursor) {
    totalCount          # ← Already present
    pageInfo { ... }
    edges { ... }
  }
}
```

**Full Extraction Mode (missing totalCount):**
```graphql
query GetClients($cursor: String) {
  clients(first: 50, after: $cursor) {
    # totalCount MISSING ← Need to add
    pageInfo { ... }
    edges { ... }
  }
}
```

### Existing Infrastructure

**Rich Progress Library** (already in use):
- `Progress` class with multiple display columns
- `BarColumn()` - visual progress bar
- `MofNCompleteColumn()` - shows "X/Y" format automatically
- `PercentageColumn()` - shows percentage automatically
- `TimeRemainingColumn()` - calculates ETA based on rate automatically
- `TransferSpeedColumn()` - shows items/second

**BaseExtractor Pattern:**
- Abstract base class for all 12 entity extractors
- `extract()` method handles pagination loop
- `get_entity_count()` abstract method (currently estimates)
- `_last_extraction_summary` tracks progress metrics

**Coordinator Pattern:**
- `BaseMigrationCoordinator` manages progress displays
- `_create_progress_display()` creates Rich Progress instance
- `_update_task_progress()` updates completed/total counts
- Already used successfully in extract mode (queue processing)

### Best Practices

1. **Graceful Degradation:** If totalCount unavailable, fall back to current behavior (spinner without percentage)
2. **First Page Extraction:** Get totalCount from first API response, store in extractor instance
3. **Efficient Storage:** totalCount is metadata - no API cost increase
4. **Type Safety:** Use Optional[int] for totalCount to handle missing values
5. **Logging Enhancement:** Include progress percentages in log messages

## Implementation Tasks

### Phase 1: GraphQL Query Updates

**Goal:** Add `totalCount` field to all full extraction queries

1. **Update Clients Query**
   - Description: Add `totalCount` to `_get_clients_query()` method
   - Files to modify: `src/clients/jobber_client.py`
   - Location: Lines 46-126
   - Pattern:
     ```python
     def _get_clients_query(self) -> str:
         return f"""
         query GetClients($cursor: String) {{
           clients(first: {page_size}, after: $cursor) {{
             totalCount  # ← ADD THIS LINE
             edges {{ ... }}
             pageInfo {{ ... }}
           }}
         }}
         """
     ```
   - Estimated effort: 5 minutes

2. **Update Remaining Entity Queries**
   - Description: Apply same pattern to all 11 other extraction queries
   - Files to modify: `src/clients/jobber_client.py`
   - Queries to update:
     - `_get_invoices_query()` (line 127)
     - `_get_quotes_query()` (line 213)
     - `_get_jobs_query()` (line 317)
     - `_get_properties_query()` (line 393)
     - `_get_requests_query()` (line 439)
     - `_get_visits_query()` (line 591)
     - `_get_timesheet_entries_query()` (line 637)
     - `_get_products_services_query()` (line 682)
     - `_get_tax_rates_query()` (line 712)
     - `_get_users_query()` (similar pattern)
     - `_get_expenses_query()` (similar pattern)
   - Dependencies: None
   - Estimated effort: 30 minutes

3. **Verify Query Responses**
   - Description: Test that API returns totalCount in responses
   - Testing: Run single-page extraction, inspect response
   - Success criteria: totalCount appears in first page response
   - Estimated effort: 10 minutes

### Phase 2: BaseExtractor Enhancement

**Goal:** Extract and store totalCount from first API response

4. **Add Abstract Method for Entity Data Extraction**
   - Description: Create `_extract_entity_data()` abstract method
   - Files to modify: `src/extractors/base_extractor.py`
   - Location: After line 258 (with other abstract methods)
   - Code to add:
     ```python
     @abstractmethod
     def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
         """
         Extract entity data container from GraphQL response.

         This method extracts the top-level entity data object that contains
         totalCount, edges, and pageInfo.

         Args:
             response: Raw GraphQL API response

         Returns:
             Entity data dictionary (e.g., response['data']['visits'])

         Example:
             response = {"data": {"visits": {"totalCount": 150, "edges": [...]}}}
             return response.get("data", {}).get("visits", {})
         """
         ...
     ```
   - Dependencies: None
   - Estimated effort: 10 minutes

5. **Extract totalCount in Main Loop**
   - Description: Modify `extract()` method to extract totalCount from first page
   - Files to modify: `src/extractors/base_extractor.py`
   - Location: Around line 536 (after first page fetch)
   - Code to add:
     ```python
     # After fetching first page
     response = self._fetch_page(current_cursor)
     edges, page_info = self._extract_edges_and_page_info(response)

     # NEW: Extract totalCount on first page
     if not hasattr(self, '_total_count'):
         entity_data = self._extract_entity_data(response)
         total_count = entity_data.get("totalCount")
         if total_count is not None:
             self._total_count = int(total_count)
             self._logger.debug(
                 f"Total {self._entity_name_plural} available: {self._total_count:,}"
             )
         else:
             self._total_count = None
             self._logger.debug("totalCount not available from API")
     ```
   - Dependencies: Task 4 (abstract method)
   - Estimated effort: 15 minutes

6. **Update get_entity_count() Implementation**
   - Description: Simplify method to return stored totalCount
   - Files to modify: `src/extractors/base_extractor.py`
   - Location: Lines 764-773
   - Current code:
     ```python
     @abstractmethod
     def get_entity_count(self) -> int:
         """Get total count - must be implemented by subclasses"""
         ...
     ```
   - New code:
     ```python
     def get_entity_count(self) -> Optional[int]:
         """
         Get total count of entities available for extraction.

         Returns totalCount from API if available, otherwise None.
         Should be called after first page is fetched.

         Returns:
             Total count if available, None if unknown
         """
         if hasattr(self, '_total_count'):
             return self._total_count

         # Fallback: Try to get from API
         try:
             response = self._fetch_page(cursor=None)
             entity_data = self._extract_entity_data(response)
             total_count = entity_data.get("totalCount")
             if total_count is not None:
                 self._total_count = int(total_count)
                 return self._total_count
         except Exception as e:
             self._logger.debug(f"Failed to get entity count: {e}")

         return None
     ```
   - Dependencies: Task 5
   - Estimated effort: 10 minutes

7. **Update Extraction Summary**
   - Description: Add totalCount to `_last_extraction_summary` dict
   - Files to modify: `src/extractors/base_extractor.py`
   - Location: Line 240 (initialization), line 889 (update method)
   - Code changes:
     ```python
     # In __init__ (line 240)
     self._last_extraction_summary = {
         "total_entities": 0,
         "total_available": None,  # ← ADD THIS
         "entities_skipped": 0,
         # ... rest of fields
     }

     # In _update_extraction_summary (line 889)
     self._last_extraction_summary["total_available"] = (
         self._total_count if hasattr(self, '_total_count') else None
     )
     ```
   - Dependencies: Task 5
   - Estimated effort: 5 minutes

### Phase 3: Concrete Extractor Implementations

**Goal:** Implement `_extract_entity_data()` in all 12 extractors

8. **Implement for Visits Extractor**
   - Description: Add `_extract_entity_data()` method
   - Files to modify: `src/extractors/visits_extractor.py`
   - Location: After `_save_entities()` method (around line 157)
   - Code to add:
     ```python
     def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
         """Extract visits data from GraphQL response."""
         return response.get("data", {}).get("visits", {})
     ```
   - Dependencies: Task 4
   - Estimated effort: 5 minutes

9. **Simplify get_entity_count() for Visits**
   - Description: Remove complex estimation logic, use parent implementation
   - Files to modify: `src/extractors/visits_extractor.py`
   - Location: Lines 159-197
   - Action: DELETE entire method (will use BaseExtractor implementation)
   - Dependencies: Task 6
   - Estimated effort: 2 minutes

10. **Implement for All Other Extractors**
    - Description: Add `_extract_entity_data()` to remaining extractors
    - Files to modify:
      - `src/extractors/clients_extractor.py`
      - `src/extractors/invoices_extractor.py`
      - `src/extractors/quotes_extractor.py`
      - `src/extractors/jobs_extractor.py`
      - `src/extractors/properties_extractor.py`
      - `src/extractors/requests_extractor.py`
      - `src/extractors/timesheet_entries_extractor.py`
      - `src/extractors/products_services_extractor.py`
      - `src/extractors/tax_rates_extractor.py`
      - `src/extractors/users_extractor.py`
      - `src/extractors/expenses_extractor.py`
    - Pattern for each:
      ```python
      def _extract_entity_data(self, response: dict[str, Any]) -> dict[str, Any]:
          """Extract {entity} data from GraphQL response."""
          return response.get("data", {}).get("{entityPlural}", {})
      ```
      Examples:
      - Clients: `return response.get("data", {}).get("clients", {})`
      - Invoices: `return response.get("data", {}).get("invoices", {})`
      - Jobs: `return response.get("data", {}).get("jobs", {})`
    - Dependencies: Task 4
    - Estimated effort: 45 minutes (11 extractors × 4 min each)

11. **Remove Legacy get_entity_count() Implementations**
    - Description: Delete custom get_entity_count() from all extractors
    - Files to modify: All extractor files (if they have custom implementations)
    - Rationale: BaseExtractor now provides universal implementation
    - Dependencies: Task 10
    - Estimated effort: 15 minutes

### Phase 4: Coordinator Progress Display Updates

**Goal:** Use totalCount to show accurate progress bars with percentages and ETA

12. **Update BaseMigrationCoordinator**
    - Description: Get totalCount before extraction starts
    - Files to modify: `src/coordinators/base_migration_coordinator.py`
    - Location: Around line 289 (entity extraction method)
    - Code changes:
      ```python
      # Before extraction loop starts
      extractor = self._create_extractor(entity_type)

      # NEW: Get total count
      total_count = extractor.get_entity_count()

      # Create progress task with total (if available)
      task_id = self._add_task(
          display_obj,
          f"Extracting {entity_name}...",
          total=total_count if total_count else None  # None = indeterminate
      )
      ```
   - Dependencies: Task 6
   - Estimated effort: 10 minutes

13. **Update Progress During Extraction**
    - Description: Update progress bar after each page with completed/total
    - Files to modify: `src/coordinators/base_migration_coordinator.py`
    - Location: In extraction loop (around line 320)
    - Code changes:
      ```python
      # After processing each page
      entities_processed = summary.get("total_entities", 0)
      total_available = summary.get("total_available")

      # Update progress display
      self._update_task_progress(
          display_obj,
          task_id,
          description=f"Extracting {entity_name}...",
          completed=entities_processed,
          total=total_available  # Shows percentage automatically
      )
      ```
   - Dependencies: Task 7, Task 12
   - Estimated effort: 10 minutes

14. **Handle Resume Mode**
    - Description: Account for already-extracted entities in progress calculation
    - Files to modify: `src/coordinators/base_migration_coordinator.py`
    - Logic:
      ```python
      # When resume=True, check existing count
      if resume:
          existing_count = repository.get_entity_count(entity_type)
          if total_count and existing_count:
              # Start progress from existing count
              self._update_task_progress(
                  display_obj, task_id,
                  completed=existing_count,
                  total=total_count
              )
      ```
   - Dependencies: Task 13
   - Estimated effort: 15 minutes

### Phase 5: Enhanced Logging

**Goal:** Add progress percentages and totals to log messages

15. **Update Start Message**
    - Description: Include total count in extraction start log
    - Files to modify: `src/extractors/base_extractor.py`
    - Location: Line 524
    - Code change:
      ```python
      # Current:
      self._logger.info(f"Starting {self._entity_name} extraction...")

      # New:
      if hasattr(self, '_total_count') and self._total_count:
          self._logger.info(
              f"Starting {self._entity_name} extraction "
              f"({self._total_count:,} entities to process)"
          )
      else:
          self._logger.info(
              f"Starting {self._entity_name} extraction "
              f"(total count unknown)"
          )
      ```
   - Dependencies: Task 5
   - Estimated effort: 5 minutes

16. **Update Page Processing Messages**
    - Description: Add percentage to "Processed X entities" messages
    - Files to modify: `src/extractors/base_extractor.py`
    - Location: Line 584 (and similar throughout)
    - Code change:
      ```python
      # Current:
      self._logger.info(
          f"Processed {len(entities)} {self._entity_name_plural} "
          f"(total: {entities_processed})"
      )

      # New:
      if hasattr(self, '_total_count') and self._total_count:
          percentage = (entities_processed / self._total_count) * 100
          self._logger.info(
              f"Processed {len(entities)} {self._entity_name_plural} "
              f"({entities_processed:,}/{self._total_count:,} - {percentage:.1f}%)"
          )
      else:
          self._logger.info(
              f"Processed {len(entities)} {self._entity_name_plural} "
              f"(total: {entities_processed:,})"
          )
      ```
   - Dependencies: Task 5
   - Estimated effort: 10 minutes

17. **Update Completion Message**
    - Description: Show final percentage in completion summary
    - Files to modify: `src/extractors/base_extractor.py`
    - Location: Line 654 (extraction complete message)
    - Code change:
      ```python
      completion_msg = (
          f"Completed {self._entity_name} extraction: "
          f"{summary['total_entities']:,} entities"
      )

      if summary.get('total_available'):
          percentage = (summary['total_entities'] / summary['total_available']) * 100
          completion_msg += f" ({percentage:.1f}% of {summary['total_available']:,})"

      self._logger.info(completion_msg)
      ```
   - Dependencies: Task 7
   - Estimated effort: 5 minutes

### Phase 6: Testing and Validation

**Goal:** Ensure progress tracking works correctly across all scenarios

18. **Unit Tests for totalCount Extraction**
    - Description: Test `_extract_entity_data()` and totalCount storage
    - Files to create: `tests/test_base_extractor_progress.py`
    - Test cases:
      ```python
      def test_extract_entity_data_returns_correct_container():
          """Test abstract method contract"""

      def test_total_count_extracted_from_first_page():
          """Test totalCount stored on first fetch"""

      def test_total_count_none_when_not_available():
          """Test graceful handling of missing totalCount"""

      def test_get_entity_count_returns_stored_total():
          """Test get_entity_count() uses cached value"""
      ```
   - Dependencies: Tasks 4-6
   - Estimated effort: 30 minutes

19. **Integration Tests for Progress Display**
    - Description: Test end-to-end progress tracking with real extractors
    - Files to modify: `tests/integration/test_progress_tracking.py`
    - Test cases:
      - Extract with totalCount available → verify percentage shown
      - Extract with totalCount missing → verify spinner shown
      - Resume extraction → verify progress starts from existing count
      - Progress updates after each page
   - Dependencies: Tasks 12-14
   - Estimated effort: 45 minutes

20. **Manual Testing with Small Dataset**
    - Description: Run full extraction on test account
    - Commands:
      ```bash
      # Fresh extraction
      uv run tightbeam migrate max-extract --entities visits

      # Verify progress bar shows:
      # - "X/Y entities" format
      # - Percentage (e.g., "42.5%")
      # - ETA (e.g., "00:02:30 remaining")
      # - Items/second rate

      # Resume extraction
      uv run tightbeam migrate max-extract --entities visits --resume

      # Verify progress starts from existing count
      ```
   - Dependencies: All previous tasks
   - Estimated effort: 20 minutes

21. **Performance Testing with Large Dataset**
    - Description: Verify no performance degradation with totalCount
    - Test scenarios:
      - Extract 10,000+ entities
      - Measure extraction speed (entities/second)
      - Compare to baseline (before totalCount)
      - Verify memory usage unchanged
   - Success criteria: <5% performance difference
   - Dependencies: All previous tasks
   - Estimated effort: 30 minutes

22. **Edge Case Testing**
    - Description: Test uncommon scenarios
    - Test cases:
      - Empty dataset (totalCount = 0)
      - Single page dataset (totalCount < page_size)
      - API error on first page (totalCount unavailable)
      - Mid-extraction resume after partial page
   - Dependencies: All previous tasks
   - Estimated effort: 20 minutes

## Technical Design

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Coordinator Layer                        │
│  ┌────────────────────────────────────────────────────┐    │
│  │    BaseMigrationCoordinator                        │    │
│  │                                                      │    │
│  │  1. Call extractor.get_entity_count()               │    │
│  │  2. Create Progress bar with total=count            │    │
│  │  3. Update progress after each page                 │    │
│  └──────────────┬──────────────────────────────────────┘    │
└─────────────────┼──────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   Extractor Layer                           │
│  ┌────────────────────────────────────────────────────┐    │
│  │    BaseExtractor                                    │    │
│  │                                                      │    │
│  │  extract() method:                                  │    │
│  │    1. Fetch first page                              │    │
│  │    2. Extract totalCount via _extract_entity_data() │    │
│  │    3. Store in self._total_count                    │    │
│  │    4. Process pages in loop                         │    │
│  │    5. Return summary with total_available           │    │
│  │                                                      │    │
│  │  get_entity_count() method:                         │    │
│  │    - Returns self._total_count (if available)       │    │
│  │    - Returns None (if unavailable)                  │    │
│  │                                                      │    │
│  │  _extract_entity_data() method:                     │    │
│  │    - Abstract (implemented by subclasses)           │    │
│  │    - Returns entity data container from response    │    │
│  └──────────────┬──────────────────────────────────────┘    │
└─────────────────┼──────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    Client Layer                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │    JobberClient                                     │    │
│  │                                                      │    │
│  │  GraphQL queries include totalCount:                │    │
│  │    query GetVisits($cursor: String) {               │    │
│  │      visits(first: 50, after: $cursor) {            │    │
│  │        totalCount  ← ADDED                          │    │
│  │        edges { ... }                                │    │
│  │        pageInfo { ... }                             │    │
│  │      }                                               │    │
│  │    }                                                 │    │
│  └──────────────┬──────────────────────────────────────┘    │
└─────────────────┼──────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  Jobber GraphQL API                         │
│                                                             │
│  Returns: {                                                 │
│    "data": {                                                │
│      "visits": {                                            │
│        "totalCount": 1547,  ← METADATA (no cost)           │
│        "edges": [...],                                      │
│        "pageInfo": {...}                                    │
│      }                                                      │
│    }                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

**Extraction Start (First Page):**
1. Coordinator calls `extractor.extract()`
2. BaseExtractor fetches first page from JobberClient
3. Response includes `totalCount` field
4. BaseExtractor calls `_extract_entity_data(response)` (implemented by subclass)
5. Extract `totalCount` from entity data: `entity_data.get("totalCount")`
6. Store in `self._total_count` instance variable
7. Log: "Starting extraction (X entities to process)"

**Extraction Loop (Subsequent Pages):**
1. Process entities from current page
2. Save entities to repository
3. Update `_last_extraction_summary["total_entities"]` (running count)
4. Coordinator calls `get_entity_count()` → returns `self._total_count`
5. Coordinator updates progress: `update(completed=X, total=Y)`
6. Rich Progress automatically calculates:
   - Percentage: `(X/Y) * 100`
   - ETA: `(Y - X) / items_per_second`
   - Display: "X/Y entities (42.5%) | 00:02:30 remaining"

**Extraction Complete:**
1. All pages processed
2. Final summary includes `total_available` field
3. Log: "Completed extraction: X entities (Y% of Z)"
4. Progress bar shows 100%

### Progress Display Format

**Rich Progress Columns (in order):**
```
[Spinner] Extracting visits... [████████░░] 850/1547 (54.9%) | 12.5 it/s | 00:05:32 | 00:00:55
  │              │                │       │      │        │        │          │
  │              │                │       │      │        │        │          └─ Time Remaining
  │              │                │       │      │        │        └─ Time Elapsed
  │              │                │       │      │        └─ Items/second
  │              │                │       │      └─ Percentage (auto-calculated)
  │              │                │       └─ "X/Y" format (auto-calculated)
  │              │                └─ Progress bar (auto-calculated)
  │              └─ Task description
  └─ Spinner animation
```

**Configuration:**
```python
Progress(
    SpinnerColumn(),                  # Animated spinner
    TextColumn("[progress.description]{task.description}"),
    BarColumn(bar_width=None),        # Full-width bar
    MofNCompleteColumn(),              # "850/1547"
    TaskProgressColumn(),              # "54.9%"
    TransferSpeedColumn(),             # "12.5 it/s"
    TimeElapsedColumn(),               # "00:05:32"
    TimeRemainingColumn(),             # "00:00:55" (calculated)
    expand=True,
)
```

## Codebase Integration Points

### Files to Modify

| File | Lines | Changes | Effort |
|------|-------|---------|--------|
| `src/clients/jobber_client.py` | 46-712 | Add `totalCount` to 12 queries | 35 min |
| `src/extractors/base_extractor.py` | 236-773 | Add abstract method, extract totalCount, update summary | 40 min |
| `src/extractors/visits_extractor.py` | 75-197 | Implement `_extract_entity_data()`, simplify count method | 7 min |
| `src/extractors/clients_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/invoices_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/quotes_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/jobs_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/properties_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/requests_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/timesheet_entries_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/products_services_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/tax_rates_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/users_extractor.py` | Similar | Same pattern | 7 min |
| `src/extractors/expenses_extractor.py` | Similar | Same pattern | 7 min |
| `src/coordinators/base_migration_coordinator.py` | 289-400 | Call get_entity_count(), update progress with totals | 35 min |

**Total Estimated Effort:** 4.5 hours

### New Files to Create

- `tests/test_base_extractor_progress.py` - Unit tests for totalCount extraction
- `tests/integration/test_progress_tracking.py` - Integration tests for progress display

### Existing Patterns to Follow

**Error Handling:**
```python
try:
    total_count = entity_data.get("totalCount")
    if total_count is not None:
        self._total_count = int(total_count)
except Exception as e:
    self._logger.debug(f"Failed to extract totalCount: {e}")
    self._total_count = None  # Graceful degradation
```

**Logging Format:**
```python
# With thousand separators
self._logger.info(f"Processing {count:,} entities")

# With percentage
percentage = (completed / total) * 100
self._logger.info(f"Progress: {completed:,}/{total:,} ({percentage:.1f}%)")
```

**Type Safety:**
```python
from typing import Optional

def get_entity_count(self) -> Optional[int]:
    """Returns count if available, None otherwise"""
    return getattr(self, '_total_count', None)
```

## Dependencies and Libraries

**No new dependencies required!**

All required libraries already in use:
- `rich` (Progress, BarColumn, TimeRemainingColumn, etc.) - already installed
- `typing` (Optional, Any) - Python standard library
- Standard Python libraries (time, logging, etc.)

## Testing Strategy

### Unit Tests
- `test_extract_entity_data()` - Verify abstract method contract
- `test_total_count_extraction()` - Test totalCount parsing from response
- `test_total_count_storage()` - Verify instance variable storage
- `test_get_entity_count()` - Test count retrieval method
- `test_graceful_degradation()` - Test behavior when totalCount missing

### Integration Tests
- `test_progress_with_total_count()` - Full extraction with progress bar
- `test_progress_without_total_count()` - Fallback to spinner mode
- `test_resume_with_progress()` - Resume extraction shows correct progress
- `test_percentage_calculation()` - Verify accurate percentage display
- `test_eta_calculation()` - Verify time remaining is reasonable

### Manual Tests
- Fresh extraction (all 12 entity types)
- Resume extraction from partial completion
- Empty dataset (totalCount = 0)
- Large dataset (10,000+ entities)
- API error scenarios

### Edge Cases to Cover
- Empty result set (totalCount = 0)
- Single page result (totalCount < page_size)
- Exact page boundary (totalCount = page_size × N)
- API returns totalCount = null
- Network error on first page
- Resume after interruption mid-page

## Success Criteria

- [ ] All 12 GraphQL queries include `totalCount` field
- [ ] BaseExtractor extracts totalCount from first API response
- [ ] `get_entity_count()` returns accurate total count
- [ ] Progress bars display "X/Y entities" format
- [ ] Progress bars display accurate percentage
- [ ] Progress bars display ETA (time remaining)
- [ ] Logs include progress percentages
- [ ] Graceful degradation when totalCount unavailable
- [ ] Resume mode shows correct starting progress
- [ ] No performance degradation (<5% difference)
- [ ] No increase in API costs
- [ ] All tests pass
- [ ] Type checking passes (mypy)
- [ ] Linting passes (ruff)

## Performance Considerations

### API Cost Analysis
- **totalCount field:** Metadata field, no additional cost
- **Query complexity:** No change (same fields as map mode)
- **Request count:** No change (same pagination)
- **Estimated impact:** 0% cost increase

### Memory Usage
- **Storage overhead:** Single integer per extractor instance (~8 bytes)
- **Progress tracking:** Already exists, no new overhead
- **Estimated impact:** <0.1% memory increase

### Extraction Speed
- **totalCount extraction:** Negligible (simple dict lookup)
- **Progress updates:** Minimal overhead (<1ms per page)
- **Logging overhead:** String formatting only when logging enabled
- **Estimated impact:** <1% speed difference

### Rate Limiting
- **No change:** Same queries, same request patterns
- **Progress display:** Client-side only, no API calls
- **Estimated impact:** 0% rate limit impact

## Notes and Considerations

### Important Insights
1. **Map mode already has totalCount** - we're just adding it to extraction mode
2. **Rich Progress handles everything** - percentage, ETA, rate all automatic
3. **No new dependencies** - everything we need is already available
4. **Backward compatible** - falls back gracefully if totalCount unavailable
5. **Type-safe** - using Optional[int] for proper None handling

### Potential Challenges
1. **API might not return totalCount for all entity types** - Solution: Graceful degradation to spinner mode
2. **totalCount might be expensive for large datasets** - Evidence: Already used in map mode without issues
3. **Resume mode needs to account for existing entities** - Solution: Start progress from repository count
4. **Progress might be slightly off if entities deleted mid-extraction** - Acceptable: totalCount is point-in-time snapshot

### Future Enhancements
- Add progress persistence (save progress to database for long-running extractions)
- Add estimated completion time to summary table
- Add "entities remaining" to log messages
- Add progress webhook notifications
- Add dashboard for real-time progress monitoring
- Add historical extraction speed metrics

### Migration Path
1. **Phase 1:** GraphQL queries (backward compatible)
2. **Phase 2:** BaseExtractor updates (backward compatible)
3. **Phase 3:** Extractor implementations (backward compatible)
4. **Phase 4:** Coordinator updates (enabled automatically)
5. **Phase 5:** Logging enhancements (optional)
6. **Phase 6:** Testing and validation

**No breaking changes - fully backward compatible!**

---

## Execution Checklist

When executing this plan with `/execute-plan`:

### Pre-Implementation
- [ ] Review plan with stakeholders
- [ ] Confirm API totalCount field availability
- [ ] Set up test environment
- [ ] Create feature branch

### During Implementation
- [ ] Follow task sequence (Phase 1 → Phase 6)
- [ ] Run tests after each phase
- [ ] Commit after each major task
- [ ] Update plan if blockers encountered

### Post-Implementation
- [ ] Run full test suite
- [ ] Perform manual testing
- [ ] Update documentation
- [ ] Create pull request
- [ ] Deploy to production

---

*This plan is ready for execution with `/execute-plan PRPs/progress-tracking-with-total-counts.md`*
