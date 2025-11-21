# Migration Coordinator Documentation

## Overview

TightBeam v2 provides three types of migration coordinators for orchestrating data extraction from the Jobber API:

1. **BaseMigrationCoordinator** - Full single-pass migration with Rich UI
2. **MapModeCoordinator** - Discovery pass (map mode) for multi-pass workflow
3. **ExtractModeCoordinator** - Extraction pass (extract mode) for multi-pass workflow

This document covers programmatic usage of these coordinators for custom integration scenarios.

## BaseMigrationCoordinator

The primary coordinator for single-pass migrations with built-in Rich UI support.

### Basic Usage

```python
from src.coordinators import BaseMigrationCoordinator
from src.clients import JobberClient
from src.mappers import EntityMapper
from src.repositories import SqliteRepository
from src.loggers import RichLogger

# Create dependencies
jobber_client = JobberClient(access_token="your_token")
entity_mapper = EntityMapper()
repository = SqliteRepository(database_url="sqlite:///tightbeam.db")
logger = RichLogger()

# Create coordinator
coordinator = BaseMigrationCoordinator(
    jobber_client=jobber_client,
    entity_mapper=entity_mapper,
    repository=repository,
    logger=logger,
    resume=False  # Set True to resume from checkpoint
)

# Run migration
summary = coordinator.migrate()

# Access results
print(f"Total entities: {summary.total_entities}")
print(f"Failed entities: {summary.failed_entities}")
```

### Constructor Parameters

- `jobber_client: JobberClient` - Client for Jobber GraphQL API
- `entity_mapper: EntityMapper` - Mapper for transforming API responses to domain models
- `repository: Repository` - Repository for database operations
- `logger: Logger` - Logger for structured output and progress tracking
- `resume: bool = False` - Enable resume from previous run

### Methods

#### `migrate() -> MigrationSummary`

Executes the complete migration process for all entity types.

**Returns:** `MigrationSummary` object with migration statistics

**Example:**
```python
summary = coordinator.migrate()
print(f"Processed: {summary.total_entities}")
print(f"Errors: {summary.error_count}")
```

### Rich UI Features

The coordinator automatically provides:

- **Progress bars** with real-time updates
- **Color-coded error panels** (red/yellow/blue)
- **Exception tracing** with syntax highlighting
- **TTY detection** for CI/CD compatibility

Progress bars show:
- Spinner animation
- Task description
- Progress bar
- Completion ratio (e.g., "45/100")
- Transfer speed (entities/sec)
- Time elapsed
- Time remaining estimate

## MapModeCoordinator

Coordinator for the discovery pass in multi-pass migrations.

### Basic Usage

```python
from src.coordinators.map_mode_coordinator import MapModeCoordinator
from src.clients import JobberClient
from src.repositories import SqliteRepository
from src.loggers import RichLogger

# Create dependencies
jobber_client = JobberClient(access_token="your_token")
repository = SqliteRepository(database_url="sqlite:///tightbeam.db")
logger = RichLogger()

# Create map coordinator
map_coordinator = MapModeCoordinator(
    jobber_client=jobber_client,
    repository=repository,
    logger=logger,
    enable_adaptive_optimization=False
)

# Run map pass
result = map_coordinator.run_map_pass(
    entity_types=["clients", "invoices", "jobs"],
    label="Q1-2025-discovery"
)

# Access snapshot info
snapshot_id = result["snapshot_id"]
entity_counts = result["entity_counts"]
print(f"Snapshot ID: {snapshot_id}")
print(f"Discovered {entity_counts['clients']} clients")
```

### Constructor Parameters

- `jobber_client: JobberClient` - Client for Jobber GraphQL API
- `repository: Repository` - Repository for database operations
- `logger: Logger` - Logger for structured output
- `config_manager: ConfigManagerImpl | None` - Optional config manager for pagination settings
- `enable_adaptive_optimization: bool = False` - Enable adaptive performance tuning

### Methods

#### `run_map_pass(entity_types: List[str], label: str | None = None) -> dict`

Executes map mode extraction for specified entity types.

**Parameters:**
- `entity_types: List[str]` - Entity types to map (e.g., `["clients", "invoices"]`)
- `label: str | None` - Optional human-friendly label for snapshot

**Returns:** Dictionary with:
- `snapshot_id: str` - UUID of created snapshot
- `entity_counts: dict` - Count per entity type
- `total_entities: int` - Total entities discovered
- `timestamp: str` - ISO8601 timestamp

