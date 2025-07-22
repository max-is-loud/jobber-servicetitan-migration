"""Debug utilities for TightBeam v2.

This module provides debug logging utilities that can be controlled via environment variables.
Debug output is only displayed when TIGHTBEAM_DEBUG environment variable is set to a truthy value.
"""

import os
from typing import Any


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled via environment variable.

    Returns:
        bool: True if TIGHTBEAM_DEBUG environment variable is set to a truthy value
    """
    debug_value = os.getenv("TIGHTBEAM_DEBUG", "").lower()
    return debug_value in ("1", "true", "yes", "on", "debug")


def debug_print(*args: Any, **kwargs: Any) -> None:
    """Print debug message only if debug mode is enabled.

    Args:
        *args: Arguments to pass to print()
        **kwargs: Keyword arguments to pass to print()
    """
    if is_debug_enabled():
        print(*args, **kwargs)
