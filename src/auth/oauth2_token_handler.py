"""
OAuth2 token handling module demonstrating the expires_in field issue.

This module shows the problematic token_data access pattern that needs to be fixed.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from ..exceptions import OAuth2Error


class OAuth2TokenHandler:
    """
    Demonstrates the problematic expires_in field access pattern.
    
    This class contains the issue mentioned in GitHub issue #4 where
    expires_in is accessed from token_data without a default value.
    """

    def handle_token_data_problematic(self, token_data: Dict[str, Any]) -> str:
        """
        PROBLEMATIC: This method demonstrates the issue where expires_in
        is accessed without a default value, which can cause KeyError.
        
        Args:
            token_data: Dictionary containing token information
            
        Returns:
            ISO formatted expiration timestamp
            
        Raises:
            KeyError: If expires_in field is missing from token_data
        """
        # THIS IS THE PROBLEMATIC CODE that the issue refers to:
        expires_in = token_data["expires_in"]  # Can raise KeyError!
        
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()
        
        return expires_at

    def handle_token_data_better_but_still_problematic(self, token_data: Dict[str, Any]) -> str:
        """
        STILL PROBLEMATIC: This method uses .get() but then validates strictly,
        which can still cause issues.
        
        Args:
            token_data: Dictionary containing token information
            
        Returns:
            ISO formatted expiration timestamp
            
        Raises:
            OAuth2Error: If expires_in field is missing or invalid
        """
        # This is still problematic because it fails when expires_in is missing
        expires_in = token_data.get("expires_in")
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise OAuth2Error("Invalid or missing 'expires_in' field in token data.")
        
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()
        
        return expires_at

    def handle_token_data_fixed(self, token_data: Dict[str, Any]) -> str:
        """
        FIXED: This method demonstrates the correct pattern using .get()
        with a default value as suggested in the issue.
        
        Args:
            token_data: Dictionary containing token information
            
        Returns:
            ISO formatted expiration timestamp
        """
        # THIS IS THE FIXED VERSION using .get() with default value:
        expires_in = token_data.get("expires_in", 3600)  # Default to 1 hour if not provided
        
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()
        
        return expires_at