**Example:**
```python
result = map_coordinator.run_map_pass(
    entity_types=["clients", "invoices"],
    label="pre-migration"
)
print(f"Created snapshot: {result['snapshot_id']}")
```

#### `supported_entity_types() -> List[str]` (classmethod)

Returns list of entity types supported by map mode.

**Returns:** Sorted list of entity type names

**Example:**
```python
types = MapModeCoordinator.supported_entity_types()
print(f"Supported types: {types}")
# Output: ['clients', 'expenses', 'invoices', 'jobs', ...]
```

### Adaptive Optimization

Enable adaptive tuning for automatic performance adjustment:

```python
from src.config import ConfigManagerImpl

config_manager = ConfigManagerImpl()

map_coordinator = MapModeCoordinator(
    jobber_client=jobber_client,
    repository=repository,
    logger=logger,
    config_manager=config_manager,
    enable_adaptive_optimization=True
)

result = map_coordinator.run_map_pass(entity_types=["clients"])

# Adaptive optimizer adjusts:
# - Page sizes based on throttling
# - Request delays to stay under rate limits
# - Logs adjustments to console
```

**Note:** Map mode does NOT persist adaptive settings to config file.

## ExtractModeCoordinator

Coordinator for the extraction pass in multi-pass migrations.

### Basic Usage

```python
from src.coordinators.extract_mode_coordinator import ExtractModeCoordinator
from src.clients import JobberClient
from src.mappers import EntityMapper
from src.repositories import SqliteRepository
from src.loggers import RichLogger

# Create dependencies
jobber_client = JobberClient(access_token="your_token")
entity_mapper = EntityMapper()
repository = SqliteRepository(database_url="sqlite:///tightbeam.db")
logger = RichLogger()

# Create extract coordinator
extract_coordinator = ExtractModeCoordinator(
    jobber_client=jobber_client,
    entity_mapper=entity_mapper,
    repository=repository,
    logger=logger,
    enable_adaptive_optimization=False
)

# Run extract pass
result = extract_coordinator.run_extract_pass(
    snapshot_id="550e8400-e29b-41d4-a716-446655440000",
    entity_types=["clients", "invoices"],
    resume=False
)

# Access results
print(f"Extracted {result['entities_extracted']} entities")
print(f"Failed: {result['entities_failed']}")
```

### Constructor Parameters

- `jobber_client: JobberClient` - Client for Jobber GraphQL API
- `entity_mapper: EntityMapper` - Mapper for transforming API responses
- `repository: Repository` - Repository for database operations
- `logger: Logger` - Logger for structured output
- `config_manager: ConfigManagerImpl | None` - Optional config manager
- `enable_adaptive_optimization: bool = False` - Enable adaptive tuning

### Methods

#### `run_extract_pass(snapshot_id: str, entity_types: List[str] | None = None, resume: bool = False) -> dict`

Executes extract mode for a map snapshot.

**Parameters:**
- `snapshot_id: str` - UUID of map snapshot to extract from
- `entity_types: List[str] | None` - Entity types to extract (None = all from snapshot)
- `resume: bool = False` - Resume from existing queues

**Returns:** Dictionary with:
- `snapshot_id: str` - Snapshot ID used
- `entities_extracted: int` - Count of successfully extracted entities
- `entities_failed: int` - Count of failed entities
- `attachment_downloads: int` - Count of downloaded attachments
- `timestamp: str` - ISO8601 timestamp

**Example:**
```python
# Full extraction
result = extract_coordinator.run_extract_pass(
    snapshot_id="550e8400-...",
    entity_types=None,  # Extract all types
    resume=False
)

# Selective extraction
result = extract_coordinator.run_extract_pass(
    snapshot_id="550e8400-...",
    entity_types=["clients"],  # Only clients
    resume=False
)

# Resume failed extraction
result = extract_coordinator.run_extract_pass(
    snapshot_id="550e8400-...",
    resume=True  # Skip 'done', retry 'failed'
)
```

### Queue Management

The extract coordinator manages work queues automatically:

**Initial Run (`resume=False`):**
1. Creates `extract_queue_item` records from `entity_inventory`
2. Creates `attachment_queue_item` records for attachments
3. Sets all items to `status='pending'`
4. Processes queues sequentially

**Resume Run (`resume=True`):**
1. Reuses existing queue records
2. Skips items with `status='done'`
3. Retries items with `status='failed'`
4. Updates `attempt_count` on retry

### Status Tracking

Entity and attachment status flow:

