# Implementation Plan: PR Readiness Fixes for Multi-Pass Extraction

## Overview

This plan addresses critical issues identified during validation of the multi-pass extraction system to make it production-ready and PR-ready. The validation revealed three main areas requiring attention:

1. **Reconcile Command Test Coverage** - Adequate tests but coverage gaps in actual functionality testing
2. **Integration Tests** - All 3 tests failing due to mock signature bug, plus 60% missing coverage
3. **Code Quality** - Deprecated datetime usage that will break in future Python versions

## Requirements Summary

Based on validation reports:
- Fix all failing integration tests (3/3 currently failing)
- Add missing integration test scenarios (4 critical scenarios)
- Improve reconcile command test coverage from ~13% to >60%
- Replace deprecated `datetime.utcnow()` calls
- Ensure all code follows modern Python best practices
- Achieve 100% test pass rate before PR submission

## Validation Report Summary

### Task 1: "Maintain Backward Compatibility for migrate start" ✅
- **Status:** PRODUCTION READY
- **Tests:** 11/11 passing (100%)
- **Action:** Mark as done

### Task 2: "Add tightbeam migrate reconcile Command" ⚠️
- **Status:** CONDITIONAL PASS
- **Tests:** 8/8 passing but mostly smoke tests
- **Coverage:** ~13.4% (inadequate)
- **Issues:** Deprecated datetime, false positive tests
- **Action:** Improve test coverage and fix deprecations

### Task 3: "Integration Tests for Multi-Pass Flow" ❌
- **Status:** FAILING
- **Tests:** 0/3 passing (100% failure rate)
- **Coverage:** ~40% of required scenarios
- **Issues:** Mock signature bug, missing scenarios
- **Action:** Fix bugs and implement missing tests

## Implementation Tasks

### Phase 1: Critical Bug Fixes (IMMEDIATE - 2 hours)

#### Task 1.1: Fix Integration Test Mock Signature Bug
**Priority:** CRITICAL
**Estimated Effort:** 30 minutes

**Description:** All 3 integration tests fail due to mock parameter mismatch

**Files to Modify:**
- `tests/integration/test_multi_pass_flow_integration.py` (line 102)

**Issue:**
```python
# Current (broken):
repo.get_attachment_queue.side_effect = lambda sid, s=None: self._get_attachment_queue(repo, sid, s)

# Fix needed:
repo.get_attachment_queue.side_effect = lambda sid, status=None, **kwargs: self._get_attachment_queue(repo, sid, status)
```

**Also fix similar issues for:**
- `get_extract_queue` mock (line ~100)
- Any other repository method mocks with keyword arguments

**Acceptance Criteria:**
- All 3 existing integration tests pass
- No TypeError exceptions
- Mock signatures match actual method signatures

---

#### Task 1.2: Replace Deprecated datetime.utcnow() in Reconcile Command
**Priority:** HIGH
**Estimated Effort:** 15 minutes

**Description:** Replace deprecated `datetime.utcnow()` with `datetime.now(UTC)`

**Files to Modify:**
- `src/cli/migrate.py` (lines 795, 806)

**Changes:**
```python
# Line 1: Add import at top of file
from datetime import datetime, UTC

# Line 795: Replace
# OLD: timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
# NEW: timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

# Line 806: Replace
# OLD: f"**Reconciliation Date:** {datetime.utcnow().isoformat()}Z",
# NEW: f"**Reconciliation Date:** {datetime.now(UTC).isoformat()}Z",
```

**Acceptance Criteria:**
- No deprecation warnings in tests
- Timestamps are still UTC
- All reconcile tests still pass

---

### Phase 2: Integration Test Coverage (HIGH PRIORITY - 8 hours)

#### Task 2.1: Implement Discrepancy Detection Test
**Priority:** HIGH
**Estimated Effort:** 2 hours

**Description:** Test that extract mode detects when actual entity count differs from inventory count

**Files to Create:**
- Add test to `tests/integration/test_multi_pass_flow_integration.py`

**Test Implementation:**
```python
def test_discrepancy_scenario_missing_entities(self, mock_repository, mock_jobber_client):
    """Test detecting missing entities after extraction."""
    # Setup
    # 1. Create inventory with 10 clients
    # 2. Mock API to return only 8 clients
    # 3. Run extract pass

    # Assertions
    # 1. Verify 2 discrepancies detected
    # 2. Verify missing entity IDs identified
    # 3. Verify discrepancy in extract result
    # 4. Verify discrepancy in extract report
```

**Acceptance Criteria:**
- Test passes
- Discrepancy detection logic validated
- Report includes discrepancy details

