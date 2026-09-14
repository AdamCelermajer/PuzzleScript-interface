from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
                "ACTION5",
                "ACTION7",
                "FINISH",
            ],
        },
        "note": {"type": "string"},
    },
    "required": ["action", "note"],
    "additionalProperties": False,
}

WORLD_MODEL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "objects": {"type": "array", "items": {"type": "string"}},
        "controls": {"type": "array", "items": {"type": "string"}},
        "transition_rules": {"type": "array", "items": {"type": "string"}},
        "goal_condition": {"type": "string"},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "failures_and_deadlocks": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "objects",
        "controls",
        "transition_rules",
        "goal_condition",
        "uncertainties",
        "failures_and_deadlocks",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class CodexSessionConfig:
    model: str = "gpt-5.6-sol"
    effort: str = "low"
    codex_bin: str = ""
    workspace_enabled: bool = False


def _find_codex_bin(explicit: str = "") -> str | None:
    requested = explicit.strip() or os.getenv("CODEX_BIN", "").strip()
    if requested:
        return requested

    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "")
        if local_app_data:
            bin_root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            candidates = sorted(
                bin_root.glob("*/codex.exe"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                return str(candidates[0])

    return shutil.which("codex")


def codex_oauth_status(explicit_bin: str = "") -> dict[str, object]:
    codex_bin = _find_codex_bin(explicit_bin)
    if not codex_bin:
        return {
            "available": False,
            "logged_in": False,
            "state": "runtime_missing",
            "message": "Codex runtime was not found.",
            "version": "",
        }
    try:
        version = subprocess.run(
            [codex_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        login = subprocess.run(
            [codex_bin, "login", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "logged_in": False,
            "state": "unavailable",
            "message": str(exc),
            "version": "",
        }
    login_text = " ".join((login.stdout or login.stderr or "").split())
    logged_in = login.returncode == 0 and "logged in" in login_text.lower()
    return {
        "available": version.returncode == 0,
        "logged_in": logged_in,
        "state": "ready" if logged_in else "login_required",
        "message": login_text or "Codex login status unavailable.",
        "version": " ".join((version.stdout or version.stderr or "").split()),
    }


class CodexGameSession:
    """One persistent Codex SDK thread for one game episode."""

    def __init__(
        self,
        config: CodexSessionConfig,
        working_directory: str | Path,
        artifact_directory: str | Path | None = None,
    ) -> None:
        self.config = config
        self.working_directory = Path(working_directory)
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self.artifact_directory = Path(
            artifact_directory or self.working_directory.parent
        )
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        self.session_log_path = self.artifact_directory / "codex_session.jsonl"
        self._codex: Any = None
        self._thread: Any = None
        self._model_cwd: Any = None
        self._request_proxy: Any = None

    def __enter__(self) -> "CodexGameSession":
        try:
            return self._start()
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def _start(self) -> "CodexGameSession":
        from avo.analysis.model_proxy import CodexRequestProxy
        from avo.analysis.request_guard import RequestGuard
        try:
            from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox
        except ImportError as exc:
            raise RuntimeError(
                "The Codex SDK is not installed. Run `uv sync` first."
            ) from exc

        codex_bin = _find_codex_bin(self.config.codex_bin)
        self._model_cwd = tempfile.TemporaryDirectory(prefix="codex-game-")
        allowed_tools = {
            "exec", "wait", "request_user_input", "apply_patch", "view_image",
            "list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource",
        } | (
            {f"mcp__codex_notes__{name}" for name in ("list_notes", "read_note", "write_note")}
            if self.config.workspace_enabled else set()
        )
        if self.config.workspace_enabled:
            allowed_tools.update({"list_notes", "read_note", "write_note"})
            allowed_tools.add("tool_search")
        self._request_proxy = CodexRequestProxy(
            self.artifact_directory / "model_requests", session_id="study",
            session_role="baseline-plus" if self.config.workspace_enabled else "baseline",
            guard=RequestGuard(forbidden_roots=(self.artifact_directory.resolve(),), allowed_tools=allowed_tools),
        )
        self._request_proxy.start()
        config_overrides = [
            "project_doc_max_bytes=0",
            'web_search="disabled"',
            "features.multi_agent=false",
            "features.js_repl=false",
            "features.code_mode_host=false",
            "features.apps=false",
            "features.plugins=false",
            "features.image_generation=false",
            "mcp_servers.node_repl.enabled=false",
            "features.memories=false",
            "memories.use_memories=false",
            "memories.generate_memories=false",
            "features.shell_tool=false",
            "features.unified_exec=false",
            "features.browser_use=false",
            "features.computer_use=false",
            'plugins."codex-app-tools@openai-bundled".enabled=false',
            'plugins."unified-computer-use@openai-bundled".enabled=false',
            "mcp_servers.node_repl.enabled_tools=[]",
            f'openai_base_url="{self._request_proxy.model_base_url}"',
        ]
        if self.config.workspace_enabled:
            note_server = Path(__file__).with_name("note_server.py").resolve()
            note_args = [
                "-u",
                str(note_server),
                "--workspace",
                str(self.working_directory.resolve()),
                "--history-dir",
                str((self.working_directory.parent / "note_history").resolve()),
            ]
            config_overrides.extend(
                [
                    f"mcp_servers.codex_notes.command={json.dumps(sys.executable)}",
                    f"mcp_servers.codex_notes.args={json.dumps(note_args)}",
                    "mcp_servers.codex_notes.startup_timeout_sec=10",
                    "mcp_servers.codex_notes.tool_timeout_sec=10",
                    'mcp_servers.codex_notes.enabled_tools=["list_notes","read_note","write_note"]',
                    'mcp_servers.codex_notes.default_tools_approval_mode="approve"',
                ]
            )
        sdk_config = CodexConfig(
            codex_bin=codex_bin,
            config_overrides=tuple(config_overrides),
            cwd=self._model_cwd.name,
            env={**{key: "" for key in os.environ if key.startswith("CODEX_")},
                 "CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "codex_cli_rs"},
        )
        self._codex = Codex(sdk_config)
        self._codex.__enter__()
        if self.config.workspace_enabled:
            base_instructions = (
                "You are playing a puzzle game. Return exactly one next game action "
                "per turn. You have a persistent workspace with tools to list, read, "
                "and write notes. Use these tools as working memory. Before your first "
                "game action, write strategy.md with your initial observations, "
                "hypotheses, and plan. On later turns, read strategy.md before acting "
                "and update it whenever evidence confirms or rejects a hypothesis, "
                "your plan changes, you encounter a dead end, or a level changes. Keep "
                "confirmed facts separate from hypotheses. Tool calls happen before "
                "your final one-action response."
            )
        else:
            base_instructions = (
                "You are playing a puzzle game. "
                "Return exactly one next game action per turn."
            )
        # Codex receives its cwd as model context. Keep it opaque and separate
        # from artifact paths, which may contain the backend's real game ID.
        initial_notes = sorted(
            path.relative_to(self.working_directory).as_posix()
            for path in self.working_directory.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}
        )
        self._thread = self._codex.thread_start(
            # General Codex mutations stay denied. Baseline+ grants approval only
            # to the three MCP note tools configured above.
            approval_mode=ApprovalMode.deny_all,
            base_instructions=base_instructions,
            cwd=self._model_cwd.name,
            ephemeral=True,
            model=self.config.model,
            sandbox=Sandbox.read_only,
        )
        self._write_isolation_manifest(
            base_instructions=base_instructions,
            config_overrides=config_overrides,
            initial_notes=initial_notes,
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if self._codex is not None:
                self._codex.__exit__(exc_type, exc, traceback)
        finally:
            if self._request_proxy is not None:
                self._request_proxy.stop()
            self._request_proxy = None
            if self._model_cwd is not None:
                self._model_cwd.cleanup()
            self._model_cwd = None
            self._thread = None
            self._codex = None

    def next_action(
        self,
        prompt: str,
        image_path: str | Path | None = None,
    ) -> dict[str, str]:
        if self._thread is None:
            raise RuntimeError("Codex game session has not been started")

        from openai_codex import LocalImageInput, TextInput

        inputs: list[Any] = [TextInput(prompt)]
        staged_image_path: Path | None = None
        if image_path is not None:
            if self._model_cwd is None:
                raise RuntimeError("Codex model workspace is unavailable")
            staged_image_path = Path(self._model_cwd.name) / "frame.png"
            shutil.copyfile(Path(image_path).resolve(), staged_image_path)
            inputs.append(LocalImageInput(str(staged_image_path)))

        result = self._run_with_retry(
            inputs,
            ACTION_OUTPUT_SCHEMA,
            turn_kind="game_action",
            prompt=prompt,
            image_path=staged_image_path,
        )
        if not result.final_response:
            raise ValueError("Codex returned no final response")

        try:
            payload = json.loads(result.final_response)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Codex returned invalid action JSON: {result.final_response}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("Codex action response must be a JSON object")

        action = str(payload.get("action", "")).strip().upper()
        allowed = set(ACTION_OUTPUT_SCHEMA["properties"]["action"]["enum"])
        if action not in allowed:
            raise ValueError(f"Codex returned unsupported action: {action or '<empty>'}")
        return {
            "operation": "FINISH" if action == "FINISH" else "ACT",
            "action": action,
            "note": str(payload.get("note", "")).strip(),
        }

    def note_tool_count(self) -> int:
        audit_path = self.working_directory / "tool_calls.jsonl"
        if not audit_path.exists():
            return 0
        return sum(1 for line in audit_path.read_text(encoding="utf-8").splitlines() if line)

    def final_world_model(self) -> dict[str, object]:
        if self._thread is None:
            raise RuntimeError("Codex game session has not been started")

        from openai_codex import TextInput

        prompt = (
            "The gameplay run has ended. Describe the environment model you learned. "
            "Identify objects, controls, transition rules, the goal condition, remaining "
            "uncertainties, and known failures or deadlocks. Distinguish observed facts "
            "from hypotheses in the wording. Do not take any more actions or use tools."
        )
        result = self._run_with_retry(
            [TextInput(prompt)],
            WORLD_MODEL_OUTPUT_SCHEMA,
            turn_kind="final_world_model",
            prompt=prompt,
        )
        if not result.final_response:
            raise ValueError("Codex returned no final world model")
        payload = json.loads(result.final_response)
        if not isinstance(payload, dict):
            raise ValueError("Codex world model response must be a JSON object")
        return payload

    def _write_isolation_manifest(
        self,
        *,
        base_instructions: str,
        config_overrides: list[str],
        initial_notes: list[str],
    ) -> None:
        payload = {
            "ephemeral_thread": True,
            "sandbox": "read_only",
            "approval_mode": "deny_all",
            "model_cwd_is_opaque_temporary_directory": True,
            "frame_attachment_is_staged_in_model_cwd": True,
            "outbound_request_capture": "model_requests/",
            "outbound_guard_checks_context_and_tool_inventory": True,
            "os_read_isolation_certified": False,
            "internal_tools_allowed_by_user": True,
            "model_visible_note_tools": (
                ["list_notes", "read_note", "write_note"]
                if self.config.workspace_enabled
                else []
            ),
            "initial_note_files": initial_notes,
            "base_instructions": base_instructions,
            "config_overrides": config_overrides,
            "prompt_omits_game_id": True,
            "prompt_omits_game_title": True,
            "prompt_omits_action_meanings": True,
        }
        (self.artifact_directory / "isolation_manifest.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _run_with_retry(
        self,
        inputs: list[Any],
        output_schema: dict,
        *,
        turn_kind: str,
        prompt: str,
        image_path: str | Path | None = None,
    ) -> Any:
        from avo.isolation import IsolationError
        if self._thread is None:
            raise RuntimeError("Codex game session has not been started")
        for attempt in range(4):
            try:
                result = self._thread.run(
                    inputs,
                    effort=self.config.effort,
                    output_schema=output_schema,
                )
                if self._request_proxy.guard.failure:
                    raise IsolationError(self._request_proxy.guard.failure)
                if self._request_proxy.guard.requests_checked == 0:
                    raise IsolationError("Missing outgoing request capture")
                self._record_turn(
                    result,
                    turn_kind=turn_kind,
                    prompt=prompt,
                    image_path=image_path,
                )
                return result
            except RuntimeError as exc:
                if self._request_proxy.guard.failure:
                    raise IsolationError(self._request_proxy.guard.failure) from exc
                if "at capacity" not in str(exc).lower() or attempt == 3:
                    raise
                time.sleep(5 * (2**attempt))
        raise RuntimeError("Codex request retry loop exited unexpectedly")

    def _record_turn(
        self,
        result: Any,
        *,
        turn_kind: str,
        prompt: str,
        image_path: str | Path | None,
    ) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "turn_kind": turn_kind,
            "request": {
                "prompt": prompt,
                "image_path": str(Path(image_path).resolve()) if image_path else None,
            },
            "turn": {
                "id": getattr(result, "id", None),
                "status": self._json_value(getattr(result, "status", None)),
                "error": self._json_value(getattr(result, "error", None)),
                "started_at": getattr(result, "started_at", None),
                "completed_at": getattr(result, "completed_at", None),
                "duration_ms": getattr(result, "duration_ms", None),
                "final_response": getattr(result, "final_response", None),
                "items": self._json_value(getattr(result, "items", [])),
                "usage": self._json_value(getattr(result, "usage", None)),
            },
        }
        with self.session_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    @classmethod
    def _json_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", by_alias=True)
        if hasattr(value, "value"):
            return cls._json_value(value.value)
        if isinstance(value, dict):
            return {str(key): cls._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_value(item) for item in value]
        return str(value)
