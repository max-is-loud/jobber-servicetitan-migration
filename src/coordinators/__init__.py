"""Coordinator classes for orchestrating complex workflows."""

from .max_extract_coordinator import MaxExtractCoordinator

# DEPRECATED: Legacy coordinators - retained for backward compatibility
# from .base_migration_coordinator import BaseMigrationCoordinator
# from .download_mode_coordinator import DownloadModeCoordinator
# from .extract_mode_coordinator import ExtractModeCoordinator
# from .map_mode_coordinator import MapModeCoordinator
# from .rich_migration_coordinator import RichMigrationCoordinator

__all__ = [
    "MaxExtractCoordinator",
    # Deprecated - use MaxExtractCoordinator instead
    # "BaseMigrationCoordinator",
    # "DownloadModeCoordinator",
    # "ExtractModeCoordinator",
    # "MapModeCoordinator",
    # "RichMigrationCoordinator",
]