---

#### Task 2.2: Implement Attachment Retry Test
**Priority:** HIGH
**Estimated Effort:** 2 hours

**Description:** Test that reconcile mode successfully retries failed attachments

**Files to Create:**
- Add test to `tests/integration/test_multi_pass_flow_integration.py`

**Test Implementation:**
```python
def test_attachment_retry_in_reconcile(self, mock_repository, mock_jobber_client):
    """Test reconcile retries failed attachments."""
    # Setup
    # 1. Create snapshot with 3 failed attachments
    # 2. Mock attachment download to succeed on retry
    # 3. Run reconcile command

    # Assertions
    # 1. Verify failed attachments reset to pending
    # 2. Verify attachments reprocessed
    # 3. Verify final status is done
    # 4. Verify retry count incremented
```

**Acceptance Criteria:**
- Test passes
- Attachment retry logic validated
- Status transitions verified (failed → pending → done)

---

#### Task 2.3: Implement Data Drift Test
**Priority:** MEDIUM
**Estimated Effort:** 2 hours

**Description:** Test detection of entities added/modified between map and extract passes

**Files to Create:**
- Add test to `tests/integration/test_multi_pass_flow_integration.py`

**Test Implementation:**
```python
def test_data_drift_detection(self, mock_repository, mock_jobber_client):
    """Test entities modified after pass1_cutoff trigger warnings."""
    # Setup
    # 1. Create map snapshot with cutoff timestamp T1
    # 2. Mock 3 entities with updatedAt > T1 (drift)
    # 3. Mock 7 entities with updatedAt <= T1 (no drift)
    # 4. Run extract

    # Assertions
    # 1. Verify drift warning for 3 entities
    # 2. Verify all entities still extracted
    # 3. Verify drift entities marked in report
```

**Acceptance Criteria:**
- Test passes
- Drift detection logic validated
- Drift entities identified in results

---

#### Task 2.4: Implement End-to-End Reconcile Test
**Priority:** HIGH
**Estimated Effort:** 2 hours

**Description:** Test complete reconcile workflow: re-map → compare → extract deltas

**Files to Create:**
- Add test to `tests/integration/test_multi_pass_flow_integration.py`

**Test Implementation:**
```python
def test_reconcile_flow_end_to_end(self, mock_repository, mock_jobber_client):
    """Test full reconcile flow with delta detection."""
    # Setup
    # 1. Run initial map (5 clients)
    # 2. Add 3 new clients to mock data
    # 3. Run reconcile

    # Assertions
    # 1. Verify new map snapshot created
    # 2. Verify 3 delta entities detected
    # 3. Verify deltas added to extract queue
    # 4. Verify extraction runs for deltas only
    # 5. Verify reconcile report generated
    # 6. Verify completeness status updated
```

**Acceptance Criteria:**
- Test passes
- Complete reconcile workflow validated
- Delta detection and extraction verified
- Report generation validated

---

### Phase 3: Reconcile Command Test Improvements (MEDIUM PRIORITY - 4 hours)

#### Task 3.1: Fix False Positive Tests
**Priority:** MEDIUM
**Estimated Effort:** 30 minutes

**Description:** Remove `--help` flag from tests that should test actual functionality

**Files to Modify:**
- `tests/cli/test_cli_integration.py` (lines 972, 1022)

**Changes:**
```python
# Test 5: test_migrate_reconcile_with_specific_entities
# Remove --help flag and add proper mocking for full execution

# Test 7: test_migrate_reconcile_with_report_dir
# Remove --help flag and add proper mocking for full execution
```

**Acceptance Criteria:**
- Tests actually execute reconcile logic
- Tests verify correct behavior, not just help text
- Tests still pass

---

#### Task 3.2: Add Delta Detection Validation Test
**Priority:** MEDIUM
**Estimated Effort:** 1.5 hours

**Description:** Test that reconcile correctly identifies delta entities

**Files to Modify:**
- `tests/cli/test_cli_integration.py` - Add new test

**Test Implementation:**
```python
def test_migrate_reconcile_detects_deltas(self, runner, monkeypatch):
    """Test reconcile detects new entities since original map."""
    # Setup mocks to simulate:
    # - Original inventory: 5 clients
    # - New inventory: 7 clients (2 deltas)

    # Verify:
    # - 2 delta entities identified
    # - Deltas added to extract queue
    # - Extract coordinator called for deltas
```

**Acceptance Criteria:**
- Test passes
- Delta detection logic exercised
- Queue creation validated

---

#### Task 3.3: Add Report Generation Validation Test
**Priority:** MEDIUM
**Estimated Effort:** 1 hour

