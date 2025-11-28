# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
