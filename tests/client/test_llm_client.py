import os
import unittest
from dataclasses import fields
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from client.engine.llm_client import Config, LlmClient


class LlmClientConfigTests(unittest.TestCase):
    def _make_client(self, cfg: Config, event_sink=None):
        """Create an LlmClient with the real OpenAI client mocked out."""
        with patch("client.engine.llm_client.OpenAI") as MockOpenAI:
            client = LlmClient(cfg, event_sink=event_sink)
            mock_client = MockOpenAI.return_value
            # Replace the instance created in __init__ with our mock client.
            client.client = mock_client
            return client, mock_client

    def test_defaults_use_openrouter_compatible_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-openrouter-key",
                "UNRELATED_LLM_KEY": "ignored",
            },
            clear=True,
        ):
            cfg = Config()
            client, _ = self._make_client(cfg)

        self.assertEqual(cfg.model, "anthropic/claude-opus-4.8")
        self.assertEqual(cfg.reasoning_effort, "")
        self.assertEqual(cfg.openrouter_api_key, "test-openrouter-key")
        self.assertFalse(hasattr(cfg, "api_key"))
        self.assertIn("model", {field.name for field in fields(Config)})
        self.assertIn("reasoning_effort", {field.name for field in fields(Config)})
        self.assertEqual(
            client._openrouter_model(),
            "anthropic/claude-opus-4.8",
        )

    def test_openrouter_prefix_is_stripped_from_model(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config(model="openrouter/moonshotai/kimi-k2.7-code")
            client, _ = self._make_client(cfg)

        self.assertEqual(client._openrouter_model(), "moonshotai/kimi-k2.7-code")

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
            client, mock_client = self._make_client(cfg, event_sink=events.append)
            mock_client.chat.completions.create.return_value = response
            result = client._call("system", "prompt", json_mode=True)

        self.assertEqual(result, '{"plan": ["ACTION1"]}')
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)
        self.assertIn("Asking anthropic/claude-opus-4.8", events[0])
        self.assertNotIn(
            "reasoning_effort",
            mock_client.chat.completions.create.call_args.kwargs,
        )

    def test_call_logs_purpose_when_supplied(self) -> None:
        events: list[str] = []
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client, mock_client = self._make_client(cfg, event_sink=events.append)
            mock_client.chat.completions.create.return_value = response
            result = client._call("system", "prompt", purpose="subgoal/action")

        self.assertEqual(result, "ok")
        self.assertEqual(
            events[0],
            "Asking anthropic/claude-opus-4.8 for subgoal/action...",
        )

    def test_call_text_uses_configured_model(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client, mock_client = self._make_client(cfg)
            mock_client.chat.completions.create.return_value = response
            result = client.call_text("system", "prompt", purpose="rule creation")

        self.assertEqual(result, "ok")
        self.assertEqual(
            mock_client.chat.completions.create.call_args.kwargs["model"],
            "anthropic/claude-opus-4.8",
        )

    def test_call_can_attach_image_data_urls_to_user_message(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"plan": []}'))]
        )
        image_url = "data:image/png;base64,iVBORw0KGgo="
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client, mock_client = self._make_client(cfg)
            mock_client.chat.completions.create.return_value = response
            result = client._call(
                "system",
                "prompt",
                json_mode=True,
                image_data_urls=[image_url],
            )

        self.assertEqual(result, '{"plan": []}')
        create_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = create_kwargs["messages"]
        self.assertEqual(create_kwargs["model"], "anthropic/claude-opus-4.8")
        self.assertEqual(messages[0], {"role": "system", "content": "system"})
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(
            messages[1]["content"],
            [
                {"type": "text", "text": "prompt"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        )

    def test_call_json_returns_object_and_rejects_invalid_json(self) -> None:
        good = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"rules": []}'))]
        )
        bad = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client, mock_client = self._make_client(cfg)
            mock_client.chat.completions.create.side_effect = [good, bad]
            self.assertEqual(client.call_json("system", "prompt"), {"rules": []})
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                client.call_json("system", "prompt")


if __name__ == "__main__":
    unittest.main()
