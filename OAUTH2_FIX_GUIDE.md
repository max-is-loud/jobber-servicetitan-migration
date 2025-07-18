# OAuth2 expires_in Fallback Fix - Implementation Guide

## Problem Statement

The fallback for missing `expires_in` field creates tokens with inconsistent expiration behavior. The default of 3600 seconds may not match actual token lifetime from Jobber API, potentially causing premature or delayed refresh attempts.

## Root Cause Analysis

From the PR code review, the issue occurs in multiple locations where OAuth2 token expiration is calculated:

1. **Line 330-332 in `src/cli.py`** (OAuth2 init with server):
```python
# Handle missing expires_in field (Jobber API doesn't always include it)
expires_in = token_data.get(
    "expires_in", 3600
)  # Default to 1 hour if not provided
```

2. **Line 433 in `src/cli.py`** (OAuth2 callback):
```python
expires_in = token_data["expires_in"]  # Direct access without handling missing field
```

3. **Line 92 in `src/auth/auth_provider.py`** (Token refresh):
```python
expires_in = new_tokens["expires_in"]  # Direct access that could fail
```

## The Fix

Replace all instances of `expires_in` field dependency with JWT token introspection using the `extract_token_expiration_for_storage()` utility function.

### Implementation Steps

#### 1. Update `src/cli.py` - OAuth Init Function

**BEFORE (Problematic):**
```python
def _oauth_init_with_server(db: Optional[Path], port: int) -> None:
    # ... existing code ...
    
    # Exchange code for tokens
    token_data = oauth_manager.exchange_code_for_tokens(auth_result["code"])
    
    # Store tokens in database
    from datetime import datetime, timedelta, timezone
    
    # Handle missing expires_in field (Jobber API doesn't always include it)
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
```

**AFTER (Fixed):**
```python
def _oauth_init_with_server(db: Optional[Path], port: int) -> None:
    # ... existing code ...
    
    # Exchange code for tokens
    token_data = oauth_manager.exchange_code_for_tokens(auth_result["code"])
    
    # Store tokens in database using JWT introspection
    from .auth.token_utils import extract_token_expiration_for_storage
    
    try:
        expires_at = extract_token_expiration_for_storage(token_data["access_token"])
    except OAuth2Error as e:
        raise OAuth2Error(
            f"Cannot determine token expiration from JWT: {e}. "
            "This may indicate that the Jobber API returned a non-standard token. "
            "Please contact support if this issue persists."
        ) from e
    
    repository.save_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
    )
```

#### 2. Update `src/cli.py` - OAuth Callback Function

**BEFORE (Problematic):**
```python
def oauth_callback(code: str, db: Optional[Path] = None) -> None:
    # ... existing code ...
    
    # Store tokens in database
    from datetime import datetime, timedelta, timezone
    
    expires_in = token_data["expires_in"]  # Could fail if missing
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    
    repository.save_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
    )
```

**AFTER (Fixed):**
```python
def oauth_callback(code: str, db: Optional[Path] = None) -> None:
    # ... existing code ...
    
    # Store tokens in database using JWT introspection
    from .auth.token_utils import extract_token_expiration_for_storage
    
    try:
        expires_at = extract_token_expiration_for_storage(token_data["access_token"])
    except OAuth2Error as e:
        raise OAuth2Error(
            f"Cannot determine token expiration from JWT: {e}. "
            "This may indicate that the Jobber API returned a non-standard token. "
            "Please contact support if this issue persists."
        ) from e
    
    repository.save_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
    )
```

#### 3. Update `src/auth/auth_provider.py` - Token Refresh

**BEFORE (Problematic):**
```python
def get_token(self) -> str:
    # ... existing code ...
    
    if is_token_expired(access_token):
        # Refresh the access token
        new_tokens = self.oauth_manager.refresh_access_token(refresh_token)
        
        # Convert expires_in to ISO 8601 timestamp
        expires_in = new_tokens["expires_in"]  # Could fail if missing
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()
        
        # Store the new tokens
        self.repository.save_oauth_tokens(
            access_token=new_tokens["access_token"],
            refresh_token=new_tokens["refresh_token"],
            expires_at=expires_at,
        )
```

**AFTER (Fixed):**
```python
def get_token(self) -> str:
    # ... existing code ...
    
    if is_token_expired(access_token):
        # Refresh the access token
        new_tokens = self.oauth_manager.refresh_access_token(refresh_token)
        
        # Extract expiration from JWT token
        from .token_utils import extract_token_expiration_for_storage
        
        try:
            expires_at = extract_token_expiration_for_storage(new_tokens["access_token"])
        except OAuth2Error as e:
            raise OAuth2Error(
                f"Cannot determine token expiration from refreshed JWT: {e}. "
                "The refresh token response may contain a non-standard token format."
            ) from e
        
        # Store the new tokens
        self.repository.save_oauth_tokens(
            access_token=new_tokens["access_token"],
            refresh_token=new_tokens["refresh_token"],
            expires_at=expires_at,
        )
```

## Benefits of This Fix

1. **Eliminates Inconsistent Behavior**: No more hardcoded 3600s fallback that may not match actual token lifetime
2. **Uses Authoritative Source**: JWT tokens contain the actual expiration time set by Jobber
3. **Handles All Scenarios**: Works whether `expires_in` field is present, missing, or incorrect
4. **Clear Error Messages**: Provides helpful error messages when tokens are non-standard
5. **Backward Compatible**: No changes required for existing environment token authentication

## Test Results

The fix has been tested with the following scenarios:

✅ **Missing expires_in field**: Uses JWT expiration correctly  
✅ **Conflicting expires_in field**: Ignores wrong API value, uses JWT  
✅ **Consistent values**: Works normally when API is accurate  
✅ **Malformed tokens**: Provides clear error messages  
✅ **Missing JWT exp claim**: Fails gracefully with helpful errors  

## Impact Assessment

This is a **minimal, surgical change** that:
- Only modifies token expiration calculation logic
- Does not change any API interfaces
- Maintains all existing functionality
- Provides better reliability and consistency
- Reduces support burden from timing-related auth issues

The fix directly addresses the issue described in the GitHub PR comment and ensures that OAuth2 token expiration handling is reliable and consistent across all flows.