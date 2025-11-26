# Implementation Plan: ServiceFactory Refactor and CLI Cleanup

## Overview
Refactor the CLI to use proper dependency injection via ServiceFactory throughout, and remove all deprecated **migrate** subcommands and options. This will leave only the two-pass ETL commands (`max-extract` and `download-attachments`) under the migrate command group, with clean, consistent dependency management.

**Important**: The `oauth` command group and its subcommands are NOT deprecated and will remain unchanged.

## Requirements Summary
- Remove 10 deprecated **migrate** subcommands (map, extract, download, reconcile, start, all, quotes, attachments, users, expenses)
- Keep `oauth` command group unchanged (login, logout, status, refresh, revoke)
- Remove 3 deprecated CLI options from migrate callback (--deferred-notes, --enable-notes-persistence, --adaptive)
- Complete ServiceFactory implementation with missing factory methods
- Refactor remaining migrate commands to use ServiceFactory for all dependencies
- Update scripts/performance_test.py to use factory pattern
- Ensure consistent dependency injection across the entire codebase

## Research Findings

### Current ServiceFactory State
The ServiceFactory already has these methods:
- `create_repository(db)` - Creates Repository with schema initialization
- `create_oauth2_manager()` - Creates OAuth2Manager with environment config
- `create_http_client()` - Creates basic HttpClient
- `get_console()` - Returns shared Rich console
- `create_rate_limited_jobber_client(...)` - Creates fully configured JobberClient with rate limiting
- `create_auth_provider(repository, logger)` - Creates AuthProvider (recently added)
- `create_entity_mapper()` - Creates EntityMapper (recently added)

### Identified Gaps
Two common dependencies are still created directly instead of via factory:
1. `RichLogger(verbose=True, console=ServiceFactory.get_console())` - Used in both commands and performance_test.py
2. `ConfigManagerImpl()` - Used in both commands and performance_test.py

### Deprecated Code Analysis
**Commands to Remove (10 total):**
- Lines 225-354: `map` command
- Lines 356-501: `extract` command
- Lines 503-722: `download` command
- Lines 724-1074: `reconcile` command
- Lines 1076-1326: `start` command
- Lines 1328-1791: `all` command
- Lines 1793-1833: `quotes` command
- Lines 1835-1877: `attachments` command
- Lines 1883-1920: `users` command
- Lines 1922-1959: `expenses` command

**Options to Remove (from migrate_callback lines 81-223):**
- Lines 86-92: `--deferred-notes`
- Lines 93-99: `--enable-notes-persistence`
- Lines 140-146: `--adaptive` / `enable_adaptive_optimization`
- Lines 111-121: `--enable-cost-monitoring` (verify not used by kept commands)
- Lines 122-132: `--cost-monitoring-verbose` (verify not used by kept commands)
- Lines 147-153: `--dry-run` (verify not used by kept commands)

**Options to Keep:**
- `--db` - Used by both commands
- `--verbose` - General logging control
- `--optimization-level` - Used by max-extract
- `--resume` - Used by max-extract

### Migrate Subcommands to Keep
1. **`max-extract`** (lines 2130-2258) - Pass 1: Metadata extraction
2. **`download-attachments`** (lines 1965-2112) - Pass 2: Binary downloads

### OAuth Command Group (Unchanged)
The `oauth` command group in `src/cli/oauth.py` and all its subcommands remain unchanged:
- `tightbeam oauth login`
- `tightbeam oauth logout`
- `tightbeam oauth status`
- `tightbeam oauth refresh`
- `tightbeam oauth revoke`

## Implementation Tasks

### Phase 1: Complete ServiceFactory Implementation

**Task 1.1: Add create_logger Factory Method**
- Description: Add factory method for creating RichLogger instances
- Files to modify: `src/cli/services/factories.py`
- Implementation:
  ```python
  @staticmethod
  def create_logger(verbose: bool = False) -> RichLogger:
      """Create RichLogger with shared console.

      Args:
          verbose: Enable verbose logging

      Returns:
          RichLogger: Configured logger instance
      """
      return RichLogger(verbose=verbose, console=ServiceFactory.get_console())
  ```
- Dependencies: None
- Estimated effort: 10 minutes

**Task 1.2: Add create_config_manager Factory Method**
- Description: Add factory method for creating ConfigManagerImpl instances
- Files to modify: `src/cli/services/factories.py`
- Implementation:
  ```python
  @staticmethod
  def create_config_manager() -> ConfigManagerImpl:
      """Create ConfigManager for application settings.

      Returns:
          ConfigManagerImpl: Configured config manager instance
      """
      return ConfigManagerImpl()
  ```
- Dependencies: None
- Estimated effort: 10 minutes

