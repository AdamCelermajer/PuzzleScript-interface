"""Direct-player session over any harness: one persistent agent conversation per episode.

``CliGameSession.next_action(prompt, image_path)`` runs one harness turn in the
agent workspace and returns the turn's single action. Nothing is deleted between turns
and the CLI keeps its own tools. Baseline says nothing about a workspace;
Baseline-plus gives a ``notes/`` directory as the agent's memory and an ``act.py`` command:
``python act.py ACTION_NAME`` submits the turn's action, and the turn is cut at the end of
that model step (acting is a tool call, so the agent never has to stop using tools to act).
A turn without a submission falls back to parsing a final JSON reply. The turn prompt asks for
``notes/world_model.md``, its current model of the game, every 100 actions and after each
level (``frameworks/baseline/turn_based.py``). ``notes/`` is mirrored to the run's ``workspace/`` folder for the
catalog and continuations. With ``memento`` every turn starts a fresh harness session with the same system
prompt and working folder, and the system prompt tells the agent so: only the folder (notes/) carries over.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from frameworks import world_model
from frameworks.baseline import prompt as baseline_prompt

GAME_ACTIONS = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7", "RESET", "FINISH"}
FRAME_NAME = "frame.png"
NOTES_DIR = "notes"
NOTES_HISTORY = "notes_history"  # in the run folder: notes/ after every harness turn
WORLD_MODEL_FILE = world_model.NAME  # in the working folder, as for the agentic player
ACT_SCRIPT = "act.py"
ACT_DIR = ".act"  # the open turn (turn.json) and its submitted action (submission.json)
ACTION_HINT = f"Submit one available action with python {ACT_SCRIPT} ACTION_NAME."
ACTION_HINT_TOOL = "Submit one available action with the act tool."

# Placed in the agent workspace; it only records the action, the controller plays it.
ACT_PROGRAM = r'''"""Submit this turn's game action: python act.py ACTION_NAME [--note "why"]"""
import argparse
import json
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description="Submit this turn's single game action.")
parser.add_argument("action")
parser.add_argument("--note", default="")
args = parser.parse_args()
state = Path(__file__).resolve().parent / ".act"
try:
    turn = json.loads((state / "turn.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    sys.exit("No game turn is open, so there is no action to submit now.")
action = args.action.strip().upper()
available = turn.get("available") or []
if available and action not in available:
    sys.exit(f"{action} is not available. Choose one of: {', '.join(available)}.")
submission = state / "submission.json"
if submission.exists():
    sys.exit("This turn's action is already submitted; the turn is ending.")
temporary = state / "submission.tmp"
temporary.write_text(json.dumps({"turn": turn.get("turn"), "action": action, "note": args.note}), encoding="utf-8")
os.replace(temporary, submission)
print(f"Submitted {action}. Your turn ends now; the next frame comes in the next turn.")
'''
TRANSIENT = ("at capacity", "rate limit", "429", "502", "503", "504", "timed out", "timeout",
             "connection", "stream disconnected", "overloaded")


def _response_json(text: str) -> Any:
    """Extract one unambiguous JSON response without constraining tool calls."""
    if "```" in text:
        blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
        if len(blocks) != 1:
            raise ValueError("Expected exactly one JSON response block")
        return json.loads(blocks[0])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        objects = []
        position = text.find("{")
        while position != -1:
            try:
                value, end = decoder.raw_decode(text, position)
            except json.JSONDecodeError:
                position = text.find("{", position + 1)
            else:
                objects.append(value)
                position = text.find("{", end)
        if len(objects) != 1:
            raise ValueError("Expected exactly one JSON response object")
        return objects[0]


MEMENTO_INSTRUCTIONS = (
    " Every turn starts a new session: you will remember nothing from earlier turns, not the conversation "
    f"and not your reasoning. Only your working directory carries over, including {NOTES_DIR}/. Before you "
    f"submit, write in {NOTES_DIR}/ everything your next turn will need."
)


def game_instructions(workspace_enabled: bool, memento: bool = False, tools: bool = False) -> str:
    """System prompt shared by every direct-player harness: with a workspace, the baseline prompt
    (frameworks/baseline/prompt.py), word for word the agentic player's but for the line on moves."""
    if workspace_enabled:
        return baseline_prompt.system_prompt("controller", tools) + (MEMENTO_INSTRUCTIONS if memento else "")
    text = (
        "You are playing a puzzle game. Return exactly one next game action per turn. "
        f"Your working directory contains {FRAME_NAME} (the current frame)."
    )
    return text + (
        ' After any tool calls finish on gameplay turns, return your final response as JSON '
        'with an "action" field and optional "note", or just the action name. '
        'Use the available game action name for "action". For the final '
        'world-model report, follow that turn\'s instructions instead.'
    )




def parse_action_reply(text: str) -> dict[str, str]:
    """Parse one final gameplay reply; ValueError triggers a correction turn."""
    text = str(text or "").strip()
    payload = {"action": text, "note": ""} if text.upper() in GAME_ACTIONS else _response_json(text)
    if not isinstance(payload, dict):
        raise ValueError("Expected one action")
    action = str(payload.get("action", "")).strip().upper()
    if action not in GAME_ACTIONS:
        raise ValueError("Missing or unsupported action")
    return {
        "operation": "FINISH" if action == "FINISH" else "ACT",
        "action": action, "note": str(payload.get("note", "")).strip(),
    }


@dataclass(frozen=True)
class GameSessionConfig:
    model: str = "gpt-5.6-sol"
    effort: str = "low"
    harness: str = "codex"
    workspace_enabled: bool = False  # baseline-plus: keep notes/
    provider: str = ""  # pinned OpenRouter upstream slug (opencode/bare); empty = OpenRouter routing
    turn_timeout: float | None = 1800.0
    memento: bool = False  # a fresh session every turn; only the working folder carries over

    def __post_init__(self) -> None:
        if self.memento and not self.workspace_enabled:
            raise ValueError("Memento needs the notes folder: it is the only memory that carries over")
        if self.memento and self.harness == "bare":
            raise ValueError("Memento needs a CLI harness: bare keeps its conversation in memory, not in a session id")
        if self.provider and not self.model.startswith(("openrouter/", "nanogpt/")):
            raise ValueError("Provider pinning is only supported for OpenRouter and NanoGPT")


class CliGameSession:
    """One persistent harness conversation for one game episode."""

    def __init__(self, config: GameSessionConfig, working_directory: str | Path,
                 artifact_directory: str | Path | None = None, *, mirror_directory: str | Path | None = None) -> None:
        self.config = config
        self.working_directory = Path(working_directory).resolve()
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self.artifact_directory = Path(artifact_directory or self.working_directory.parent).resolve()
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        self.mirror_directory = Path(mirror_directory).resolve() if mirror_directory else None
        self.session_log_path = self.artifact_directory / "agent_events.jsonl"
        self.deadline: float | None = None  # monotonic; set by a wall-clock budget
        self.operations = 0
        self.session: Any = None
        self.turn_count = 0
        self.available_actions: list[str] = []  # set by the runner before each turn
        self.action_hint = ACTION_HINT if config.workspace_enabled else ""

    def __enter__(self) -> "CliGameSession":
        from harnesses.registry import create_session

        if self.config.workspace_enabled:
            (self.working_directory / NOTES_DIR).mkdir(exist_ok=True)
        initial_notes = sorted(path.relative_to(self.working_directory).as_posix()
                               for path in self.working_directory.rglob("*") if path.is_file())
        self.session = create_session(self.config.harness)
        tools = baseline_prompt.game_tools("controller", self.session) if self.config.workspace_enabled else []
        self.session.game_tools = tools
        if tools:
            self.action_hint = ACTION_HINT_TOOL
        instructions = game_instructions(self.config.workspace_enabled, self.config.memento, bool(tools))
        if self.config.workspace_enabled:
            (self.working_directory / ACT_SCRIPT).write_text(ACT_PROGRAM, encoding="utf-8")
            (self.working_directory / ACT_DIR).mkdir(exist_ok=True)
        self.session.start(self.working_directory, instructions, self.config.model, self.config.effort,
                           "player", self.artifact_directory, provider=self.config.provider)
        if self.config.workspace_enabled:
            self.session.stop_check = lambda: self._act_path("submission.json").is_file()
        (self.artifact_directory / "isolation_manifest.json").write_text(json.dumps({
            "harness": self.config.harness, "model": self.config.model, "effort": self.config.effort,
            "model_provider": self.session.provider, "openrouter_provider": self.config.provider or None,
            "isolation": "one Docker container per run (harnesses.launch)",
            "workspace_policy": ("a fresh session every turn; only the working folder (notes/) carries over"
                                 if self.config.memento else
                                 "nothing deleted between turns; notes/ given as working memory"
                                 if self.config.workspace_enabled else
                                 "nothing deleted between turns; no workspace mentioned"),
            "initial_note_files": initial_notes, "base_instructions": instructions,
            "web_tools": "disabled", "prompt_omits_game_id": True, "prompt_omits_game_title": True,
            "prompt_omits_action_meanings": True,
        }, indent=2), encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.session is not None:
            self.session.close()
        self.session = None

    def _timeout(self) -> float | None:
        timeout = self.config.turn_timeout
        if self.deadline is not None:
            remaining = max(1.0, self.deadline - time.monotonic())
            timeout = remaining if timeout is None else min(timeout, remaining)
        return timeout

    def _turn(self, prompt: str, images: list[Path], kind: str) -> str:
        if self.session is None:
            raise RuntimeError("Game session has not been started")
        result = None
        for attempt in range(4):
            if self.config.memento:
                self.session.session_id = ""  # no --session/resume: the harness opens a new session
            result = self.session.turn(prompt, images=images, timeout=self._timeout())
            self.operations += sum(1 for event in result.events
                                   if event["type"] in {"command", "file_change", "tool"})
            with (self.artifact_directory / "turns.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"), "turn_kind": kind,
                                         "turn": self.session.turn_number, "session_id": result.session_id,
                                         "text": result.text, "error": result.error, "usage": result.usage}) + "\n")
            self._after_turn()
            if result.text or not result.error or self._submission() is not None:
                return result.text
            if result.timed_out or attempt == 3 or not any(word in result.error.lower() for word in TRANSIENT):
                break
            time.sleep(2 ** attempt)
        raise RuntimeError(f"{self.config.harness} turn failed: {result.error if result else 'no result'}")

    def _after_turn(self) -> None:
        if (self.mirror_directory is not None and self.config.workspace_enabled
                and (self.working_directory / NOTES_DIR).is_dir()):
            target = self.mirror_directory / NOTES_DIR
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(self.working_directory / NOTES_DIR, target, symlinks=False)
            # The mirror holds only the latest notes; each turn's version is kept for analysis, named like
            # raw/turn-N.jsonl, outside workspace/ (a continuation seeds its notes from every file there).
            shutil.copytree(self.working_directory / NOTES_DIR,
                            self.artifact_directory / NOTES_HISTORY / f"turn-{self.session.turn_number:04d}", symlinks=False,
                            dirs_exist_ok=True)

    def _act_path(self, name: str) -> Path:
        return self.working_directory / ACT_DIR / name

    def _open_turn(self) -> None:
        """Clear the last submission and tell act.py which actions this turn allows."""
        self.turn_count += 1
        self._act_path("submission.json").unlink(missing_ok=True)
        temporary = self._act_path("turn.tmp")
        temporary.write_text(json.dumps({"turn": self.turn_count, "available": self.available_actions}),
                             encoding="utf-8")
        temporary.replace(self._act_path("turn.json"))

    def _close_turn(self) -> None:
        # Nothing stays open between turns, so the final report turn is never cut short.
        self._act_path("turn.json").unlink(missing_ok=True)
        self._act_path("submission.json").unlink(missing_ok=True)

    def _submission(self) -> dict[str, str] | None:
        if not self.config.workspace_enabled:
            return None
        try:
            payload = json.loads(self._act_path("submission.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        action = str(payload.get("action", "")).strip().upper()
        if payload.get("turn") != self.turn_count or action not in GAME_ACTIONS - {"FINISH"}:
            return None
        return {"operation": "ACT", "action": action, "note": str(payload.get("note", "")).strip()}

    def next_action(self, prompt: str, image_path: str | Path | None = None) -> dict[str, str]:
        # The picture is not attached: it would stay in the conversation every turn. The system prompt
        # names frame.png; the player opens it with its own tools when it needs to.
        images: list[Path] = []
        if image_path is not None:
            shutil.copyfile(Path(image_path), self.working_directory / FRAME_NAME)
        if not self.config.workspace_enabled:
            return parse_action_reply(self._turn(prompt, images, "game_action"))
        self._open_turn()
        try:
            text = self._turn(prompt, images, "game_action")
            submitted = self._submission()
        finally:
            self._close_turn()
        # No act.py submission: fall back to a final JSON reply (a ValueError asks again).
        return submitted if submitted is not None else parse_action_reply(text)

    def note_tool_count(self) -> int:
        return self.operations

    @property
    def world_model_path(self) -> Path | None:
        """The world-model file the player keeps (with notes only)."""
        return self.working_directory / WORLD_MODEL_FILE if self.config.workspace_enabled else None

    @property
    def world_model_file(self) -> str | None:
        """The same file as the player names it, relative to its working directory."""
        return WORLD_MODEL_FILE if self.config.workspace_enabled else None

    def final_world_model(self, reason: str = "", levels: int = 0, total: int = 0) -> Path | None:
        """The end-of-game report: the agent rewrites its world-model file; returns it when present."""
        self._turn(baseline_prompt.REPORT_PROMPT.format(reason=reason, levels=levels, total=total), [],
                   "final_world_model")
        path = self.world_model_path or self.working_directory / world_model.NAME
        return path if path.is_file() else None
