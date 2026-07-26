from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
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


@dataclass(frozen=True)
class CodexSessionConfig:
    model: str = "gpt-5.6-sol"
    effort: str = "low"
    codex_bin: str = ""


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
    ) -> None:
        self.config = config
        self.working_directory = Path(working_directory)
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self._codex: Any = None
        self._thread: Any = None

    def __enter__(self) -> "CodexGameSession":
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
        self._thread = self._codex.thread_start(
            approval_mode=ApprovalMode.deny_all,
            base_instructions=(
                "You are a puzzle-game action selector, not a coding agent. "
                "Solve only from the frames and transition feedback supplied in the "
                "conversation. Do not inspect files, run commands, browse, or use tools. "
                "Return exactly one next game action per turn."
            ),
            cwd=str(self.working_directory),
            ephemeral=True,
            model=self.config.model,
            sandbox=Sandbox.read_only,
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._codex is not None:
            self._codex.__exit__(exc_type, exc, traceback)
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
        if image_path is not None:
            inputs.append(LocalImageInput(str(Path(image_path).resolve())))

        result = self._thread.run(
            inputs,
            effort=self.config.effort,
            output_schema=ACTION_OUTPUT_SCHEMA,
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
            "action": action,
            "note": str(payload.get("note", "")).strip(),
        }
