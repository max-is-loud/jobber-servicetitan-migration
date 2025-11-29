# Implementation Plan: Tightbeam-v2 Rich UI Consolidation

## Overview
Consolidate all migration coordinators into a unified MaxExtractCoordinator-based architecture with consistent Rich UI presentation layer. Remove legacy multi-pass extraction, map-mode coordinators, and snapshot/queue logic, replacing fragmented UI output with a structured MigrationUI class.

## Requirements Summary
- Create unified `MigrationUI` class for consistent Rich-based CLI output
- Integrate MigrationUI into MaxExtractCoordinator as the primary UI layer
- Standardize all CLI commands (migrate, oauth) to use Rich components
- Remove unused coordinators: BaseMigrationCoordinator, RichMigrationCoordinator, MapModeCoordinator, DownloadModeCoordinator, ExtractModeCoordinator
- Delete map-mode extractors (entire `src/extractors/map_mode/` directory)
- Remove snapshot/queue models: MapSnapshot, EntityInventory, ExtractQueueItem, AttachmentQueueItem
- Delete old report generators: MapReportGenerator, DownloadReportGenerator, ReportGenerator
- Clean up unused CLI service helpers: entity_extraction.py, error_handling.py
- Update documentation to remove references to deprecated features

## Research Findings

### Best Practices (from codebase analysis)

**Rich UI Patterns:**
- Single shared Console instance via `SharedServices.get_console()`
- Progress displays use `Live` context managers for real-time updates
- Error panels provide consistent styling (red=error, yellow=warning, blue=info)
- Status spinners use `Status` context manager with "dots" spinner
- Summary tables use `Table` with styled columns and borders

**Coordinator Patterns:**
- Dependency injection via constructor parameters
- Lazy-loaded extractors built in `_build_extractors()` method
- Entity extraction follows dependency order defined in `ENTITY_ORDER`
- Progress tracking uses `migration_state` from repository
- Resume capability via checkpoint-based extraction in each extractor

**Attachment Download Patterns:**
- Worker threads create progress tasks on-demand (not upfront for 30k files)
- Workers update progress via callback functions
- Workers hide tasks immediately on completion
- Main thread handles all database writes (SQLite thread-safety requirement)
- MultiProgressDisplay uses Live layout with log buffer (top 75%) and progress bars (bottom 25%)

**Separation of Concerns:**
- `RichLogger` handles structured logging to files
- UI layer (MigrationUI) handles user-facing terminal output
- No mixing of print() statements - all output via Rich console
- ServiceFactory provides dependency injection for shared services

### Reference Implementations

**MultiProgressDisplay Pattern:**
- File: `src/ui/multi_progress_display.py`
- Full-screen takeover with split layout (logs + progress bars)
- 30Hz refresh rate for smooth visual updates
- Automatic task hiding when completed
- Unlimited log buffer with scroll capability

**MaxExtractCoordinator Structure:**
- File: `src/coordinators/max_extract_coordinator.py`
- ENTITY_ORDER defines dependency-based extraction sequence
- Each extractor is self-contained with own pagination logic
- Returns aggregated results dictionary with counts per entity
- Uses migration_state for progress tracking and resume capability

**OAuth UI Pattern:**
- File: `src/cli/oauth.py`
- Status spinners for long operations
- Success panels with styled borders and emojis
- Status tables showing component states
- Clear next-step instructions in panel content

### Technology Decisions

**Rich Library (already in use):**
- Purpose: Terminal UI with colors, progress bars, panels, tables
- Rationale: Already integrated, provides consistent UX, mature and well-documented
- Components to use: Console, Progress, Panel, Table, Live, Status

**SharedServices Pattern (already in use):**
- Purpose: Singleton-like access to console and database path resolution
- Rationale: Prevents multiple Console instances which can conflict
- Usage: `console = SharedServices.get_console()`

**MigrationSummary Model (already exists):**
- Purpose: Structured data for migration results
- Fields: entities_processed counts, duration, errors, skip statistics
- Methods: `format_duration()`, `format_summary()`, `get_total_entities()`
- Rationale: Already used, comprehensive metrics tracking

**ApiMetrics (to be added):**
- Purpose: Track API request counts, rate limiting, errors
- Rationale: Mentioned in PRD but not yet implemented - use dict fallback for now
- Future: Create proper model when API metrics tracking is added

## Implementation Tasks

### Phase 1: Foundation - Create MigrationUI

#### Task 1: Create MigrationUI class
- **Description**: Create `src/ui/migration_ui.py` with unified UI methods
- **Files to create**:
  - `src/ui/migration_ui.py`
- **Dependencies**: None
- **Estimated effort**: 2-3 hours