```
pending → in_progress → done (success)
                      → failed (error, can retry)
```

Query queue status:

```python
from src.models import ExtractQueueItem

# Get failed entities
failed = repository.query(
    ExtractQueueItem,
    filters={"status": "failed", "map_snapshot_id": snapshot_id}
)

for item in failed:
    print(f"{item.entity_type}/{item.entity_id}: {item.last_error}")
```

## Backward Compatibility

### RichMigrationCoordinator

A deprecated alias for `BaseMigrationCoordinator`:

```python
from src.coordinators import RichMigrationCoordinator

# Same as BaseMigrationCoordinator
coordinator = RichMigrationCoordinator(
    jobber_client=jobber_client,
    entity_mapper=entity_mapper,
    repository=repository,
    logger=logger
)
```

**Recommendation:** Use `BaseMigrationCoordinator` for new code.

## Service Factory Pattern

Use the `ServiceFactory` for dependency injection:

```python
from src.services import ServiceFactory

# Create all dependencies at once
factory = ServiceFactory(
    database_url="sqlite:///tightbeam.db",
    access_token="your_token"
)

# Get configured coordinator
coordinator = factory.create_migration_coordinator(resume=False)

# Or get individual services
jobber_client = factory.create_jobber_client()
repository = factory.create_repository()
logger = factory.create_logger()
```

## Error Handling

All coordinators provide comprehensive error handling:

### Migration Errors

```python
from src.coordinators import BaseMigrationCoordinator

try:
    coordinator = BaseMigrationCoordinator(...)
    summary = coordinator.migrate()

    if summary.failed_entities > 0:
        print(f"Migration completed with {summary.failed_entities} failures")
        for error in summary.errors:
            print(f"  {error.entity_type}/{error.entity_id}: {error.message}")
except Exception as e:
    print(f"Migration failed: {e}")
    # Exception includes full traceback in Rich display
```

### API Throttling

Coordinators handle throttling automatically:

```python
# Throttling is detected and handled via backoff
coordinator = BaseMigrationCoordinator(...)

# With adaptive optimization
map_coordinator = MapModeCoordinator(
    ...,
    enable_adaptive_optimization=True  # Auto-adjust on throttle
)
```

When throttling occurs:
1. Logger displays yellow warning panel
2. Coordinator applies exponential backoff
3. Adaptive optimizer adjusts page size/delay (if enabled)
4. Operation retries automatically

### Error Recovery

```python
# Resume from failures
coordinator = BaseMigrationCoordinator(..., resume=True)
summary = coordinator.migrate()

# For multi-pass, resume extract
extract_coordinator.run_extract_pass(
    snapshot_id="...",
    resume=True  # Retry failed entities only
)
```

## Logging and Progress

### Rich Logger

All coordinators use `RichLogger` for output:

```python
from src.loggers import RichLogger

logger = RichLogger()

# Automatic progress bars
with logger.progress("Migrating clients") as progress_task:
    # Progress updates automatically
    pass

# Error panels
logger.error("API Error", details="Rate limit exceeded")

# Info panels
logger.info("Migration Complete", details="1000 entities processed")
```

### Custom Logging

Implement custom logger by inheriting from `Logger` interface:

```python
from src.interfaces import Logger

class CustomLogger(Logger):
    def info(self, message: str, **kwargs) -> None:
        print(f"INFO: {message}")

    def error(self, message: str, **kwargs) -> None:
        print(f"ERROR: {message}")

    # Implement other Logger methods...

# Use custom logger
coordinator = BaseMigrationCoordinator(
    ...,
    logger=CustomLogger()
)
```

## Testing

### Unit Testing Coordinators

```python
import pytest
from unittest.mock import Mock
from src.coordinators import MapModeCoordinator

def test_map_coordinator():
    # Mock dependencies
    mock_client = Mock()
    mock_repository = Mock()
    mock_logger = Mock()

    # Create coordinator
    coordinator = MapModeCoordinator(
        jobber_client=mock_client,
        repository=mock_repository,
        logger=mock_logger
    )

    # Configure mocks
    mock_client.query.return_value = {"clients": [{"id": "1"}]}

    # Run map pass
    result = coordinator.run_map_pass(entity_types=["clients"])

    # Assert
    assert result["entity_counts"]["clients"] == 1
    mock_repository.save_map_snapshot.assert_called_once()
```

### Integration Testing

