"""Domain-specific exceptions for TightBeam application."""


class TightBeamError(Exception):
    """Base exception for all TightBeam errors."""

    pass


class ConfigurationError(TightBeamError):
    """Raised when configuration is invalid or missing."""

    pass


class JobberApiError(TightBeamError):
    """Raised when Jobber API operations fail."""

    pass


class DatabaseError(TightBeamError):
    """Raised when database operations fail."""

    pass
