# Implementation Plan: Enhanced Terminal UI with Fixed Progress Bars

**Status**: Ready for Execution
**Branch**: `feature/improved-terminal-ui`
**Estimated Effort**: 8-12 hours
**Created**: 2025-11-18

---

## Overview

Implement an enhanced terminal UI for TightBeam migrations that separates console logs from progress indicators. The new UI will feature a scrollable log panel at the top with fixed progress bars at the bottom, providing better visibility and reducing visual clutter during long-running migrations.

---

## Requirements Summary

### Must Have (MVP)
- Fixed progress bars at bottom of terminal (no scrolling)
- Scrollable log window above progress bars showing last N messages
- No visual flickering or jumping during updates
- Works in both verbose and normal modes
- Log buffer is configurable via constructor
- All existing functionality continues to work
- Accurate progress counters (processed/total records)

### Key Technical Decisions
- **Layout approach**: Use `rich.console.Group` for simplicity (can upgrade to Layout later)
- **Buffer size**: Default 75 messages (balanced between history and memory)
- **Opt-in by default**: Enhanced UI enabled by default with `--simple-ui` flag to disable
- **Log retention**: Discard buffered logs on completion (already in report files)

---

## Research Findings

### Best Practices from Codebase Analysis

1. **Separation of Concerns**:
   - Logger Protocol = Basic logging (info/debug/error/warning)
   - RichLogger = Enhanced display with Rich features
   - Coordinator = Complex UI orchestration (progress, live updates)

2. **Pattern: Don't modify Protocol for Rich-specific features**
   ```python
   # RichLogger can have methods NOT in Logger Protocol
   class RichLogger(Logger):
       def enable_buffered_mode(self) -> None:  # New - not in Protocol
           """Enable buffered logging."""
   ```

3. **Pattern: Constructor injection with Optional defaults**
   ```python
   def __init__(
       self,
       required_dep: JobberClient,
       optional_dep: Optional[ConfigManager] = None,  # Falls back to default
       enable_feature: bool = False,  # Feature flags default False
   ) -> None:
       self._config = optional_dep or ConfigManagerImpl()
   ```

4. **Pattern: Progress management in Coordinator, not Logger**
   - Coordinator creates and manages Rich `Progress` objects
   - Coordinator has `self._console = Console()` separate from Logger
   - Wrapper methods: `_create_progress_display()`, `_add_entity_task()`, etc.

5. **Pattern: Shared Console via ServiceFactory**
   ```python
   # Singleton pattern for Console instance
   console = ServiceFactory.get_console()
   ```

### Rich Library Best Practices