**Task 1.3: Add Required Imports**
- Description: Add imports for RichLogger and ConfigManagerImpl if not present
- Files to modify: `src/cli/services/factories.py`
- Add to imports:
  ```python
  from src.config import ConfigManagerImpl
  from src.loggers.rich_logger import RichLogger
  ```
- Dependencies: None
- Estimated effort: 5 minutes

### Phase 2: Remove Deprecated CLI Commands

**Task 2.1: Remove Deprecated Migrate Subcommand Functions**
- Description: Delete all deprecated migrate subcommand functions from migrate.py (oauth commands are untouched)
- Files to modify: `src/cli/migrate.py`
- Lines to delete:
  - Lines 225-354: `map` command
  - Lines 356-501: `extract` command
  - Lines 503-722: `download` command
  - Lines 724-1074: `reconcile` command
  - Lines 1076-1326: `start` command
  - Lines 1328-1791: `all` command
  - Lines 1793-1833: `quotes` command
  - Lines 1835-1877: `attachments` command
  - Lines 1883-1920: `users` command
  - Lines 1922-1959: `expenses` command
- Dependencies: None
- Estimated effort: 20 minutes

**Task 2.2: Remove Deprecated Options from migrate_callback**
- Description: Remove deprecated option parameters from callback function
- Files to modify: `src/cli/migrate.py`
- Remove from callback signature and body:
  - `deferred_notes` parameter and logic (lines 86-92, 183)
  - `enable_notes_persistence` parameter and logic (lines 93-99, 184)
  - `enable_adaptive_optimization` parameter and logic (lines 140-146, 189)
- Verify if used by kept commands, then remove if not:
  - `enable_cost_monitoring` (lines 111-121)
  - `cost_monitoring_verbose` (lines 122-132)
  - `dry_run` (lines 147-153)
- Dependencies: Task 2.1 (commands must be removed first to verify option usage)
- Estimated effort: 15 minutes

**Task 2.3: Clean Up Unused Imports**
- Description: Remove imports that were only used by deprecated commands
- Files to modify: `src/cli/migrate.py`
- Search for and remove unused:
  - Coordinator imports (MapModeCoordinator, ExtractModeCoordinator, etc.)
  - Other utilities only used by removed commands
- Dependencies: Tasks 2.1, 2.2
- Estimated effort: 10 minutes

### Phase 3: Refactor max-extract Command

**Task 3.1: Update max-extract to Use create_logger**
- Description: Replace direct RichLogger instantiation with factory method
- Files to modify: `src/cli/migrate.py` (line 2201)
- Change from:
  ```python
  logger = RichLogger(verbose=True, console=ServiceFactory.get_console())
  ```
- Change to:
  ```python
  logger = ServiceFactory.create_logger(verbose=True)
  ```
- Dependencies: Task 1.1
- Estimated effort: 5 minutes

**Task 3.2: Update max-extract to Use create_config_manager**
- Description: Replace direct ConfigManagerImpl instantiation with factory method
- Files to modify: `src/cli/migrate.py` (line 2202)
- Change from:
  ```python
  config_manager = ConfigManagerImpl()
  ```
- Change to:
  ```python
  config_manager = ServiceFactory.create_config_manager()
  ```
- Dependencies: Task 1.2
- Estimated effort: 5 minutes

**Task 3.3: Remove Unnecessary Imports from max-extract**
- Description: Remove direct imports since we're using factory
- Files to modify: `src/cli/migrate.py` (around line 2185-2187)
- Remove from command imports if not needed:
  ```python
  from src.config import ConfigManagerImpl
  ```
- Keep coordinator import:
  ```python
  from src.coordinators.max_extract_coordinator import MaxExtractCoordinator
  ```
- Dependencies: Tasks 3.1, 3.2
- Estimated effort: 5 minutes

### Phase 4: Refactor download-attachments Command

**Task 4.1: Update download-attachments to Use create_logger**
- Description: Replace direct RichLogger instantiation with factory method
- Files to modify: `src/cli/migrate.py` (line 2030)
- Change from:
  ```python
  logger = RichLogger(verbose=True, console=ServiceFactory.get_console())
  ```
- Change to:
  ```python
  logger = ServiceFactory.create_logger(verbose=True)
  ```
- Dependencies: Task 1.1
- Estimated effort: 5 minutes

**Task 4.2: Verify download-attachments Dependencies**
- Description: Check if AttachmentDownloader instantiation should be factorized
- Files to review: `src/cli/migrate.py` (lines 2046-2051)
- Current:
  ```python
  downloader = AttachmentDownloader(
      repository=repository,
      logger=logger,
      output_dir=str(output_dir),
      max_retries=3,
  )
  ```
