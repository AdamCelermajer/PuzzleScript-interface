import os
import unittest
from dataclasses import fields
from types import SimpleNamespace
from unittest.mock import patch

from client.engine.llm_client import Config, LlmClient


class LlmClientConfigTests(unittest.TestCase):
    def test_defaults_route_gpt_55_model_through_openrouter(self) -> None:
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

        self.assertEqual(cfg.model, "openai/gpt-5.5")
        self.assertEqual(cfg.reasoning_effort, "low")
        self.assertEqual(cfg.openrouter_api_key, "test-openrouter-key")
        self.assertEqual(routed_key, "test-openrouter-key")
        self.assertFalse(hasattr(cfg, "api_key"))
        self.assertIn("model", {field.name for field in fields(Config)})
        self.assertIn("reasoning_effort", {field.name for field in fields(Config)})
        self.assertEqual(
            client._litellm_model(),
            "openrouter/openai/gpt-5.5",
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
        self.assertIn("Asking openrouter/openai/gpt-5.5", events[0])
        self.assertEqual(completion.call_args.kwargs["reasoning_effort"], "low")

    def test_call_logs_purpose_when_supplied(self) -> None:
        events: list[str] = []
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client = LlmClient(cfg, event_sink=events.append)
            with patch(
                "client.engine.llm_client.litellm.completion",
                return_value=response,
            ):
                result = client._call("system", "prompt", purpose="subgoal/action")

        self.assertEqual(result, "ok")
        self.assertEqual(
            events[0],
            "Asking openrouter/openai/gpt-5.5 for subgoal/action...",
        )

    def test_call_text_uses_single_low_reasoning_model(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client = LlmClient(cfg)
            with patch(
                "client.engine.llm_client.litellm.completion",
                return_value=response,
            ) as completion:
                result = client.call_text("system", "prompt", purpose="rule creation")

        self.assertEqual(result, "ok")
        self.assertEqual(
            completion.call_args.kwargs["model"],
            "openrouter/openai/gpt-5.5",
        )
        self.assertEqual(completion.call_args.kwargs["reasoning_effort"], "low")

    def test_call_can_attach_image_data_urls_to_user_message(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"plan": []}'))]
        )
        image_url = "data:image/png;base64,iVBORw0KGgo="
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            cfg = Config()
            client = LlmClient(cfg)
            with patch(
                "client.engine.llm_client.litellm.completion",
                return_value=response,
            ) as completion:
                result = client._call(
                    "system",
                    "prompt",
                    json_mode=True,
                    image_data_urls=[image_url],
                )

        self.assertEqual(result, '{"plan": []}')
        messages = completion.call_args.kwargs["messages"]
        self.assertEqual(
            completion.call_args.kwargs["model"],
            "openrouter/openai/gpt-5.5",
        )
        self.assertEqual(completion.call_args.kwargs["reasoning_effort"], "low")
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
