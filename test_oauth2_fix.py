#!/usr/bin/env python3
"""
Test script to verify the OAuth2Manager token_type validation fix.

This script tests that the OAuth2Manager correctly handles missing or non-bearer
token_type fields without raising errors, addressing the issue where the Jobber
API might not always return this field.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.auth.oauth2_manager import OAuth2Manager
from src.exceptions import OAuth2Error, ConfigurationError


def test_token_type_validation_resilience():
    """Test that token_type validation is resilient to missing/non-standard values."""
    
    # Create OAuth2Manager instance
    manager = OAuth2Manager(
        client_id="test_client",
        client_secret="test_secret", 
        redirect_uri="http://localhost/callback"
    )
    
    print("🧪 Testing OAuth2Manager token_type validation resilience...")
    
    # Test 1: Valid response with bearer token type (should pass)
    try:
        valid_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "bearer",
            "expires_in": 3600
        }
        manager._validate_token_response(valid_response)
        print("✅ Test 1 PASSED: Valid response with 'bearer' token_type")
    except Exception as e:
        print(f"❌ Test 1 FAILED: {e}")
        return False

    # Test 2: Valid response with missing token_type (should pass)
    try:
        response_missing_token_type = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600
        }
        manager._validate_token_response(response_missing_token_type)
        print("✅ Test 2 PASSED: Valid response with missing token_type field")
    except Exception as e:
        print(f"❌ Test 2 FAILED: {e}")
        return False
    
    # Test 3: Valid response with non-bearer token_type (should pass - this is the main fix)
    try:
        response_non_bearer = {
            "access_token": "test_access_token", 
            "refresh_token": "test_refresh_token",
            "token_type": "mac",  # Non-bearer token type
            "expires_in": 3600
        }
        manager._validate_token_response(response_non_bearer)
        print("✅ Test 3 PASSED: Valid response with non-bearer token_type (resilient)")
    except Exception as e:
        print(f"❌ Test 3 FAILED: {e}")
        return False

    # Test 4: Valid response with case-insensitive bearer (should pass)
    try:
        response_case_bearer = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token", 
            "token_type": "Bearer",  # Different case
            "expires_in": 3600
        }
        manager._validate_token_response(response_case_bearer)
        print("✅ Test 4 PASSED: Valid response with 'Bearer' (case insensitive)")
    except Exception as e:
        print(f"❌ Test 4 FAILED: {e}")
        return False

    # Test 5: Invalid response missing access_token (should fail)
    try:
        invalid_response = {
            "refresh_token": "test_refresh_token",
            "token_type": "bearer"
        }
        manager._validate_token_response(invalid_response)
        print("❌ Test 5 FAILED: Should have raised OAuth2Error for missing access_token")
        return False
    except OAuth2Error:
        print("✅ Test 5 PASSED: Correctly raised OAuth2Error for missing access_token")
    except Exception as e:
        print(f"❌ Test 5 FAILED: Wrong exception type: {e}")
        return False

    # Test 6: Invalid response with error field (should fail)
    try:
        error_response = {
            "error": "invalid_grant",
            "error_description": "The provided authorization grant is invalid"
        }
        manager._validate_token_response(error_response)
        print("❌ Test 6 FAILED: Should have raised OAuth2Error for error response")
        return False
    except OAuth2Error as e:
        if "invalid_grant" in str(e):
            print("✅ Test 6 PASSED: Correctly raised OAuth2Error for error response")
        else:
            print(f"❌ Test 6 FAILED: Wrong error message: {e}")
            return False
    except Exception as e:
        print(f"❌ Test 6 FAILED: Wrong exception type: {e}")
        return False

    return True


def test_oauth2_manager_creation():
    """Test OAuth2Manager instance creation with proper validation."""
    
    print("\n🧪 Testing OAuth2Manager instance creation...")
    
    # Test valid creation
    try:
        manager = OAuth2Manager(
            client_id="test_client",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback"
        )
        print("✅ Valid OAuth2Manager creation successful")
    except Exception as e:
        print(f"❌ Valid creation failed: {e}")
        return False
    
    # Test invalid creation (empty client_id)
    try:
        manager = OAuth2Manager(
            client_id="",
            client_secret="test_secret",
            redirect_uri="http://localhost/callback"
        )
        print("❌ Should have failed with empty client_id")
        return False
    except ConfigurationError:
        print("✅ Correctly rejected empty client_id")
    except Exception as e:
        print(f"❌ Wrong exception for empty client_id: {e}")
        return False
    
    return True


def main():
    """Run all tests to verify the OAuth2Manager fix."""
    
    print("🚀 OAuth2Manager Token Type Validation Fix Verification")
    print("=" * 60)
    
    # Test OAuth2Manager creation
    if not test_oauth2_manager_creation():
        print("\n💥 OAuth2Manager creation tests FAILED")
        return 1
    
    # Test token validation resilience
    if not test_token_type_validation_resilience():
        print("\n💥 Token type validation tests FAILED")
        return 1
        
    print("\n🎉 ALL TESTS PASSED!")
    print("\n✅ The OAuth2Manager token_type validation fix is working correctly:")
    print("   - Handles missing token_type fields gracefully")
    print("   - Ignores non-bearer token_type values instead of raising errors") 
    print("   - Supports case-insensitive bearer token validation")
    print("   - Still validates required fields like access_token")
    print("   - Properly handles OAuth2 error responses")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())