**Implementation details:**
```python
class MigrationUI:
    """Unified Rich UI for migration operations."""

    def __init__(self, console: Console):
        """Initialize with shared console from SharedServices."""
        self._console = console
        self._progress: Optional[Progress] = None
        self._live: Optional[Live] = None
        self._entity_tasks: dict[str, TaskID] = {}

    def show_run_header(self, db_path: str, config: Optional[dict] = None):
        """Display migration run header panel."""

    def start_entity_progress(self, entity_names: list[str]) -> Progress:
        """Create and start progress display with Live context."""

    def update_entity_progress(self, entity: str, completed: int, total: int | None):
        """Update progress for specific entity."""

    def show_run_summary(self, summary: MigrationSummary, metrics: Optional[dict] = None):
        """Display final summary table with metrics."""

    def show_error(self, exc: Exception):
        """Display error panel with traceback."""

    def show_keyboard_interrupt(self):
        """Display keyboard interrupt message."""

    def finalize(self):
        """Clean up Live display and progress bars."""
```

**Pattern to follow**: Based on `MultiProgressDisplay` and `BaseMigrationCoordinator` patterns:
- Use `Live` context manager for real-time updates
- Progress bars with standard columns: Spinner, Description, Bar, MofN, Speed, Time
- Store entity task IDs in dict for lookup during updates
- Error panels with styled borders (red for errors)
- Console.print_exception() for traceback display

#### Task 2: Add unit tests for MigrationUI
- **Description**: Create test suite for MigrationUI methods
- **Files to create**:
  - `tests/unit/test_migration_ui.py`
- **Dependencies**: Task 1
- **Estimated effort**: 1-2 hours

**Test coverage:**
- Mock Console to verify print/display calls
- Test progress bar creation and updates
- Verify panel styling and content
- Test error display with mock exceptions
- Verify finalize cleanup behavior

### Phase 2: Integration - MaxExtractCoordinator

#### Task 3: Integrate MigrationUI into MaxExtractCoordinator
- **Description**: Add MigrationUI parameter and wrap extraction flow with UI methods
- **Files to modify**:
  - `src/coordinators/max_extract_coordinator.py`
- **Dependencies**: Task 1
- **Estimated effort**: 2-3 hours

**Changes required:**
1. Add `migration_ui: Optional[MigrationUI] = None` parameter to `__init__`
2. Create MigrationUI instance if not provided
3. Update `extract_all()` method to use MigrationUI:
   - Call `show_run_header()` at start
   - Call `start_entity_progress()` before entity loop
   - Call `update_entity_progress()` for each entity extraction
   - Call `show_run_summary()` on success
   - Call `show_error()` on exception
   - Call `finalize()` in finally block

**Pattern:**
```python
def extract_all(self, entities: Optional[List[str]] = None, resume: bool = False):
    """Extract entities with MigrationUI display."""
    # Show header
    self._migration_ui.show_run_header(
        db_path=str(self._repository.db_path),
        config=None  # No config manager currently
    )

    # Start progress
    progress = self._migration_ui.start_entity_progress(ordered_entities)

    try:
        # Extract each entity
        for entity_type in ordered_entities:
            # Get total from migration_state
            state = self._repository.get_migration_state(entity_type)
            total = state.total_count if state else None

            # Update progress (start)
            self._migration_ui.update_entity_progress(entity_type, 0, total)

            # Extract
            extractor = self._extractors[entity_type]
            extractor.extract_all(resume=resume)

            # Update progress (complete)
            state = self._repository.get_migration_state(entity_type)
            count = state.total_fetched if state else 0
            self._migration_ui.update_entity_progress(entity_type, count, total)

        # Show summary
        summary = self._build_summary(results)
        self._migration_ui.show_run_summary(summary, metrics=None)

    except Exception as e:
        self._migration_ui.show_error(e)
        raise
    finally:
        self._migration_ui.finalize()
```

#### Task 4: Update CLI migrate command to use MigrationUI
- **Description**: Modify `max-extract` command to pass MigrationUI to coordinator
- **Files to modify**:
  - `src/cli/migrate.py` (max_extract function)
- **Dependencies**: Task 3
- **Estimated effort**: 1 hour

**Changes:**
```python
@migrate_app.command(name="max-extract")
def max_extract(db: Optional[Path] = None, verbose: bool = False):
    """Extract entities with unified Rich UI."""
    console = SharedServices.get_console()

    # Create services
    logger = ServiceFactory.create_logger(verbose=verbose)
    repository = ServiceFactory.create_repository(db)

    # Create MigrationUI
    migration_ui = MigrationUI(console)

    # Create coordinator with UI
    coordinator = MaxExtractCoordinator(
        jobber_client=jobber_client,
        repository=repository,
        logger=logger,
        entity_mapper=entity_mapper,
        migration_ui=migration_ui  # Pass UI instance
    )

    # Extract (UI handled inside coordinator)
    coordinator.extract_all(resume=True)
```

### Phase 3: Attachment Download UX

