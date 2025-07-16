# AI Agent Development Guidelines - Jobber Data Migration Tool

## Project Overview

- **Purpose**: Object-oriented CLI tool for fetching Jobber GraphQL data and persisting to SQLite
- **Technology Stack**: Python, Typer (CLI), SQLite3, requests (HTTP), GraphQL
- **Architecture**: Strict OOP with dependency injection, single responsibility principle
- **Version**: v0.1 MVP focusing on Clients and Invoices entities

## Project Architecture Rules

### Core Class Structure

- **MUST** implement exactly these classes with specified responsibilities:
  - `AuthProvider`: Read/validate `JOBBER_TOKEN` environment variable only
  - `JobberClient`: Execute GraphQL queries only, depend on AuthProvider
  - `EntityModel` package: `Client` and `Invoice` dataclasses only
  - `EntityMapper`: Transform GraphQL payloads to EntityModel objects only
  - `Repository`: SQLite operations only, implement CRUD interface
  - `MigrationCoordinator`: Orchestrate workflow only, depend on all above classes
  - `CLI`: Typer-based argument parsing only, instantiate MigrationCoordinator

### Dependency Injection Requirements

- **MUST** inject all dependencies via constructor parameters
- **PROHIBITED**: Global variables, singleton patterns, direct instantiation within classes
- **MUST** use dependency injection in `cli.py` to wire up all components
- **EXAMPLE**: `JobberClient(auth_provider: AuthProvider, http_client: HttpClient)`

### Single Responsibility Enforcement

- **PROHIBITED**: Classes handling multiple concerns (e.g., JobberClient doing persistence)
- **MUST** delegate cross-cutting concerns to dedicated classes
- **EXAMPLE**: Authentication logic only in AuthProvider, never in JobberClient

## Code Standards

### Type Hints and Imports

- **MUST** use built-in `dict` type instead of `typing.Dict` (UP035 linting rule)
- **MUST** use `List[EntityType]` not `typing.List`
- **MUST** import `from typing import Optional, List, Generic` when needed
- **PROHIBITED**: `from typing import Dict`

### Naming Conventions

- **MUST** use PascalCase for class names: `JobberClient`, `EntityMapper`
- **MUST** use snake_case for methods/variables: `fetch_clients()`, `client_id`
- **MUST** prefix private methods with underscore: `_validate_token()`
- **MUST** use descriptive names reflecting single responsibility

### Error Handling

- **MUST** define domain-specific exceptions: `ConfigurationError`, `JobberApiError`
- **MUST** raise ConfigurationError when JOBBER_TOKEN missing
- **PROHIBITED**: Generic Exception, print() statements for errors
- **MUST** let exceptions bubble up to CLI layer for handling

## File Organization Rules

### Directory Structure

```sh
tightbeam-v2/
├── src/
│   ├── auth/
│   │   └── auth_provider.py      # AuthProvider class
│   ├── clients/
│   │   └── jobber_client.py      # JobberClient class
│   ├── models/
│   │   ├── __init__.py
│   │   ├── client.py             # Client dataclass
│   │   └── invoice.py            # Invoice dataclass
│   ├── mappers/
│   │   └── entity_mapper.py      # EntityMapper class
│   ├── repositories/
│   │   └── repository.py         # Repository class with CRUD interface
│   ├── coordinators/
│   │   └── migration_coordinator.py  # MigrationCoordinator class
│   └── cli.py                    # Typer CLI and dependency injection
├── requirements.txt              # Dependencies
└── shrimp-rules.md              # This file
```

### Module Dependencies

- **MUST** follow import hierarchy: CLI → Coordinator → (Client, Mapper, Repository) → Models
- **PROHIBITED**: Circular imports between same-level modules
- **MUST** import models in mappers and repositories
- **PROHIBITED**: Models importing business logic classes

## CLI Implementation Standards

### Typer Configuration

- **MUST** use `typer.Typer()` for main app
- **MUST** implement `migrate` command with required `--db` parameter
- **MUST** support `--verbose` flag for detailed logging
- **MUST** use `typer.Option()` for all parameters
- **EXAMPLE**:

```python
@app.command()
def migrate(
    db: Path = typer.Option(..., help="SQLite database path"),
    verbose: bool = typer.Option(False, "-v", help="Verbose logging")
):
    # Implementation here
```

### Environment Variable Handling

- **MUST** validate `JOBBER_TOKEN` in AuthProvider, not CLI
- **MUST** use `typer.Option(..., envvar="JOBBER_TOKEN")` for token parameter if exposed
- **PROHIBITED**: Direct `os.environ` access outside AuthProvider

## Database Operations Standards

### Repository Pattern Implementation

- **MUST** implement generic `CrudRepository[T]` interface
- **MUST** provide `create()`, `read()`, `update()`, `delete()` methods
- **MUST** use parameterized queries for all SQL operations
- **EXAMPLE**:

```python
def create(self, client: Client):
    self.db.execute(
        "INSERT INTO clients VALUES (?,?,?,?,?,?)",
        (client.id, client.first_name, client.last_name, 
         client.email, client.phone, client.created_at)
    )
```

