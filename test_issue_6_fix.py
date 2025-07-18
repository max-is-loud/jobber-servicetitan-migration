#!/usr/bin/env python3
"""
Specific test to demonstrate the fix for GitHub Issue #6.

This test specifically addresses the issue: "The check for token_type is too strict. 
The Jobber API might not always return this field, and the code should be more 
resilient to this. Instead of raising an error if the token_type is not 'bearer', 
the code should simply ignore the token_type if it's present and not 'bearer'."
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.auth.oauth2_manager import OAuth2Manager
from src.exceptions import OAuth2Error


def test_issue_6_fix():
    """
    Test the specific fix for GitHub Issue #6.
    
    This test verifies that the OAuth2Manager handles the following scenarios
    without raising errors:
    1. Jobber API response with missing token_type field
    2. Jobber API response with non-bearer token_type
    3. Jobber API response with bearer token_type (should still work)
    """
    print("🔧 Testing GitHub Issue #6 Fix")
    print("=" * 50)
    print("Issue: token_type validation is too strict")
    print("Fix: Make validation resilient to missing/non-bearer token_type")
    print()
    
    manager = OAuth2Manager(
        client_id="test_client",
        client_secret="test_secret",
        redirect_uri="http://localhost/callback"
    )
    
    # Scenario 1: Jobber API response without token_type field
    print("📝 Scenario 1: Jobber API response missing token_type field")
    try:
        jobber_response_no_token_type = {
            "access_token": "jobber_access_token_12345",
            "refresh_token": "jobber_refresh_token_67890",
            "expires_in": 3600
            # Note: No token_type field - this should not cause an error
        }
        manager._validate_token_response(jobber_response_no_token_type)
        print("   ✅ PASS: Missing token_type handled gracefully")
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        return False
    
    # Scenario 2: Jobber API response with non-bearer token_type
    print("\n📝 Scenario 2: Jobber API response with non-bearer token_type")
    try:
        jobber_response_non_bearer = {
            "access_token": "jobber_access_token_12345",
            "refresh_token": "jobber_refresh_token_67890", 
            "expires_in": 3600,
            "token_type": "custom"  # Non-bearer type - should be ignored
        }
        manager._validate_token_response(jobber_response_non_bearer)
        print("   ✅ PASS: Non-bearer token_type ignored (not raising error)")
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        return False
    
    # Scenario 3: Standard bearer token (should still work)
    print("\n📝 Scenario 3: Standard bearer token_type (regression test)")
    try:
        standard_response = {
            "access_token": "jobber_access_token_12345",
            "refresh_token": "jobber_refresh_token_67890",
            "expires_in": 3600,
            "token_type": "bearer"  # Standard bearer - should work
        }
        manager._validate_token_response(standard_response)
        print("   ✅ PASS: Bearer token_type works correctly")
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        return False
    
    # Scenario 4: Case insensitive bearer
    print("\n📝 Scenario 4: Case-insensitive Bearer token_type")
    try:
        case_insensitive_response = {
            "access_token": "jobber_access_token_12345",
            "refresh_token": "jobber_refresh_token_67890",
            "expires_in": 3600,
            "token_type": "Bearer"  # Capital B - should work
        }
        manager._validate_token_response(case_insensitive_response)
        print("   ✅ PASS: Case-insensitive Bearer token_type works")
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        return False
    
    print("\n🎯 Issue #6 Fix Verification")
    print("=" * 30)
    print("✅ The OAuth2Manager now correctly handles:")
    print("   • Missing token_type fields from Jobber API")
    print("   • Non-bearer token_type values (ignores them)")
    print("   • Standard bearer tokens (backward compatibility)")
    print("   • Case-insensitive token type validation")
    print()
    print("🔍 Before fix: Would raise OAuth2Error for missing/non-bearer token_type")
    print("✨ After fix: Gracefully handles all Jobber API response variations")
    
    return True


def test_still_validates_required_fields():
    """Ensure we still validate truly required fields like access_token."""
    print("\n🛡️ Testing Required Field Validation (should still work)")
    print("=" * 55)
    
    manager = OAuth2Manager(
        client_id="test_client", 
        client_secret="test_secret",
        redirect_uri="http://localhost/callback"
    )
    
    # Missing access_token should still fail
    try:
        invalid_response = {
            "refresh_token": "some_refresh_token",
            "expires_in": 3600,
            "token_type": "bearer"
            # Missing access_token - should still fail
        }
        manager._validate_token_response(invalid_response)
        print("❌ FAIL: Should have raised error for missing access_token")
        return False
    except OAuth2Error as e:
        if "access_token" in str(e):
            print("✅ PASS: Still correctly validates required access_token field")
            return True
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False
    except Exception as e:
        print(f"❌ FAIL: Wrong exception type: {e}")
        return False


def main():
    """Run the specific test for GitHub Issue #6."""
    
    print("🚀 GitHub Issue #6 - OAuth2 token_type Validation Fix")
    print("=" * 60)
    print()
    
    # Test the main fix
    if not test_issue_6_fix():
        print("\n💥 Issue #6 fix verification FAILED")
        return 1
    
    # Ensure we still validate required fields
    if not test_still_validates_required_fields():
        print("\n💥 Required field validation test FAILED")
        return 1
    
    print("\n🎉 GitHub Issue #6 has been SUCCESSFULLY FIXED!")
    print("\nSummary of changes:")
    print("• OAuth2Manager._validate_token_response() is now resilient")
    print("• Missing token_type fields are handled gracefully")
    print("• Non-bearer token_type values are ignored (not rejected)")
    print("• Bearer tokens still work (backward compatibility)")
    print("• Required fields like access_token are still validated")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())