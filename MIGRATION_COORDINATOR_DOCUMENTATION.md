# Migration Coordinator Documentation

## Overview

This document provides comprehensive guidance for using the new Rich-based migration coordinator system in TightBeam v2. The migration coordinator has been refactored to provide enhanced visual feedback, better error handling, and a unified Rich-based user interface.

## Architecture Changes

### Before: Multiple Coordinator Classes

```python
# Old system (removed)
MigrationCoordinator          # Console/logging based
BaseMigrationCoordinator      # Abstract base with template methods
RichMigrationCoordinator      # Rich UI implementation
```

### After: Unified Rich-Based System

```python
# New system (current)
BaseMigrationCoordinator      # Concrete Rich-based coordinator
RichMigrationCoordinator      # Thin compatibility wrapper
```

## New BaseMigrationCoordinator

The `BaseMigrationCoordinator` is now the primary migration coordinator class with built-in Rich UI components.

### Key Features

- **Rich Progress Bars**: Custom columns with transfer speed, time elapsed/remaining
- **Error Panels**: Styled error display with color-coded severity levels
- **Multi-task Support**: Concurrent progress tracking for different entity types
- **Environment Adaptation**: Automatic TTY/non-TTY environment detection
- **Interruption Handling**: Graceful Ctrl+C handling with clean shutdown

### Class Structure

```python
class BaseMigrationCoordinator:
    """
    Base class for migration coordinators with Rich UI and Template Method pattern.
    
    Provides shared migration workflow logic with Rich-based progress and error reporting.
    All progress display and error reporting uses Rich exclusively for enhanced
    visual feedback during migration operations.
    """
```

## Usage Patterns

### Basic Usage

```python
from src.coordinators import BaseMigrationCoordinator

# Create coordinator with required dependencies
coordinator = BaseMigrationCoordinator(
    jobber_client=jobber_client,
    entity_mapper=entity_mapper,
    repository=repository,
    logger=logger,
)

# Run migration with Rich UI
summary = coordinator.migrate()
```

### Advanced Usage with Optional Components

```python
coordinator = BaseMigrationCoordinator(
    jobber_client=jobber_client,
    entity_mapper=entity_mapper,
    repository=repository,
    logger=logger,
    # Optional extractors for enhanced functionality
    notes_extractor=notes_extractor,
    quotes_extractor=quotes_extractor,
    attachment_downloader=attachment_downloader,
    # Configuration and optimization
    config_manager=config_manager,
    resume=True,
    enable_adaptive_optimization=True,
)

summary = coordinator.migrate(include_extended_entities=True)
```

### CLI Integration

```python
# In CLI commands (src/cli/migrate.py)
from src.coordinators import BaseMigrationCoordinator

# Create unified Rich-based migration coordinator
migration_coordinator = BaseMigrationCoordinator(
    jobber_client=jobber_client,
    entity_mapper=entity_mapper,
    repository=repository,
    logger=logger,
)

# Run migration with enhanced visual feedback
summary = migration_coordinator.migrate()
```

## Rich UI Components

### Progress Bar Features

The new progress bars include custom columns optimized for migration workflows:

```python
Progress(
    SpinnerColumn(),                    # Animated spinner
    TextColumn(                         # Task description with styling
        "[progress.description]{task.description}",
        table_column=Column(ratio=2, min_width=20),
    ),
    BarColumn(                          # Progress bar with custom styling
        bar_width=None,
        complete_style="green",
        finished_style="bright_green",
        table_column=Column(ratio=3),
    ),
    MofNCompleteColumn(                 # "N/M" completion display
        table_column=Column(min_width=12, justify="right")
    ),
    TextColumn("•", justify="center"),  # Separator
    TransferSpeedColumn(                # Transfer speed in bytes/s
        table_column=Column(min_width=12, justify="right")
    ),
    TextColumn("•", justify="center"),  # Separator
    TimeElapsedColumn(                  # Time elapsed
        table_column=Column(min_width=8, justify="right")
    ),
    TextColumn("/"),                    # Separator
    TimeRemainingColumn(                # Estimated time remaining
        table_column=Column(min_width=8, justify="right")
    ),
    console=console,
    expand=True,
)
```

### Error Panel System

The coordinator provides styled error panels for different error types:

```python
# Error panel styles
ERROR_STYLES = {
    "error": "red",      # Critical errors, exceptions
    "warning": "yellow", # API throttling, recoverable issues  
    "info": "blue"       # Informational messages
}
```

#### Error Panel Examples

```python
# API Communication Error (Warning for throttling, Error otherwise)
self._display_error_panel(
    "API Communication Error",
    f"Failed to fetch clients page {page_number}: {str(e)}",
    "warning" if "throttled" in str(e).lower() else "error"
)

# Data Transformation Error
self._display_error_panel(
    "Data Transformation Error",
    f"Failed to process clients data on page {page_number}: {str(e)}",
    "error"
)

# Database Error
self._display_error_panel(
    "Database Error",
    f"Failed to save clients from page {page_number}: {str(e)}",
    "error"
)
```

