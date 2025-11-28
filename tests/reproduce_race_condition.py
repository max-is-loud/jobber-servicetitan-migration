import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
import time
import threading
import sys
import os
import sqlite3

# Ensure current directory is in path
if os.getcwd() not in sys.path:
    sys.path.append(os.getcwd())

from src.auth.auth_provider import AuthProvider
from src.repositories.repository import Repository
from src.exceptions import ConfigurationError, OAuth2Error


class TestAuthProviderRaceCondition(unittest.TestCase):
    def setUp(self):
        # Use in-memory SQLite DB
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.repository = Repository(self.connection)
        self.repository.init_schema()

        self.mock_oauth_manager = MagicMock()
        self.auth_provider = AuthProvider(self.mock_oauth_manager, self.repository)

        # Setup initial expired token in DB
        self.initial_expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.repository.save_oauth_tokens(
            access_token="old_access_token", refresh_token="old_refresh_token", expires_at=self.initial_expires_at
        )

    def tearDown(self):
        self.connection.close()

    def test_race_condition_refresh(self):
        """
        Simulate two threads trying to refresh the token at the same time.
        Thread 1 succeeds.
        Thread 2 should recover by finding the new token.
        """

        # We will simulate the race condition by manually invoking the refresh logic
        # because true threading with SQLite :memory: and transactions is complex to orchestrate deterministically.

        # Scenario:
        # 1. Initial state: old_refresh_token in DB.
        # 2. Thread 1 starts refresh.
        # 3. Thread 2 starts refresh (with old_refresh_token).

        # We'll use the real repository method `refresh_oauth_token_transactionally`.

        # Mock the oauth manager to return new tokens
        def refresh_side_effect(refresh_token):
            if refresh_token == "old_refresh_token":
                return {"access_token": "new_access_token", "refresh_token": "new_refresh_token", "expires_in": 3600}
            elif refresh_token == "new_refresh_token":
                return {
                    "access_token": "newer_access_token",
                    "refresh_token": "newer_refresh_token",
                    "expires_in": 3600,
                }
            raise OAuth2Error("Invalid refresh token")

        self.mock_oauth_manager.refresh_access_token.side_effect = refresh_side_effect

        print("--- Simulating Thread 1 ---")
        # Thread 1 calls get_token, which calls refresh_oauth_token_transactionally
        t1_token = self.auth_provider.get_token()
        print(f"Thread 1 got: {t1_token}")

        self.assertEqual(t1_token, "new_access_token")

        # Verify DB state
        tokens = self.repository.get_oauth_tokens()
        self.assertEqual(tokens["refresh_token"], "new_refresh_token")

        print("\n--- Simulating Thread 2 (Recovery) ---")
        # Thread 2 has the "old_refresh_token" (simulated) and tries to refresh it.
        # It calls refresh_oauth_token_transactionally with old_refresh_token.

        # We pass the SAME callback.
        # The repository method should detect that the token in DB ("new_refresh_token")
        # is different from "old_refresh_token", and return the DB token WITHOUT calling the callback.

        # Reset mock to ensure it's not called again for Thread 2
        self.mock_oauth_manager.refresh_access_token.reset_mock()

        # Manually call the repository method as AuthProvider would
        # (AuthProvider.get_token would re-read from DB first, but we want to simulate
        # the race where it *already* read the old token and decided to refresh)

        result = self.repository.refresh_oauth_token_transactionally(
            old_refresh_token="old_refresh_token", refresh_callback=self.mock_oauth_manager.refresh_access_token
        )

        print(f"Thread 2 got result: {result}")

        # Assertions
        self.assertEqual(result["access_token"], "new_access_token")
        self.assertEqual(result["refresh_token"], "new_refresh_token")

        # Crucially, the callback should NOT have been called, because the token was already refreshed
        self.mock_oauth_manager.refresh_access_token.assert_not_called()
        print("✓ Callback was NOT called for Thread 2 (Race condition handled)")


if __name__ == "__main__":
    unittest.main()
