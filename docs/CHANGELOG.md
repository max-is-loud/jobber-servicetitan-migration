# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-11-29

### Added
- Unified `MigrationUI` class for consistent Rich-based CLI output across all commands
- Real-time progress bars for all entity extraction operations with live updates
- Styled error panels and success messages with Rich components
- Comprehensive summary tables displaying migration metrics and statistics
- Full-screen multi-progress display for parallel attachment downloads

### Changed
- `MaxExtractCoordinator` now uses `MigrationUI` for all user-facing terminal output
- Attachment downloads integrated with unified UI layer replacing standalone `MultiProgressDisplay`
- OAuth commands standardized with Rich panels and status displays for consistency
- Separation of concerns: `RichLogger` handles file logging, `MigrationUI` handles terminal output

### Removed
- **BREAKING**: Legacy multi-pass extraction workflow coordinators (already deprecated)
- **BREAKING**: Map-mode coordinators and extractors (`MapModeCoordinator`, all map-mode entity extractors)
- **BREAKING**: Snapshot and queue-based extraction models (`MapSnapshot`, `EntityInventory`, `ExtractQueueItem`, `AttachmentQueueItem`)
- **BREAKING**: Legacy report generators (`MapReportGenerator`, `DownloadReportGenerator`, `ReportGenerator`, `ExtractReportGenerator`)
- `BaseMigrationCoordinator` - consolidated into `MaxExtractCoordinator`
- `RichMigrationCoordinator` - functionality merged into `MigrationUI`
- `DownloadModeCoordinator` and `ExtractModeCoordinator` - no longer needed
- Entire `src/extractors/map_mode/` directory (14 map-mode extractor files)
- Unused CLI service helpers (`entity_extraction.py`, `error_handling.py`) that were made redundant by new architecture

### Migration Guide

**For End Users:**
- No action required - all existing commands (`max-extract`, `download-attachments`, `oauth`) continue to work with improved Rich UI
- Database schema remains unchanged - existing databases are fully compatible
- Enjoy the improved visual feedback and progress tracking

**For Developers with Custom Scripts:**
- If importing removed coordinators (`BaseMigrationCoordinator`, `RichMigrationCoordinator`, `MapModeCoordinator`):
  - Update to use `MaxExtractCoordinator` directly
  - Pass optional `MigrationUI` instance for custom UI behavior

- If importing removed models (`MapSnapshot`, `EntityInventory`, queue items):
  - These were internal implementation details - use repository methods instead
  - Migration state tracking continues via `repository.get_migration_state()`
  - **WARNING**: The following repository methods are deprecated and will fail:
    - `save_map_snapshot()`, `get_map_snapshot()`, `list_map_snapshots()`
    - `save_entity_inventory()`, `get_entity_inventory()`
    - Model classes are deleted, so imports will fail with `ImportError`
    - Use `repository.get_migration_state()` for state tracking instead

- If using removed report generators:
  - Summary data now available via `MigrationSummary` model
  - UI output handled automatically by `MigrationUI`

**Example Migration:**
```python
# Before:
from src.coordinators.rich_migration_coordinator import RichMigrationCoordinator
coordinator = RichMigrationCoordinator(...)

# After:
from src.coordinators.max_extract_coordinator import MaxExtractCoordinator
from src.ui.migration_ui import MigrationUI
from src.cli.services.shared import SharedServices

console = SharedServices.get_console()
migration_ui = MigrationUI(console)
coordinator = MaxExtractCoordinator(..., migration_ui=migration_ui)
```

## [0.2.0] - 2025-01-21

### Added
- Multi-pass extraction system for comprehensive data migration
- Map mode query validation for all entity types
- Relation tracking for expenses and visits map extractors
- Multi-pass migration documentation

### Changed
- Project name updated to "Project Tightbeam"
- Disabled adaptive config persistence for map mode
- Updated migration CLI with multi-pass support

## [0.1.3] - 2024-11-17

### Added
- Comprehensive release process documentation (RELEASING.md)
- Pre-release checklists and troubleshooting guide
- Automated version bumping considerations

### Changed
- Version management now uses single source of truth (pyproject.toml)
- `src/constants.py` reads version from package metadata via `importlib.metadata`

### Added
- ServiceFactory pattern for centralized rate limiting setup
- Comprehensive unit tests for ServiceFactory (13 test cases, 77% coverage)
- Unit tests for constants module (95% coverage)
- Architecture analysis documentation for rate limiting and notes optimization
- `.gitignore` improvements for UV package manager and migration artifacts

### Changed
- Refactored `src/cli/migrate.py` to use ServiceFactory (reduced 32 lines to 8)
- Refactored `src/cli/services/entity_extraction.py` to use ServiceFactory (reduced 28 lines to 8)
- Moved architecture documentation to `docs/architecture/` directory
- Updated README.md with UV installation instructions
- Migrated from Poetry to UV package manager

### Fixed
- PEP 8 violation: moved ServiceFactory import to top of file
- `.gitignore` patterns now use `/` prefix for root-only matching
- Removed invalid bulk notes fetching code

### Security
- Verified no secrets in git history
- Enhanced `.gitignore` to prevent accidental credential commits

### Documentation
- Created `docs/architecture/README.md` for architecture documentation organization
- Created `docs/architecture/rate-limiting.md` (459 lines) - comprehensive rate limiting analysis
- Created `docs/architecture/notes-optimization.md` (279 lines) - GraphQL query cost optimization analysis

## [0.1.2] - 2024-11-XX

### Changed
- Adjusted invoice pagination limit in settings.yaml
- Refactored migration coordinator architecture
- Updated database path and enhanced migration functionality

### Fixed
- Various OAuth utility improvements
- Migration coordinator dry-pass functionality

## [0.1.1] - 2024-XX-XX

### Added
- Initial OAuth2 authentication flow
- Basic migration coordinator
- Rich-based CLI interface
- SQLite persistence layer

### Changed
- Enhanced error handling and logging

## [0.1.0] - 2024-XX-XX

### Added
- Initial project structure
- Jobber GraphQL client implementation
- Entity mappers for clients and invoices
- Basic CLI commands (oauth, migrate)
- Rate limiting with token bucket algorithm
- Dependency injection architecture

---

## Release Notes Format

Each release should include:

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Now removed features
- **Fixed**: Bug fixes
- **Security**: Security fixes

Links to releases:
- https://github.com/max-is-loud/tightbeam-v2/releases