#### Task 5: Create DownloadUI class for attachment downloads
- **Description**: Create specialized UI for parallel attachment downloads (or extend MigrationUI)
- **Files to modify/create**:
  - `src/ui/migration_ui.py` (add download methods) OR
  - `src/ui/download_ui.py` (new specialized class)
- **Dependencies**: Task 1
- **Estimated effort**: 2-3 hours

**Decision point**: Extend MigrationUI vs separate DownloadUI
- **Recommendation**: Add download methods to MigrationUI to keep unified interface
- Methods to add:
  - `start_download_progress(total_files: int, total_bytes: int)`
  - `add_download_task(filename: str, file_size: int) -> TaskID`
  - `update_download_task(task_id: TaskID, bytes_downloaded: int)`
  - `complete_download_task(task_id: TaskID, filename: str)`
  - `show_download_summary(total_files: int, total_bytes: int, duration: float, failures: int)`

**Pattern from MultiProgressDisplay:**
- Full-screen layout with logs (top 75%) and progress bars (bottom 25%)
- Individual task progress bars created on-demand in worker threads
- Automatic hiding of completed tasks
- Summary table at end with totals

#### Task 6: Integrate DownloadUI into download-attachments command
- **Description**: Replace MultiProgressDisplay with MigrationUI in attachment download flow
- **Files to modify**:
  - `src/cli/migrate.py` (download_attachments function)
- **Dependencies**: Task 5
- **Estimated effort**: 2-3 hours

**Changes:**
1. Replace `MultiProgressDisplay` instantiation with `MigrationUI`
2. Update worker function to use new download methods
3. Add summary table display after downloads complete
4. Handle keyboard interrupt with MigrationUI method

**Pattern:**
```python
def download_worker(attachment, migration_ui, _task_id):
    """Worker thread for parallel downloads."""
    task_name = Path(attachment["file_path"]).name
    file_size = attachment.get("file_size", 0)

    # Create task on-demand
    task_id = migration_ui.add_download_task(task_name, file_size)

    def progress_callback(bytes_chunk: int):
        migration_ui.update_download_task(task_id, bytes_chunk)

    # Download with progress
    result = downloader.download_attachment(attachment, progress_callback)

    # Hide task when done
    migration_ui.complete_download_task(task_id, task_name)
    return result
```

### Phase 4: OAuth UX Standardization

#### Task 7: Standardize OAuth commands with Rich UI
- **Description**: Update all OAuth commands to use consistent Rich panels and status displays
- **Files to modify**:
  - `src/cli/oauth.py` (all commands)
- **Dependencies**: Task 1 (MigrationUI exists as pattern reference)
- **Estimated effort**: 1-2 hours

**Changes:**
- Ensure all commands use `SharedServices.get_console()`
- Replace any print() calls with console.print()
- Use Status spinners for long operations
- Use Panel for success/error messages with styled borders
- Use Table for status display (oauth status command)

**Pattern already mostly implemented** - verify consistency:
```python
# Status spinner
with Status("[bold green]Fetching token...", console=console, spinner="dots"):
    token = auth_provider.get_token()

# Success panel
console.print(Panel(
    success_content,
    title="✅ OAuth Complete",
    border_style="green"
))

# Status table
table = Table(title="🔍 Authentication Status")
table.add_column("Component", style="dim", width=20)
table.add_column("Status", justify="left")
console.print(table)
```

### Phase 5: Validation

#### Task 8: Test max-extract with new MigrationUI
- **Description**: End-to-end testing of max-extract command with unified UI
- **Files to test**: N/A (manual testing)
- **Dependencies**: Tasks 3, 4
- **Estimated effort**: 1 hour

**Test cases:**
1. Fresh extraction (no resume) - verify header, progress bars, summary
2. Resume extraction - verify progress pickup from checkpoint
3. Error scenario (API failure) - verify error panel display
4. Keyboard interrupt (Ctrl+C) - verify graceful shutdown message
5. Empty database - verify initialization and first-time extraction

#### Task 9: Test download-attachments with DownloadUI
- **Description**: End-to-end testing of attachment downloads with new UI
- **Files to test**: N/A (manual testing)
- **Dependencies**: Tasks 5, 6
- **Estimated effort**: 1 hour

**Test cases:**
1. Parallel downloads (3-5 workers) - verify progress bars appear/disappear
2. Large file download - verify progress percentage updates
3. Download failures - verify error handling and retry
4. Empty attachment list - verify graceful no-op
5. Resume download - verify skip of already-downloaded files

#### Task 10: Test OAuth commands
- **Description**: Verify all OAuth commands use consistent Rich UI
- **Files to test**: N/A (manual testing)
- **Dependencies**: Task 7
- **Estimated effort**: 30 minutes

**Test cases:**
1. oauth init - verify panel displays and status spinners
2. oauth status - verify table display with styled columns
3. oauth revoke - verify confirmation and success panel
4. oauth refresh - verify status spinner and success message

### Phase 6: Code Removal

