# Implementation Plan: Database Filename Consistency Fix

## Overview
Fix database filename inconsistencies across the codebase. Currently, different components use different default database filenames:
- OAuth commands default to `tightbeam.sqlite`
- Max-extract and download-attachments commands default to `jobber_export.db`
- Config file specifies `tightbeam.sqlite` as `database.default_path`
- Constants file specifies `tightbeam.db`

This plan establishes a consistent hierarchy: Environment variable → Config file → Default fallback (`tightbeam.sqlite`)

## Requirements Summary
- Centralize database path resolution in a single location (ServiceFactory/SharedServices)
- Support environment variable override (e.g., `TIGHTBEAM_DB`)
- Fall back to config file value (`config/settings.yaml` → `database.default_path`)
- Final fallback to `tightbeam.sqlite` throughout the codebase
- Update all CLI commands to use the centralized resolution
- Ensure OAuth operations and migration operations use the same database by default

## Research Findings

### Current Database References
**Files with inconsistencies:**
1. `src/cli/oauth.py:336,417` - Uses `tightbeam.sqlite` as default
2. `src/cli/migrate.py:130,156,321` - Uses `jobber_export.db` for max-extract and download-attachments
3. `src/constants.py:48` - Defines `DEFAULT_DB_PATH = "tightbeam.db"` (without .sqlite extension)
4. `src/cli/services/shared.py:24` - Defines `DEFAULT_DB_PATH = Path("tightbeam.sqlite")`
5. `config/settings.yaml:48` - Defines `database.default_path: tightbeam.sqlite`

### Existing Architecture Patterns
- `ServiceFactory` in `src/cli/services/factories.py` - Factory pattern for creating services
- `SharedServices` in `src/cli/services/shared.py` - Shared utilities with `resolve_db_path()` method
- `ConfigManagerImpl` in `src/config/config_manager.py` - Manages YAML configuration with `get_database_config()`
- All services are created through `ServiceFactory` methods

### Current Resolution Logic
`SharedServices.resolve_db_path(db)` currently:
1. Takes optional `db` parameter
2. Returns `db` if provided, otherwise `cls.DEFAULT_DB_PATH`
3. Does NOT check environment variables or config file

## Implementation Tasks

### Phase 1: Environment Variable and Config Integration

**Task 1.1: Add environment variable support to SharedServices**
- Description: Enhance `SharedServices.resolve_db_path()` to check environment variable first
- Files to modify:
  - `src/cli/services/shared.py` - Update `resolve_db_path()` method
- Implementation:
  ```python
  @classmethod
  def resolve_db_path(cls, db: Optional[Path] = None) -> Path:
      """Resolve database path with environment variable and config fallback.

      Resolution order:
      1. Explicit db parameter (if provided)
      2. TIGHTBEAM_DB environment variable
      3. Config file database.default_path
      4. Hardcoded DEFAULT_DB_PATH fallback
      """
      if db is not None:
          return db

      # Check environment variable
      env_db = os.environ.get("TIGHTBEAM_DB")
      if env_db:
          return Path(env_db)

      # Check config file
      try:
          from src.config import ConfigManagerImpl
          config_manager = ConfigManagerImpl()
          db_config = config_manager.get_database_config()
          return Path(db_config["default_path"])
      except Exception:
          # Fall back to hardcoded default if config loading fails
          pass

      return cls.DEFAULT_DB_PATH
  ```
- Dependencies: None
- Estimated effort: 30 minutes

**Task 1.2: Update constants to match config file**
- Description: Change `DEFAULT_DB_PATH` in constants.py from `tightbeam.db` to `tightbeam.sqlite`
- Files to modify:
  - `src/constants.py` - Line 48: `DEFAULT_DB_PATH = "tightbeam.sqlite"`
- Dependencies: None
- Estimated effort: 5 minutes

### Phase 2: Update CLI Commands

**Task 2.1: Remove hardcoded defaults from migrate.py**
- Description: Remove `jobber_export.db` defaults from max-extract and download-attachments commands
- Files to modify:
  - `src/cli/migrate.py:130` - Change callback default from `Path("tightbeam.sqlite")` to use resolved path
  - `src/cli/migrate.py:156` - Remove `= Path("jobber_export.db")` default, use resolved path
  - `src/cli/migrate.py:321` - Remove `= Path("jobber_export.db")` default, use resolved path
- Implementation approach:
  - In `migrate_callback()`, store resolved path in context: `ctx.obj["db"] = SharedServices.resolve_db_path(db)`
  - In command functions, use: `db = db or SharedServices.resolve_db_path(None)`
  - Or make db required from context
