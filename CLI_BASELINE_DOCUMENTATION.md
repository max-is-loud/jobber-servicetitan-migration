# TightBeam v2 CLI Baseline Documentation

This document establishes the baseline for all CLI commands, options, and help messages before refactoring into modular subcommand structure.

## Main CLI Application

**Command:** `tightbeam --help`

```
Usage: tightbeam [OPTIONS] COMMAND [ARGS]...

TightBeam v2 - Jobber Data Migration Tool

Options:
  --help          Show this message and exit.

Commands:
  migrate             Data migration commands
  oauth               OAuth authentication setup commands
```

## OAuth Commands

### Main OAuth Group

**Command:** `tightbeam oauth --help`

```
Usage: tightbeam oauth [OPTIONS] COMMAND [ARGS]...

OAuth authentication setup commands

Options:
  --help          Show this message and exit.

Commands:
  callback  Handle OAuth2 callback and exchange authorization code for tokens.
  clear     Clear stored OAuth2 tokens from database.
  init      Initialize OAuth2 authorization flow.
  setup     Display OAuth authentication setup instructions.
  status    Check the status of authentication configuration. Shows current authentication mode and token status.
```

### OAuth Init Command

**Command:** `tightbeam oauth init --help`

```
Usage: tightbeam oauth init [OPTIONS]

Initialize OAuth2 authorization flow.
By default, starts a local callback server to automatically handle the OAuth2 callback. Alternatively, generates an authorization URL for manual completion.

Options:
  --db          PATH     SQLite database path for token storage [default: None]
  --port        INTEGER  Local callback server port [default: 8080]
  --auto                 Automatically complete OAuth2 flow with local callback server [default: True]
  --help                 Show this message and exit.
```

### OAuth Callback Command

**Command:** `tightbeam oauth callback --help`

- **Purpose:** Handle OAuth2 callback and exchange authorization code for tokens
- **Required Arguments:** Authorization code from OAuth2 callback
- **Options:** Database path for token storage

### OAuth Clear Command

**Command:** `tightbeam oauth clear --help`

- **Purpose:** Clear stored OAuth2 tokens from database
- **Options:** Database path, confirmation flag (--yes/-y)

### OAuth Setup Command

**Command:** `tightbeam oauth setup --help`

- **Purpose:** Display OAuth authentication setup instructions
- **Options:** None

### OAuth Status Command

**Command:** `tightbeam oauth status --help`

- **Purpose:** Check authentication configuration status
- **Options:** None

## Migration Commands

### Main Migration Group

**Command:** `tightbeam migrate --help`

```
Usage: tightbeam migrate [OPTIONS] COMMAND [ARGS]...

Data migration commands

Options:
  --db                                                         PATH  SQLite database path [default: None]
  --verbose                   -v                                     Enable verbose logging
  --deferred-notes                --immediate-notes                  Use deferred notes loading to prevent GraphQL throttling [default: deferred-notes]
  --enable-notes-persistence                                         Enable temporary storage for note references (for very large migrations)
  --optimization-level                                         TEXT  Rate limiting optimization level:
                                                                    • conservative (4 req/s): Safest option with 52% safety margin, recommended for production
                                                                    • moderate (6 req/s): Balanced performance with 28% safety margin, default recommended
                                                                    • aggressive (8 req/s): Maximum speed with 4% safety margin, requires active monitoring
                                                                    [default: moderate]
  --enable-cost-monitoring        --disable-cost-monitoring          Enable GraphQL cost monitoring and rate limit tracking. Provides detailed performance insights and API usage statistics. Recommended for performance analysis and optimization tuning. [default: enable-cost-monitoring]
  --cost-monitoring-verbose                                          Enable verbose cost monitoring output during migration. Shows detailed GraphQL query costs, accuracy percentages, and rate limit analysis. Use for detailed performance debugging and optimization insights.
  --resume                                                           Skip entities that already exist in database (for resuming interrupted migrations)
  --adaptive                      --no-adaptive                      Enable adaptive performance optimization (auto-tune page size and delays) [default: no-adaptive]
  --help                                                             Show this message and exit.

Commands:
  all                  Migrate all data from Jobber API to SQLite database.
  attachments          Extract attachment data and download files from Jobber API to local storage.
  expenses             Extract expense data from Jobber API to SQLite database.
  products             Extract product/service data from Jobber API to SQLite database.
  quotes               Extract quote data from Jobber API to SQLite database.
  tax-rates            Extract tax rate data from Jobber API to SQLite database.
  timesheet-entries    Extract timesheet entry data from Jobber API to SQLite database.
  users                Extract user data from Jobber API to SQLite database.
  visits               Extract visit data from Jobber API to SQLite database.
```

### Migration All Command

**Command:** `tightbeam migrate all --help`

