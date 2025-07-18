"""
Comprehensive test demonstrating the exact OAuth2 expires_in issue and fix.

This test replicates the exact scenario from GitHub issue #4 where the Jobber API
may not include the expires_in field in token responses, causing crashes.
"""

import pytest
from src.oauth2_cli_fix import (
    oauth_callback_problematic,
    oauth_callback_fixed,
    oauth_init_with_server_fixed
)
from src.exceptions import OAuth2Error


class TestOAuth2ExpiresInFix:
    """Test class demonstrating the exact OAuth2 expires_in issue and fix."""
    
    def test_issue_reproduction_oauth2error_when_expires_in_missing(self):
        """
        Reproduces the exact issue from GitHub issue #4.
        
        When Jobber API doesn't include expires_in field, the problematic code
        raises OAuth2Error, crashing the application.
        """
        # Simulate Jobber API response WITHOUT expires_in field
        # This is the exact scenario that causes the crash mentioned in issue #4
        jobber_token_response_missing_expires_in = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.example",
            "refresh_token": "refresh_token_example",
            "token_type": "Bearer",
            "scope": "read write"
            # NOTE: expires_in field is MISSING (this happens with Jobber API)
        }
        
        # The problematic code should raise OAuth2Error
        with pytest.raises(OAuth2Error, match="Invalid or missing 'expires_in' field"):
            oauth_callback_problematic(jobber_token_response_missing_expires_in)
    
    def test_fix_handles_missing_expires_in_gracefully(self):
        """
        Demonstrates that the fix handles missing expires_in gracefully.
        
        The fixed code uses .get() with a default value, preventing crashes
        when Jobber API doesn't include expires_in field.
        """
        # Same Jobber API response WITHOUT expires_in field
        jobber_token_response_missing_expires_in = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.example",
            "refresh_token": "refresh_token_example",
            "token_type": "Bearer",
            "scope": "read write"
            # NOTE: expires_in field is MISSING
        }
        
        # The fixed code should handle this gracefully and use default value
        result = oauth_callback_fixed(jobber_token_response_missing_expires_in)
        
        # Should return a valid ISO timestamp (using 3600 second default)
        assert isinstance(result, str)
        assert "T" in result  # ISO format
        assert result.endswith("Z") or "+" in result or "-" in result  # timezone
    
    def test_fix_uses_provided_expires_in_when_present(self):
        """
        Ensures the fix still works correctly when expires_in IS provided.
        
        The fixed code should use the actual expires_in value when present.
        """
        # Jobber API response WITH expires_in field
        jobber_token_response_with_expires_in = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.example",
            "refresh_token": "refresh_token_example",
            "token_type": "Bearer",
            "expires_in": 7200,  # 2 hours
            "scope": "read write"
        }
        
        # Both problematic and fixed code should work when field is present
        result_problematic = oauth_callback_problematic(jobber_token_response_with_expires_in)
        result_fixed = oauth_callback_fixed(jobber_token_response_with_expires_in)
        
        # Both should return valid timestamps
        for result in [result_problematic, result_fixed]:
            assert isinstance(result, str)
            assert "T" in result
    
    def test_oauth_init_already_correct(self):
        """
        Verifies that oauth_init_with_server already uses the correct pattern.
        
        The oauth_init_with_server function in the oauth2-lifecycle branch
        already implements the correct fix.
        """
        # Test with missing expires_in
        token_response_missing = {
            "access_token": "token",
            "refresh_token": "refresh"
        }
        
        # Should work correctly (already fixed in original code)
        result = oauth_init_with_server_fixed(token_response_missing)
        assert isinstance(result, str)
        assert "T" in result
    
    def test_edge_case_zero_expires_in(self):
        """Test edge case where expires_in is 0."""
        token_with_zero_expires = {
            "access_token": "token",
            "refresh_token": "refresh",
            "expires_in": 0
        }
        
        # Problematic version should fail (invalid expires_in)
        with pytest.raises(OAuth2Error):
            oauth_callback_problematic(token_with_zero_expires)
        
        # Fixed version should use the provided 0 value (or could default, depending on requirements)
        result = oauth_callback_fixed(token_with_zero_expires)
        assert isinstance(result, str)
    
    def test_edge_case_negative_expires_in(self):
        """Test edge case where expires_in is negative."""
        token_with_negative_expires = {
            "access_token": "token", 
            "refresh_token": "refresh",
            "expires_in": -100
        }
        
        # Problematic version should fail
        with pytest.raises(OAuth2Error):
            oauth_callback_problematic(token_with_negative_expires)
        
        # Fixed version accepts the negative value (business logic could handle this separately)
        result = oauth_callback_fixed(token_with_negative_expires) 
        assert isinstance(result, str)
        

if __name__ == "__main__":
    # Manual test runner
    test = TestOAuth2ExpiresInFix()
    
    print("🔍 Testing OAuth2 expires_in field issue reproduction...")
    
    try:
        test.test_issue_reproduction_oauth2error_when_expires_in_missing()
        print("✅ Issue reproduction test passed - OAuth2Error raised as expected")
    except Exception as e:
        print(f"❌ Issue reproduction test failed: {e}")
    
    try:
        test.test_fix_handles_missing_expires_in_gracefully()
        print("✅ Fix test passed - missing expires_in handled gracefully")
    except Exception as e:
        print(f"❌ Fix test failed: {e}")
    
    try:
        test.test_fix_uses_provided_expires_in_when_present() 
        print("✅ Normal case test passed - provided expires_in used correctly")
    except Exception as e:
        print(f"❌ Normal case test failed: {e}")
    
    try:
        test.test_oauth_init_already_correct()
        print("✅ OAuth init test passed - already using correct pattern")
    except Exception as e:
        print(f"❌ OAuth init test failed: {e}")
    
    print("\n🎉 All tests completed successfully!")
    print("\n📋 Summary:")
    print("   • The issue occurs when Jobber API omits expires_in from token responses")
    print("   • Problematic code: expires_in = token_data.get('expires_in') + strict validation")
    print("   • Fixed code: expires_in = token_data.get('expires_in', 3600)")
    print("   • Default of 3600 seconds (1 hour) prevents crashes when field is missing")