- Dependencies: Task 1.1
- Estimated effort: 45 minutes

**Task 2.2: Update oauth.py to use SharedServices**
- Description: Remove hardcoded `"tightbeam.sqlite"` strings and use `SharedServices.resolve_db_path()`
- Files to modify:
  - `src/cli/oauth.py:336` - Replace `str(db) if db is not None else "tightbeam.sqlite"`
  - `src/cli/oauth.py:417` - Replace `str(db) if db is not None else "tightbeam.sqlite"`
- Implementation:
  ```python
  db_path_used = str(db if db is not None else SharedServices.get_default_db_path())
  ```
- Dependencies: Task 1.1
- Estimated effort: 15 minutes

**Task 2.3: Update oauth_utils.py display function**
- Description: Update `display_oauth_success()` to use resolved path
- Files to modify:
  - `src/utils/oauth_utils.py:189` - Replace `"tightbeam.sqlite"` with resolved default
- Implementation:
  ```python
  from ..cli.services import SharedServices
  db_display = db_path if db_path else str(SharedServices.get_default_db_path())
  ```
- Dependencies: Task 1.1
- Estimated effort: 10 minutes

### Phase 3: Update Scripts and Documentation

**Task 3.1: Update scripts to use environment variable**
- Description: Update standalone scripts to support TIGHTBEAM_DB environment variable
- Files to modify:
  - `scripts/validate_extraction.py` - Add env var support for db path
  - `scripts/performance_test.py` - Add env var support for db path
  - `scripts/explore_jobber_api.py:18` - Change default from `tightbeam.db` to `tightbeam.sqlite`
- Implementation pattern for each script:
  ```python
  import os
  default_db = os.environ.get("TIGHTBEAM_DB", "tightbeam.sqlite")
  ```
- Dependencies: Task 1.2
- Estimated effort: 30 minutes

**Task 3.2: Update documentation**
- Description: Update documentation to reflect new database path resolution
- Files to modify:
  - `docs/max_extract_guide.md` - Update references to database paths
  - `docs/TROUBLESHOOTING.md` - Add TIGHTBEAM_DB environment variable documentation
  - `README.md` - Update examples to use consistent database filename
- Add section about TIGHTBEAM_DB environment variable:
  ```markdown
  ### Database Configuration

  TightBeam uses the following precedence for database file location:
  1. Explicit `--db` parameter
  2. `TIGHTBEAM_DB` environment variable
  3. `database.default_path` in `config/settings.yaml`
  4. Default: `tightbeam.sqlite`

  Example:
  ```bash
  export TIGHTBEAM_DB=/path/to/my-database.db
  tightbeam oauth init  # Uses /path/to/my-database.db
  tightbeam migrate max-extract  # Uses same database
  ```
  ```
- Dependencies: All Phase 1 and Phase 2 tasks
- Estimated effort: 45 minutes

### Phase 4: Testing and Validation

**Task 4.1: Create unit tests**
- Description: Add tests for database path resolution logic
- Files to create:
  - `tests/cli/services/test_shared_services.py` - Test `resolve_db_path()` with various scenarios
- Test scenarios:
  1. Explicit db parameter provided → returns that path
  2. Environment variable set → returns env var path
  3. Config file available → returns config path
  4. Fallback → returns DEFAULT_DB_PATH
  5. Precedence: explicit > env > config > default
- Dependencies: Tasks 1.1, 1.2
- Estimated effort: 1 hour

**Task 4.2: Integration testing**
- Description: Manually test all CLI commands with different database configurations
- Test cases:
  1. Run `oauth init` without any config → uses `tightbeam.sqlite`
  2. Set `TIGHTBEAM_DB=custom.db` → both oauth and migrate use `custom.db`
  3. Use `--db` flag → overrides everything
  4. Modify config file → uses config value
  5. Run max-extract after oauth init → same database used
- Dependencies: All Phase 2 and Phase 3 tasks
- Estimated effort: 1 hour

**Task 4.3: Update existing tests**
- Description: Update existing tests that may hardcode database paths
- Files to review:
  - `tests/cli/test_cli_download_command.py`
  - `tests/cli/test_cli_integration.py`
  - `tests/cli/services/test_factories.py`
- Ensure tests use temporary databases and don't rely on specific filenames
- Dependencies: Task 4.1
- Estimated effort: 30 minutes

## Codebase Integration Points