- Decision: Keep as-is (command-specific configuration, not a shared service)
- Dependencies: None
- Estimated effort: 5 minutes (review only)

### Phase 5: Refactor scripts/performance_test.py

**Task 5.1: Update performance_test.py to Use create_logger**
- Description: Replace direct RichLogger instantiation with factory method
- Files to modify: `scripts/performance_test.py` (line 65)
- Change from:
  ```python
  logger = RichLogger(verbose=True)
  ```
- Change to:
  ```python
  logger = ServiceFactory.create_logger(verbose=True)
  ```
- Dependencies: Task 1.1
- Estimated effort: 5 minutes

**Task 5.2: Update performance_test.py to Use create_config_manager**
- Description: Replace direct ConfigManagerImpl instantiation with factory method
- Files to modify: `scripts/performance_test.py` (line 64)
- Change from:
  ```python
  config_manager = ConfigManagerImpl()
  ```
- Change to:
  ```python
  config_manager = ServiceFactory.create_config_manager()
  ```
- Dependencies: Task 1.2
- Estimated effort: 5 minutes

### Phase 6: Testing and Validation

**Task 6.1: Verify max-extract Command Works**
- Description: Run max-extract with --help and test basic execution
- Commands to run:
  ```bash
  uv run tightbeam migrate max-extract --help
  # Verify help displays correctly
  ```
- Dependencies: Phase 3 complete
- Estimated effort: 10 minutes

**Task 6.2: Verify download-attachments Command Works**
- Description: Run download-attachments with --help
- Commands to run:
  ```bash
  uv run tightbeam migrate download-attachments --help
  # Verify help displays correctly
  ```
- Dependencies: Phase 4 complete
- Estimated effort: 10 minutes

**Task 6.3: Verify Deprecated Migrate Subcommands Are Gone**
- Description: Verify removed migrate subcommands don't appear in CLI, but oauth commands remain
- Commands to run:
  ```bash
  uv run tightbeam migrate --help
  # Should only show: max-extract, download-attachments

  uv run tightbeam oauth --help
  # Should still show: login, logout, status, refresh, revoke (unchanged)
  ```
- Dependencies: Phase 2 complete
- Estimated effort: 5 minutes

**Task 6.4: Run Existing Tests**
- Description: Ensure existing tests still pass
- Commands to run:
  ```bash
  uv run pytest tests/cli/services/test_factories.py -v
  # Verify all ServiceFactory tests pass
  ```
- Dependencies: All phases complete
- Estimated effort: 10 minutes

**Task 6.5: Update Tests for New Factory Methods**
- Description: Add tests for new create_logger and create_config_manager methods
- Files to modify: `tests/cli/services/test_factories.py`
- Add test cases:
  - `test_create_logger_default()`
  - `test_create_logger_verbose()`
  - `test_create_config_manager()`
- Dependencies: Tasks 1.1, 1.2
- Estimated effort: 20 minutes

## Codebase Integration Points

### Files to Modify

1. **`src/cli/services/factories.py`**
   - Add `create_logger(verbose: bool = False) -> RichLogger`
   - Add `create_config_manager() -> ConfigManagerImpl`
   - Add imports for RichLogger and ConfigManagerImpl

2. **`src/cli/migrate.py`**
   - Remove deprecated commands (lines 225-1959)
   - Remove deprecated options from migrate_callback
   - Update max-extract command to use new factory methods (lines ~2201-2202)
   - Update download-attachments command to use new factory methods (line ~2030)
   - Clean up unused imports

3. **`scripts/performance_test.py`**
   - Update to use `ServiceFactory.create_logger()` (line 65)
   - Update to use `ServiceFactory.create_config_manager()` (line 64)

4. **`tests/cli/services/test_factories.py`**
   - Add tests for new factory methods

### New Files to Create
None - all changes are modifications to existing files

### Existing Patterns to Follow

**Factory Method Pattern:**
```python
@staticmethod
def create_service_name(...) -> ServiceType:
    """Create ServiceType with description.

    Args:
        param1: Description

    Returns:
        ServiceType: Configured instance
    """
    return ServiceType(...)
```

**Factory Usage Pattern in Commands:**
```python
try:
    repository = ServiceFactory.create_repository(db)
    logger = ServiceFactory.create_logger(verbose=True)
    config_manager = ServiceFactory.create_config_manager()
    auth_provider = ServiceFactory.create_auth_provider(repository, logger)
    # ... use services
except Exception as e:
    console.print(f"❌ Failed: {e}")
```

## Technical Design

### Dependency Injection Flow