#### Task 11: Remove unused coordinators
- **Description**: Delete legacy coordinator files no longer needed
- **Files to delete**:
  - `src/coordinators/base_migration_coordinator.py`
  - `src/coordinators/rich_migration_coordinator.py`
  - `src/coordinators/map_mode_coordinator.py`
  - `src/coordinators/download_mode_coordinator.py`
  - `src/coordinators/extract_mode_coordinator.py`
- **Dependencies**: Tasks 8, 9, 10 (validation complete)
- **Estimated effort**: 30 minutes

**Verification before deletion:**
1. Search for imports: `grep -r "from.*coordinators import.*" src/`
2. Verify only MaxExtractCoordinator is imported
3. Check CLI commands don't reference deleted coordinators

#### Task 12: Delete map-mode extractors
- **Description**: Remove entire map-mode extractor directory
- **Files to delete**:
  - `src/extractors/map_mode/` (entire directory including `__init__.py`)
- **Dependencies**: Task 11
- **Estimated effort**: 15 minutes

**Files to be deleted:**
- base_map_extractor.py
- clients_map_extractor.py
- expenses_map_extractor.py
- invoices_map_extractor.py
- jobs_map_extractor.py
- products_services_map_extractor.py
- properties_map_extractor.py
- quotes_map_extractor.py
- requests_map_extractor.py
- tax_rates_map_extractor.py
- timesheet_entries_map_extractor.py
- users_map_extractor.py
- visits_map_extractor.py

**Verification:**
```bash
# Check for imports
grep -r "map_mode" src/
grep -r "MapExtractor" src/
```

#### Task 13: Remove snapshot and queue models
- **Description**: Delete snapshot/queue model files
- **Files to delete**:
  - `src/models/map_snapshot.py`
  - `src/models/entity_inventory.py`
  - `src/models/extract_queue_item.py`
  - `src/models/attachment_queue_item.py`
- **Dependencies**: Task 12
- **Estimated effort**: 30 minutes

**Additional cleanup:**
1. Check `src/models/__init__.py` for exports - remove deleted models
2. Search repository methods that use these models
3. Remove repository methods for snapshot/queue operations
4. Drop corresponding database tables in schema (if safe)

**Verification:**
```bash
# Check for usage
grep -r "MapSnapshot" src/
grep -r "EntityInventory" src/
grep -r "ExtractQueueItem" src/
grep -r "AttachmentQueueItem" src/
```

#### Task 14: Delete old report generators
- **Description**: Remove legacy report generator files
- **Files to delete**:
  - `src/reports/map_report_generator.py`
  - `src/reports/download_report_generator.py`
  - `src/reports/report_generator.py`
  - `src/reports/extract_report_generator.py` (if exists)
- **Dependencies**: Task 13
- **Estimated effort**: 30 minutes

**Keep:**
- `src/reports/__init__.py` (may be empty or removed if no reports remain)

**Verification:**
```bash
# Check for imports
grep -r "ReportGenerator" src/
grep -r "from.*reports import" src/
```

#### Task 15: Remove unused CLI service helpers
- **Description**: Delete CLI service files if they're completely unused
- **Files to check and potentially delete**:
  - `src/cli/services/entity_extraction.py`
  - `src/cli/services/error_handling.py`
- **Dependencies**: Task 14
- **Estimated effort**: 30 minutes

**Verification steps:**
1. Search for imports of these modules
2. If unused, delete files
3. If partially used, refactor usage into MigrationUI or remove dependency
4. Update `src/cli/services/__init__.py` to remove deleted exports

**Keep:**
- `src/cli/services/shared.py` (SharedServices - critical)
- `src/cli/services/factories.py` (ServiceFactory - critical)

### Phase 7: Import and Reference Cleanup

#### Task 16: Fix broken imports
- **Description**: Update all imports referencing deleted modules
- **Files to check**: All Python files in `src/`
- **Dependencies**: Tasks 11-15
- **Estimated effort**: 1-2 hours

**Search patterns:**
```bash
# Find all imports that might be broken
grep -r "from.*coordinators.*import.*BaseMigrationCoordinator" src/
grep -r "from.*coordinators.*import.*RichMigrationCoordinator" src/
grep -r "from.*coordinators.*import.*MapModeCoordinator" src/
grep -r "from.*extractors.map_mode" src/
grep -r "from.*models.*import.*MapSnapshot" src/
grep -r "from.*models.*import.*EntityInventory" src/
grep -r "from.*models.*import.*ExtractQueueItem" src/
grep -r "from.*reports.*import" src/
```

**Fix approach:**
1. Remove unused imports
2. Replace with MigrationUI where appropriate
3. Update tests that referenced deleted modules

#### Task 17: Run linting and type checking
- **Description**: Ensure no broken references remain in codebase
- **Commands to run**:
  ```bash
  uv run ruff check src/
  uv run mypy src/
  uv run pytest tests/
  ```