### Files to Modify
1. **src/cli/services/shared.py** - Core database path resolution logic
   - Add `import os`
   - Import ConfigManagerImpl conditionally
   - Enhance `resolve_db_path()` method

2. **src/constants.py** - Fix default database path constant
   - Change `DEFAULT_DB_PATH` from `"tightbeam.db"` to `"tightbeam.sqlite"`

3. **src/cli/migrate.py** - Remove hardcoded `jobber_export.db` defaults
   - Lines 130, 156, 321: Remove hardcoded defaults
   - Use `SharedServices.resolve_db_path()`

4. **src/cli/oauth.py** - Remove hardcoded `tightbeam.sqlite` strings
   - Lines 336, 417: Use `SharedServices.get_default_db_path()`

5. **src/utils/oauth_utils.py** - Update success display
   - Line 189: Use `SharedServices.get_default_db_path()`

6. **scripts/*.py** - Add environment variable support
   - `validate_extraction.py`, `performance_test.py`, `explore_jobber_api.py`
   - Add `TIGHTBEAM_DB` environment variable check

### New Files to Create
- **tests/cli/services/test_shared_services.py** - Unit tests for path resolution

### Existing Patterns to Follow
1. **ServiceFactory pattern**: All service creation goes through `ServiceFactory`
2. **SharedServices pattern**: Utility functions in `SharedServices` class methods
3. **Config-driven**: Use `ConfigManagerImpl` for configuration access
4. **Environment variable naming**: Follow pattern `JOBBER_*` for Jobber-specific, `TIGHTBEAM_*` for app-specific
5. **Path handling**: Use `pathlib.Path` for all file paths

## Technical Design

### Database Path Resolution Flow
```
┌─────────────────────────────────────────────┐
│  CLI Command (oauth/migrate)                │
│  Calls: ServiceFactory.create_repository(db)│
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│  ServiceFactory.create_repository()         │
│  Calls: SharedServices.resolve_db_path(db)  │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│  SharedServices.resolve_db_path(db)         │
│                                             │
│  1. If db parameter provided → return db    │
│  2. Check TIGHTBEAM_DB env var → return if set│
│  3. Load config file → return default_path  │
│  4. Return DEFAULT_DB_PATH fallback         │
└─────────────────────────────────────────────┘
```

### Environment Variable
- **Name**: `TIGHTBEAM_DB`
- **Format**: Absolute or relative path to SQLite database file
- **Example**: `export TIGHTBEAM_DB=/var/lib/tightbeam/production.db`
- **Scope**: Application-level (applies to all commands)

### Configuration Hierarchy
1. **Explicit parameter** (highest priority): `--db /path/to/db.sqlite`
2. **Environment variable**: `TIGHTBEAM_DB=/path/to/db.sqlite`
3. **Config file**: `config/settings.yaml` → `database.default_path: tightbeam.sqlite`
4. **Hardcoded fallback** (lowest priority): `tightbeam.sqlite`

## Success Criteria
- [ ] All CLI commands use the same default database filename
- [ ] `TIGHTBEAM_DB` environment variable is respected by all commands
- [ ] Config file `database.default_path` is used when no env var is set
- [ ] OAuth operations and migration operations share the same database by default
- [ ] No hardcoded database filenames in CLI commands (except fallback constant)
- [ ] All existing functionality continues to work
- [ ] Unit tests pass for path resolution logic
- [ ] Documentation updated to reflect new behavior
- [ ] Scripts updated to support environment variable

## Notes and Considerations

### Backwards Compatibility
- Existing scripts/workflows using `--db` parameter will continue to work unchanged
- Users currently relying on `jobber_export.db` default for max-extract will need to:
  - Set `TIGHTBEAM_DB=jobber_export.db`, OR
  - Update config file, OR
  - Use `--db jobber_export.db` explicitly
- Consider adding a migration guide in release notes

### Config Loading Performance
- Loading `ConfigManagerImpl` in `resolve_db_path()` could add overhead
- Mitigated by:
  - ConfigManagerImpl is a singleton (only one instance created)
  - Config loading is cached
  - Fallback to default if config loading fails (graceful degradation)

### Error Handling
- If config file is missing or invalid, fall back gracefully to hardcoded default
- Log warnings if environment variable points to non-existent directory
- No breaking changes if config system fails

### Future Enhancements
- Consider adding `tightbeam config show` command to display resolved database path
- Add validation to check if database file is readable/writable
- Support database connection strings for future database backends

---
*This plan is ready for execution with `/execute-plan`*
