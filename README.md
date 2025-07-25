# TightBeam v2 - Jobber Data Migration Tool

A powerful, user-friendly command-line tool for migrating data from Jobber to other systems, featuring a modern Rich-based interface with real-time progress tracking and enhanced error reporting.

## Features

### ✨ Rich Interactive Interface

- **Real-time progress bars** with transfer speed, time elapsed, and time remaining
- **Colored error panels** with severity-based styling (error/warning/info)
- **Professional exception display** with full stack traces
- **Multi-task progress tracking** for complex operations
- **TTY and non-TTY compatibility** for both interactive and CI/CD environments

### 🚀 Advanced Migration Capabilities

- **Incremental migration** with resume support
- **Adaptive optimization** for performance tuning
- **OAuth2 authentication** with automatic token refresh
- **Rate limiting** and throttling protection
- **Comprehensive error handling** and recovery

### 🛠 Developer-Friendly Architecture

- **Dependency injection** for easy testing and customization
- **Modular design** with clear separation of concerns
- **Rich logging** with structured output
- **Comprehensive test suite** with 100% pass rate

## Quick Start

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd tightbeam-v2
```

2. Install dependencies using Poetry:

```bash
poetry install
```

3. Set up authentication:

```bash
poetry run tightbeam oauth init
```

### Basic Usage

1. **Initialize OAuth authentication:**

```bash
poetry run tightbeam oauth init
# Follow the displayed instructions to set up your environment variables
```

2. **Run a migration:**

```bash
poetry run tightbeam migrate start
```

3. **Resume a migration:**

```bash
poetry run tightbeam migrate start --resume
```

## Migration Coordinator Architecture

TightBeam v2 uses a **unified Rich-based migration coordinator** system that provides:

### `BaseMigrationCoordinator`

The primary migration coordinator with built-in Rich UI support:

```python
from src.coordinators import BaseMigrationCoordinator

# Create coordinator with dependencies
coordinator = BaseMigrationCoordinator(
    jobber_client=jobber_client,
    entity_mapper=entity_mapper,
    repository=repository,
    logger=logger,
    resume=True  # Enable resume functionality
)

# Run migration with Rich progress bars
summary = coordinator.migrate()
```

### `RichMigrationCoordinator`

A backward-compatible wrapper that inherits all functionality from `BaseMigrationCoordinator`:

```python
from src.coordinators import RichMigrationCoordinator

# Drop-in replacement for existing code
coordinator = RichMigrationCoordinator(
    # Same parameters as BaseMigrationCoordinator
)
```

## Rich UI Features

### Progress Bars

- **Multi-column display**: Spinner, description, progress bar, completion ratio
- **Transfer speed**: Real-time processing rate
- **Time tracking**: Elapsed time and estimated time remaining
- **Custom styling**: Color-coded progress indicators

### Error Reporting

- **Severity levels**:
  - 🔴 **Error** (red): Critical failures and exceptions
  - 🟡 **Warning** (yellow): API throttling, recoverable issues
  - 🔵 **Info** (blue): Important status updates
- **Structured panels**: Bordered, padded error displays
- **Exception tracing**: Full stack traces with syntax highlighting

### Environment Compatibility

- **TTY environments**: Full Rich rendering with colors and animations
- **Non-TTY environments**: Graceful fallback to plain text
- **CI/CD support**: Optimized output for automated environments

## CLI Commands

### OAuth Management

```bash
# Initialize OAuth setup
poetry run tightbeam oauth init

# Get current authentication status
poetry run tightbeam oauth status
```

### Migration Operations

```bash
# Start a new migration
poetry run tightbeam migrate start

# Resume an interrupted migration
poetry run tightbeam migrate start --resume

# Dry run mode (preview only)
poetry run tightbeam migrate start --dry-run

# Advanced options
poetry run tightbeam migrate start \
    --resume \
    --adaptive-optimization \
    --optimization-level 3
```

## Configuration

### Environment Variables

```bash
# Required OAuth credentials
JOBBER_CLIENT_ID=your_client_id
JOBBER_CLIENT_SECRET=your_client_secret
JOBBER_REDIRECT_URI=http://localhost:8080/callback
JOBBER_TOKEN=your_access_token  # Optional: skip OAuth flow

# Optional database configuration
DATABASE_URL=sqlite:///tightbeam.db
```

### .env File Support

Create a `.env` file in the project root:

```env
JOBBER_CLIENT_ID=your_client_id
JOBBER_CLIENT_SECRET=your_client_secret
JOBBER_REDIRECT_URI=http://localhost:8080/callback
```

## Migration from Legacy System

If you're upgrading from an older version of TightBeam:

### Code Updates

```python
# OLD (no longer available)
from src.coordinators import MigrationCoordinator

# NEW (Rich-based)
from src.coordinators import BaseMigrationCoordinator
```

### Benefits of Migration

- **Enhanced user experience**: Professional Rich UI
- **Better error handling**: Color-coded error panels
- **Improved performance**: Optimized Rich rendering
- **Future-proof**: Modern architecture for easy extension

For detailed migration instructions, see [MIGRATION_COORDINATOR_DOCUMENTATION.md](MIGRATION_COORDINATOR_DOCUMENTATION.md).

## Development

### Project Structure

```
src/
├── auth/              # OAuth2 authentication
├── cli/               # Command-line interface
├── coordinators/      # Migration coordination (Rich-based)
├── clients/           # External API clients
├── mappers/           # Data transformation
├── repositories/      # Data persistence
└── loggers/           # Rich logging system
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src

# Run specific test categories
poetry run pytest tests/unit/
poetry run pytest tests/integration/
```

### Code Quality

```bash
# Linting
poetry run ruff check src/

# Type checking
poetry run mypy src/

# Formatting
poetry run black src/
```

## Architecture Documentation

For detailed technical documentation:

- **[Migration Coordinator Documentation](MIGRATION_COORDINATOR_DOCUMENTATION.md)**: Complete usage guide
- **[Architecture Updates](ARCHITECTURE_UPDATES.md)**: Technical architecture changes
- **[Rich Testing Results](RICH_TESTING_RESULTS.md)**: Environment compatibility testing

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make changes with proper tests
4. Run the test suite: `poetry run pytest`
5. Submit a pull request

## License

[Add your license information here]

## Support

For issues and questions:

1. Check the documentation files in the repository
2. Review the test suite for usage examples
3. Create an issue on the project repository

---

**Built with Rich UI for an enhanced command-line experience** ✨