### Exception Display

Rich-formatted exception tracebacks with customizable detail levels:

```python
self._print_exception(exception)
# Uses Rich's console.print_exception() with:
# - show_locals=False
# - max_frames=5  
# - word_wrap=True
# - extra_lines=2
```

## Indeterminate Progress Support

For tasks with unknown totals, the coordinator supports indeterminate progress:

```python
# Add indeterminate task
task_id = self._add_indeterminate_task(
    progress, 
    "clients", 
    "[cyan]Discovering client count..."
)

# Start with total when known
self._start_task(progress, task_id, total=discovered_count)

# Continue with normal updates
self._update_task_progress(progress, task_id, description, completed, total)
```

## Migration from Old System

### Breaking Changes

1. **Removed Classes**:
   - `MigrationCoordinator` (console-based) - **DELETED**
   - Abstract methods removed from `BaseMigrationCoordinator`

2. **Import Changes**:

   ```python
   # Old (no longer works)
   from src.coordinators import MigrationCoordinator
   
   # New (recommended)
   from src.coordinators import BaseMigrationCoordinator
   
   # Also works (backward compatibility)
   from src.coordinators import RichMigrationCoordinator
   ```

3. **Constructor Changes**:
   - `BaseMigrationCoordinator` is now concrete (no abstract methods)
   - All Rich UI functionality built-in
   - Same constructor signature maintained for compatibility

### Migration Steps

#### Step 1: Update Imports

```python
# Before
from src.coordinators import MigrationCoordinator

# After  
from src.coordinators import BaseMigrationCoordinator
```

#### Step 2: Update Instantiation

```python
# Before
coordinator = MigrationCoordinator(...)

# After
coordinator = BaseMigrationCoordinator(...)
```

#### Step 3: Update CLI Integration

```python
# Before (in CLI files)
from src.coordinators import RichMigrationCoordinator
migration_coordinator = RichMigrationCoordinator(...)

# After (recommended)
from src.coordinators import BaseMigrationCoordinator  
migration_coordinator = BaseMigrationCoordinator(...)
```

### Backward Compatibility

For existing code using `RichMigrationCoordinator`, no changes are required:

```python
# This still works (backward compatibility maintained)
from src.coordinators import RichMigrationCoordinator
coordinator = RichMigrationCoordinator(...)
```

However, `BaseMigrationCoordinator` is now the recommended approach as it's the direct implementation.

## Environment Behavior

### TTY Environments (Interactive Terminals)

- Full Rich features enabled (colors, animations, interactive elements)
- Real-time progress bar updates with spinners
- Colored error panels with full styling
- Optimal user experience for development and manual operations

### Non-TTY Environments (CI/CD, Pipes, Redirects)

- Rich automatically adapts by disabling animations
- Progress information displayed but may be static
- Error panels maintain structure but may lose some styling
- Output remains machine-readable and parseable
- Suitable for automated deployments and logging

### Testing Environments

Both environments have been thoroughly tested:

```bash
# TTY testing
python migration_script.py

# Non-TTY testing  
python migration_script.py > migration.log 2>&1
```

## Error Handling Best Practices

### Use Appropriate Error Types

```python
try:
    # Migration operation
    pass
except JobberApiError as e:
    # API-specific error handling
    if "throttled" in str(e).lower():
        self._display_error_panel("API Rate Limit", str(e), "warning")
    else:
        self._display_error_panel("API Error", str(e), "error")
        
except MappingError as e:
    # Data transformation error
    self._display_error_panel("Data Error", str(e), "error")
    
except RepositoryError as e:
    # Database error
    self._display_error_panel("Database Error", str(e), "error")
    
except Exception as e:
    # Unexpected error with full traceback
    self._display_error_panel("Unexpected Error", str(e), "error")
    self._print_exception(e)
```

### Progressive Error Display

For page-level operations, display specific context:

```python
error_msg = f"Error processing {entity_type} page {page_number}: {e}"
self._logger.error(error_msg)

self._display_error_panel(
    f"{entity_type.title()} Processing Error",
    f"Failed on page {page_number} of {total_pages}: {str(e)}",
    "error"
)
```

## Performance Considerations

### Progress Bar Refresh Rate

```python
# Optimized refresh rate (4 refreshes/second)
Live(display_obj, console=self._console, refresh_per_second=4)
```

### Resource Usage

- Rich displays have minimal performance impact
- Progress updates are efficient and non-blocking
- Memory usage remains stable during long migrations
- No significant CPU overhead from Rich rendering

### Scalability