```
ServiceFactory
├── create_repository(db) → Repository
├── create_oauth2_manager() → OAuth2Manager
├── create_http_client() → HttpClient
├── create_logger(verbose) → RichLogger
├── create_config_manager() → ConfigManagerImpl
├── create_auth_provider(repository, logger) → AuthProvider
│   └── Uses: create_oauth2_manager()
├── create_entity_mapper() → EntityMapper
└── create_rate_limited_jobber_client(...) → JobberClient
    └── Uses: AuthProvider, Repository, ConfigManager

Commands Use Factory For All Dependencies
├── max-extract
│   ├── create_repository(db)
│   ├── create_logger(verbose=True)
│   ├── create_config_manager()
│   ├── create_auth_provider(repository, logger)
│   ├── create_rate_limited_jobber_client(...)
│   └── create_entity_mapper()
│
└── download-attachments
    ├── create_repository(db)
    └── create_logger(verbose=True)
```

### Before vs After: max-extract Command

**Before:**
```python
from src.config import ConfigManagerImpl
from src.coordinators.max_extract_coordinator import MaxExtractCoordinator

repository = ServiceFactory.create_repository(db)
logger = RichLogger(verbose=True, console=ServiceFactory.get_console())  # Direct
config_manager = ConfigManagerImpl()  # Direct
auth_provider = ServiceFactory.create_auth_provider(repository, logger)
jobber_client = ServiceFactory.create_rate_limited_jobber_client(...)
entity_mapper = ServiceFactory.create_entity_mapper()
```

**After:**
```python
from src.coordinators.max_extract_coordinator import MaxExtractCoordinator

repository = ServiceFactory.create_repository(db)
logger = ServiceFactory.create_logger(verbose=True)  # Factory
config_manager = ServiceFactory.create_config_manager()  # Factory
auth_provider = ServiceFactory.create_auth_provider(repository, logger)
jobber_client = ServiceFactory.create_rate_limited_jobber_client(...)
entity_mapper = ServiceFactory.create_entity_mapper()
```

## Dependencies and Libraries

No new dependencies required. All changes use existing libraries:
- `src.loggers.rich_logger.RichLogger` - Already in use
- `src.config.ConfigManagerImpl` - Already in use

## Testing Strategy

### Unit Tests
- Test `create_logger()` with verbose=True and verbose=False
- Test `create_config_manager()` returns ConfigManagerImpl instance
- Verify logger uses shared console from `get_console()`

### Integration Tests
- Verify max-extract command loads without errors
- Verify download-attachments command loads without errors
- Verify deprecated commands don't appear in CLI help
- Verify deprecated options don't appear in command signatures

### Manual Testing
- Run `uv run tightbeam migrate --help` - Should show only 2 commands
- Run `uv run tightbeam migrate max-extract --help` - Should work
- Run `uv run tightbeam migrate download-attachments --help` - Should work

## Success Criteria

- [ ] All 10 deprecated commands removed from migrate.py
- [ ] All 3 deprecated options removed from migrate_callback
- [ ] ServiceFactory has create_logger() method
- [ ] ServiceFactory has create_config_manager() method
- [ ] max-extract command uses factory for all dependencies
- [ ] download-attachments command uses factory for all dependencies
- [ ] scripts/performance_test.py uses factory for all dependencies
- [ ] CLI help only shows max-extract and download-attachments commands
- [ ] All existing tests pass
- [ ] New tests added for create_logger() and create_config_manager()
- [ ] No direct instantiation of RichLogger or ConfigManagerImpl in commands
- [ ] Code follows consistent dependency injection pattern

## Rollback Plan

If issues are encountered:
1. Git branches allow easy rollback: `git checkout HEAD~1`
2. Each phase is independent - can revert specific commits
3. Tests validate each change before proceeding

## Notes and Considerations

### Why Remove These Commands?
All removed commands are legacy implementations that have been superseded by the two-pass ETL architecture:
- **Pass 1**: `max-extract` - Extracts all metadata including attachment URLs
- **Pass 2**: `download-attachments` - Downloads binary files based on collected metadata

The old commands (map, extract, reconcile, etc.) were part of earlier iterations and are no longer needed.

### Why Factory Pattern for Everything?
Benefits:
1. **Testability**: Easy to mock dependencies via factory
2. **Consistency**: All dependencies created the same way
3. **Maintainability**: Changes to service creation centralized
4. **Discoverability**: All available services in one place

### Potential Challenges
- Existing tests may mock old command signatures - these will need updates
- Any external scripts using deprecated commands will break (intended)
- Performance test script needs careful testing after refactor

### Future Enhancements
After this refactor, consider:
- Add factory methods for coordinators if they become shared
- Add factory method for AttachmentDownloader if needed elsewhere
- Document ServiceFactory API for contributors

---
*This plan is ready for execution with `/execute-plan PRPs/service-factory-refactor-and-cli-cleanup.md`*
