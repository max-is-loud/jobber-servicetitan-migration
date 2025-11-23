import unittest
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from src.repositories.repository import Repository, RepositoryError


class TestOAuthRefreshRobustness(unittest.TestCase):
    def setUp(self):
        # Use in-memory SQLite DB
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.repository = Repository(self.connection)
        self.repository.init_schema()

        # Setup initial token
        self.initial_access_token = "old_access_token"
        self.initial_refresh_token = "old_refresh_token"
        self.initial_expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        self.repository.save_oauth_tokens(
            self.initial_access_token, self.initial_refresh_token, self.initial_expires_at
        )

    def tearDown(self):
        self.connection.close()

    def test_refresh_succeeds_with_missing_expires_in(self):
        """
        Test that refresh_oauth_token_transactionally succeeds even if the
        callback returns a token dictionary missing the 'expires_in' field.
        """

        # Mock callback that returns a token WITHOUT expires_in
        # This simulates the Jobber API behavior that causes the crash
        def mock_refresh_callback(refresh_token):
            return {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                # "expires_in": 3600  <-- MISSING!
            }

        # This should currently FAIL with RepositoryError("Missing 'expires_in'...")
        # After fix, it should SUCCEED
        try:
            result = self.repository.refresh_oauth_token_transactionally(
                old_refresh_token=self.initial_refresh_token, refresh_callback=mock_refresh_callback
            )

            # Assertions for SUCCESS case (after fix)
            self.assertEqual(result["access_token"], "new_access_token")
            self.assertEqual(result["refresh_token"], "new_refresh_token")

            # Verify it was saved to DB
            tokens = self.repository.get_oauth_tokens()
            self.assertEqual(tokens["access_token"], "new_access_token")
            self.assertEqual(tokens["refresh_token"], "new_refresh_token")

            print("\n✅ Test PASSED: Refresh succeeded despite missing 'expires_in'")

        except RepositoryError as e:
            print(f"\n❌ Test FAILED (Expected before fix): {e}")
            # Re-raise to fail the test if we expect it to pass
            raise


if __name__ == "__main__":
    unittest.main()