```python
from src.coordinators import BaseMigrationCoordinator
from src.services import ServiceFactory

def test_full_migration():
    # Use test database
    factory = ServiceFactory(
        database_url="sqlite:///test.db",
        access_token="test_token"
    )

    coordinator = factory.create_migration_coordinator()

    # Run migration
    summary = coordinator.migrate()

    # Verify
    assert summary.total_entities > 0
    assert summary.failed_entities == 0
```

## Performance Tuning

### Rate Limiting

Configure rate limiting via coordinator options:

```python
from src.config import ConfigManagerImpl

config_manager = ConfigManagerImpl()

# Set optimization level
config_manager.set_optimization_level("aggressive")  # 8 req/s
# config_manager.set_optimization_level("moderate")  # 6 req/s (default)
# config_manager.set_optimization_level("conservative")  # 4 req/s

coordinator = MapModeCoordinator(
    ...,
    config_manager=config_manager
)
```

### Adaptive Optimization

Enable adaptive tuning for automatic adjustment:

```python
coordinator = MapModeCoordinator(
    ...,
    enable_adaptive_optimization=True
)

# Coordinator will:
# - Monitor throttling events
# - Adjust page sizes dynamically
# - Adjust request delays
# - Log adjustments to console
```

### Page Size Control

Adjust page sizes via config manager:

```python
config_manager = ConfigManagerImpl()

# Set smaller pages for heavy entities
config_manager.set_page_size("clients", 25)  # Default: 50

# Set larger pages for light entities
config_manager.set_page_size("taxRates", 100)
```

## Advanced Patterns

### Multi-Pass with Custom Filtering

```python
# Map all entities
map_result = map_coordinator.run_map_pass(
    entity_types=MapModeCoordinator.supported_entity_types(),
    label="full-inventory"
)

snapshot_id = map_result["snapshot_id"]

# Extract high-priority entities first
extract_coordinator.run_extract_pass(
    snapshot_id=snapshot_id,
    entity_types=["clients", "invoices"]
)

# Extract remaining entities later
extract_coordinator.run_extract_pass(
    snapshot_id=snapshot_id,
    entity_types=["jobs", "quotes", "requests"]
)
```

### Snapshot Comparison

```python
# Create baseline snapshot
baseline = map_coordinator.run_map_pass(
    entity_types=["clients"],
    label="baseline-2025-01"
)

# Later, create comparison snapshot
comparison = map_coordinator.run_map_pass(
    entity_types=["clients"],
    label="comparison-2025-02"
)

# Compare in database
baseline_count = baseline["entity_counts"]["clients"]
comparison_count = comparison["entity_counts"]["clients"]
growth = comparison_count - baseline_count

print(f"Client growth: {growth} (+{growth/baseline_count*100:.1f}%)")
```

### Incremental Updates

```python
from datetime import datetime, timedelta

# Get entities updated in last 7 days
cutoff_date = (datetime.now() - timedelta(days=7)).isoformat()

# Map with temporal filter (requires custom extractor modification)
# Note: Not currently implemented, planned for future
```

## Best Practices

### 1. Use Dependency Injection

```python
# Good: Use ServiceFactory
factory = ServiceFactory(...)
coordinator = factory.create_migration_coordinator()

# Avoid: Manual dependency creation in production code
```

### 2. Always Handle Errors

```python
summary = coordinator.migrate()

if summary.failed_entities > 0:
    # Log failures
    # Alert operators
    # Consider retry logic
    pass
```

### 3. Label Important Snapshots

```python
map_coordinator.run_map_pass(
    entity_types=["clients"],
    label="pre-migration-audit"  # Easy to reference later
)
```

### 4. Use Resume for Long Operations

```python
# Initial run
extract_coordinator.run_extract_pass(snapshot_id=id, resume=False)

# If interrupted, resume
extract_coordinator.run_extract_pass(snapshot_id=id, resume=True)
```

### 5. Monitor Queue Status

```python
# Check extraction progress
from src.repositories import SqliteRepository

repository = SqliteRepository(...)
queue_status = repository.get_extract_queue_status(snapshot_id)

print(f"Pending: {queue_status['pending']}")
print(f"Done: {queue_status['done']}")
print(f"Failed: {queue_status['failed']}")
```

## See Also

- [Multi-Pass Migration Guide](MULTI_PASS_MIGRATION.md) - Complete workflow guide
- [Database Schema](DATABASE_SCHEMA.md) - Database structure reference
- [README](README.md) - CLI usage and quick start

---

**Migration Coordinator Documentation** - Programmatic usage guide for TightBeam v2 coordinators
