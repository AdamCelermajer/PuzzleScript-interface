"""Persistent agent session interface shared by every harness.

One ``CliSession`` is one agent conversation. ``start`` fixes the workspace, system
prompt, model and effort; every ``turn`` runs one autonomous agent turn (a CLI
process, or one in-process tool loop for ``bare``) and resumes the same session id.
Each turn writes its raw stdout to ``<analysis>/raw/turn-<n>.jsonl`` and normalized
events (contract section 1) to ``<analysis>/agent_events.jsonl``.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = "agent-event-v1"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
EVENT_TYPES = ("message", "reasoning", "command", "file_change", "tool", "image", "usage", "error", "turn_end")
OUTPUT_LIMIT = 16_000
# Never handed to commands the agent runs through the in-process bare harness.
CREDENTIAL_ENV = ("OPENROUTER_API_KEY", "NANOGPT_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
                  "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


class HarnessError(RuntimeError):
    """Harness configuration or CLI failure (infrastructure, not an agent outcome)."""


@dataclass
class TurnResult:
    text: str
    session_id: str
    usage: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)
    exit_code: int | None = 0
    timed_out: bool = False
    error: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def truncate(value: Any, limit: int = OUTPUT_LIMIT) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    head = limit // 4
    return text[:head] + f"\n[... {len(text) - limit} characters omitted ...]\n" + text[-(limit - head):]


def usage_record(input: Any = 0, output: Any = 0, reasoning: Any = 0, cached: Any = 0, **extra: Any) -> dict[str, Any]:
    def number(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    record: dict[str, Any] = {"input": number(input), "output": number(output),
                              "reasoning": number(reasoning), "cached": number(cached)}
    record.update({key: value for key, value in extra.items() if value is not None})
    return record


def add_usage(total: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    for key, value in part.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total[key] = total.get(key, 0) + value
    return total


class EventLog:
    """Append-only normalized event log for one agent session."""

    def __init__(self, analysis_dir: Path, *, harness: str, model: str, role: str) -> None:
        self.root = Path(analysis_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "raw").mkdir(exist_ok=True)
        self.path = self.root / "agent_events.jsonl"
        self.harness, self.model, self.role = harness, model, role
        self._lock = threading.Lock()

    def raw_path(self, turn: int) -> Path:
        return self.root / "raw" / f"turn-{turn}.jsonl"

    def write(self, *, turn: int, type: str, session: str = "", **fields: Any) -> dict[str, Any]:
        if type not in EVENT_TYPES:
            raise ValueError(f"Unknown agent event type: {type}")
        record: dict[str, Any] = {"schema": SCHEMA, "t": utc_now(), "session": session, "role": self.role,
                                  "turn": turn, "type": type}
        for key, value in fields.items():
            if value is None or value == "":
                continue
            record[key] = truncate(value) if key in {"text", "output"} else value
        record["harness"] = self.harness
        record["model"] = self.model
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        return record


def kill_tree(process: subprocess.Popen) -> None:
    """Kill a CLI and every process it started."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass


def run_streaming(command: Sequence[str], *, cwd: Path, env: dict[str, str], timeout: float | None,
                  raw_path: Path, on_line, stdin_data: str | None = None) -> tuple[int | None, bool, str]:
    """Run one CLI turn; stream stdout lines to ``raw_path`` and ``on_line``.

    stdin is closed (or receives ``stdin_data`` then EOF). On timeout the whole
    process tree is killed. Returns (exit_code, timed_out, stderr_tail).
    """
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path = raw_path.with_name(raw_path.stem + ".stderr.txt")
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    with raw_path.open("a", encoding="utf-8") as raw, stderr_path.open("a", encoding="utf-8") as errors:
        process = subprocess.Popen(list(command), cwd=str(cwd), env=env,
                                   stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        failures: list[BaseException] = []

        def read_stdout() -> None:
            assert process.stdout is not None
            for chunk in iter(process.stdout.readline, b""):
                line = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
                raw.write(line + "\n")
                raw.flush()
                if line.strip():
                    try:
                        on_line(line)
                    except Exception as exc:  # normalization must never stall the CLI pipe
                        failures.append(exc)

        def read_stderr() -> None:
            assert process.stderr is not None
            for chunk in iter(process.stderr.readline, b""):
                errors.write(chunk.decode("utf-8", errors="replace"))
                errors.flush()

        readers = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=read_stderr, daemon=True)]
        for reader in readers:
            reader.start()
        if stdin_data is not None:
            assert process.stdin is not None
            try:
                process.stdin.write(stdin_data.encode("utf-8"))
            except OSError:
                pass
            finally:
                process.stdin.close()
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(process)
            process.wait()
        for reader in readers:
            reader.join(timeout=30)
    if failures:
        raise HarnessError(f"Event normalization failed: {type(failures[0]).__name__}: {failures[0]}") from failures[0]
    tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:] if stderr_path.exists() else ""
    return process.returncode, timed_out, tail


