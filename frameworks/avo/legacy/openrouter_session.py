from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI, OpenAIError

from frameworks.avo.legacy.session import (
    ACTION_NAMES,
    MAIN_INSTRUCTIONS,
    PLAN_OUTPUT_SCHEMA,
    SUPERVISOR_INSTRUCTIONS,
    SUPERVISOR_OUTPUT_SCHEMA,
)
from client.engine.utils import extract_json


load_dotenv()


WORKSPACE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read an allowed UTF-8 file from the isolated game workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "One of current_state.json, trajectory.jsonl, KNOWLEDGE.md, "
                            "WORKING.md, prior_run_final_state.json, helpers/solver.py, "
                            "or helpers/scratch.py."
                        ),
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Replace an allowed notebook or helper file in the isolated workspace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": [
                            "KNOWLEDGE.md",
                            "WORKING.md",
                            "helpers/solver.py",
                            "helpers/scratch.py",
                        ],
                    },
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Run one pre-created helper with isolated Python in the game workspace. "
                "Use this for parsers, simulators, BFS, A*, or other internal computation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": ["helpers/solver.py", "helpers/scratch.py"],
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 20,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


@dataclass(frozen=True)
class OpenRouterAvoConfig:
    model: str = "anthropic/claude-opus-5-fast"
    effort: str = "high"
    supervisor_effort: str = "medium"
    max_output_tokens: int = 8192
    max_tool_rounds: int = 12
    python_timeout_seconds: int = 20
    compact_between_decisions: bool = True
    api_key: str = ""


