"""CLI module for TightBeam v2 Jobber data migration tool."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_cli_module() -> ModuleType:
    """Load the main CLI module dynamically to avoid circular imports."""
    cli_file_path = Path(__file__).parent.parent / "cli.py"
    spec = importlib.util.spec_from_file_location("main_cli", cli_file_path)

    if spec is None or spec.loader is None:
        raise ImportError("Could not load main CLI module")

    main_cli = importlib.util.module_from_spec(spec)

    # Add parent to path for module imports
    parent_path = str(Path(__file__).parent.parent)
    if parent_path not in sys.path:
        sys.path.insert(0, parent_path)

    spec.loader.exec_module(main_cli)
    return main_cli


# Load the CLI module once
_cli_module = _load_cli_module()

# Export the app and main
app = _cli_module.app


def main() -> None:
    """Entry point wrapper for the CLI application."""
    _cli_module.main()


__all__ = ["app", "main"]