- Multi-task progress displays scale well (tested with multiple concurrent tasks)
- Custom columns don't impact performance
- Error panel display doesn't slow down migration operations

## Testing

### Unit Testing

```python
# Test Rich components work correctly
from rich.console import Console
from rich.progress import Progress

def test_rich_coordinator():
    console = Console()
    coordinator = BaseMigrationCoordinator(...)
    
    # Test progress display creation
    progress = coordinator._create_progress_display()
    assert isinstance(progress, Progress)
    
    # Test error panel display
    coordinator._display_error_panel("Test Error", "Test message", "error")
```

### Integration Testing

Use the provided test scripts:

```bash
# Test all environments
python test_rich_coordinator_simple.py

# Test specific scenarios
python test_interruption.py
```

### Environment Testing

```bash
# TTY environment
python your_migration_script.py

# Non-TTY environment  
python your_migration_script.py > output.log 2>&1

# Background execution
nohup python your_migration_script.py &
```

## Examples

### Basic Migration Script

```python
#!/usr/bin/env python3
"""Basic migration script using Rich coordinator."""

from src.coordinators import BaseMigrationCoordinator
from src.clients import JobberClient
from src.mappers import EntityMapper  
from src.repositories import Repository
from src.loggers import RichLogger

def main():
    # Setup dependencies
    logger = RichLogger()
    repository = Repository("migration.db")
    jobber_client = JobberClient()
    entity_mapper = EntityMapper()
    
    # Create Rich-based coordinator
    coordinator = BaseMigrationCoordinator(
        jobber_client=jobber_client,
        entity_mapper=entity_mapper,
        repository=repository,
        logger=logger,
    )
    
    try:
        # Run migration with Rich UI
        summary = coordinator.migrate()
        
        # Display results
        logger.info(f"Migration completed: {summary.clients_processed} clients processed")
        
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    main()
```

### Advanced Migration with Resume

```python
#!/usr/bin/env python3
"""Advanced migration script with resume capability."""

from src.coordinators import BaseMigrationCoordinator
# ... other imports

def main():
    # Setup with advanced features
    coordinator = BaseMigrationCoordinator(
        jobber_client=jobber_client,
        entity_mapper=entity_mapper,
        repository=repository,
        logger=logger,
        resume=True,  # Enable resume functionality
        enable_adaptive_optimization=True,  # Performance optimization
    )
    
    try:
        # Run comprehensive migration
        summary = coordinator.migrate(include_extended_entities=True)
        
        # Log detailed results
        logger.info(f"""
        Migration Summary:
        - Clients: {summary.clients_processed}
        - Invoices: {summary.invoices_processed}  
        - Total Duration: {summary.duration}
        - Errors: {len(summary.errors)}
        """)
        
    except Exception as e:
        coordinator._display_error_panel(
            "Migration Failed", 
            f"Critical error: {str(e)}", 
            "error"
        )
        coordinator._print_exception(e)
        raise

if __name__ == "__main__":
    main()
```

## Troubleshooting

### Common Issues

1. **Progress bars not displaying**:
   - Check TTY environment: `python -c "import sys; print(sys.stdout.isatty())"`
   - Force terminal mode: `Console(force_terminal=True)`

2. **Error panels not styled**:
   - Ensure Rich library is installed: `pip install rich`
   - Check terminal color support

3. **Performance issues**:
   - Reduce refresh rate: `refresh_per_second=2`
   - Disable progress for very fast operations

### Debugging

```python
# Enable Rich debug mode
import rich
rich.print("Rich version:", rich.__version__)

# Test console capabilities  
from rich.console import Console
console = Console()
console.print("Color test", style="bold red")
```

## Future Considerations

### Planned Enhancements

1. **Additional Progress Columns**: Data rate, ETA accuracy improvements
2. **Custom Themes**: Configurable color schemes for different environments
3. **Progress Persistence**: Save/restore progress state across restarts
4. **Advanced Error Recovery**: Interactive error resolution prompts

### Extension Points

The coordinator can be extended for custom use cases:

```python
class CustomMigrationCoordinator(BaseMigrationCoordinator):
    """Custom coordinator with additional features."""
    
    def _create_progress_display(self):
        """Override to add custom columns."""
        progress = super()._create_progress_display()
        # Add custom columns
        return progress
        
    def _display_error_panel(self, title, message, error_type="error"):
        """Override for custom error handling."""
        super()._display_error_panel(title, message, error_type)
        # Add custom error logging/notifications
```

## Conclusion

The new Rich-based migration coordinator provides a significant improvement in user experience while maintaining full backward compatibility. The unified design eliminates complexity while adding powerful visual feedback and error handling capabilities.

For any questions or issues, refer to the test suite in `test_rich_coordinator_simple.py` or the comprehensive testing documentation in `RICH_TESTING_RESULTS.md`.
