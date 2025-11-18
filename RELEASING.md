# Release Process

This document outlines the step-by-step process for creating a new release of TightBeam v2.

## Table of Contents

- [Versioning Strategy](#versioning-strategy)
- [Pre-Release Checklist](#pre-release-checklist)
- [Release Steps](#release-steps)
- [Post-Release Tasks](#post-release-tasks)
- [Hotfix Releases](#hotfix-releases)
- [Troubleshooting](#troubleshooting)

## Versioning Strategy

TightBeam v2 follows [Semantic Versioning](https://semver.org/) (SemVer):

```
MAJOR.MINOR.PATCH (e.g., 0.1.3)
```

### Version Components

- **MAJOR** (`X.0.0`): Breaking changes that are not backward compatible
  - API changes that break existing integrations
  - Removal of deprecated features
  - Major architectural changes

- **MINOR** (`0.X.0`): New features that are backward compatible
  - New entity extractors
  - New CLI commands
  - Performance improvements
  - New configuration options

- **PATCH** (`0.0.X`): Backward compatible bug fixes
  - Bug fixes
  - Security patches
  - Documentation updates
  - Dependency updates (non-breaking)

### Version Storage

**Single Source of Truth:** `pyproject.toml`

The version is defined once in `pyproject.toml` and automatically read by the application using `importlib.metadata`. Never hardcode the version elsewhere.

```toml
[tool.poetry]
version = "0.1.3"  # Update this value for releases
```

## Pre-Release Checklist

Before creating a release, ensure all items are completed:

### 1. Code Quality

- [ ] All tests pass locally: `uv run python -m pytest -v`
- [ ] Code coverage meets targets (aim for 80%+)
- [ ] No failing CI/CD checks on GitHub
- [ ] All PRs merged to `master` branch
- [ ] No outstanding critical bugs or security issues

### 2. Documentation

- [ ] README.md is up to date
- [ ] CHANGELOG.md updated with release notes (see format below)
- [ ] Architecture documentation reflects current implementation
- [ ] API changes documented (if applicable)
- [ ] Migration guides written for breaking changes (major releases only)

### 3. Testing

- [ ] Unit tests pass: `uv run python -m pytest tests/ -v`
- [ ] Integration tests pass (if applicable)
- [ ] Manual testing completed for new features
- [ ] Tested on target Python versions (3.8, 3.9, 3.10, 3.11, 3.12+)
- [ ] Tested OAuth flow end-to-end
- [ ] Tested migration workflow with real Jobber account (if available)

### 4. Dependencies

- [ ] Dependencies are up to date and compatible
- [ ] `uv.lock` is committed and up to date
- [ ] No security vulnerabilities: Check GitHub Security tab
- [ ] Removed unused dependencies

## Release Steps

### Step 1: Update Version

1. **Determine the new version** based on changes:
   ```bash
   # Review changes since last release
   git log $(git describe --tags --abbrev=0)..HEAD --oneline
   ```

2. **Update version in `pyproject.toml`:**
   ```toml
   [tool.poetry]
   version = "0.2.0"  # Example: bumping minor version
   ```

3. **Verify version is read correctly:**
   ```bash
   uv pip install -e .
   uv run python -c "from src.constants import APP_VERSION; print(APP_VERSION)"
   # Should output: 0.2.0
   ```

### Step 2: Update CHANGELOG

Create or update `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-01-15

### Added
- New ClientsExtractor with optimized nested notes queries
- InvoicesExtractor for better architecture consistency
- Unit tests for ServiceFactory

### Changed
- Refactored rate limiting setup to use ServiceFactory pattern
- Moved architecture docs to docs/architecture/

### Fixed
- PEP 8 violation in entity_extraction.py
- .gitignore patterns now use root-only prefix

### Security
- Verified no secrets in git history

## [0.1.3] - 2024-XX-XX
...
```

### Step 3: Commit Version Changes

```bash
# Stage changes
git add pyproject.toml CHANGELOG.md

# Commit with release message
git commit -m "chore: bump version to 0.2.0

See CHANGELOG.md for full release notes."

# Push to master
git push origin master
```

### Step 4: Create Git Tag

```bash
# Create annotated tag (preferred)
git tag -a v0.2.0 -m "Release v0.2.0

Major changes:
- Centralized rate limiting setup
- Optimized note extraction architecture
- Improved test coverage

See CHANGELOG.md for details."

# Push tag to GitHub
git push origin v0.2.0
```

### Step 5: Build Distribution

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build source distribution and wheel
uv build

# Verify build contents
ls -lh dist/
# Should show:
# tightbeam_v2-0.2.0-py3-none-any.whl
# tightbeam_v2-0.2.0.tar.gz
```

### Step 6: Create GitHub Release

1. Go to https://github.com/max-is-loud/tightbeam-v2/releases/new

2. **Tag:** Select `v0.2.0` (the tag created in Step 4)

3. **Release Title:** `TightBeam v0.2.0`

4. **Release Notes:** Copy from CHANGELOG.md and format with GitHub markdown:

   ```markdown
   ## What's Changed

   ### Added
   - New ClientsExtractor with optimized nested notes queries
   - InvoicesExtractor for better architecture consistency

   ### Changed
   - Refactored rate limiting setup to use ServiceFactory pattern
   - Moved architecture docs to docs/architecture/

   ### Fixed
   - PEP 8 violation in entity_extraction.py

   ## Installation

   ```bash
   git clone https://github.com/max-is-loud/tightbeam-v2.git
   cd tightbeam-v2
   git checkout v0.2.0
   uv sync
   ```

   ## Full Changelog
   https://github.com/max-is-loud/tightbeam-v2/compare/v0.1.3...v0.2.0
   ```

5. **Attach binaries:**
   - Upload `dist/tightbeam_v2-0.2.0-py3-none-any.whl`
   - Upload `dist/tightbeam_v2-0.2.0.tar.gz`

6. **Publish release**

### Step 7: Publish to PyPI (Optional)

> **Note:** Only publish to PyPI if the package is intended for public distribution.

```bash
# Test on PyPI Test first (recommended)
uv publish --repository testpypi dist/*

# Verify installation from Test PyPI
pip install --index-url https://test.pypi.org/simple/ tightbeam-v2==0.2.0

# If successful, publish to production PyPI
uv publish dist/*
```

## Post-Release Tasks

### 1. Verify Release

- [ ] GitHub release is visible and assets are attached
- [ ] Tag appears in git history: `git tag -l`
- [ ] Installation works from release: `git clone && git checkout v0.2.0 && uv sync`
- [ ] PyPI package installs (if published): `pip install tightbeam-v2==0.2.0`

### 2. Update Documentation

- [ ] Update README badges (if version badges exist)
- [ ] Announce release in project channels (if applicable)
- [ ] Update any external documentation references

### 3. Prepare for Next Development Cycle

- [ ] Create milestone for next version on GitHub
- [ ] Update project board with next sprint tasks
- [ ] Consider bumping to next development version (e.g., `0.3.0-dev`) in `pyproject.toml`

## Hotfix Releases

For critical bugs in production that require immediate release:

### 1. Create Hotfix Branch

```bash
# From the release tag that needs fixing
git checkout v0.2.0
git checkout -b hotfix/0.2.1
```

### 2. Apply Fix

```bash
# Make minimal changes to fix the critical issue
# Commit the fix
git add .
git commit -m "fix: critical bug in rate limiting"
```

### 3. Update Version and Release

```bash
# Update version to 0.2.1 in pyproject.toml
# Update CHANGELOG.md
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version to 0.2.1"

# Merge to master
git checkout master
git merge hotfix/0.2.1
git push origin master

# Tag and release
git tag -a v0.2.1 -m "Hotfix release v0.2.1"
git push origin v0.2.1

# Build and publish
uv build
# Create GitHub release as in Step 6
```

### 4. Clean Up

```bash
# Delete hotfix branch
git branch -d hotfix/0.2.1
```

## Troubleshooting

### Version Not Updating

**Problem:** `APP_VERSION` shows old version after updating `pyproject.toml`

**Solution:**
```bash
# Reinstall package in editable mode
uv pip install -e .

# Verify version
uv run python -c "from src.constants import APP_VERSION; print(APP_VERSION)"
```

### Build Fails

**Problem:** `uv build` fails with errors

**Solution:**
```bash
# Ensure pyproject.toml is valid
uv sync --all-extras

# Clean build artifacts
rm -rf dist/ build/ *.egg-info

# Retry build
uv build
```

### Git Tag Already Exists

**Problem:** Tag name conflicts with existing tag

**Solution:**
```bash
# Delete local tag
git tag -d v0.2.0

# Delete remote tag (use with caution!)
git push --delete origin v0.2.0

# Recreate tag with correct commit
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

### Tests Fail on CI but Pass Locally

**Problem:** CI tests fail but local tests pass

**Solution:**
```bash
# Run tests exactly as CI does
uv run python -m pytest tests/ -v --cov=src

# Check Python version matches CI
python --version

# Ensure dependencies are locked
uv sync
git status  # Check if uv.lock needs committing
```

## Automation Considerations

Future improvements to automate this process:

### 1. Version Bumping Tools

Consider using tools like:
- [`bump2version`](https://github.com/c4urself/bump2version): Automate version bumping
- [`python-semantic-release`](https://github.com/python-semantic-release/python-semantic-release): Fully automated releases

Example `bump2version` configuration (`.bumpversion.cfg`):
```ini
[bumpversion]
current_version = 0.1.3
commit = True
tag = True
tag_name = v{new_version}

[bumpversion:file:pyproject.toml]
search = version = "{current_version}"
replace = version = "{new_version}"
```

Usage:
```bash
# Bump patch version (0.1.3 -> 0.1.4)
bump2version patch

# Bump minor version (0.1.3 -> 0.2.0)
bump2version minor

# Bump major version (0.1.3 -> 1.0.0)
bump2version major
```

### 2. GitHub Actions

Create `.github/workflows/release.yml` to automate:
- Running tests on release branches
- Building distributions
- Creating GitHub releases
- Publishing to PyPI

### 3. Release Checklists

Use GitHub issue templates for release checklists:
`.github/ISSUE_TEMPLATE/release.md`

---

**Last Updated:** 2025-01-17
**Maintained By:** TightBeam Development Team