class OpenRouterAvoSession:
    """Persistent OpenRouter agent loop with bounded workspace tools."""

    _READABLE = {
        "current_state.json",
        "trajectory.jsonl",
        "KNOWLEDGE.md",
        "WORKING.md",
        "helpers/solver.py",
        "helpers/scratch.py",
        "prior_run_final_state.json",
    }
    _WRITABLE = {
        "KNOWLEDGE.md",
        "WORKING.md",
        "helpers/solver.py",
        "helpers/scratch.py",
    }
    _RUNNABLE = {"helpers/solver.py", "helpers/scratch.py"}

    def __init__(
        self,
        config: OpenRouterAvoConfig,
        working_directory: str | Path,
        *,
        client: Any | None = None,
    ) -> None:
        self.config = config
        self.working_directory = Path(working_directory).resolve()
        self.working_directory.mkdir(parents=True, exist_ok=True)
        api_key = config.api_key or os.getenv("OPENROUTER_API_KEY", "")
        if client is None and not api_key:
            raise ValueError("OPENROUTER_API_KEY not found")
        self._client = client or OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=180,
        )
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": MAIN_INSTRUCTIONS}
        ]
        self._supervisor_messages: list[dict[str, Any]] = [
            {"role": "system", "content": SUPERVISOR_INSTRUCTIONS}
        ]
        self._usage = {
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "wall_seconds": 0.0,
        }
        self.events_path = self.working_directory / "agent_events.jsonl"

    def __enter__(self) -> "OpenRouterAvoSession":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def next_plan(
        self,
        prompt: str,
        image_path: str | Path | None = None,
    ) -> dict[str, object]:
        content: str | list[dict[str, Any]] = prompt
        if image_path is not None:
            image = Path(image_path)
            encoded = base64.b64encode(image.read_bytes()).decode("ascii")
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                },
            ]
        snapshot = self._workspace_snapshot()
        if isinstance(content, str):
            content = f"{content}\n\nCurrent workspace snapshot:\n{snapshot}"
        else:
            content[0]["text"] = (
                f"{content[0]['text']}\n\nCurrent workspace snapshot:\n{snapshot}"
            )
        self._messages.append({"role": "user", "content": content})
        payload = self._run_tool_loop(self._messages)
        if self.config.compact_between_decisions:
            self._messages = [{"role": "system", "content": MAIN_INSTRUCTIONS}]
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
        self._supervisor_messages.append({"role": "user", "content": prompt})
        response = self._request(
            self._supervisor_messages,
            effort=self.config.supervisor_effort,
            response_schema=SUPERVISOR_OUTPUT_SCHEMA,
            schema_name="avo_supervisor",
        )
        message = response.choices[0].message
        assistant = self._assistant_message(message)
        self._supervisor_messages.append(assistant)
        payload = self._parse_payload(message.content, "supervisor")
        return {
            "diagnosis": str(payload.get("diagnosis", "")).strip(),
            "advice": str(payload.get("advice", "")).strip(),
        }

    def usage_summary(self) -> dict[str, object]:
        return {
            "provider": "openrouter",
            "model": self.config.model,
            **self._usage,
        }

    def _run_tool_loop(self, messages: list[dict[str, Any]]) -> dict:
        for round_index in range(self.config.max_tool_rounds):
            response = self._request(
                messages,
                effort=self.config.effort,
                tools=WORKSPACE_TOOLS,
                tool_choice="auto",
                response_schema=PLAN_OUTPUT_SCHEMA,
                schema_name="avo_plan",
            )
            message = response.choices[0].message
            messages.append(self._assistant_message(message))
            calls = list(getattr(message, "tool_calls", None) or [])
            if not calls:
                return self._parse_payload(message.content, "plan")

            for call in calls:
                name = str(call.function.name)
                arguments: dict[str, Any] = {}
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be an object")
                    result = self._execute_tool(name, arguments)
                except Exception as exc:  # tool failures are evidence for the agent
                    result = json.dumps({"ok": False, "error": str(exc)})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": name,
                        "content": result,
                    }
                )
                self._append_event(
                    {
                        "type": "tool",
                        "name": name,
                        "arguments": arguments,
                        "result": result,
                    }
                )
        raise RuntimeError(
            f"OpenRouter AVO exceeded {self.config.max_tool_rounds} tool rounds"
        )

    def _request(
        self,
        messages: list[dict[str, Any]],
        *,
        effort: str,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_schema: dict | None = None,
        schema_name: str = "response",
    ):
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_output_tokens,
            "extra_body": {"reasoning": {"effort": effort}},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = True
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if response_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_schema,
                },
            }
        started = time.perf_counter()
        response = None
        for attempt in range(5):
            try:
                response = self._client.chat.completions.create(**kwargs)
                break
            except APIStatusError as exc:
                body = exc.body if isinstance(exc.body, dict) else {}
                error_data = body.get("error", body)
                metadata = (
                    error_data.get("metadata", {})
                    if isinstance(error_data, dict)
                    else {}
                )
                retryable = (
                    exc.status_code == 402
                    and metadata.get("reason") == "in_flight_budget_exhausted"
                )
                if not retryable or attempt == 4:
                    raise ValueError(f"OpenRouter provider error: {exc}") from exc
                raw_delay = metadata.get("headers", {}).get("Retry-After", 30)
                try:
                    requested_delay = int(raw_delay)
                except (TypeError, ValueError):
                    requested_delay = 30
                delay = max(5, min(requested_delay, 30))
                self._append_event(
                    {
                        "type": "provider_retry",
                        "reason": "in_flight_budget_exhausted",
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                    }
                )
                time.sleep(delay)
            except OpenAIError as exc:
                raise ValueError(f"OpenRouter provider error: {exc}") from exc
        if response is None:
            raise RuntimeError("OpenRouter request ended without a response")
        elapsed = time.perf_counter() - started
        self._record_usage(response, elapsed)
        return response

    def _execute_tool(self, name: str, arguments: dict) -> str:
        relative = self._normalize_path(str(arguments.get("path", "")))
        if name == "read_file":
            if relative not in self._READABLE:
                raise ValueError(f"read_file path is not allowed: {relative}")
            path = self.working_directory / relative
            if not path.exists():
                return json.dumps({"ok": True, "path": relative, "content": ""})
            content = path.read_text(encoding="utf-8")
            return json.dumps(
                {"ok": True, "path": relative, "content": content[-120_000:]}
            )

        if name == "write_file":
            if relative not in self._WRITABLE:
                raise ValueError(f"write_file path is not allowed: {relative}")
            content = str(arguments.get("content", ""))
            if len(content) > 200_000:
                raise ValueError("write_file content exceeds 200000 characters")
            path = self.working_directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return json.dumps(
                {"ok": True, "path": relative, "characters": len(content)}
            )

        if name == "run_python":
            if relative not in self._RUNNABLE:
                raise ValueError(f"run_python path is not allowed: {relative}")
            raw_args = arguments.get("args", [])
            if not isinstance(raw_args, list) or len(raw_args) > 20:
                raise ValueError("run_python args must be a list with at most 20 items")
            args = [str(value)[:1000] for value in raw_args]
            path = self.working_directory / relative
            safe_env = {
                key: os.environ[key]
                for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
                if key in os.environ
            }
            safe_env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [sys.executable, "-I", str(path), *args],
                cwd=self.working_directory,
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=self.config.python_timeout_seconds,
                check=False,
            )
            return json.dumps(
                {
                    "ok": completed.returncode == 0,
                    "path": relative,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-30_000:],
                    "stderr": completed.stderr[-30_000:],
                }
            )

        raise ValueError(f"unsupported tool: {name}")

    def _workspace_snapshot(self) -> str:
        sections = []
        for relative in (
            "current_state.json",
            "KNOWLEDGE.md",
            "WORKING.md",
            "prior_run_final_state.json",
        ):
            path = self.working_directory / relative
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            sections.append(f"--- {relative} ---\n{content[-30_000:]}")
        return "\n".join(sections)

    @staticmethod
    def _assistant_message(message: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
        }
        calls = list(getattr(message, "tool_calls", None) or [])
        if calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in calls
            ]
        return payload

    @staticmethod
    def _parse_payload(raw: str | None, label: str) -> dict:
        if not raw:
            raise ValueError(f"OpenRouter AVO {label} returned no response")
        try:
            payload = json.loads(extract_json(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"OpenRouter AVO {label} returned invalid JSON: {raw}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(f"OpenRouter AVO {label} must be a JSON object")
        return payload

    @staticmethod
    def _normalize_path(raw: str) -> str:
        value = raw.strip().replace("\\", "/")
        path = Path(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"workspace path is not allowed: {raw}")
        return path.as_posix()

    def _record_usage(self, response: Any, elapsed: float) -> None:
        usage = getattr(response, "usage", None)
        self._usage["requests"] += 1
        self._usage["wall_seconds"] = round(
            float(self._usage["wall_seconds"]) + elapsed, 3
        )
        if usage is None:
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self._usage[key] += int(getattr(usage, key, 0) or 0)

    def _append_event(self, record: dict[str, Any]) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            **record,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
