#!/usr/bin/env python3
"""
Version Synchronization Script

This script reads the version from src/constants.py and updates pyproject.toml
to ensure version consistency across the application.

Usage:
    python scripts/sync_version.py
"""

import re
import sys
from pathlib import Path

# Add src to path to import constants
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from constants import APP_VERSION, APP_DESCRIPTION, APP_AUTHORS, APP_LICENSE, PACKAGE_KEYWORDS
except ImportError as e:
    print(f"Error importing constants: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def update_pyproject_toml():
    """Update pyproject.toml with values from constants.py"""
    pyproject_path = Path("pyproject.toml")

    if not pyproject_path.exists():
        print("Error: pyproject.toml not found")
        sys.exit(1)

    # Read current content
    content = pyproject_path.read_text()

    # Update version
    content = re.sub(r'version = "[^"]*"', f'version = "{APP_VERSION}"', content)

    # Update description
    content = re.sub(r'description = "[^"]*"', f'description = "{APP_DESCRIPTION}"', content)

    # Update authors (convert list to TOML format)
    authors_toml = str(APP_AUTHORS).replace("'", '"')
    content = re.sub(r"authors = \[[^\]]*\]", f"authors = {authors_toml}", content)

    # Update license
    content = re.sub(r'license = "[^"]*"', f'license = "{APP_LICENSE}"', content)

    # Update keywords (convert list to TOML format)
    keywords_toml = str(PACKAGE_KEYWORDS).replace("'", '"')
    content = re.sub(r"keywords = \[[^\]]*\]", f"keywords = {keywords_toml}", content)

    # Write updated content
    pyproject_path.write_text(content)

    print(f"✅ Updated pyproject.toml with version {APP_VERSION}")
    print(f"   Description: {APP_DESCRIPTION}")
    print(f"   Authors: {APP_AUTHORS}")
    print(f"   License: {APP_LICENSE}")
    print(f"   Keywords: {PACKAGE_KEYWORDS}")


if __name__ == "__main__":
    update_pyproject_toml()
