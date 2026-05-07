import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from client.engine.llm_client import Config, LlmClient


class LlmClientConfigTests(unittest.TestCase):
    def test_defaults_route_nitro_model_through_openrouter(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-openrouter-key",
                "UNRELATED_LLM_KEY": "ignored",
            },
            clear=True,
        ):
            cfg = Config()
            client = LlmClient(cfg)
            routed_key = os.environ["OPENROUTER_API_KEY"]

        self.assertEqual(cfg.flash_model, "openai/gpt-oss-120b:nitro")
        self.assertEqual(cfg.pro_model, "openai/gpt-oss-120b:nitro")
        self.assertEqual(cfg.openrouter_api_key, "test-openrouter-key")
        self.assertEqual(routed_key, "test-openrouter-key")
        self.assertFalse(hasattr(cfg, "api_key"))
        self.assertEqual(
            client._litellm_model("flash"),
            "openrouter/openai/gpt-oss-120b:nitro",
        )

    def test_openrouter_key_is_required(self) -> None:
        with patch.dict(os.environ, {"UNRELATED_LLM_KEY": "ignored"}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENROUTER_API_KEY not found"):
                Config()

    def test_call_logs_before_single_openrouter_request(self) -> None:
        events: list[str] = []
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"plan": ["ACTION1"]}'))
            ]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client = LlmClient(cfg, event_sink=events.append)
            with patch("client.engine.llm_client.litellm.completion", return_value=response) as completion:
                result = client._call("system", "prompt", json_mode=True)

        self.assertEqual(result, '{"plan": ["ACTION1"]}')
        self.assertEqual(completion.call_count, 1)
        self.assertIn("Asking openrouter/openai/gpt-oss-120b:nitro", events[0])

    def test_call_json_returns_object_and_rejects_invalid_json(self) -> None:
        good = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"rules": []}'))]
        )
        bad = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client = LlmClient(cfg)
            with patch(
                "client.engine.llm_client.litellm.completion",
                side_effect=[good, bad],
            ):
                self.assertEqual(client.call_json("system", "prompt"), {"rules": []})
                with self.assertRaisesRegex(ValueError, "invalid JSON"):
                    client.call_json("system", "prompt")


if __name__ == "__main__":
    unittest.main()
