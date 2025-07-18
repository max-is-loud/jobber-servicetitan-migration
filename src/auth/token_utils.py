"""
Token utility functions for JWT token expiration detection and validation.

This module provides utility functions for working with JWT tokens, specifically
for checking expiration status and extracting expiration information. These
utilities are used by AuthProvider for automatic token refresh logic.
"""

from datetime import datetime, timezone
from typing import Optional

import jwt

from ..exceptions import OAuth2Error


def is_token_expired(token: str, buffer_seconds: int = 30) -> bool:
    """
    Check if a JWT token is expired or will expire soon.

    This function decodes the JWT token without signature verification and checks
    the 'exp' (expiration) claim against the current time. Includes a configurable
    buffer to trigger refresh before actual expiration.

    Args:
        token: JWT token string to check
        buffer_seconds: Buffer time in seconds before expiration to consider
                       token as expired (default: 30 seconds)

    Returns:
        True if token is expired or will expire within buffer_seconds, False otherwise

    Raises:
        OAuth2Error: If token is malformed or missing expiration claim

    Example:
        >>> token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        >>> is_expired = is_token_expired(token)
        >>> if is_expired:
        ...     # Token needs refreshing
        ...     refresh_access_token()
    """
    try:
        # Decode token without signature verification to access claims
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except jwt.DecodeError as e:
        raise OAuth2Error(f"Malformed JWT token: {e}") from e

    # Check if exp claim exists
    if "exp" not in payload:
        raise OAuth2Error("JWT token missing expiration claim")

    try:
        # Convert Unix timestamp to datetime
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

        # Get current time with timezone
        now = datetime.now(timezone.utc)

        # Check if token is expired or will expire within buffer
        time_until_expiry = (exp_datetime - now).total_seconds()
        return time_until_expiry <= buffer_seconds

    except (ValueError, TypeError, OSError) as e:
        raise OAuth2Error(f"Invalid expiration timestamp in JWT token: {e}") from e


def get_token_expiration(token: str) -> Optional[datetime]:
    """
    Extract expiration datetime from a JWT token.

    This function decodes the JWT token without signature verification and
    extracts the 'exp' (expiration) claim, converting it to a timezone-aware
    datetime object.

    Args:
        token: JWT token string to analyze

    Returns:
        Timezone-aware datetime object representing token expiration,
        or None if token has no expiration claim

    Raises:
        OAuth2Error: If token is malformed or has invalid expiration format

    Example:
        >>> token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        >>> expiration = get_token_expiration(token)
        >>> if expiration:
        ...     print(f"Token expires at: {expiration.isoformat()}")
    """
    try:
        # Decode token without signature verification to access claims
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except jwt.DecodeError as e:
        raise OAuth2Error(f"Malformed JWT token: {e}") from e

    # Return None if no expiration claim
    if "exp" not in payload:
        return None

    try:
        # Convert Unix timestamp to timezone-aware datetime
        exp_timestamp = payload["exp"]
        return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    except (ValueError, TypeError, OSError) as e:
        raise OAuth2Error(f"Invalid expiration timestamp in JWT token: {e}") from e


def is_token_valid(token: str) -> bool:
    """
    Perform basic JWT token structure validation.

    This function checks if the provided string is a properly formatted JWT token
    by attempting to decode it without signature verification. It validates the
    basic structure but does not verify signatures or claims.

    Args:
        token: JWT token string to validate

    Returns:
        True if token has valid JWT structure, False otherwise

    Example:
        >>> token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        >>> if is_token_valid(token):
        ...     # Token has valid structure, safe to use
        ...     expiration = get_token_expiration(token)
        >>> else:
        ...     # Invalid token format
        ...     request_new_tokens()
    """
    if not token or not isinstance(token, str):
        return False

    try:
        # Attempt to decode token structure without verification
        jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
        return True
    except jwt.DecodeError:
        return False


def extract_token_expiration_for_storage(token: str) -> str:
    """
    Extract expiration from JWT token and return as ISO format string for storage.

    This function extracts the 'exp' claim from a JWT token and converts it to
    an ISO 8601 formatted string suitable for database storage. This eliminates
    the need to rely on the unreliable expires_in field from token responses.

    Args:
        token: JWT access token string

    Returns:
        ISO 8601 formatted expiration timestamp string

    Raises:
        OAuth2Error: If token is malformed or missing expiration claim
                     or if expires_in field was needed but token has no exp claim

    Example:
        >>> token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        >>> expires_at = extract_token_expiration_for_storage(token)
        >>> # Store expires_at in database instead of calculating from expires_in
    """
    expiration = get_token_expiration(token)
    if expiration is None:
        raise OAuth2Error(
            "JWT token missing expiration claim. Cannot determine token lifetime. "
            "This may indicate a non-standard token format from the Jobber API."
        )
    
    return expiration.isoformat()