- **Dependencies**: Task 16
- **Estimated effort**: 1 hour

**Fix any issues:**
- Import errors from deleted modules
- Type annotation errors from removed classes
- Test failures from missing fixtures

### Phase 8: Documentation

#### Task 18: Update README.md
- **Description**: Remove references to deprecated features and update command examples
- **Files to modify**:
  - `README.md`
- **Dependencies**: Task 17
- **Estimated effort**: 1 hour

**Changes:**
- Remove references to multi-pass extraction
- Remove references to map-mode
- Remove references to snapshot/queue system
- Update command examples to show new Rich UI
- Add screenshots or examples of Rich UI output (optional)
- Update architecture section to reflect MigrationUI layer

**Sections to update:**
1. Architecture overview - mention MigrationUI as UI layer
2. Command reference - only show active commands (max-extract, download-attachments, oauth)
3. Workflow - remove multi-pass references
4. Features - highlight unified Rich UI

#### Task 19: Update inline documentation
- **Description**: Update docstrings and comments referencing removed features
- **Files to check**: All modified files
- **Dependencies**: Task 18
- **Estimated effort**: 30 minutes

**Search patterns:**
```bash
# Find docstring references to deprecated features
grep -r "multi-pass" src/
grep -r "map-mode" src/
grep -r "snapshot" src/ | grep -v ".pyc"
grep -r "queue" src/ | grep -v ".pyc"
```

**Fix:**
- Update docstrings in MaxExtractCoordinator
- Update docstrings in MigrationUI
- Update module-level docstrings in modified files

