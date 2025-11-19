# Terminal UI Enhancement - Requirements Document

**Feature Branch**: `feature/improved-terminal-ui`
**Status**: Planning
**Last Updated**: 2025-11-18
**Owner**: TBD

---

## 1. Executive Summary

Improve the TightBeam migration terminal UI by separating console logs from progress indicators. This enhancement will create a fixed progress bar section at the bottom of the terminal with a scrollable log window above, providing better visibility and reducing visual clutter during long-running migrations.

---

## 2. Problem Statement

### Current Issues

1. **Visual Clutter**: Progress bars jump around as new log messages are printed, making it difficult to track migration progress
2. **Poor Readability**: Console output intermingles with progress indicators, creating a confusing display
3. **Lost Context**: Important log messages scroll off-screen and are hard to review during execution
4. **UX During Long Migrations**: Users cannot easily see both recent logs and current progress simultaneously
5. **Total number of records processed / remaining always displays 0 / ?**: likely because we aren't first polling the db to create an index of somekind.

### Impact

- Reduced confidence in migration progress
- Difficulty debugging issues in real-time
- Poor user experience during verbose migrations
- Hard to monitor multiple entity extractions concurrently

---

## 3. Goals & Objectives

### Primary Goals

1. **Fixed Progress Display**: Keep progress bars anchored at the bottom of the terminal
2. **Scrollable Logs**: Display recent log messages in a dedicated window above progress bars
3. **Improved Readability**: Clear visual separation between logs and progress indicators
4. **Maintain Performance**: No degradation in migration speed or terminal responsiveness

### Secondary Goals

- Configurable log buffer size
- Support for different terminal sizes
- Backward compatibility with existing code
- Enhanced visual polish (colors, formatting)

---

## 4. Functional Requirements

### FR1: Dual-Section Layout

**Description**: Terminal display shall be split into two distinct sections
**Priority**: MUST HAVE

- **Upper Section**: Scrollable log panel showing last N messages
- **Lower Section**: Fixed progress bars for all active entity migrations
- Sections shall have clear visual separation (border/divider)
- Layout shall remain stable during updates

### FR2: Log Buffering

**Description**: Logger shall maintain a ring buffer of recent messages
**Priority**: MUST HAVE

- Default buffer size: 50-100 messages (configurable)
- Buffer shall preserve log levels (INFO, WARNING, ERROR, DEBUG)
- Buffer shall preserve timestamps and formatting
- Oldest messages shall be automatically discarded when buffer is full

### FR3: Progress Bar Persistence

**Description**: Progress bars shall remain fixed at bottom of terminal
**Priority**: MUST HAVE

- Progress bars shall not scroll with log messages
- Multiple progress bars shall be visible simultaneously (clients, invoices, quotes, etc.)
- Progress bars shall update smoothly without flicker
- Progress counters will reflect accurate number of processed vs total records.
- Completion status shall be clearly indicated

### FR4: Real-Time Updates

**Description**: Both sections shall update in real-time
**Priority**: MUST HAVE

- Log messages shall appear immediately in upper section
- Progress bars & counters shall reflect current state without delay
- Updates shall occur without screen flicker or tearing
- Terminal shall remain responsive during heavy logging

### FR5: Verbose Mode Support

**Description**: Enhanced UI shall work in both normal and verbose modes
**Priority**: MUST HAVE

- Verbose mode shall show DEBUG messages in log panel
- Normal mode shall show INFO/WARNING/ERROR only
- Mode switch shall not break the UI layout
- Buffer size may differ based on verbosity level

---

## 5. Non-Functional Requirements

### NFR1: Performance

- Log buffering shall add < 5ms overhead per message
- Display updates shall complete within 50ms
- Memory usage for log buffer shall not exceed 10MB
- No measurable impact on migration throughput

### NFR2: Compatibility

- Shall work on Linux, macOS, and Windows terminals
- Shall support terminal widths from 80-300 columns
- Shall support terminal heights from 24-100 rows
- Shall gracefully degrade if Rich features are unavailable

### NFR3: Maintainability

- Changes shall be isolated to logger and coordinator components
- Existing log calls shall continue to work without modification
- Unit tests shall be provided for new functionality
- Code shall follow existing project patterns

### NFR4: Usability

- UI shall be intuitive without documentation
- Log levels shall be color-coded consistently
- Progress bars shall use clear labels and percentages
- Terminal resize shall be handled gracefully

---

## 6. Technical Approach

### 6.1 Architecture

