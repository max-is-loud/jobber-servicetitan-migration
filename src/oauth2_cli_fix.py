"""
CLI module demonstrating the expires_in fix for OAuth2 token handling.

This module contains the simplified OAuth2 callback function that demonstrates
the issue and its fix.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .exceptions import OAuth2Error


def oauth_callback_problematic(token_data: Dict[str, Any]) -> str:
    """
    PROBLEMATIC VERSION: This function demonstrates the issue mentioned in GitHub issue #4.
    
    The expires_in field is accessed using .get() but then validated strictly,
    which causes OAuth2Error when the field is missing from Jobber API response.
    
    Args:
        token_data: Token response from OAuth2 API
        
    Returns:
        ISO formatted expiration timestamp
        
    Raises:
        OAuth2Error: If expires_in field is missing or invalid
    """
    # THIS IS THE PROBLEMATIC PATTERN from the oauth2-lifecycle branch:
    expires_in = token_data.get("expires_in")
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise OAuth2Error("Invalid or missing 'expires_in' field in token data.")
    
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    
    return expires_at


def oauth_callback_fixed(token_data: Dict[str, Any]) -> str:
    """
    FIXED VERSION: This function demonstrates the fix suggested in GitHub issue #4.
    
    Uses .get() method with a default value to prevent KeyError and OAuth2Error
    when expires_in field is missing from the token response.
    
    Args:
        token_data: Token response from OAuth2 API
        
    Returns:
        ISO formatted expiration timestamp
    """
    # THIS IS THE FIXED PATTERN using .get() with default value:
    expires_in = token_data.get("expires_in", 3600)  # Default to 1 hour if not provided
    
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    
    return expires_at


def oauth_init_with_server_fixed(token_data: Dict[str, Any]) -> str:
    """
    ALREADY FIXED: This function already uses the correct pattern.
    
    This represents the _oauth_init_with_server function from the oauth2-lifecycle
    branch which already implements the correct pattern.
    
    Args:
        token_data: Token response from OAuth2 API
        
    Returns:
        ISO formatted expiration timestamp
    """
    # This pattern is already correct in the oauth2-lifecycle branch:
    expires_in = token_data.get("expires_in", 3600)  # Default to 1 hour if not provided
    
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    
    return expires_at