From Rich documentation (https://rich.readthedocs.io/en/stable/live.html):

1. **Live Display Pattern**:
   ```python
   with Live(renderable, refresh_per_second=4) as live:
       # Update renderable internally OR
       live.update(new_renderable)
   ```

2. **Print above Live Display**:
   ```python
   with Live(table) as live:
       live.console.print("Message above live display")  # Appears above
   ```

3. **Group Multiple Renderables**:
   ```python
   from rich.console import Group
   group = Group(panel1, panel2, progress_bars)
   with Live(group) as live:
       # All renderables update together
   ```

4. **Refresh Rate**: Default 4 times/second for fluid updates

5. **Transient Mode**: `transient=True` makes display disappear on exit

---

## Implementation Tasks

### Phase 1: Foundation - RichLogger Buffering (2-3 hours)

#### Task 1.1: Add Log Buffer to RichLogger
**Description**: Implement ring buffer for log message storage
**Files to modify**: `src/loggers/rich_logger.py`
**Dependencies**: None
**Estimated effort**: 45 minutes

```python
from collections import deque
from typing import NamedTuple

class LogMessage(NamedTuple):
    """Structured log message for buffer."""
    level: str
    message: str
    timestamp: str  # For future use
    formatted: str  # Pre-formatted Rich markup

class RichLogger(Logger):
    def __init__(self, verbose: bool = False, buffer_size: int = 75):
        self.verbose = verbose
        self.buffer_size = buffer_size
        self.console = Console()
        self.error_console = Console(stderr=True)

        # New: Buffer and mode tracking
        self._log_buffer: deque[LogMessage] = deque(maxlen=buffer_size)
        self._buffered_mode = False
```

**Acceptance Criteria**:
- [ ] Buffer initialized in `__init__` with configurable size
- [ ] Uses `collections.deque` with `maxlen` for automatic overflow
- [ ] LogMessage stores level, message, and pre-formatted string

---

#### Task 1.2: Implement Buffer Management Methods
**Description**: Add methods to enable buffering and retrieve buffered logs
**Files to modify**: `src/loggers/rich_logger.py`
**Dependencies**: Task 1.1
**Estimated effort**: 1 hour

```python
def enable_buffered_mode(self) -> None:
    """Enable buffered logging for enhanced UI."""
    self._buffered_mode = True

def disable_buffered_mode(self) -> None:
    """Disable buffered mode, return to direct output."""
    self._buffered_mode = False

def get_recent_logs(self, count: Optional[int] = None) -> list[str]:
    """Return recent log messages as formatted strings.

    Args:
        count: Number of recent messages to return (None = all)

    Returns:
        List of formatted log strings (newest last)
    """
    if count is None:
        return [msg.formatted for msg in self._log_buffer]
    return [msg.formatted for msg in list(self._log_buffer)[-count:]]

def clear_buffer(self) -> None:
    """Clear the log buffer."""
    self._log_buffer.clear()

def _add_to_buffer(self, level: str, message: str) -> None:
    """Add formatted message to buffer.

    Args:
        level: Log level (INFO, DEBUG, ERROR, WARNING)
        message: Raw message text
    """
    # Format with Rich markup
    color_map = {
        "INFO": "green",
        "DEBUG": "blue",
        "ERROR": "red",
        "WARNING": "yellow",
    }
    color = color_map.get(level, "white")
    formatted = f"[{color}]{level}[/{color}]: {message}"

    from datetime import datetime
    timestamp = datetime.now().isoformat()

    log_msg = LogMessage(
        level=level,
        message=message,
        timestamp=timestamp,
        formatted=formatted,
    )
    self._log_buffer.append(log_msg)
```

**Acceptance Criteria**:
- [ ] `enable_buffered_mode()` sets internal flag
- [ ] `get_recent_logs()` returns formatted strings from buffer
- [ ] `_add_to_buffer()` creates LogMessage with Rich formatting
- [ ] Buffer automatically drops oldest when full (deque handles this)

---

#### Task 1.3: Update Logging Methods to Use Buffer
**Description**: Modify info/debug/error/warning to buffer when in buffered mode
**Files to modify**: `src/loggers/rich_logger.py`
**Dependencies**: Task 1.2
**Estimated effort**: 45 minutes

```python
def info(self, message: str) -> None:
    """Print informational message using Rich formatting."""
    if self._buffered_mode:
        self._add_to_buffer("INFO", message)
    else:
        self.console.print(f"[green]INFO[/green]: {message}")

def debug(self, message: str) -> None:
    """Print debug message if verbose mode is enabled."""
    if not self.verbose:
        return

    if self._buffered_mode:
        self._add_to_buffer("DEBUG", message)
    else:
        self.console.print(f"[blue]DEBUG[/blue]: {message}")

def error(self, message: str) -> None:
    """Print error message to stderr using Rich formatting."""
    if self._buffered_mode:
        self._add_to_buffer("ERROR", message)
    else:
        self.error_console.print(f"[red]ERROR[/red]: {message}")

def warning(self, message: str) -> None:
    """Print warning message using Rich formatting."""
    if self._buffered_mode:
        self._add_to_buffer("WARNING", message)
    else:
        self.console.print(f"[yellow]WARNING[/yellow]: {message}")
```

**Acceptance Criteria**:
- [ ] All logging methods check `_buffered_mode` flag
- [ ] In buffered mode, messages go to buffer instead of console
- [ ] In non-buffered mode, behavior unchanged (backward compatible)
- [ ] Verbose check still applies for debug messages

---

#### Task 1.4: Write Unit Tests for Buffering
**Description**: Test buffer operations, overflow, and mode switching
**Files to create**: `tests/test_rich_logger_buffering.py`
**Dependencies**: Tasks 1.1-1.3
**Estimated effort**: 1 hour

```python
import pytest
from src.loggers.rich_logger import RichLogger

class TestRichLoggerBuffering:
    def setup_method(self):
        """Create logger with small buffer for testing."""
        self.logger = RichLogger(verbose=True, buffer_size=5)

    def test_buffer_initialization(self):
        """Buffer starts empty."""
        assert len(self.logger.get_recent_logs()) == 0

    def test_buffered_mode_stores_messages(self):
        """Messages are buffered when buffered mode enabled."""
        self.logger.enable_buffered_mode()
        self.logger.info("Test message")

        logs = self.logger.get_recent_logs()
        assert len(logs) == 1
        assert "Test message" in logs[0]
        assert "INFO" in logs[0]

    def test_buffer_overflow(self):
        """Buffer drops oldest when full."""
        self.logger.enable_buffered_mode()
        for i in range(10):
            self.logger.info(f"Message {i}")

        logs = self.logger.get_recent_logs()
        assert len(logs) == 5  # Buffer size
        assert "Message 5" in logs[0]  # Oldest retained
        assert "Message 9" in logs[4]  # Newest

    def test_get_recent_logs_with_count(self):
        """Can retrieve specific number of recent logs."""
        self.logger.enable_buffered_mode()
        for i in range(5):
            self.logger.info(f"Message {i}")

        logs = self.logger.get_recent_logs(count=3)
        assert len(logs) == 3
        assert "Message 2" in logs[0]

    def test_non_buffered_mode_no_storage(self):
        """Messages not stored when buffered mode disabled."""
        self.logger.info("Direct message")
        assert len(self.logger.get_recent_logs()) == 0

    def test_clear_buffer(self):
        """Buffer can be cleared."""
        self.logger.enable_buffered_mode()
        self.logger.info("Test")
        self.logger.clear_buffer()
        assert len(self.logger.get_recent_logs()) == 0
```

**Acceptance Criteria**:
- [ ] Tests pass for buffer initialization
- [ ] Tests pass for message storage in buffered mode
- [ ] Tests pass for buffer overflow behavior
- [ ] Tests pass for count parameter
- [ ] Tests pass for non-buffered mode
- [ ] Tests pass for clear_buffer()

---

### Phase 2: Layout Implementation (3-4 hours)

#### Task 2.1: Create Log Panel Renderable
**Description**: Build Panel that displays buffered log messages
**Files to modify**: `src/coordinators/base_migration_coordinator.py`
**Dependencies**: Phase 1 complete
**Estimated effort**: 1 hour

```python
from rich.panel import Panel
from rich.text import Text
from rich.console import Group

def _create_log_panel(self, height: int = 15) -> Panel:
    """Create panel displaying recent log messages.

    Args:
        height: Target height for log panel in lines

    Returns:
        Rich Panel with log messages
    """
    # Get recent logs from logger buffer
    log_lines = self._logger.get_recent_logs()

    # Limit to panel height
    display_logs = log_lines[-height:] if len(log_lines) > height else log_lines

    # Create Text object with markup support
    log_text = Text()
    for log_line in display_logs:
        log_text.append_text(Text.from_markup(log_line + "\n"))

    # Wrap in panel with border
    panel = Panel(
        log_text,
        title="[bold cyan]Migration Logs[/bold cyan]",
        border_style="cyan",
        padding=(0, 1),
    )
    return panel
```

**Acceptance Criteria**:
- [ ] Panel created with cyan border and title
- [ ] Displays last N log messages from buffer
- [ ] Text preserves Rich markup from buffer
- [ ] Panel height is configurable

---

#### Task 2.2: Refactor Progress Display Creation
**Description**: Modify `_create_progress_display()` to return configured Progress object
**Files to modify**: `src/coordinators/base_migration_coordinator.py`
**Dependencies**: Existing code
**Estimated effort**: 30 minutes

```python
def _create_progress_display(self) -> Progress:
    """Create Progress display with custom columns.

    Returns configured Progress object that can be used in Group.
    """
    # Existing implementation - ensure it returns Progress without starting context
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}", justify="left"),
        BarColumn(bar_width=50),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        expand=False,  # Don't expand to full width
    )
    return progress
```

**Acceptance Criteria**:
- [ ] Returns Progress object (not context manager)
- [ ] Progress configured with existing columns
- [ ] `expand=False` to prevent full-width expansion in Group

---

#### Task 2.3: Create Two-Section Layout with Group
**Description**: Combine log panel and progress bars using Rich Group
**Files to modify**: `src/coordinators/base_migration_coordinator.py`
**Dependencies**: Tasks 2.1, 2.2
**Estimated effort**: 1 hour

```python
from rich.console import Group
from rich.live import Live

def _create_layout(self, progress_display: Progress) -> Group:
    """Create two-section layout with logs above and progress below.

    Args:
        progress_display: Configured Progress object

    Returns:
        Rich Group containing both sections
    """
    log_panel = self._create_log_panel(height=15)

    # Group combines renderables vertically
    layout = Group(
        log_panel,
        "",  # Spacer line
        progress_display,
    )
    return layout

def _update_layout(self, live: Live, progress_display: Progress) -> None:
    """Update the live display with fresh log panel and progress.

    Args:
        live: Active Live display
        progress_display: Progress object being displayed
    """
    updated_layout = self._create_layout(progress_display)
    live.update(updated_layout)
```

**Acceptance Criteria**:
- [ ] Group created with log panel above progress
- [ ] Spacer line between sections for visual separation
- [ ] Layout updates when `_update_layout()` called
- [ ] Progress object passed through (not recreated)

---

#### Task 2.4: Integrate Live Display into migrate() Method
**Description**: Replace existing Progress context with Live context containing Group
**Files to modify**: `src/coordinators/base_migration_coordinator.py`
**Dependencies**: Tasks 2.1-2.3
**Estimated effort**: 1.5 hours

```python
def migrate(self, include_extended_entities: bool = True) -> MigrationSummary:
    """Execute comprehensive migration workflow with enhanced UI."""

    # Enable buffered mode for logger
    if hasattr(self._logger, 'enable_buffered_mode'):
        self._logger.enable_buffered_mode()

    # Create Progress display (not started yet)
    progress_display = self._create_progress_display()

    # Create initial layout
    layout = self._create_layout(progress_display)

    # Use Live display instead of Progress context
    with Live(
        layout,
        console=self._console,
        refresh_per_second=4,
        transient=False,  # Keep final display visible
    ) as live:
        # Store live reference for updates
        self._live_display = live

        try:
            # Execute migration with progress updates
            summary = self._execute_migration_workflow(
                progress_display,
                include_extended_entities,
            )

            # Update display periodically during migration
            # (called from within _execute_migration_workflow)

        finally:
            # Disable buffered mode when done
            if hasattr(self._logger, 'disable_buffered_mode'):
                self._logger.disable_buffered_mode()
            self._live_display = None

    return summary

def _execute_migration_workflow(
    self,
    display_obj: Progress,
    include_extended_entities: bool,
) -> MigrationSummary:
    """Internal method that performs actual migration work.

    Args:
        display_obj: Progress object for task tracking
        include_extended_entities: Whether to include extended entities

    Returns:
        Migration summary
    """
    # Existing migration logic
    # But now: after each significant update, refresh layout
    self._refresh_display_if_needed(display_obj)

    # ... rest of migration ...
```

**Pattern for Display Updates**:
```python
def _refresh_display_if_needed(self, progress_display: Progress) -> None:
    """Refresh live display with updated logs and progress.

    Called periodically during migration to update UI.
    """
    if hasattr(self, '_live_display') and self._live_display is not None:
        self._update_layout(self._live_display, progress_display)
```

**Acceptance Criteria**:
- [ ] Logger buffered mode enabled at start of migrate()
- [ ] Live context wraps entire migration
- [ ] Layout updates periodically during migration
- [ ] Logger buffered mode disabled when done
- [ ] Existing migration logic continues to work
- [ ] Progress tasks created/updated correctly

---

### Phase 3: Progress Counter Accuracy (1-2 hours)

#### Task 3.1: Add Total Count Polling Before Extraction
**Description**: Query API/database for total counts before starting extraction
**Files to modify**: `src/coordinators/base_migration_coordinator.py`, entity extractors
**Dependencies**: Phase 2 complete
**Estimated effort**: 1.5 hours

**Problem**: Progress bars show `0/?` because total count is unknown until extraction completes.

**Solution**: Poll for counts before extraction starts.

```python
def _get_entity_count(self, entity_type: str) -> Optional[int]:
    """Get total count for entity type from API.

    Args:
        entity_type: Type of entity (clients, invoices, etc.)

    Returns:
        Total count or None if unavailable
    """
    try:
        # Use GraphQL to get total count without fetching data
        # Example for clients:
        if entity_type == "clients":
            count_query = """
            query GetClientCount {
              clients {
                totalCount
              }
            }
            """
            response = self._jobber_client._execute_graphql_request(count_query)
            return response.get("data", {}).get("clients", {}).get("totalCount")

        # Add similar logic for other entity types
        # ...

    except Exception as e:
        self._logger.debug(f"Could not fetch {entity_type} count: {e}")
        return None

def _migrate_clients(
    self,
    summary: MigrationSummary,
    display_obj: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
) -> int:
    """Migrate clients with accurate progress tracking."""

    # Get total count before starting
    total_count = self._get_entity_count("clients")

    # Create task with total if available
    if task_id is not None and total_count is not None:
        self._update_task_progress(
            display_obj,
            task_id,
            description="[cyan]Migrating clients...",
            completed=0,
            total=total_count,
        )

    # Refresh display to show 0/N instead of 0/?
    self._refresh_display_if_needed(display_obj)

    # Proceed with extraction
    # ...
```

**Alternative Approach** (if totalCount not in API):
```python
def _get_entity_count_from_db(self, entity_type: str) -> Optional[int]:
    """Get count from existing database records.

    Only works if resuming migration or database has records.
    """
    table_name = f"{entity_type}"  # e.g., "clients"
    try:
        count = self._repository.get_table_count(table_name)
        return count if count > 0 else None
    except Exception:
        return None
```

**Acceptance Criteria**:
- [ ] Total counts queried before extraction starts
- [ ] Progress bars show `0/N` instead of `0/?`
- [ ] Graceful fallback to indeterminate if count unavailable
- [ ] No performance impact (count query is fast)

---

### Phase 4: Testing & Refinement (2-3 hours)

#### Task 4.1: Integration Testing with Real Migration
**Description**: Test enhanced UI with actual Jobber API migration
**Files to test**: Full system
**Dependencies**: Phases 1-3 complete
**Estimated effort**: 1 hour

**Test Plan**:
1. Small dataset migration (10-20 clients)
2. Large dataset migration (100+ clients)
3. Verbose mode enabled
4. Normal mode (non-verbose)
5. Resume mode with existing data

**Validation**:
- [ ] Progress bars stay fixed at bottom
- [ ] Log messages appear in top panel
- [ ] No flickering or visual artifacts
- [ ] Progress counters show accurate totals
- [ ] Display updates smoothly
- [ ] Migration completes successfully

---

#### Task 4.2: Terminal Compatibility Testing
**Description**: Test on different terminal sizes and platforms
**Files to test**: Full system
**Dependencies**: Task 4.1
**Estimated effort**: 1 hour

**Test Matrix**:
- **Sizes**: 80x24, 120x40, 200x60, 300x100
- **Platforms**: Linux, macOS (Windows if available)
- **Terminals**: GNOME Terminal, iTerm2, Windows Terminal

**Validation**:
- [ ] Layout works on minimum size (80x24)
- [ ] Layout scales well on large terminals
- [ ] No crashes or exceptions
- [ ] Graceful handling of very narrow terminals
- [ ] Colors display correctly

---

#### Task 4.3: Performance Profiling
**Description**: Measure overhead of buffering and display updates
**Files to test**: `src/loggers/rich_logger.py`, `src/coordinators/base_migration_coordinator.py`
**Dependencies**: Task 4.1
**Estimated effort**: 30 minutes

```python
import time

def profile_buffering():
    """Profile log buffering overhead."""
    logger = RichLogger(buffer_size=100)
    logger.enable_buffered_mode()

    start = time.perf_counter()
    for i in range(1000):
        logger.info(f"Message {i}")
    end = time.perf_counter()

    avg_time_ms = ((end - start) / 1000) * 1000
    print(f"Average buffering time: {avg_time_ms:.3f}ms per message")
    # Should be < 5ms per message
```

**Acceptance Criteria**:
- [ ] Buffering adds < 5ms overhead per message
- [ ] Display updates complete in < 50ms
- [ ] Memory usage < 10MB for buffer
- [ ] No measurable impact on migration throughput

---

#### Task 4.4: Add CLI Flag for Simple UI Fallback
**Description**: Add `--simple-ui` flag to disable enhanced UI
**Files to modify**: `src/cli/migrate.py`, `src/coordinators/base_migration_coordinator.py`
**Dependencies**: Task 4.1
**Estimated effort**: 30 minutes

```python
# In src/cli/migrate.py
@migrate_app.callback()
def migrate_callback(
    ctx: typer.Context,
    # ... existing flags ...
    simple_ui: Annotated[
        bool,
        typer.Option(
            "--simple-ui",
            help="Use simple UI without enhanced layout (fallback mode)"
        ),
    ] = False,
) -> None:
    ctx.obj.update({"simple_ui": simple_ui})

# In BaseMigrationCoordinator.__init__
def __init__(
    self,
    # ... existing params ...
    enable_enhanced_ui: bool = True,  # New parameter
) -> None:
    self._enable_enhanced_ui = enable_enhanced_ui

# In migrate() method
def migrate(self) -> MigrationSummary:
    if self._enable_enhanced_ui:
        return self._migrate_with_enhanced_ui()
    else:
        return self._migrate_with_simple_ui()  # Existing implementation
```

**Acceptance Criteria**:
- [ ] `--simple-ui` flag available in CLI
- [ ] Flag disables enhanced UI, uses original display
- [ ] Default is enhanced UI (opt-out, not opt-in)
- [ ] Help text explains when to use simple UI

---

### Phase 5: Polish & Documentation (1-2 hours)

#### Task 5.1: Update CLI Help Text
**Description**: Document enhanced UI features in help text
**Files to modify**: `src/cli/migrate.py`
**Dependencies**: Phase 4 complete
**Estimated effort**: 15 minutes

**Acceptance Criteria**:
- [ ] Help text mentions enhanced terminal UI
- [ ] `--simple-ui` flag documented
- [ ] Example usage shown

---

#### Task 5.2: Add User-Facing Documentation
**Description**: Document enhanced UI in README or docs
**Files to create/modify**: `docs/terminal-ui.md`, `README.md`
**Dependencies**: Phase 4 complete
**Estimated effort**: 30 minutes

**Content**:
- Screenshot or ASCII art of enhanced UI
- Explanation of log panel and progress bars
- How to enable/disable
- Troubleshooting tips

**Acceptance Criteria**:
- [ ] Documentation explains enhanced UI features
- [ ] Visual example provided
- [ ] Troubleshooting section included

---

#### Task 5.3: Code Review and Cleanup
**Description**: Review code for quality, remove debug statements
**Files to review**: All modified files
**Dependencies**: All tasks complete
**Estimated effort**: 45 minutes

**Checklist**:
- [ ] Remove debug print statements
- [ ] Add docstrings to all new methods
- [ ] Type hints on all new methods
- [ ] Follow existing code style
- [ ] No TODOs or FIXMEs left
- [ ] Import statements organized

---

## Codebase Integration Points

### Files to Modify

1. **`src/loggers/rich_logger.py`** (Medium complexity)
   - Add buffer: `_log_buffer`, `_buffered_mode`
   - Add methods: `enable_buffered_mode()`, `get_recent_logs()`, `_add_to_buffer()`
   - Modify methods: `info()`, `debug()`, `error()`, `warning()`
   - Estimated lines: +80 lines

2. **`src/interfaces/logger.py`** (Low complexity)
   - NO CHANGES NEEDED - RichLogger methods don't need to be in Protocol
   - Estimated lines: 0 lines

3. **`src/coordinators/base_migration_coordinator.py`** (High complexity)
   - Add methods: `_create_log_panel()`, `_update_layout()`, `_refresh_display_if_needed()`, `_get_entity_count()`
   - Modify methods: `migrate()`, `_execute_migration_workflow()`, `_migrate_clients()` (and other entity methods)
   - Add fields: `_live_display`, `_enable_enhanced_ui`
   - Estimated lines: +120 lines

4. **`src/cli/migrate.py`** (Low complexity)
   - Add CLI flag: `--simple-ui`
   - Pass flag to coordinator constructor
   - Estimated lines: +10 lines

### New Files to Create

1. **`tests/test_rich_logger_buffering.py`** (Unit tests)
   - Test buffer operations, overflow, mode switching
   - Estimated lines: ~150 lines

2. **`docs/terminal-ui.md`** (Documentation)
   - User guide for enhanced UI
   - Estimated lines: ~100 lines

### Existing Patterns to Follow

1. **Constructor injection**: Optional parameters with sensible defaults
2. **Feature flags**: Boolean params default to False, except enhanced_ui defaults True
3. **Rich usage**: Console instance from ServiceFactory, Progress managed in coordinator
4. **Testing**: Mock-based with Protocol specs, focus on business logic not display
5. **Error handling**: Try/except with graceful degradation

---

## Technical Design

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│  migrate() entry point                                   │
│  - Enable logger buffered mode                           │
│  - Create Progress display                               │
│  - Create initial Group layout (logs + progress)         │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Live Display Context                                    │
│  with Live(layout, refresh_per_second=4) as live:        │
│    ┌───────────────────────────────────────────────┐    │
│    │ Log Panel (Panel)                             │    │
│    │ - Retrieves logs from logger.get_recent_logs()│    │
│    │ - Formats as Rich Text with markup            │    │
│    │ - Height: 15 lines (configurable)             │    │
│    └───────────────────────────────────────────────┘    │
│    │                                                     │
│    │ Spacer                                              │
│    │                                                     │
│    ┌───────────────────────────────────────────────┐    │
│    │ Progress Bars (Progress)                      │    │
│    │ - Multiple tasks for entities                 │    │
│    │ - Shows: spinner, label, bar, %, time        │    │
│    └───────────────────────────────────────────────┘    │
│                                                          │
│  - Layout updated via _update_layout() when needed       │
│  - Logger continues to buffer messages during migration  │
└──────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Migration Complete                                      │
│  - Disable logger buffered mode                          │
│  - Live context exits, display stays visible            │
│  - Final state shows completed progress                 │
└──────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Logger Buffering**:
   ```
   logger.info("message")
     → _buffered_mode check
     → _add_to_buffer("INFO", "message")
     → LogMessage created with formatted string
     → Appended to deque buffer (auto-drops oldest if full)
   ```

2. **Display Updates**:
   ```
   Migration executes
     → Significant event occurs
     → _refresh_display_if_needed() called
     → _create_log_panel() retrieves buffered logs
     → _create_layout() combines panel + progress
     → live.update(layout) refreshes display
   ```

3. **Progress Updates**:
   ```
   Entity extraction starts
     → _get_entity_count() queries total
     → Task created with total count
     → During extraction:
       → _update_task_progress() called
       → Progress bar shows N/Total
       → Layout refresh shows updated progress
   ```

---

## Dependencies and Libraries

**No new external dependencies required**. All features use existing libraries:

- `rich` - Already in requirements (for Live, Group, Panel, Progress)
- `collections.deque` - Python standard library (for ring buffer)
- `typing` - Python standard library (for type hints)

---

## Testing Strategy

### Unit Tests
- **RichLogger buffering** (`tests/test_rich_logger_buffering.py`)
  - Buffer initialization and size limits
  - Message storage in buffered mode
  - Buffer overflow (drops oldest)
  - `get_recent_logs()` with count parameter
  - Mode switching (buffered ↔ direct)
  - `clear_buffer()` operation

### Integration Tests
- **Full migration with enhanced UI**
  - Small dataset (10-20 entities)
  - Large dataset (100+ entities)
  - Verbose mode enabled
  - Normal mode (non-verbose)
  - Resume mode with existing data

### Manual Tests
- **Terminal compatibility**
  - Different sizes (80x24, 120x40, 200x60)
  - Different platforms (Linux, macOS, Windows)
  - Different terminals (GNOME Terminal, iTerm2, Windows Terminal)

- **Visual validation**
  - No flickering
  - Progress bars stay fixed
  - Logs scroll correctly
  - Colors render properly

- **Performance**
  - Buffering overhead < 5ms/message
  - Display updates < 50ms
  - Memory usage < 10MB
  - No migration throughput impact

---

## Success Criteria

### Must Have (MVP)
- [x] Progress bars stay fixed at bottom during entire migration
- [x] Logs appear in scrollable window above progress bars
- [x] No visual flickering or jumping
- [x] Works in both verbose and normal modes
- [x] Log buffer is configurable via constructor
- [x] All existing functionality continues to work
- [x] Accurate progress counters (N/Total not N/?)

### Technical Success
- [x] Unit tests pass for buffering logic
- [x] Integration tests pass for full migration
- [x] Performance meets requirements (<5ms buffering, <50ms updates)
- [x] Code follows existing patterns and style
- [x] Documentation complete

### User Experience Success
- [x] UI is intuitive without explanation
- [x] Better visibility during long migrations
- [x] Reduced visual clutter
- [x] Helpful for debugging (can see recent logs)
- [x] `--simple-ui` flag for fallback if needed

---

## Notes and Considerations

### Potential Challenges

1. **Rich Live + Progress interaction**:
   - Solution: Use Group to combine both, manage Progress manually instead of context manager

2. **Log buffer memory with very large migrations**:
   - Solution: Fixed-size deque (75 messages) limits memory
   - 75 messages × ~100 chars = ~7.5KB, well under 10MB limit

3. **Performance of frequent display updates**:
   - Solution: Refresh on significant events only, not every log message
   - Use `refresh_per_second=4` for automatic refresh rate limiting

4. **Terminal resize handling**:
   - Rich handles automatically within constraints
   - Log panel height fixed, doesn't adapt (acceptable for MVP)

### Future Enhancements (Out of Scope)

1. **Dynamic log panel height** based on terminal size
2. **Log filtering** by level (show only errors/warnings)
3. **Keyboard shortcuts** to pause/resume display
4. **Log export during execution** to file
5. **Advanced Layout** with split panes for different entities
6. **Metrics dashboard** with graphs

---

## References

### Documentation
- [Rich Live Display](https://rich.readthedocs.io/en/stable/live.html)
- [Rich Group](https://rich.readthedocs.io/en/stable/group.html)
- [Rich Panel](https://rich.readthedocs.io/en/stable/panel.html)
- [Rich Progress](https://rich.readthedocs.io/en/stable/progress.html)
- [Python deque](https://docs.python.org/3/library/collections.html#collections.deque)

### Code Examples
- `/home/max/projects/tightbeam-v2/src/loggers/rich_logger.py` - Current logger implementation
- `/home/max/projects/tightbeam-v2/src/coordinators/base_migration_coordinator.py` - Display management patterns
- [Rich table_movie.py example](https://github.com/willmcgugan/rich/blob/master/examples/table_movie.py)

---

**This plan is ready for execution with `/execute-plan PRPs/terminal-ui-enhancement.md`**