```
┌─────────────────────────────────────────────────┐
│  RichLogger (Enhanced)                          │
│  - Ring buffer for messages                     │
│  - get_recent_logs() method                     │
│  - Buffered vs. direct output modes             │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  BaseMigrationCoordinator                       │
│  - rich.live.Live for persistent display        │
│  - Two-section layout management                │
│  - Update orchestration                         │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  Terminal Display (Rich)                        │
│  ┌───────────────────────────────────────────┐  │
│  │ Log Panel (scrollable)                    │  │
│  │ ────────────────────────────────────────  │  │
│  │ INFO: Starting migration...               │  │
│  │ INFO: Fetching clients page 1             │  │
│  │ WARNING: Rate limit approaching           │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │ Progress Bars (fixed)                     │  │
│  │ ────────────────────────────────────────  │  │
│  │ Clients:  ████████░░░░  450/1000 (45%)    │  │
│  │ Invoices: ██░░░░░░░░░░  120/2000 (6%)     │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 6.2 Key Technologies

- **rich.live.Live**: For persistent, updating display
- **rich.layout.Layout** OR **rich.console.Group**: For section composition
- **rich.panel.Panel**: For log window with borders
- **rich.progress.Progress**: Existing progress bars (no change)
- **collections.deque**: For efficient ring buffer

### 6.3 Implementation Components

#### Component 1: Enhanced RichLogger

```python
class RichLogger(Logger):
    def __init__(self, verbose: bool = False, buffer_size: int = 75):
        self.verbose = verbose
        self.buffer_size = buffer_size
        self.log_buffer = deque(maxlen=buffer_size)
        self.buffered_mode = False  # Toggle for new behavior
        # ... existing code

    def enable_buffered_mode(self) -> None:
        """Enable buffered logging for enhanced UI"""

    def get_recent_logs(self) -> list[str]:
        """Return recent log messages as formatted strings"""

    def _add_to_buffer(self, level: str, message: str) -> None:
        """Add formatted message to ring buffer"""
```

#### Component 2: Migration Coordinator Display Logic

```python
class BaseMigrationCoordinator:
    def migrate(self) -> MigrationSummary:
        # Enable buffered mode
        self._logger.enable_buffered_mode()

        # Create Live display with layout
        with Live(self._create_layout(), refresh_per_second=4) as live:
            # Run migration
            # Update layout on each log/progress change

    def _create_layout(self) -> Group:
        """Create two-section layout with logs and progress"""

    def _update_display(self, live: Live) -> None:
        """Update both log panel and progress bars"""
