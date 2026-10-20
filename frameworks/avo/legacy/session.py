from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from frameworks.baseline.session import _find_codex_bin


ACTION_NAMES = [
    "RESET",
    "ACTION1",
    "ACTION2",
    "ACTION3",
    "ACTION4",
    "ACTION5",
    "ACTION7",
]

PLAN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {"type": "string", "enum": ACTION_NAMES},
            "minItems": 1,
            "maxItems": 20,
        },
        "prediction": {"type": "string"},
        "note": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": ["actions", "prediction", "note", "confidence"],
    "additionalProperties": False,
}

SUPERVISOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis": {"type": "string"},
        "advice": {"type": "string"},
    },
    "required": ["diagnosis", "advice"],
    "additionalProperties": False,
}


MAIN_INSTRUCTIONS = """You are the autonomous variation operator for an unknown interactive
environment. Available action IDs are opaque: never assume or import their meanings. Infer
useful structure only from observations and recorded transitions.

You have an isolated run workspace. Work only inside the current working directory. Never
inspect parent directories, repository files, game source, solution files, the web, or any
external resource. The only authoritative evidence is current_state.json, trajectory.jsonl,
and the images and transition feedback supplied by the harness.

Use coding tools when useful. Maintain:
- KNOWLEDGE.md: concise durable rules, goals, confirmed facts, contradictions, and failures.
- WORKING.md: current-level state, hypotheses, and plan.
- helpers/solver.py and helpers/scratch.py: pre-created slots for reusable Python parsers,
  predictors, and search code. Edit these files rather than creating new helper filenames so
  the harness can archive them after sandbox exit. Never encode a rule merely because a
  familiar game is recognized.

Use the supplied tools in whatever order is useful. You may inspect evidence, write notes or
code, create competing executable hypotheses, replay them, request real probes, revise or
abandon candidates, and stop. The harness, not you, executes environment actions and owns
authoritative evaluation.

All actions count, so avoid repeating failed probes. Knowledge must transfer across levels.
"""


SUPERVISOR_INSTRUCTIONS = """You supervise a long-horizon environment-learning agent.
You receive only its observed trajectory and working notes. Diagnose stagnation or repeated
mistakes and give concise, game-general advice for the next turn. Do not invent mechanics,
provide game-specific prior knowledge, inspect files, run tools, or propose hidden solutions.
Return only the required JSON object.
"""


@dataclass(frozen=True)
class AvoSessionConfig:
    model: str = "gpt-5.6-sol"
    effort: str = "high"
    supervisor_effort: str = "medium"
    codex_bin: str = ""


class AvoCodexSession:
    """Persistent coding-agent session plus an independent stagnation supervisor."""

    def __init__(
        self,
        config: AvoSessionConfig,
        working_directory: str | Path,
    ) -> None:
        self.config = config
        self.working_directory = Path(working_directory)
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self._codex: Any = None
        self._thread: Any = None
        self._supervisor: Any = None

    def __enter__(self) -> "AvoCodexSession":
        try:
            from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox
        except ImportError as exc:
            raise RuntimeError(
                "The Codex SDK is not installed. Run `uv sync` first."
            ) from exc

        codex_bin = _find_codex_bin(self.config.codex_bin)
        sdk_config = CodexConfig(codex_bin=codex_bin) if codex_bin else None
        self._codex = Codex(sdk_config)
        self._codex.__enter__()
        common = {
            "approval_mode": ApprovalMode.deny_all,
            "cwd": str(self.working_directory.resolve()),
            "ephemeral": True,
            "model": self.config.model,
        }
        self._thread = self._codex.thread_start(
            base_instructions=MAIN_INSTRUCTIONS,
            sandbox=Sandbox.workspace_write,
            **common,
        )
        self._supervisor = self._codex.thread_start(
            base_instructions=SUPERVISOR_INSTRUCTIONS,
            sandbox=Sandbox.read_only,
            **common,
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._codex is not None:
            self._codex.__exit__(exc_type, exc, traceback)
        self._thread = None
        self._supervisor = None
        self._codex = None

    def next_plan(
        self,
        prompt: str,
        image_path: str | Path | None = None,
    ) -> dict[str, object]:
        if self._thread is None:
            raise RuntimeError("AVO main session has not been started")

        from openai_codex import LocalImageInput, TextInput

        inputs: list[Any] = [TextInput(prompt)]
        if image_path is not None:
            inputs.append(LocalImageInput(str(Path(image_path).resolve())))
        result = self._thread.run(
            inputs,
            effort=self.config.effort,
            output_schema=PLAN_OUTPUT_SCHEMA,
        )
        payload = self._parse_payload(result.final_response, "plan")
        actions = [str(action).strip().upper() for action in payload.get("actions", [])]
        if not actions or any(action not in ACTION_NAMES for action in actions):
            raise ValueError(f"AVO returned unsupported actions: {actions!r}")
        return {
            "actions": actions,
            "prediction": str(payload.get("prediction", "")).strip(),
            "note": str(payload.get("note", "")).strip(),
            "confidence": str(payload.get("confidence", "low")).strip().lower(),
        }

    def supervise(self, prompt: str) -> dict[str, str]:
        if self._supervisor is None:
            raise RuntimeError("AVO supervisor session has not been started")

        from openai_codex import TextInput

        result = self._supervisor.run(
            [TextInput(prompt)],
            effort=self.config.supervisor_effort,
            output_schema=SUPERVISOR_OUTPUT_SCHEMA,
        )
        payload = self._parse_payload(result.final_response, "supervisor")
        return {
            "diagnosis": str(payload.get("diagnosis", "")).strip(),
            "advice": str(payload.get("advice", "")).strip(),
        }

    @staticmethod
    def _parse_payload(raw: str | None, label: str) -> dict:
        if not raw:
            raise ValueError(f"AVO {label} returned no response")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"AVO {label} returned invalid JSON: {raw}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"AVO {label} response must be a JSON object")
        return payload