### Schema Management

- **MUST** implement `init_schema()` method in Repository
- **MUST** use `CREATE TABLE IF NOT EXISTS` statements
- **MUST** define foreign key relationships in SQL
- **PROHIBITED**: Manual schema creation outside Repository

### Table Schema Requirements

```sql
-- MUST use exactly these schemas
CREATE TABLE IF NOT EXISTS clients (
  id TEXT PRIMARY KEY,
  first_name TEXT,
  last_name TEXT,
  email TEXT,
  phone TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL REFERENCES clients(id),
  number TEXT,
  total_cents INTEGER,
  status TEXT,
  issued_at TEXT
);
```

## GraphQL Client Standards

### Query Structure

- **MUST** use cursor-based pagination with `$cursor` variable
- **MUST** implement `fetch_clients(cursor=None)` and `fetch_invoices(cursor=None)`
- **MUST** return raw dict payloads, no transformation in JobberClient
- **PROHIBITED**: Entity mapping logic in JobberClient

### HTTP Request Pattern

- **MUST** use `requests.post()` with JSON payload
- **MUST** include authentication headers from AuthProvider
- **MUST** handle HTTP status codes and JSON parsing errors
- **EXAMPLE**:

```python
response = requests.post(
    self.api_url,
    headers=self.auth_provider.get_headers(),
    json={"query": query, "variables": variables}
)
```

## Multi-File Coordination Rules

### Entity Model Changes

- **WHEN** modifying `Client` or `Invoice` dataclass:
  - **MUST** update corresponding `EntityMapper` methods
  - **MUST** update `Repository` CRUD methods
  - **MUST** update SQL schema in `init_schema()`
  - **MUST** verify GraphQL query fields match model attributes

### Schema Evolution

- **WHEN** adding new entity types:
  - **MUST** create new model in `models/` directory
  - **MUST** add mapper methods in `EntityMapper`
  - **MUST** extend Repository with new CRUD methods
  - **MUST** add table creation in `init_schema()`
  - **MUST** add fetch method in `JobberClient`

### CLI Command Changes

- **WHEN** adding new commands:
  - **MUST** create new methods in `MigrationCoordinator`
  - **MUST** add corresponding Typer command functions
  - **MUST** update dependency injection in `cli.py`

## AI Decision-Making Standards

### Class Responsibility Conflicts

- **IF** unsure which class should handle functionality:
  - **PRIORITY 1**: Check if it involves external API → JobberClient
  - **PRIORITY 2**: Check if it involves data transformation → EntityMapper
  - **PRIORITY 3**: Check if it involves persistence → Repository
  - **PRIORITY 4**: Check if it involves orchestration → MigrationCoordinator

### Dependency Direction Rules

- **IF** class A needs functionality from class B:
  - **MUST** inject B into A via constructor
  - **PROHIBITED**: A importing B's methods directly
  - **PROHIBITED**: B depending on A (creates circular dependency)

### Error Handling Decision Tree

- **IF** error occurs during authentication → raise `ConfigurationError`
- **IF** error occurs during API call → raise `JobberApiError`
- **IF** error occurs during data transformation → raise `MappingError`
- **IF** error occurs during persistence → raise `RepositoryError`

## Prohibited Actions

### Architecture Violations

- **PROHIBITED**: Direct database access from any class except Repository
- **PROHIBITED**: GraphQL queries from any class except JobberClient
- **PROHIBITED**: Authentication logic outside AuthProvider
- **PROHIBITED**: CLI argument parsing outside `cli.py`

### Code Quality Violations

- **PROHIBITED**: Using `typing.Dict` (use built-in `dict`)
- **PROHIBITED**: Global variables or module-level state
- **PROHIBITED**: print() statements (use Logger interface)
- **PROHIBITED**: Hardcoded values (use configuration or environment variables)

### Testing and Validation

- **PROHIBITED**: Manual testing code in production classes
- **PROHIBITED**: Debug print statements in committed code
- **PROHIBITED**: Temporary files or directories in version control

## Implementation Sequence Requirements

### Phase 1: Core Infrastructure

1. **MUST** implement `AuthProvider` first
2. **MUST** implement entity models before dependent classes
3. **MUST** implement `Repository.init_schema()` before persistence methods

### Phase 2: Data Flow Implementation

1. **MUST** implement `JobberClient` after AuthProvider
2. **MUST** implement `EntityMapper` after models
3. **MUST** implement Repository CRUD after schema

### Phase 3: Orchestration

1. **MUST** implement `MigrationCoordinator` after all dependencies
2. **MUST** implement CLI after MigrationCoordinator
3. **MUST** test end-to-end flow last

## Success Validation Criteria

- **MUST** instantiate all classes without runtime errors
- **MUST** complete `fetch-jobber --db ./test.sqlite` without exceptions
- **MUST** populate both `clients` and `invoices` tables with data
- **MUST** display summary output via Logger interface
- **MUST** pass dependency injection validation (no direct instantiation in classes)
