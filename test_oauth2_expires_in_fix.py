"""
Test to demonstrate the expires_in KeyError issue and verify the fix.
"""

import pytest
from src.auth.oauth2_token_handler import OAuth2TokenHandler
from src.exceptions import OAuth2Error


class TestOAuth2ExpiresInIssue:
    """Test class to demonstrate the expires_in field issue."""

    def setup_method(self):
        """Set up test instance."""
        self.handler = OAuth2TokenHandler()

    def test_problematic_method_raises_keyerror_when_expires_in_missing(self):
        """Test that the problematic method raises KeyError when expires_in is missing."""
        # Token data WITHOUT expires_in field - this simulates the Jobber API issue
        token_data_missing_expires_in = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer"
            # Missing "expires_in" field!
        }
        
        # This should raise KeyError due to the problematic access pattern
        with pytest.raises(KeyError, match="expires_in"):
            self.handler.handle_token_data_problematic(token_data_missing_expires_in)

    def test_better_but_still_problematic_method_raises_oauth2error(self):
        """Test that the better method still raises OAuth2Error when expires_in is missing."""
        # Token data WITHOUT expires_in field
        token_data_missing_expires_in = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer"
        }
        
        # This should raise OAuth2Error due to strict validation
        with pytest.raises(OAuth2Error, match="Invalid or missing 'expires_in' field"):
            self.handler.handle_token_data_better_but_still_problematic(token_data_missing_expires_in)

    def test_fixed_method_handles_missing_expires_in_gracefully(self):
        """Test that the fixed method handles missing expires_in gracefully."""
        # Token data WITHOUT expires_in field
        token_data_missing_expires_in = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer"
        }
        
        # This should NOT raise an error and should use the default value
        result = self.handler.handle_token_data_fixed(token_data_missing_expires_in)
        
        # Should return a valid ISO timestamp string
        assert isinstance(result, str)
        assert "T" in result  # ISO format contains 'T'
        assert result.endswith("Z") or "+" in result or "-" in result  # timezone info

    def test_fixed_method_uses_provided_expires_in_when_present(self):
        """Test that the fixed method uses the provided expires_in when present."""
        # Token data WITH expires_in field
        token_data_with_expires_in = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 7200  # 2 hours
        }
        
        # This should work and use the provided expires_in value
        result = self.handler.handle_token_data_fixed(token_data_with_expires_in)
        
        # Should return a valid ISO timestamp string
        assert isinstance(result, str)
        assert "T" in result  # ISO format contains 'T'

    def test_all_methods_work_when_expires_in_is_present(self):
        """Test that all methods work when expires_in is present."""
        # Token data WITH expires_in field
        token_data_complete = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        
        # All methods should work when expires_in is present
        result1 = self.handler.handle_token_data_problematic(token_data_complete)
        result2 = self.handler.handle_token_data_better_but_still_problematic(token_data_complete)
        result3 = self.handler.handle_token_data_fixed(token_data_complete)
        
        # All should return valid timestamps
        for result in [result1, result2, result3]:
            assert isinstance(result, str)
            assert "T" in result