#### Task 20: Create migration changelog entry
- **Description**: Document changes for users upgrading from previous versions
- **Files to create/modify**:
  - `CHANGELOG.md` (create if doesn't exist)
- **Dependencies**: Task 19
- **Estimated effort**: 30 minutes

**Changelog entry:**
```markdown
## [Version X.X.X] - 2025-11-28

### Added
- Unified MigrationUI class for consistent Rich terminal UI
- Real-time progress bars for all entity extraction operations
- Styled error panels and success messages across all commands
- Summary tables with comprehensive migration metrics

### Changed
- MaxExtractCoordinator now uses MigrationUI for all output
- Attachment downloads use unified UI instead of MultiProgressDisplay
- OAuth commands standardized with Rich panels and status displays

### Removed
- **BREAKING**: Multi-pass extraction workflow (was already deprecated)
- **BREAKING**: Map-mode coordinators and extractors
- **BREAKING**: Snapshot and queue-based extraction models
- Legacy report generators (map, download, extract)
- BaseMigrationCoordinator and RichMigrationCoordinator

### Migration Guide
- No action required for users - all existing commands work with improved UI
- If you have custom scripts importing removed coordinators, update to use MaxExtractCoordinator
- Database schema unchanged - existing databases compatible
```

## Codebase Integration Points

### Files to Modify

**Core Integration:**
- `src/coordinators/max_extract_coordinator.py`
  - Add `migration_ui` parameter to `__init__`
  - Wrap `extract_all()` with MigrationUI calls
  - Replace direct logger output with UI methods for user-facing messages

**CLI Commands:**
- `src/cli/migrate.py`
  - Update `max_extract()` to create and pass MigrationUI
  - Update `download_attachments()` to use MigrationUI download methods

- `src/cli/oauth.py`
  - Verify all commands use Rich components consistently
  - Replace any remaining print() calls with console.print()

**Models:**
- `src/models/__init__.py`
  - Remove exports for deleted models (MapSnapshot, EntityInventory, etc.)

**Reports:**
- `src/reports/__init__.py`
  - Remove exports for deleted report generators

**Services:**
- `src/cli/services/__init__.py`
  - Remove exports for deleted service helpers (if deleted)

### New Files to Create

**UI Layer:**
- `src/ui/migration_ui.py`
  - MigrationUI class with methods: show_run_header, start_entity_progress, update_entity_progress, show_run_summary, show_error, show_keyboard_interrupt, finalize
  - Download methods: start_download_progress, add_download_task, update_download_task, complete_download_task, show_download_summary

**Tests:**
- `tests/unit/test_migration_ui.py`
  - Unit tests for MigrationUI methods with mocked Console

**Documentation:**
- `CHANGELOG.md` (if doesn't exist)
  - Version history with breaking changes documentation

### Existing Patterns to Follow

**Shared Console Access:**
```python
from ..cli.services.shared import SharedServices
console = SharedServices.get_console()
```

**Progress Display Creation:**
```python
from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn
progress = Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(complete_style="green"),
    MofNCompleteColumn(),
    TransferSpeedColumn(),
    TimeElapsedColumn(),
    console=console,
    expand=True
)
```

**Live Context for Real-time Updates:**
```python
from rich.live import Live
with Live(progress, console=console, refresh_per_second=4):
    # Progress updates happen automatically
    pass
```

**Error Panel Display:**
```python
from rich.panel import Panel
from rich.text import Text
panel = Panel(
    Text(message, style="white"),
    title="[bold red]Error",
    border_style="red",
    padding=(1, 2)
)
console.print(panel)
console.print_exception(show_locals=False)  # For tracebacks
```

**Summary Table Display:**
```python
from rich.table import Table
table = Table(title="📊 Migration Summary", show_header=True)
table.add_column("Metric", style="cyan", width=25)
table.add_column("Value", style="green", justify="right")
table.add_row("Total Entities", f"{count:,}")
console.print(table)
```

**Dependency Injection Pattern:**
```python
class MaxExtractCoordinator:
    def __init__(
        self,
        jobber_client: JobberClient,
        repository: Repository,
        logger: Logger,
        entity_mapper: EntityMapper,
        migration_ui: Optional[MigrationUI] = None,  # New parameter
    ):
        # Create default if not provided
        if migration_ui is None:
            console = SharedServices.get_console()
            self._migration_ui = MigrationUI(console)
        else:
            self._migration_ui = migration_ui
```

## Technical Design

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                            │
│  (src/cli/migrate.py, src/cli/oauth.py)                    │
│  - max-extract command                                       │
│  - download-attachments command                             │
│  - oauth commands (init, status, refresh, revoke)           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ creates
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                     UI Layer (NEW)                          │
│  (src/ui/migration_ui.py)                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MigrationUI                                         │   │
│  │  - show_run_header()                                 │   │
│  │  - start_entity_progress()                           │   │
│  │  - update_entity_progress()                          │   │
│  │  - show_run_summary()                                │   │
│  │  - show_error()                                      │   │
│  │  - start_download_progress() (attachments)           │   │
│  │  - add_download_task()                               │   │
│  │  - complete_download_task()                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│                         │ uses                               │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SharedServices.get_console()                        │   │
│  │  (Rich Console singleton)                            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                 ▲
                 │ passed to
                 │
┌────────────────┴────────────────────────────────────────────┐
│                  Coordinator Layer                          │
│  (src/coordinators/max_extract_coordinator.py)             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MaxExtractCoordinator                               │   │
│  │  - extract_all() wrapped with UI calls              │   │
│  │  - Entity loop with progress updates                │   │
│  │  - Error handling with UI display                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ orchestrates
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   Extractor Layer                           │
│  (src/extractors/)                                          │
│  - ClientsExtractor                                         │
│  - InvoicesExtractor                                        │
│  - UsersExtractor                                           │
│  - ... (all entity extractors)                              │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ persists to
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  Repository Layer                           │
│  (src/repositories/repository.py)                           │
│  - save_client(), save_invoice(), etc.                      │
│  - get_migration_state() for progress tracking             │
│  - update_migration_state() for checkpoints                │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

**Migration Extraction Flow:**
```
1. User runs: uv run tightbeam migrate max-extract
2. CLI creates MigrationUI with SharedServices console
3. CLI creates MaxExtractCoordinator with MigrationUI
4. Coordinator.extract_all() calls:
   a. migration_ui.show_run_header() → Display panel
   b. migration_ui.start_entity_progress() → Create progress bars
   c. For each entity:
      - migration_ui.update_entity_progress() → Update bar (start)
      - extractor.extract_all() → Fetch & persist data
      - repository.get_migration_state() → Get final count
      - migration_ui.update_entity_progress() → Update bar (complete)
   d. migration_ui.show_run_summary() → Display table
   e. migration_ui.finalize() → Cleanup
5. Console output rendered to terminal
```

**Attachment Download Flow:**
```
1. User runs: uv run tightbeam migrate download-attachments
2. CLI creates MigrationUI with SharedServices console
3. CLI calls migration_ui.start_download_progress()
4. ThreadPoolExecutor spawns worker threads
5. Each worker:
   a. migration_ui.add_download_task() → Create progress bar
   b. AttachmentDownloader.download() with progress callback
   c. Callback → migration_ui.update_download_task() → Update bar
   d. migration_ui.complete_download_task() → Hide bar
   e. Return result to main thread
6. Main thread:
   a. Process results (DB writes - thread-safe)
   b. migration_ui.show_download_summary() → Display table
7. Console output rendered to terminal
```

### API Endpoints
N/A - This is a CLI refactor, no API changes.

## Dependencies and Libraries

**Already in use (no new dependencies):**
- `rich` - Terminal UI library
  - Console: Main output interface
  - Progress: Progress bars with customizable columns
  - Panel: Styled message boxes
  - Table: Tabular data display
  - Live: Real-time updating display context
  - Status: Spinner status indicators

- `typer` - CLI framework (unchanged)
- `sqlite3` - Database (unchanged)

**New Python standard library imports for MigrationUI:**
- `typing.Optional` - Already used
- `typing.Union` - May be needed for type hints
- `contextlib.contextmanager` - If creating context manager methods

## Testing Strategy

### Unit Tests

**MigrationUI Tests (`tests/unit/test_migration_ui.py`):**
```python
import pytest
from unittest.mock import Mock, call
from rich.console import Console
from src.ui.migration_ui import MigrationUI
from src.models.migration_summary import MigrationSummary

@pytest.fixture
def mock_console():
    """Mock Rich Console."""
    return Mock(spec=Console)

@pytest.fixture
def migration_ui(mock_console):
    """Create MigrationUI with mocked console."""
    return MigrationUI(mock_console)

def test_show_run_header_displays_panel(migration_ui, mock_console):
    """Test run header displays styled panel."""
    migration_ui.show_run_header("/path/to/db.sqlite", config=None)

    # Verify console.print called with Panel
    assert mock_console.print.called
    # Verify panel contains database path

def test_start_entity_progress_creates_progress_bars(migration_ui):
    """Test progress bar creation for entities."""
    entities = ["clients", "invoices", "users"]
    progress = migration_ui.start_entity_progress(entities)

    assert progress is not None
    # Verify progress tasks created

def test_update_entity_progress_updates_correct_task(migration_ui):
    """Test progress update targets correct entity."""
    entities = ["clients"]
    migration_ui.start_entity_progress(entities)

    migration_ui.update_entity_progress("clients", completed=50, total=100)

    # Verify task update called with correct values

def test_show_error_displays_exception(migration_ui, mock_console):
    """Test error display with traceback."""
    exc = ValueError("Test error")
    migration_ui.show_error(exc)

    # Verify print_exception called
    assert mock_console.print_exception.called
```

**MaxExtractCoordinator Integration Tests:**
- Test coordinator with MigrationUI passed in
- Test coordinator creates MigrationUI when not provided
- Verify UI methods called in correct order during extraction
- Test error handling calls show_error()

### Integration Tests

**End-to-End CLI Tests:**
```python
def test_max_extract_with_migration_ui(tmp_path):
    """Test max-extract command uses MigrationUI."""
    # Setup: Create test database, mock Jobber API
    # Execute: Run max-extract command
    # Verify: Check Rich output contains progress bars, summary table

def test_download_attachments_with_migration_ui(tmp_path):
    """Test attachment downloads use MigrationUI."""
    # Setup: Create test database with pending attachments
    # Execute: Run download-attachments command
    # Verify: Check progress bars created, summary displayed
```

### Edge Cases to Cover

**MigrationUI Edge Cases:**
1. Empty entity list - should show header but no progress bars
2. Entity with zero records - progress bar shows 0/0
3. Entity with unknown total (None) - progress bar shows spinner only
4. Multiple errors during extraction - all displayed in error panel
5. Keyboard interrupt - graceful shutdown message
6. Very long entity names - truncation or wrapping in progress bar

**Attachment Download Edge Cases:**
1. No attachments to download - graceful message
2. All attachments already downloaded - skip message
3. Download failures mid-batch - partial success summary
4. Very large files (>1GB) - progress percentage updates
5. Network timeout - error handling and retry logic
6. Parallel worker crashes - main thread handles exception

**Coordinator Edge Cases:**
1. Database locked - error display with retry suggestion
2. API rate limiting - pause and resume with UI feedback
3. Missing dependencies (e.g., clients not extracted) - clear error message
4. Resume from checkpoint - progress starts from saved state
5. Partial entity list (selective extraction) - only show requested entities

## Success Criteria

### Functional Criteria

✅ **Max-Extract Uses Unified Rich UI:**
- [ ] Run header panel displays database path and configuration
- [ ] Progress bars show for each entity being extracted
- [ ] Progress updates in real-time as entities are fetched
- [ ] Summary table displays at completion with all metrics
- [ ] Errors display in styled error panels with tracebacks
- [ ] Keyboard interrupt shows graceful shutdown message

✅ **Download-Attachments Uses Unified Rich UI:**
- [ ] Download progress bars appear for active downloads
- [ ] Progress percentages update as files download
- [ ] Completed downloads hide their progress bars immediately
- [ ] Summary table shows total files, bytes, duration, failures
- [ ] Parallel downloads (3-5 workers) work without UI conflicts

✅ **OAuth Commands Use Rich Feedback:**
- [ ] oauth init - Status spinner during token fetch, success panel on completion
- [ ] oauth status - Styled table with component states
- [ ] oauth refresh - Status spinner and success message
- [ ] oauth revoke - Confirmation and success panel

### Codebase Criteria

✅ **All Obsolete Code Removed:**
- [ ] BaseMigrationCoordinator deleted
- [ ] RichMigrationCoordinator deleted
- [ ] MapModeCoordinator deleted
- [ ] DownloadModeCoordinator deleted
- [ ] ExtractModeCoordinator deleted
- [ ] src/extractors/map_mode/ directory deleted (all 14 files)
- [ ] MapSnapshot model deleted
- [ ] EntityInventory model deleted
- [ ] ExtractQueueItem model deleted
- [ ] AttachmentQueueItem model deleted
- [ ] MapReportGenerator deleted
- [ ] DownloadReportGenerator deleted
- [ ] ReportGenerator deleted
- [ ] ExtractReportGenerator deleted (if exists)

✅ **No Import Errors:**
- [ ] `uv run ruff check src/` passes with no errors
- [ ] `uv run mypy src/` passes with no type errors
- [ ] `uv run pytest tests/` passes with all tests green
- [ ] No broken imports referencing deleted modules
- [ ] `grep -r "map_mode" src/` returns no results
- [ ] `grep -r "MapSnapshot" src/` returns no results
- [ ] `grep -r "QueueItem" src/` returns no results

✅ **Repository Cleanup:**
- [ ] No database methods reference deleted models
- [ ] Schema initialization doesn't create snapshot/queue tables (or drops if safe)
- [ ] Migration state tracking still works for resume capability

### Documentation Criteria

✅ **README Updated:**
- [ ] Architecture section mentions MigrationUI layer
- [ ] Command examples show max-extract and download-attachments (no map-mode)
- [ ] Multi-pass extraction references removed
- [ ] Snapshot/queue system references removed
- [ ] Features section highlights unified Rich UI

✅ **Changelog Created:**
- [ ] Version entry with date
- [ ] Added section lists MigrationUI and UI improvements
- [ ] Changed section lists coordinator and download updates
- [ ] Removed section lists all deleted coordinators, models, reports
- [ ] Migration guide provides upgrade instructions

✅ **Inline Documentation:**
- [ ] MigrationUI class has comprehensive docstrings
- [ ] MaxExtractCoordinator docstring updated to mention UI integration
- [ ] Module-level docstrings updated in modified files
- [ ] No docstrings reference deleted features (multi-pass, map-mode, snapshot)

## Notes and Considerations

### Important Notes

**Thread Safety:**
- SQLite database writes MUST happen in main thread only
- Worker threads for attachment downloads should create progress tasks on-demand
- Use progress callbacks to update UI from worker threads (Rich handles thread-safety)

**Backward Compatibility:**
- Database schema unchanged - existing databases fully compatible
- MaxExtractCoordinator signature extended (new optional parameter)
- No breaking changes to CLI command names or arguments
- Users upgrading see improved UI automatically

**Logging vs UI Separation:**
- RichLogger continues to handle structured logging to files
- MigrationUI handles user-facing terminal output
- Never mix logger.info() with console.print() for same message
- Logger for debugging/audit trail, UI for user feedback

**ApiMetrics Fallback:**
- PRD mentions ApiMetrics parameter but model doesn't exist yet
- Use `Optional[dict]` type hint for metrics parameter
- Accept None and dict for forward compatibility
- Show metrics in summary table if provided, skip if None

### Potential Challenges

**Challenge 1: MultiProgressDisplay Replacement**
- **Issue**: MultiProgressDisplay has sophisticated layout with log buffer
- **Mitigation**: MigrationUI can use similar Live layout pattern if needed
- **Decision**: Start simple (progress bars only), add log buffer if users request

**Challenge 2: Progress Bar Creation Overhead**
- **Issue**: Creating 30k progress tasks upfront causes lag
- **Mitigation**: Create tasks on-demand in worker threads (existing pattern)
- **Pattern**: Worker calls `add_download_task()` when starting download

**Challenge 3: Testing Rich UI**
- **Issue**: Hard to test visual terminal output
- **Mitigation**: Mock Console and verify method calls, not visual appearance
- **Approach**: Test that correct Rich components created with correct data

**Challenge 4: Database Schema Cleanup**
- **Issue**: Dropping snapshot/queue tables might break existing databases
- **Mitigation**: Leave tables in place but unused (safe approach)
- **Alternative**: Migration script to drop tables (more complex)
- **Recommendation**: Leave tables, document as deprecated in schema comments

### Future Enhancements

**Phase 2 Enhancements (Out of Scope):**
1. ApiMetrics model - proper tracking of API requests, rate limits, errors
2. Log buffer in MigrationUI - show recent log messages above progress bars
3. Interactive mode - pause/resume extraction with keyboard commands
4. Progress persistence - save progress to database for cross-session resume
5. Parallel entity extraction - extract independent entities concurrently
6. Adaptive extraction tuning - adjust batch sizes based on API performance

**Configuration Options:**
1. `--quiet` flag - suppress progress bars, show summary only
2. `--verbose` flag - show detailed logs in addition to progress
3. `--no-color` flag - disable Rich styling for non-TTY environments
4. `--progress-refresh-rate` - adjust update frequency (default 4Hz)

---

*This plan is ready for execution with `/execute-plan PRPs/tightbeam-v2-rich-ui-consolidation.md`*