**Description:** Test that reconcile generates correct report content

**Files to Modify:**
- `tests/cli/test_cli_integration.py` - Add new test

**Test Implementation:**
```python
def test_migrate_reconcile_generates_report(self, runner, monkeypatch, tmp_path):
    """Test reconcile report generation and content."""
    # Use tmp_path for report directory
    # Run reconcile with mocked data

    # Verify:
    # - Report file created
    # - Report contains snapshot IDs
    # - Report contains delta counts
    # - Report contains completeness metrics
```

**Acceptance Criteria:**
- Test passes
- Report file creation validated
- Report content validated

---

#### Task 3.4: Add Failed Attachment Retry Test
**Priority:** MEDIUM
**Estimated Effort:** 1 hour

**Description:** Test Phase 4 of reconcile (attachment retry)

**Files to Modify:**
- `tests/cli/test_cli_integration.py` - Add new test

**Test Implementation:**
```python
def test_migrate_reconcile_retries_failed_attachments(self, runner, monkeypatch):
    """Test reconcile Phase 4: retry failed attachments."""
    # Mock repository with failed attachments
    # Run reconcile

    # Verify:
    # - Failed attachments queried
    # - Status reset to pending
    # - Extract coordinator called for attachments
```

**Acceptance Criteria:**
- Test passes
- Phase 4 execution validated
- Status transitions verified

---

### Phase 4: Code Quality & Cleanup (LOW PRIORITY - 1 hour)

#### Task 4.1: Update Task Statuses in Archon
**Priority:** LOW
**Estimated Effort:** 15 minutes

**Description:** Update Archon task statuses to reflect actual state

**Actions:**
1. Mark "Maintain Backward Compatibility for migrate start" as **done**
2. Keep "Add tightbeam migrate reconcile Command" in **review** (will move to done after Phase 3)
3. Move "Integration Tests for Multi-Pass Flow" to **doing** (currently failing)

---

#### Task 4.2: Add Test Execution Verification
**Priority:** LOW
**Estimated Effort:** 30 minutes

**Description:** Ensure all test suites pass before PR

**Files to Run:**
```bash
# Unit tests
uv run pytest tests/cli/test_cli_integration.py::TestMigrateStartCommand -v
uv run pytest tests/cli/test_cli_integration.py::TestMigrateReconcileCommand -v

# Integration tests
uv run pytest tests/integration/test_multi_pass_flow_integration.py -v

# Full test suite
uv run pytest tests/ -v
```

**Acceptance Criteria:**
- All tests pass
- No warnings or deprecations
- Coverage reports generated

---

#### Task 4.3: Documentation Updates
**Priority:** LOW
**Estimated Effort:** 15 minutes

**Description:** Ensure documentation reflects all implemented features

**Files to Review:**
- `MULTI_PASS_MIGRATION.md` - Update with reconcile command details
- `README.md` - Update command examples
- `MIGRATION_COORDINATOR_DOCUMENTATION.md` - Update if needed

**Acceptance Criteria:**
- All commands documented
- Examples are accurate
- Usage instructions clear

---

## Codebase Integration Points

### Files to Modify

**Critical Fixes:**
- `tests/integration/test_multi_pass_flow_integration.py` (line 102) - Fix mock signature
- `src/cli/migrate.py` (lines 795, 806) - Replace deprecated datetime

**Test Improvements:**
- `tests/integration/test_multi_pass_flow_integration.py` - Add 4 new test methods
- `tests/cli/test_cli_integration.py` - Modify 2 tests, add 3 new tests

**Documentation:**
- `MULTI_PASS_MIGRATION.md` - Update with reconcile details
- `README.md` - Update examples

### Existing Patterns to Follow

**Test Structure (from test_multi_pass_flow_integration.py):**
```python
class TestMultiPassFlowIntegration:
    @pytest.fixture
    def mock_repository(self):
        # Create mock with state tracking

    def test_scenario_name(self, mock_repository, mock_jobber_client):
        # 1. Setup phase
        # 2. Execution phase
        # 3. Assertion phase
```

**Mock Signature Pattern:**
```python
# Always use **kwargs for keyword arguments
repo.method.side_effect = lambda arg1, kwarg1=None, **kwargs: implementation
```

**Test Assertions Pattern:**
```python
# Verify multiple aspects
assert result is not None
assert result["status"] == expected_status
assert len(result["items"]) == expected_count
assert coordinator_mock.called
```

## Technical Design

### Test Coverage Goals

**Before PR:**
- Integration tests: 100% pass rate (currently 0%)
- Integration test scenarios: 100% coverage (currently 40%)
- Reconcile CLI tests: >60% coverage (currently 13%)
- Overall test suite: 100% pass rate