```

---

## 7. Files to Modify

| File | Changes | Complexity |
|------|---------|------------|
| `src/loggers/rich_logger.py` | Add buffering, get_recent_logs() | Medium |
| `src/interfaces/logger.py` | Add protocol methods for buffering | Low |
| `src/coordinators/base_migration_coordinator.py` | Refactor display logic with Live | High |
| `tests/test_rich_logger.py` | Add tests for buffering | Medium |
| `tests/test_migration_coordinator.py` | Update for new display behavior | Low |

---

## 8. Success Criteria

### Must Have (MVP)

- [ ] Progress bars stay fixed at bottom during entire migration
- [ ] Logs appear in scrollable window above progress bars
- [ ] No visual flickering or jumping
- [ ] Works in both verbose and normal modes
- [ ] Log buffer is configurable via constructor
- [ ] All existing functionality continues to work

### Nice to Have (Future)

- [ ] Log filtering by level (show only errors/warnings)
- [ ] Ability to pause/resume display updates
- [ ] Export logs to file during execution
- [ ] Color themes for different migration states
- [ ] Terminal resize handling with layout adjustment

---

## 9. Open Questions & Decisions

### Question 1: Log Buffer Size
**Question**: What should the default buffer size be?
**Options**:
- A) 50 messages (minimal memory, might lose context)
- B) 75 messages (balanced)
- C) 100 messages (more history, more memory)
- D) Adaptive based on terminal height

**Decision**: TBD

---

### Question 2: Layout Library
**Question**: Should we use `rich.layout.Layout` or `rich.console.Group`?
**Options**:
- A) `Layout` - More structured, supports resize, more complex
- B) `Group` - Simpler, less overhead, fixed sizing

**Decision**: TBD (suggest starting with Group for simplicity)

---

### Question 3: Backward Compatibility
**Question**: Should enhanced UI be opt-in or default?
**Options**:
- A) Default ON, flag to disable (--simple-ui)
- B) Default OFF, flag to enable (--enhanced-ui)
- C) Auto-detect based on terminal capabilities

**Decision**: TBD

---

### Question 4: Log Retention After Migration
**Question**: What happens to buffered logs when migration completes?
**Options**:
- A) Dump all to console
- B) Save to file automatically
- C) Discard (already in report files)
- D) Ask user

**Decision**: TBD

---

## 10. Implementation Phases

### Phase 1: Foundation (Estimated: 2-3 hours)
- [ ] Add log buffering to RichLogger
- [ ] Add buffer configuration and retrieval methods
- [ ] Write unit tests for buffering logic
- [ ] Update Logger protocol

### Phase 2: Layout Implementation (Estimated: 3-4 hours)
- [ ] Create two-section layout in coordinator
- [ ] Integrate with Live display
- [ ] Wire up log buffer to upper panel
- [ ] Ensure progress bars work in lower section

### Phase 3: Testing & Refinement (Estimated: 2-3 hours)
- [ ] Test with real migration (small dataset)
- [ ] Test with real migration (large dataset)
- [ ] Verify verbose mode
- [ ] Test terminal resize behavior
- [ ] Performance profiling

### Phase 4: Polish & Documentation (Estimated: 1-2 hours)
- [ ] Add configuration options
- [ ] Update CLI help text if needed
- [ ] Write user-facing documentation
- [ ] Code review and cleanup

**Total Estimated Effort**: 8-12 hours

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Rich library compatibility issues | Low | High | Thorough testing, fallback to simple mode |
| Performance degradation | Medium | Medium | Profile early, optimize buffer operations |
| Terminal compatibility problems | Medium | High | Test on multiple platforms, graceful degradation |
| Breaking existing CLI behavior | Low | High | Comprehensive testing, feature flag |
| Increased code complexity | High | Medium | Good documentation, modular design |

---

## 12. Testing Strategy

### Unit Tests
- RichLogger buffering operations
- Buffer overflow behavior
- Log formatting preservation
- Get recent logs functionality

### Integration Tests
- Full migration with enhanced UI
- Log messages appear correctly
- Progress updates work correctly
- Mode switching (verbose/normal)

### Manual Tests
- Different terminal sizes (80x24, 120x40, 200x60)
- Different platforms (Linux, macOS, Windows)
- Long-running migrations (visual stability)
- High-frequency logging (performance)

---

## 13. Future Enhancements

Ideas for future iterations (not in scope for initial implementation):

1. **Interactive Controls**: Pause/resume migration with keyboard shortcuts
2. **Log Search**: Filter logs in real-time by keyword or level
3. **Historical View**: Navigate through log history with arrow keys
4. **Export During Execution**: Save logs to file while migration runs
5. **Split Views**: Show different entity migrations in side-by-side panels
6. **Metrics Dashboard**: Real-time graphs of throughput, API usage
7. **Error Highlighting**: Flash or highlight errors in log panel

---

## 14. References

- [Rich Live Display Documentation](https://rich.readthedocs.io/en/latest/live.html)
- [Rich Layout Documentation](https://rich.readthedocs.io/en/latest/layout.html)
- [Rich Group Documentation](https://rich.readthedocs.io/en/latest/group.html)
- [Rich Panel Documentation](https://rich.readthedocs.io/en/latest/panel.html)
- [Python deque Documentation](https://docs.python.org/3/library/collections.html#collections.deque)

---

## 15. Collaboration Notes

### How to Contribute to This Document

1. Add comments or suggestions as markdown comments
2. Update "Last Updated" date when making changes
3. Move decisions from "Open Questions" to appropriate sections
4. Update implementation phases as work progresses

### Discussion Topics

<!-- Add discussion points here -->

- Should we support color themes?
- Should buffer size be configurable via CLI flag?
- Do we need different layouts for narrow terminals?

---

## Appendix A: Example Terminal Output

### Current Behavior (Problem)
```
INFO: Starting migration process
INFO: Fetching clients page 1
Migrating clients... ████████░░░░  45/100 (45%)
INFO: Fetching clients page 2
INFO: Rate limit approaching
Migrating clients... █████████░░░  55/100 (55%)
INFO: Fetching clients page 3
Migrating invoices... ██░░░░░░░░░░  12/200 (6%)
INFO: Throttled, waiting 2s
...
```

### Proposed Behavior (Solution)
```
┌─ Migration Logs ────────────────────────────────────────┐
│ INFO: Starting migration process                        │
│ INFO: Fetching clients page 1                           │
│ INFO: Fetching clients page 2                           │
│ INFO: Rate limit approaching                            │
│ INFO: Fetching clients page 3                           │
│ WARNING: Throttled, waiting 2s                          │
│ INFO: Resuming client extraction                        │
│ INFO: Fetching invoices page 1                          │
└─────────────────────────────────────────────────────────┘
┌─ Progress ──────────────────────────────────────────────┐
│ Clients:    █████████░░░  55/100 (55%)  ETA: 2m 15s    │
│ Invoices:   ██░░░░░░░░░░  12/200 (6%)   ETA: 8m 30s    │
└─────────────────────────────────────────────────────────┘
```

---

**End of Document**
