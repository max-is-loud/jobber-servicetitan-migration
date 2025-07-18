#!/usr/bin/env python3
"""
Fix for OAuth2 expires_in fallback inconsistency issue.

This script demonstrates the solution to the problem where hardcoded fallback
for missing expires_in field creates inconsistent token expiration behavior.

The issue: Using a fixed 3600 seconds default when expires_in is missing
can cause premature or delayed refresh attempts if the actual token lifetime
differs from the fallback value.

The solution: Extract expiration directly from JWT tokens, eliminating
dependence on the unreliable expires_in field.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add the src directory to the path so we can import modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from src.auth.token_utils import extract_token_expiration_for_storage, get_token_expiration
    from src.exceptions import OAuth2Error
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure to run this from the project root directory")
    sys.exit(1)


def demonstrate_problematic_code():
    """Show the problematic code pattern that creates inconsistent behavior."""
    print("=== PROBLEMATIC CODE (Before Fix) ===")
    print()
    
    # This is the pattern from the original code that causes issues
    def process_token_data_old_way(token_data):
        """Old way: relies on unreliable expires_in field with hardcoded fallback."""
        # This is the problematic code from the PR
        expires_in = token_data.get("expires_in", 3600)  # Hardcoded fallback!
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()
        return expires_at
    
    # Simulate scenarios where Jobber API behavior varies
    scenarios = [
        {"description": "API returns expires_in", "token_data": {"access_token": "token1", "expires_in": 7200}},
        {"description": "API missing expires_in", "token_data": {"access_token": "token2"}},
        {"description": "API returns zero expires_in", "token_data": {"access_token": "token3", "expires_in": 0}},
    ]
    
    for scenario in scenarios:
        print(f"Scenario: {scenario['description']}")
        token_data = scenario["token_data"]
        expires_at = process_token_data_old_way(token_data)
        expires_in_used = token_data.get("expires_in", 3600)
        print(f"  Token data: {token_data}")
        print(f"  expires_in used: {expires_in_used} seconds")
        print(f"  Calculated expires_at: {expires_at}")
        print(f"  Problem: Using {'hardcoded fallback' if 'expires_in' not in token_data else 'API value'}")
        print()


def demonstrate_fixed_code():
    """Show the fixed code that uses JWT introspection for consistent behavior."""
    print("=== FIXED CODE (After Fix) ===")
    print()
    
    def process_token_data_new_way(token_data):
        """New way: extract expiration directly from JWT token."""
        access_token = token_data["access_token"]
        try:
            # Use JWT introspection instead of unreliable expires_in field
            expires_at = extract_token_expiration_for_storage(access_token)
            return expires_at
        except OAuth2Error as e:
            # Only error if we can't determine expiration from the token itself
            raise OAuth2Error(
                f"Cannot determine token expiration: {e}. "
                "This indicates the token may not be a standard JWT or may be malformed."
            )
    
    # Create sample JWT tokens for demonstration
    # In real implementation, these would come from Jobber API
    sample_jwt_payload_2h = {
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "sub": "user123"
    }
    
    sample_jwt_payload_30min = {
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()), 
        "sub": "user456"
    }
    
    # For demonstration, create simple JWT-like tokens
    # In reality, these would be properly signed JWT tokens from Jobber
    import base64
    import json
    
    def create_demo_jwt(payload):
        """Create a demo JWT token for testing (not properly signed)."""
        header = {"alg": "HS256", "typ": "JWT"}
        header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = "demo_signature"
        return f"{header_encoded}.{payload_encoded}.{signature}"
    
    # Test scenarios with actual JWT tokens containing expiration info
    scenarios = [
        {
            "description": "Token with 2-hour expiration (no expires_in field)",
            "token_data": {
                "access_token": create_demo_jwt(sample_jwt_payload_2h),
                # Note: no expires_in field - this would use 3600s fallback in old code
            }
        },
        {
            "description": "Token with 30-min expiration (conflicting expires_in)", 
            "token_data": {
                "access_token": create_demo_jwt(sample_jwt_payload_30min),
                "expires_in": 7200  # Wrong value - JWT says 30min but field says 2h
            }
        }
    ]
    
    for scenario in scenarios:
        print(f"Scenario: {scenario['description']}")
        token_data = scenario["token_data"]
        
        try:
            expires_at = process_token_data_new_way(token_data)
            
            # Show what each method would produce
            access_token = token_data["access_token"]
            jwt_expiration = get_token_expiration(access_token)
            old_way_expires_in = token_data.get("expires_in", 3600)
            old_way_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=old_way_expires_in)
            ).isoformat()
            
            print(f"  Token data: access_token=<JWT>, expires_in={token_data.get('expires_in', 'missing')}")
            print(f"  JWT exp claim: {jwt_expiration}")
            print(f"  NEW WAY result: {expires_at}")
            print(f"  OLD WAY would use: {old_way_expires_in}s -> {old_way_expires_at}")
            
            # Calculate difference
            if jwt_expiration:
                time_diff = jwt_expiration.timestamp() - datetime.fromisoformat(old_way_expires_at.replace('Z', '+00:00')).timestamp()
                print(f"  Difference: {time_diff/60:.1f} minutes ({'JWT is later' if time_diff > 0 else 'JWT is earlier'})")
                print(f"  Fix: Eliminates {abs(time_diff/60):.1f} minutes of timing inconsistency!")
            
        except OAuth2Error as e:
            print(f"  Error: {e}")
        
        print()


def main():
    """Demonstrate the OAuth2 expires_in fallback fix."""
    print("OAuth2 expires_in Fallback Fix Demonstration")
    print("=" * 50)
    print()
    print("This demonstrates the fix for the issue where hardcoded")
    print("expires_in fallback creates inconsistent token expiration behavior.")
    print()
    
    demonstrate_problematic_code()
    demonstrate_fixed_code()
    
    print("=== SUMMARY ===")
    print()
    print("The fix eliminates inconsistent expiration behavior by:")
    print("1. Removing dependency on unreliable expires_in field from API responses")
    print("2. Using JWT token introspection to extract actual expiration times")
    print("3. Providing consistent behavior regardless of API response variations")
    print("4. Failing fast with clear errors if tokens don't contain expiration info")
    print()
    print("Benefits:")
    print("- No more premature refresh attempts")
    print("- No more delayed refresh attempts") 
    print("- Consistent behavior across all OAuth2 flows")
    print("- Clear error messages when tokens are non-standard")


if __name__ == "__main__":
    main()