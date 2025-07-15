# TightBeam v2 MVP Development Plan

*Created: 2025-07-15 15:15:03 (Vancouver)*

## Project Overview

**Goal**: Build a minimal, object-oriented CLI tool to fetch Jobber GraphQL data (Clients & Invoices) and persist to SQLite database with strict OOP principles and dependency injection.

**Technology Stack**:

- Python 3.8+
- Typer (CLI framework)
- SQLite3 (database)
- Requests (HTTP client)
- GraphQL (API queries)

**Architecture**: Strict OOP with single responsibility principle, dependency injection, and clear separation of concerns.

## Success Criteria

1. ✅ All classes instantiate cleanly without runtime errors
2. ✅ Command `fetch-jobber --db ./test.sqlite` completes without exceptions  
3. ✅ Both `clients` and `invoices` tables populated with real data
4. ✅ Summary output via Logger interface
5. ✅ Full dependency injection (no direct instantiation in classes)
6. ✅ Adherence to OOP principles and code standards

## Overall Architecture

### Core Classes (7 Required)

```
📁 src/
├── 🔐 auth/auth_provider.py          # AuthProvider
├── 🌐 clients/jobber_client.py       # JobberClient  
├── 📊 models/                        # EntityModel package
│   ├── client.py                     # Client dataclass
│   └── invoice.py                    # Invoice dataclass
├── 🔄 mappers/entity_mapper.py       # EntityMapper
├── 💾 repositories/repository.py     # Repository
├── 🎯 coordinators/migration_coordinator.py  # MigrationCoordinator
└── 🖥️ cli.py                        # CLI + Dependency Injection
```

### Data Flow

```
CLI → MigrationCoordinator → [AuthProvider, JobberClient, EntityMapper, Repository] → SQLite
```

## Phase Breakdown

### Phase 1: Core Infrastructure (Days 1-2)

**Focus**: Foundation classes with authentication and data models

**Deliverables**:

- ✅ Project structure and dependencies
- ✅ AuthProvider class with environment variable handling
- ✅ Entity models (Client, Invoice dataclasses)
- ✅ Basic Repository with schema initialization
- ✅ Initial error handling classes

**Success**: Classes instantiate, schema creates, token validation works

### Phase 2: Data Fetching & Transformation (Days 2-3)  

**Focus**: GraphQL client and data mapping

**Deliverables**:

- ✅ JobberClient with GraphQL query execution
- ✅ EntityMapper for payload transformation
- ✅ Repository CRUD operations
- ✅ Pagination handling
- ✅ Error handling for API failures

**Success**: Can fetch and transform raw GraphQL data to domain objects

### Phase 3: Orchestration & CLI (Days 3-4)

**Focus**: Workflow coordination and user interface

**Deliverables**:

- ✅ MigrationCoordinator orchestration logic
- ✅ Typer-based CLI with dependency injection
- ✅ Logging interface implementation
- ✅ End-to-end workflow integration
- ✅ Summary reporting

**Success**: Complete CLI command works end-to-end

### Phase 4: Testing & Refinement (Days 4-5)

**Focus**: Validation, error handling, and polish

**Deliverables**:

- ✅ Manual testing scenarios
- ✅ Error handling refinement
- ✅ Performance validation
- ✅ Documentation updates
- ✅ Code quality review

**Success**: Production-ready MVP with proper error handling

## Development Standards

### Code Quality Rules

- ✅ Use built-in `dict` instead of `typing.Dict` (UP035 rule)
- ✅ PascalCase for classes, snake_case for methods/variables
- ✅ Single responsibility per class
- ✅ Constructor dependency injection only
- ✅ Domain-specific exceptions
- ✅ No global variables or singletons

### File Organization Requirements

```
tightbeam-v2/
├── src/
│   ├── auth/auth_provider.py
│   ├── clients/jobber_client.py  
│   ├── models/__init__.py
│   ├── models/client.py
│   ├── models/invoice.py
│   ├── mappers/entity_mapper.py
│   ├── repositories/repository.py
│   ├── coordinators/migration_coordinator.py
│   └── cli.py
├── requirements.txt
└── overall_plan.md
```

### Dependency Flow (Import Hierarchy)

```
CLI → Coordinator → (Client, Mapper, Repository) → Models
```

## Technical Specifications

### Database Schema

```sql
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

### GraphQL Query Patterns

```python
# JobberClient cursor-based pagination
def fetch_clients(cursor=None) -> dict
def fetch_invoices(cursor=None) -> dict

# EntityMapper transformations  
def map_client(data: dict) -> Client
def map_invoice(data: dict) -> Invoice
```

### CLI Interface

```bash
fetch-jobber migrate --db ./data.sqlite [--verbose]
```

## Implementation Sequence

### Critical Path Dependencies

1. **AuthProvider** → **JobberClient** (auth needed for API)
2. **Models** → **EntityMapper** (models needed for transformation)  
3. **Models** → **Repository** (models needed for persistence)
4. **All Components** → **MigrationCoordinator** (orchestration needs all)
5. **MigrationCoordinator** → **CLI** (CLI needs coordinator)

### Parallel Development Opportunities

- Models + Repository schema can be developed simultaneously
- EntityMapper can be built alongside JobberClient
- Error handling classes can be developed in parallel

## Risk Mitigation

### Technical Risks

- **API Rate Limiting**: Implement pagination with reasonable delays
- **Authentication Expiry**: Handle 401 errors gracefully  
- **Data Volume**: Use cursor-based pagination, batch database operations
- **Network Failures**: Implement retry logic with exponential backoff

### Architecture Risks  

- **Circular Dependencies**: Strict import hierarchy enforcement
- **Tight Coupling**: Constructor injection pattern prevents direct coupling
- **Testing Difficulties**: Dependency injection enables easy mocking

## Documentation Requirements

### Available Resources

- ✅ Jobber API Documentation (developer.getjobber.com)
- ✅ Python SQLite3 Documentation (docs.python.org)  
- ✅ Requests Library Documentation (requests.readthedocs.io)
- ✅ Typer Documentation (typer.tiangolo.com)

### Implementation Guides

- Entity schema mapping from Jobber API docs
- HTTP request patterns using requests library
- SQLite query patterns and transaction management
- Typer CLI patterns with dependency injection

## Next Steps

1. **Immediate**: Execute Phase 1 implementation using plan_task tool
2. **Daily**: Review progress against phase deliverables
3. **Continuous**: Validate architecture adherence and dependency injection
4. **End of Phase**: Manual testing and validation before next phase

---

*This plan will be updated as implementation progresses and requirements evolve.*