```
Usage: tightbeam migrate all [OPTIONS]

Migrate all data from Jobber API to SQLite database.
Fetches all clients, invoices, quotes, notes, and attachments from the Jobber GraphQL API using cursor-based pagination and stores them in the specified SQLite database. Attachment files are downloaded to ./attachments directory. Features deferred notes loading by default to prevent GraphQL throttling issues.

Deferred Notes Loading (Default):
- Collects note IDs during client/invoice processing
- Processes notes separately to avoid nested query complexity
- Prevents GraphQL throttling on large datasets
- Use --immediate-notes to disable (legacy mode)

Resume Mode (--resume):
- Skips entities that already exist in the database
- Enables resuming interrupted migrations without duplicate processing
- Uses fast primary key lookups for efficient existence checking
- Works with all entity types including clients, invoices, quotes, notes, and attachments

Authentication options:
1. Set JOBBER_TOKEN environment variable with a valid Jobber API token
2. Configure OAuth2 variables and run 'tightbeam oauth init'

Options:
  --db                                                            PATH  SQLite database path [default: tightbeam.db]
  --verbose                   -v                                        Enable verbose logging
  --deferred-notes                --immediate-notes                     Use deferred notes loading to prevent GraphQL throttling [default: deferred-notes]
  --enable-notes-persistence                                            Enable temporary storage for note references (for very large migrations)
  --resume                                                              Skip entities that already exist in database (for resuming interrupted migrations)
  --optimization-level                                            TEXT  [default: moderate]
  --enable-cost-monitoring        --no-enable-cost-monitoring           [default: enable-cost-monitoring]
  --cost-monitoring-verbose       --no-cost-monitoring-verbose          [default: no-cost-monitoring-verbose]
  --adaptive                      --no-adaptive                         Enable adaptive performance optimization (auto-tune page size and delays) [default: no-adaptive]
  --help                                                                Show this message and exit.
```

### Individual Entity Migration Commands

**Pattern:** `tightbeam migrate <entity> --help`

All individual entity migration commands share these common options:

- `--limit INTEGER`: Limit number of pages for testing [default: None]
- `--resume`: Skip entities that already exist in database
- `--help`: Show help message

#### Quotes Migration

**Command:** `tightbeam migrate quotes --help`

```
Usage: tightbeam migrate quotes [OPTIONS]

Extract quote data from Jobber API to SQLite database.
Fetches all quotes from the Jobber GraphQL API using cursor-based pagination and stores them in the specified SQLite database. Uses centralized rate limiting configuration from parent command options.

Note: Individual migrate commands use simplified GraphQL queries and don't support deferred notes loading. For deferred notes, use 'migrate all' command.

Args:
    page_limit: Optional limit on number of pages to process (for testing)
    resume: Skip entities that already exist in database (for resuming interrupted migrations)

Options:
  --limit         INTEGER  Limit number of pages for testing [default: None]
  --resume                 Skip entities that already exist in database
  --help                   Show this message and exit.
```

#### Attachments Migration

**Command:** `tightbeam migrate attachments --help`

Additional specific option:

- `--download-path TEXT`: Base path for attachment downloads [default: ./attachments]

#### Other Entity Migrations

The following commands follow the same pattern as quotes:

- `tightbeam migrate users`
- `tightbeam migrate expenses`
- `tightbeam migrate visits`
- `tightbeam migrate timesheet-entries`
- `tightbeam migrate products`
- `tightbeam migrate tax-rates`

## Implementation Details

### Key CLI Components (from src/cli.py)

1. **Main Application Setup**
   - Created with Typer
   - Main app with two subcommand groups: `oauth` and `migrate`

2. **OAuth Subcommand Group**
   - Commands: init, callback, clear, setup, status
   - Handles OAuth2 authentication flow
   - Manages token storage in SQLite database

3. **Migration Subcommand Group**
   - Callback-based with shared configuration
   - Default command: 'all' when no subcommand specified
   - Individual entity extraction commands
   - Comprehensive error handling and exit codes

4. **Shared Configuration Pattern**
   - Group-level options stored in Typer context
   - Individual commands access shared config via `ctx.obj`
   - Rate limiting, database path, verbose mode shared across commands

5. **Error Handling**
   - Structured exit codes:
     - 0: Success
     - 1: Configuration errors
     - 2: API errors
     - 3: Data mapping errors
     - 4: Database errors
     - 5: Unexpected errors
     - 130: User interruption

6. **Dependencies**
   - Rich console for enhanced output
   - Typer for CLI framework
   - Complex dependency injection pattern for components

## Test Coverage Requirements

Based on the CLI structure, comprehensive tests should cover:

1. **Command Help Output Tests**
   - All main and subcommand help messages
   - Option parsing and validation
   - Default value verification

2. **OAuth Command Tests**
   - OAuth flow initialization
   - Token management (callback, clear, status)
   - Error handling for missing configuration

3. **Migration Command Tests**
   - All entity migration commands
   - Shared configuration inheritance
   - Resume functionality
   - Rate limiting configuration
   - Progress reporting and logging

4. **Integration Tests**
   - End-to-end command execution
   - Database operations
   - File operations (attachments)
   - Error scenarios and recovery

5. **Configuration Tests**
   - Environment variable handling
   - Database path resolution
   - Option precedence (command-level vs group-level)

This baseline documentation captures the complete current CLI structure before refactoring into modular subcommand modules.
