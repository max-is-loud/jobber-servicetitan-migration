"""
TightBeam v2 Application Constants

Centralized location for all application metadata, version information,
and configuration constants. Update these values in one place to ensure
consistency across the entire application.
"""

from importlib.metadata import version, PackageNotFoundError

# Application Metadata
APP_NAME = "TightBeam"

# Read version from package metadata (pyproject.toml is the single source of truth)
try:
    APP_VERSION = version("tightbeam-v2")
except PackageNotFoundError:
    # Fallback for development/editable installs where package metadata isn't available
    APP_VERSION = "0.0.0-dev"

APP_DESCRIPTION = "Jobber Data Migration Tool"
APP_FULL_DESCRIPTION = "A command-line tool for extracting client and invoice data from Jobber GraphQL API and persisting it to SQLite database using object-oriented architecture."

# Author Information
APP_AUTHORS = ["Maxime Langlois-Morin <max@maxmorin.ca>"]
APP_LICENSE = "Proprietary"

# Package Information
PACKAGE_NAME = "tightbeam"
PACKAGE_KEYWORDS = ["jobber", "graphql", "sqlite", "data-migration", "cli"]

# CLI Configuration
CLI_COMMAND_NAME = "tightbeam"
CLI_HELP_TEXT = f"{APP_NAME} - {APP_DESCRIPTION}"

# Version Display
VERSION_DISPLAY = f"🚀 {APP_NAME} version {APP_VERSION}"
VERSION_SUBTITLE = APP_DESCRIPTION

# Environment Variables
REQUIRED_OAUTH_VARS = {
    "JOBBER_CLIENT_ID": "Your Jobber application's client ID",
    "JOBBER_CLIENT_SECRET": "Your Jobber application's client secret",
    "JOBBER_REDIRECT_URI": "OAuth redirect URI for your application",
}

# File Paths and Names
DEFAULT_DB_PATH = "tightbeam.db"
DEFAULT_ATTACHMENTS_DIR = "attachments"
ENV_FILE_NAME = ".env"

# API Configuration
DEFAULT_PORT = 8080
OAUTH_TIMEOUT_SECONDS = 300  # 5 minutes

# Exit Codes
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_AUTH_ERROR = 2
EXIT_API_ERROR = 3
EXIT_DATABASE_ERROR = 4
EXIT_UNEXPECTED_ERROR = 5
EXIT_INTERRUPTED = 130

# Rate Limiting Defaults
DEFAULT_OPTIMIZATION_LEVEL = "moderate"
OPTIMIZATION_LEVELS = ["conservative", "moderate", "aggressive"]

# Console Display Constants
OAUTH_EMOJI = "🔑"
MIGRATION_EMOJI = "📊"
DRY_RUN_EMOJI = "🔍"
VERSION_EMOJI = "🚀"
SUCCESS_EMOJI = "✅"
ERROR_EMOJI = "❌"
WARNING_EMOJI = "⚠️"
INFO_EMOJI = "💡"
