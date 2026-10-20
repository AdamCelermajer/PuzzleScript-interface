"""Direct-player session over any harness: one persistent agent conversation per episode.

``CliGameSession.next_action(prompt, image_path)`` runs one harness turn in the
agent workspace and parses the single action reply. Baseline (conversation only):
after every turn the controller deletes every workspace file that is not the
provided frame. Baseline-plus additionally keeps the ``notes/`` directory, which is
mirrored to the run's ``workspace/`` folder for the catalog and continuations.
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

from harnesses.codex import codex_oauth_status  # noqa: F401  (re-exported for the workbench)
from harnesses.codex import find_codex_bin as _find_codex_bin  # noqa: F401  (avo/legacy imports it)

GAME_ACTIONS = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7", "FINISH"}
FRAME_NAME = "frame.png"
NOTES_DIR = "notes"
# Harness state some CLIs keep inside their working directory; never agent memory.
HARNESS_STATE = {"antigravity": {".gemini"}}
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


def game_instructions(workspace_enabled: bool) -> str:
    """System prompt shared by every direct-player harness."""
    if workspace_enabled:
        text = (
            "You are playing a puzzle game. Return exactly one next game action per turn. "
            f"Your working directory contains {FRAME_NAME} (the current frame) and a {NOTES_DIR}/ "
            f"directory. Only {NOTES_DIR}/ persists between turns; every other file you create is "
            f"deleted after each turn. Use {NOTES_DIR}/ as working memory. Before your first game "
            f"action, write {NOTES_DIR}/strategy.md with your initial observations, hypotheses, and "
            f"plan. On later turns, read {NOTES_DIR}/strategy.md before acting and update it whenever "
            "evidence confirms or rejects a hypothesis, your plan changes, you encounter a dead end, or "
            "a level changes. Keep confirmed facts separate from hypotheses. File and tool work "
            "happens before your final one-action response."
        )
    else:
        text = (
            "You are playing a puzzle game. Return exactly one next game action per turn. "
            f"Your working directory contains only {FRAME_NAME} (the current frame); anything you "
            "write there is deleted after each turn, so this conversation is your only memory."
        )
    return text + (
        ' After any tool calls finish on gameplay turns, return your final response as JSON '
        'with an "action" field and optional "note", or just the action name. '
        'Use the available game action name for "action". For the final '
        'environment-model report, use the report fields requested instead.'
    )


WORLD_MODEL_PROMPT = (
    "The gameplay run has ended. Describe the environment model you learned. "
    "Identify objects, controls, transition rules, the goal condition, remaining "
    "uncertainties, and known failures or deadlocks. Distinguish observed facts "
    "from hypotheses in the wording. Do not take any more actions or use tools."
    " Return a JSON object with these fields: objects, controls, "
    "transition_rules, goal_condition, uncertainties, failures_and_deadlocks. "
    "Use arrays of strings for all fields except goal_condition, which is a string."
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

    def __post_init__(self) -> None:
        if self.provider and not self.model.startswith("openrouter/"):
            raise ValueError("Provider pinning is only supported for OpenRouter")


def wipe_workspace(workspace: Path, keep: set[str]) -> list[str]:
    """Delete every top-level entry of ``workspace`` whose name is not in ``keep``."""
    removed = []
    for path in sorted(workspace.iterdir()):
        if path.name in keep:
            continue
        removed.append(path.name)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    return removed


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

    @property
    def keep(self) -> set[str]:
        keep = {FRAME_NAME} | HARNESS_STATE.get(self.config.harness, set())
        if self.config.workspace_enabled:
            keep.add(NOTES_DIR)
        return keep

    def __enter__(self) -> "CliGameSession":
        from harnesses.registry import create_session

        if self.config.workspace_enabled:
            (self.working_directory / NOTES_DIR).mkdir(exist_ok=True)
        wipe_workspace(self.working_directory, self.keep)
        initial_notes = sorted(path.relative_to(self.working_directory).as_posix()
                               for path in self.working_directory.rglob("*") if path.is_file())
        instructions = game_instructions(self.config.workspace_enabled)
        self.session = create_session(self.config.harness)
        self.session.start(self.working_directory, instructions, self.config.model, self.config.effort,
                           "player", self.artifact_directory, provider=self.config.provider)
        (self.artifact_directory / "isolation_manifest.json").write_text(json.dumps({
            "harness": self.config.harness, "model": self.config.model, "effort": self.config.effort,
            "model_provider": self.session.provider, "openrouter_provider": self.config.provider or None,
            "isolation": "one Docker container per run (harnesses.launch)",
            "workspace_policy": ("keep frame.png and notes/; delete everything else after each turn"
                                 if self.config.workspace_enabled else
                                 "keep frame.png only; delete everything else after each turn"),
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
            result = self.session.turn(prompt, images=images, timeout=self._timeout())
            self.operations += sum(1 for event in result.events
                                   if event["type"] in {"command", "file_change", "tool"})
            with (self.artifact_directory / "turns.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"), "turn_kind": kind,
                                         "turn": self.session.turn_number, "session_id": result.session_id,
                                         "text": result.text, "error": result.error, "usage": result.usage}) + "\n")
            self._after_turn()
            if result.text or not result.error:
                return result.text
            if result.timed_out or attempt == 3 or not any(word in result.error.lower() for word in TRANSIENT):
                break
            time.sleep(2 ** attempt)
        raise RuntimeError(f"{self.config.harness} turn failed: {result.error if result else 'no result'}")

    def _after_turn(self) -> None:
        wipe_workspace(self.working_directory, self.keep)
        if (self.mirror_directory is not None and self.config.workspace_enabled
                and (self.working_directory / NOTES_DIR).is_dir()):
            target = self.mirror_directory / NOTES_DIR
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(self.working_directory / NOTES_DIR, target, symlinks=False)

    def next_action(self, prompt: str, image_path: str | Path | None = None) -> dict[str, str]:
        images: list[Path] = []
        if image_path is not None:
            frame = self.working_directory / FRAME_NAME
            shutil.copyfile(Path(image_path), frame)
            images.append(frame)
        return parse_action_reply(self._turn(prompt, images, "game_action"))

    def note_tool_count(self) -> int:
        return self.operations

    def final_world_model(self) -> dict[str, object]:
        text = self._turn(WORLD_MODEL_PROMPT, [], "final_world_model")
        if not text:
            raise ValueError("The agent returned no final world model")
        payload = _response_json(text)
        if not isinstance(payload, dict):
            raise ValueError("World model response must be a JSON object")
        return payload
