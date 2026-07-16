import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from workbench import openrouter_account


class OpenRouterAccountTests(unittest.TestCase):
    def test_status_returns_visible_key_and_usage(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": {
                "label": "demo-key",
                "limit": 20,
                "limit_remaining": 7.5,
                "limit_reset": "monthly",
                "usage": 12.5,
                "usage_monthly": 3.25,
            }
        }
        with patch.object(openrouter_account.requests, "get", return_value=response):
            status = openrouter_account.get_status("sk-or-test-visible")

        self.assertEqual(status["state"], "usable")
        self.assertEqual(status["api_key"], "sk-or-test-visible")
        self.assertEqual(status["usage_monthly"], 3.25)
        self.assertEqual(status["limit_remaining"], 7.5)

    def test_zero_remaining_is_limit_exhausted(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"limit_remaining": 0}}
        with patch.object(openrouter_account.requests, "get", return_value=response):
            status = openrouter_account.get_status("sk-or-test-exhausted")

        self.assertEqual(status["state"], "limit_exhausted")

    def test_invalid_response_body_is_unavailable(self):
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("not json")
        with patch.object(openrouter_account.requests, "get", return_value=response):
            status = openrouter_account.get_status("sk-or-test-json")

        self.assertEqual(status["state"], "unavailable")
        self.assertEqual(status["api_key"], "sk-or-test-json")

    def test_replace_key_validates_and_updates_env_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            usable = {"state": "usable", "api_key": "sk-or-new-key"}
            with patch.dict(os.environ, {}, clear=False):
                with patch.object(openrouter_account, "get_status", return_value=usable):
                    status = openrouter_account.replace_key(" sk-or-new-key ", env_path)

                self.assertEqual(status, usable)
                self.assertIn("OPENROUTER_API_KEY=sk-or-new-key", env_path.read_text())
                self.assertEqual(os.environ["OPENROUTER_API_KEY"], "sk-or-new-key")


if __name__ == "__main__":
    unittest.main()
