"""
OAuth2 expires_in fallback fix implementation.

This module provides the fixed implementation for handling OAuth2 token expiration
that eliminates the inconsistent behavior caused by hardcoded fallbacks.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from src.auth.token_utils import extract_token_expiration_for_storage
from src.exceptions import OAuth2Error


def store_oauth_tokens_fixed(repository, token_data: Dict[str, Any]) -> None:
    """
    Fixed version of OAuth token storage that uses JWT introspection.
    
    This function replaces the problematic code pattern that relied on
    unreliable expires_in field with hardcoded fallback.
    
    Args:
        repository: Repository instance for token storage
        token_data: Token response from OAuth API
        
    Raises:
        OAuth2Error: If token expiration cannot be determined from JWT
    """
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    
    # FIXED: Use JWT introspection instead of unreliable expires_in field
    try:
        expires_at = extract_token_expiration_for_storage(access_token)
    except OAuth2Error as e:
        # Provide helpful error message about the missing field
        raise OAuth2Error(
            f"Cannot determine token expiration from JWT: {e}. "
            "This may indicate that the Jobber API returned a non-standard token. "
            "Please contact support if this issue persists."
        ) from e
    
    repository.save_oauth_tokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def store_oauth_tokens_old_problematic(repository, token_data: Dict[str, Any]) -> None:
    """
    OLD PROBLEMATIC version that demonstrates the issue.
    
    This is the pattern from the original code that creates inconsistent behavior.
    DO NOT USE - shown for comparison only.
    """
    access_token = token_data["access_token"] 
    refresh_token = token_data["refresh_token"]
    
    # PROBLEMATIC: Hardcoded fallback creates inconsistent behavior
    expires_in = token_data.get("expires_in", 3600)  # This is the problem!
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    
    repository.save_oauth_tokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def validate_expires_in_consistency(token_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Utility function to validate consistency between expires_in field and JWT expiration.
    
    This can be used for debugging or logging to detect when the Jobber API
    provides inconsistent expiration information.
    
    Args:
        token_data: Token response from OAuth API
        
    Returns:
        Dictionary with analysis results
    """
    access_token = token_data["access_token"]
    expires_in_field = token_data.get("expires_in")
    
    try:
        from src.auth.token_utils import get_token_expiration
        jwt_expiration = get_token_expiration(access_token)
        
        if jwt_expiration is None:
            return {
                "status": "no_jwt_exp",
                "message": "JWT token missing expiration claim",
                "expires_in_field": expires_in_field,
                "recommendation": "Use expires_in field if available, error if not"
            }
        
        if expires_in_field is None:
            return {
                "status": "missing_expires_in",
                "message": "API response missing expires_in field",
                "jwt_expiration": jwt_expiration.isoformat(),
                "recommendation": "Use JWT expiration (this is what the fix does)"
            }
        
        # Both are available - check consistency
        now = datetime.now(timezone.utc)
        expected_expiration = now + timedelta(seconds=expires_in_field)
        time_diff = (jwt_expiration - expected_expiration).total_seconds()
        
        if abs(time_diff) > 60:  # More than 1 minute difference
            return {
                "status": "inconsistent",
                "message": f"expires_in field ({expires_in_field}s) conflicts with JWT exp claim",
                "jwt_expiration": jwt_expiration.isoformat(),
                "field_would_give": expected_expiration.isoformat(),
                "difference_minutes": time_diff / 60,
                "recommendation": "Use JWT expiration for accuracy"
            }
        else:
            return {
                "status": "consistent",
                "message": "expires_in field matches JWT expiration",
                "jwt_expiration": jwt_expiration.isoformat(),
                "difference_seconds": time_diff
            }
            
    except OAuth2Error as e:
        return {
            "status": "jwt_error",
            "message": f"Cannot parse JWT token: {e}",
            "expires_in_field": expires_in_field,
            "recommendation": "Use expires_in field if available, error if not"
        }


# Example of how to apply the fix to the CLI code from the PR
CLI_FIX_EXAMPLE = '''
# BEFORE (from original PR - PROBLEMATIC):
def _oauth_init_with_server(db, port):
    # ... authorization flow code ...
    
    # Exchange code for tokens
    token_data = oauth_manager.exchange_code_for_tokens(auth_result["code"])
    
    # Store tokens in database
    from datetime import datetime, timedelta, timezone
    
    # PROBLEMATIC: Handle missing expires_in field (Jobber API doesn't always include it)
    expires_in = token_data.get(
        "expires_in", 3600
    )  # Default to 1 hour if not provided
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    
    repository.save_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
    )

# AFTER (FIXED):
def _oauth_init_with_server(db, port):
    # ... authorization flow code ...
    
    # Exchange code for tokens
    token_data = oauth_manager.exchange_code_for_tokens(auth_result["code"])
    
    # Store tokens in database using the fixed method
    store_oauth_tokens_fixed(repository, token_data)
'''

CALLBACK_FIX_EXAMPLE = '''
# BEFORE (from original PR - PROBLEMATIC):
def oauth_callback(code, db):
    # ... token exchange code ...
    
    # Store tokens in database
    from datetime import datetime, timedelta, timezone
    
    expires_in = token_data["expires_in"]  # Direct access without fallback - would fail if missing
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()

# AFTER (FIXED):
def oauth_callback(code, db):
    # ... token exchange code ...
    
    # Store tokens in database using the fixed method
    store_oauth_tokens_fixed(repository, token_data)
'''