### Mock Architecture

```
MockRepository (in-memory state)
    ├── Snapshots dict
    ├── Inventory dict
    ├── Extract queues dict
    ├── Attachment queues dict
    └── State management methods

MockJobberClient (simulated API)
    ├── Mock entity data
    ├── Paginated responses
    └── Error simulation
```

### Test Execution Flow

```
Phase 1: Fix Bugs
    ├── Fix mock signatures
    ├── Fix datetime deprecations
    └── Verify existing tests pass

Phase 2: Add Integration Tests
    ├── Test 1: Discrepancy detection
    ├── Test 2: Attachment retry
    ├── Test 3: Data drift
    └── Test 4: Reconcile end-to-end

Phase 3: Improve CLI Tests
    ├── Fix false positives
    ├── Add delta detection test
    ├── Add report generation test
    └── Add attachment retry test

Phase 4: Final Validation
    ├── Run all tests
    ├── Check coverage
    ├── Update docs
    └── Update Archon tasks
```

## Testing Strategy

### Unit Test Coverage
- CLI command parsing and validation
- Error handling and edge cases
- Parameter validation
- Help text accuracy

### Integration Test Coverage
- Map → Extract workflow
- Extract resume scenario
- Discrepancy detection
- Attachment retry logic
- Data drift detection
- Reconcile end-to-end flow

### Edge Cases to Cover
- Empty snapshots
- No deltas (everything up-to-date)
- All entities are deltas (complete drift)
- Failed attachment retry failures
- Invalid snapshot IDs
- Invalid entity types
- Concurrent reconciliation attempts

## Success Criteria

### Must Have (Phase 1 & 2)
- [ ] All 3 integration tests pass (currently failing)
- [ ] 4 new integration test scenarios implemented and passing
- [ ] No deprecated datetime usage
- [ ] No TypeError or similar runtime errors

### Should Have (Phase 3)
- [ ] Reconcile command test coverage >60% (currently 13%)
- [ ] No false positive tests
- [ ] Delta detection validated
- [ ] Report generation validated
- [ ] Attachment retry validated

### Nice to Have (Phase 4)
- [ ] Documentation updated
- [ ] Archon task statuses accurate
- [ ] Test execution automated
- [ ] Coverage reports reviewed

## Dependencies

**Required:**
- pytest
- pytest-cov (for coverage)
- unittest.mock (standard library)
- typer.testing (CliRunner)

**No New Dependencies Required** - All fixes use existing test infrastructure

## Notes and Considerations

### Testing Philosophy
- **Integration tests** should use mocks but test real coordinator logic
- **CLI tests** should mock coordinators to test CLI layer only
- **Unit tests** should test isolated components

### Mock Design Principles
- Mocks should match actual signatures (use `**kwargs` for keyword args)
- Mock state should be consistent across test execution
- Mocks should simulate realistic data flows

### Potential Challenges
1. **Mock Complexity** - Integration tests use complex mocks with state
   - Solution: Use helper methods to build test data

2. **Test Isolation** - Tests share fixtures
   - Solution: Ensure fixtures create fresh instances

3. **Coverage Metrics** - CLI tests mock dependencies heavily
   - Solution: Focus on integration tests for coordinator coverage

### Future Enhancements
After PR is merged:
- Add performance benchmarks for large datasets
- Add concurrency tests for parallel extractions
- Add real API integration tests (sandbox environment)
- Add visual progress bar testing

## Execution Order

**Immediate (Day 1):**
1. Task 1.1: Fix mock signature bug (30 min)
2. Task 1.2: Fix datetime deprecations (15 min)
3. Verify all existing tests pass

**High Priority (Day 2-3):**
4. Task 2.1: Discrepancy test (2 hrs)
5. Task 2.2: Attachment retry test (2 hrs)
6. Task 2.3: Data drift test (2 hrs)
7. Task 2.4: Reconcile end-to-end test (2 hrs)

**Medium Priority (Day 4):**
8. Task 3.1: Fix false positives (30 min)
9. Task 3.2: Delta detection CLI test (1.5 hrs)
10. Task 3.3: Report generation CLI test (1 hr)
11. Task 3.4: Attachment retry CLI test (1 hr)

**Final (Day 5):**
12. Task 4.1: Update Archon tasks (15 min)
13. Task 4.2: Test suite validation (30 min)
14. Task 4.3: Documentation updates (15 min)

**Total Estimated Effort:** ~15 hours over 5 days

---

*This plan is ready for execution. Start with Phase 1 critical bug fixes to unblock all other work.*
