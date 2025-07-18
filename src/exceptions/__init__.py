"""Domain-specific exceptions for TightBeam application."""


class TightBeamError(Exception):
    """Base exception for all TightBeam errors."""

    pass


class ConfigurationError(TightBeamError):
    """Raised when configuration is invalid or missing.

    This exception is raised when:
    - Environment variables (like JOBBER_TOKEN) are missing or empty
    - Configuration files are malformed or inaccessible
    - Required authentication credentials are invalid
    - Application settings fail validation

    Examples:
        - Missing JOBBER_TOKEN environment variable
        - Invalid token format or expired credentials
        - Malformed configuration parameters
    """

    pass


class JobberApiError(TightBeamError):
    """Raised when Jobber API communication fails.

    This exception is raised when:
    - HTTP requests to Jobber API fail (network errors, timeouts)
    - Jobber API returns error responses (4xx, 5xx status codes)
    - GraphQL query syntax errors or invalid operations
    - Authentication failures with Jobber API
    - API rate limiting or quota exceeded

    Examples:
        - Network connectivity issues
        - Invalid GraphQL queries
        - Expired or invalid access tokens
        - API service unavailable (503)
    """

    pass


class MappingError(TightBeamError):
    """Raised when data transformation or mapping operations fail.

    This exception is raised when:
    - Jobber API response data doesn't match expected schema
    - Required fields are missing from API responses
    - Data type conversion fails during entity mapping
    - Invalid data formats that cannot be processed
    - Entity validation fails during transformation

    Examples:
        - Missing required client fields in API response
        - Invalid date format in invoice data
        - Unexpected data types in GraphQL response
        - Schema validation failures
    """

    pass


class RepositoryError(TightBeamError):
    """Raised when database repository operations fail.

    This exception is raised when:
    - SQLite database connection failures
    - SQL execution errors (syntax, constraint violations)
    - Database schema creation or migration failures
    - Transaction rollback issues
    - File system errors affecting database access

    Examples:
        - Database file permission errors
        - SQL constraint violations during insert/update
        - Database corruption or integrity issues
        - Insufficient disk space for database operations
    """

    pass


class OAuth2Error(TightBeamError):
    """Raised when OAuth2 authentication and token management operations fail.

    This exception is raised when:
    - OAuth2 authorization flow failures (invalid authorization codes)
    - Token exchange failures with Jobber OAuth API
    - Access token refresh failures or invalid refresh tokens  
    - JWT token validation errors (expired, malformed, invalid signatures)
    - OAuth2 token storage or retrieval failures

    Examples:
        - Invalid or expired authorization codes
        - Network failures during token exchange
        - Malformed JWT tokens or signature validation failures
        - Refresh token rotation failures
        - Token storage database errors
    """

    pass


__all__ = [
    "TightBeamError",
    "ConfigurationError",
    "JobberApiError",
    "MappingError",
    "RepositoryError",
    "OAuth2Error",
]
