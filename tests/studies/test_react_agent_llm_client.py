import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from studies.react_agent.llm_client import ReactLlmClient, ReactLlmConfig


class ReactLlmClientTests(unittest.TestCase):
    def _make_client(self, cfg: ReactLlmConfig):
        with patch("studies.react_agent.llm_client.OpenAI") as MockOpenAI:
            client = ReactLlmClient(cfg)
            mock_client = MockOpenAI.return_value
            client.client = mock_client
            return client, mock_client, MockOpenAI

    def test_requires_react_specific_moonshot_key(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "main-key"}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "REACT_AGENT_KIMI_API_KEY or REACT_AGENT_MOONSHOT_API_KEY not found",
            ):
                ReactLlmConfig()

    def test_uses_kimi_and_react_specific_key(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch.dict(
            os.environ,
            {"REACT_AGENT_KIMI_API_KEY": "react-key"},
            clear=True,
        ):
            cfg = ReactLlmConfig()
            client, mock_client, mock_openai = self._make_client(cfg)
            mock_client.chat.completions.create.return_value = response

            result = client.call_text("system", "prompt", purpose="react agent")

        self.assertEqual(result, "ok")
        self.assertEqual(cfg.model, "kimi-k2.6")
        self.assertEqual(cfg.base_url, "https://api.kimi.com/coding/v1")
        self.assertEqual(cfg.kimi_api_key, "react-key")
        self.assertEqual(mock_openai.call_args.kwargs["base_url"], cfg.base_url)
        self.assertEqual(
            mock_client.chat.completions.create.call_args.kwargs["model"],
            "kimi-k2.6",
        )
        self.assertEqual(
            mock_client.chat.completions.create.call_args.kwargs["extra_body"],
            {"thinking": {"type": "disabled"}},
        )

    def test_moonshot_prefix_is_stripped(self) -> None:
        with patch.dict(
            os.environ,
            {"REACT_AGENT_KIMI_API_KEY": "react-key"},
            clear=True,
        ):
            cfg = ReactLlmConfig(model="moonshot/kimi-k2.6")
            client, _, _ = self._make_client(cfg)

        self.assertEqual(client.model_id(), "kimi-k2.6")

    def test_legacy_moonshot_key_env_is_accepted(self) -> None:
        with patch.dict(
            os.environ,
            {"REACT_AGENT_MOONSHOT_API_KEY": "legacy-key"},
            clear=True,
        ):
            cfg = ReactLlmConfig()

        self.assertEqual(cfg.kimi_api_key, "legacy-key")


if __name__ == "__main__":
    unittest.main()