def private_root() -> Path:
    """Per-session CLI state (config, session stores) lives outside the workspace."""
    root = Path(os.environ.get("HARNESS_PRIVATE_ROOT") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


class CliSession:
    """Base class. Subclasses implement ``command`` and ``normalize``."""

    harness_id = ""
    # The registry fills these from the model id.
    provider = ""
    native_model = ""

    def __init__(self) -> None:
        self.session_id = ""
        self.turn_number = 0
        self.started = False
        self.workspace = Path(".")
        self.system_prompt = ""
        self.model = ""
        self.effort = "medium"
        self.role = "player"
        self.analysis_dir = Path(".")
        self.pin_provider = ""
        self.env: dict[str, str] = {}
        self.private = Path(".")
        self.log: EventLog | None = None
        self._text_parts: list[str] = []
        self._final_text = ""
        self._usage: dict[str, Any] = {}
        self._turn_errors: list[str] = []

    # -- lifecycle -----------------------------------------------------------------
    def start(self, workspace: str | Path, system_prompt: str, model: str, effort: str, role: str,
              analysis_dir: str | Path, *, provider: str = "") -> "CliSession":
        from harnesses.registry import resolve_model_for

        if effort not in EFFORTS:
            raise HarnessError(f"Unsupported effort {effort!r}; use one of {', '.join(EFFORTS)}")
        self.provider, self.native_model = resolve_model_for(self.harness_id, model)
        if provider and self.provider != "openrouter":
            raise HarnessError("Provider pinning is only supported for OpenRouter models")
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.system_prompt, self.model, self.effort, self.role = system_prompt, model, effort, role
        self.pin_provider = provider
        self.analysis_dir = Path(analysis_dir).resolve()
        self.log = EventLog(self.analysis_dir, harness=self.harness_id, model=model, role=role)
        self.private = Path(tempfile.mkdtemp(prefix=f"{self.harness_id}-", dir=private_root()))
        self.env = self.base_env()
        self.prepare()
        manifest = {
            "schema": "agent-session-v1", "harness": self.harness_id, "model": model, "provider": self.provider,
            "native_model": self.native_model, "openrouter_provider": provider or None, "effort": effort,
            "role": role, "workspace": str(self.workspace), "started_at": utc_now(),
            "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "web_tools": "disabled", "permission_prompts": "disabled (Docker container is the sandbox)",
        }
        (self.analysis_dir / "session.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (self.analysis_dir / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")
        self.started = True
        return self

    def close(self) -> None:
        self.started = False

    def __enter__(self) -> "CliSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- subclass hooks ------------------------------------------------------------
    def base_env(self) -> dict[str, str]:
        return dict(os.environ)

    def prepare(self) -> None:
        """Write private CLI config before the first turn."""

    def command(self, instruction: str, images: Sequence[Path]) -> list[str]:
        raise NotImplementedError

    def stdin_payload(self, instruction: str, images: Sequence[Path]) -> str | None:
        return None

    def normalize(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Map one raw CLI event to normalized events; may set session id / text / usage."""
        raise NotImplementedError

    def final_text(self) -> str:
        return self._final_text or "\n".join(part for part in self._text_parts if part).strip()

    # -- turns ---------------------------------------------------------------------
    def turn(self, instruction: str, images: Iterable[str | Path] = (), timeout: float | None = None) -> TurnResult:
        if not self.started or self.log is None:
            raise HarnessError("Session has not been started")
        self.turn_number += 1
        number = self.turn_number
        image_paths = [Path(image).resolve() for image in images]
        self._text_parts, self._final_text, self._usage, self._turn_errors = [], "", {}, []
        events: list[dict[str, Any]] = []
        log = self.log

        def on_line(line: str) -> None:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                return
            if not isinstance(payload, dict):
                return
            for event in self.normalize(payload):
                kind = event.pop("type")
                events.append(log.write(turn=number, type=kind, session=self.session_id, **event))

        command = self.command(instruction, image_paths)
        exit_code, timed_out, stderr = run_streaming(
            command, cwd=self.workspace, env=self.env, timeout=timeout, raw_path=log.raw_path(number),
            on_line=on_line, stdin_data=self.stdin_payload(instruction, image_paths))
        return self._finish_turn(number, events, exit_code, timed_out, stderr, timeout)

    def _finish_turn(self, number: int, events: list[dict[str, Any]], exit_code: int | None, timed_out: bool,
                     stderr: str, timeout: float | None) -> TurnResult:
        assert self.log is not None
        error = ""
        if timed_out:
            error = f"turn timed out after {int(timeout or 0)} s"
        elif exit_code not in (0, None):
            error = self._turn_errors[-1] if self._turn_errors else f"{self.harness_id} exited {exit_code}: {stderr[-1500:].strip()}"
        if error:
            events.append(self.log.write(turn=number, type="error", session=self.session_id, text=error))
        if self._usage:
            events.append(self.log.write(turn=number, type="usage", session=self.session_id, usage=self._usage))
        text = self.final_text()
        events.append(self.log.write(turn=number, type="turn_end", session=self.session_id, text=text,
                                     exit_code=exit_code, usage=self._usage or None))
        return TurnResult(text=text, session_id=self.session_id, usage=dict(self._usage), events=events,
                          exit_code=exit_code, timed_out=timed_out, error=error)
