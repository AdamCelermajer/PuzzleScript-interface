"""Explicit new-session continuation; never presented as the original thread."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from game.types import GameAction
from game.grid import last_grid


def load_parent(directory: str | Path) -> tuple[dict, list[dict]]:
    root = Path(directory).resolve()
    history = [json.loads(line) for line in (root / "transitions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if (root / "result.json").is_file():
        result = json.loads((root / "result.json").read_text(encoding="utf-8"))
        if result.get("solved") or result.get("reason") != "step_budget_exhausted":
            raise ValueError("Continue only an unsolved run that exhausted its action budget")
    else:
        error = json.loads((root / "error.json").read_text(encoding="utf-8"))
        if not error.get("message"):
            raise ValueError("Failed continuation requires a recorded error")
        config = json.loads((root / "run_config.json").read_text(encoding="utf-8"))
        if not history or history[-1]["after"]["state"] == "WIN" or len(history) >= config["max_steps"]:
            raise ValueError("Failed parent has no recoverable unsolved action budget")
        result = {"status": "failed", "reason": "recorded_error", "solved": False, "action_count": len(history)}
    if not history or len(history) != result["action_count"]:
        raise ValueError("Parent transition history is incomplete")
    return result, history


def load_moves(directory: str | Path) -> list[dict]:
    """The moves of a run that stopped early for any reason (a crash, a hang, failed turns)."""
    root = Path(directory).resolve()
    path = root / "transitions.jsonl"
    history = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []
    config = json.loads((root / "run_config.json").read_text(encoding="utf-8"))
    if history and (history[-1]["after"]["state"] == "WIN" or len(history) >= config["max_steps"]):
        raise ValueError("The parent has no moves left to play")
    return history


def carry_over(parent: str | Path, output: Path, history: list[dict]) -> None:
    """The child's record starts as the parent's: it holds the whole game, so a child can be resumed too."""
    root = Path(parent).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "transitions.jsonl").write_text("".join(json.dumps(item) + "\n" for item in history), encoding="utf-8")
    if (root / "frames").is_dir():
        shutil.copytree(root / "frames", output / "frames", dirs_exist_ok=True)


def restore_folder(parent: str | Path, target: Path) -> None:
    """The player's files as it left them; a run without the file record has its notes."""
    if (Path(parent).resolve() / "agent_files" / "index.jsonl").is_file():
        restore_files(parent, target)
    else:
        seed_notes(parent, target)


def seed_notes(parent: str | Path, target: Path) -> None:
    source = Path(parent).resolve() / "workspace"
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Parent notes contain a link")
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            relative = path.relative_to(source)
            # Notes persist only under notes/; older runs kept them at the workspace root.
            if relative.parts[0] != "notes":
                relative = Path("notes") / relative
            destination = target / relative
            if destination.exists():
                raise ValueError("Continuation requires an empty note workspace")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


def restore_game(env, frame, history: list[dict]):
    # Replaying on a new environment leaves the original run untouched. Check
    # every state, not just the last board; refuse nondeterministic restoration.
    for index, transition in enumerate(history, 1):
        if transition["action_index"] != index:
            raise ValueError("Parent action indices are not consecutive")
        if last_grid(frame.frame) != transition["before"]["grid"]:
            raise ValueError(f"Restoration mismatch before action {index}")
        action = GameAction[transition["action"]]
        frame = env.reset() if action is GameAction.RESET else env.step(action)
        actual = {"grid": last_grid(frame.frame), "state": getattr(frame.state, "value", str(frame.state)),
                  "levels_completed": frame.levels_completed, "win_levels": frame.win_levels}
        if actual != transition["after"]:
            raise ValueError(f"Restoration mismatch after action {index}")
    return frame


def restore_files(parent: str | Path, target: Path) -> None:
    """Every file the player had, at its last recorded version (agent_files/, not only its notes)."""
    root = Path(parent).resolve() / "agent_files"
    latest: dict[str, dict] = {}
    for line in (root / "index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        latest[row["path"]] = row
    target.mkdir(parents=True, exist_ok=True)
    for path, row in latest.items():
        if row["status"] != "deleted" and row.get("file"):
            destination = (target / path).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ValueError(f"Parent file outside the folder: {path}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / row["file"], destination)


def last_context(parent: str | Path) -> dict:
    """The last request that followed a complete answer: the conversation without the failed retries
    after it. A summary request is not the conversation, so it is never the one taken."""
    root = Path(parent).resolve() / "calls"
    calls = []
    for path in sorted(root.glob("[0-9][0-9][0-9][0-9].json")):
        call = json.loads(path.read_text(encoding="utf-8"))
        if call.get("method") == "POST":
            calls.append(call)
    def answered(call: dict) -> bool:
        response = call.get("response") or {}
        return not call.get("error") and not response.get("error") and response.get("finish_reason") in ("tool_calls", "stop")
    def summary(call: dict) -> bool:
        return "context summarization" in json.dumps((call.get("request") or {}).get("messages", [])[:1])[:400]
    for before, call in reversed(list(zip(calls, calls[1:]))):
        if answered(before) and not summary(before) and not summary(call):
            messages = call["request"]["messages"]
            content = messages[0].get("content")
            system = content if isinstance(content, str) else " ".join(str(p.get("text", "")) for p in content)
            found = re.search(r"Working directory: (/\S+)", system)
            if not found:
                raise ValueError("The recorded request does not name its working directory")
            return {"call": call.get("call"), "messages": messages, "directory": found[1],
                    "images": root, "usage": before["response"].get("usage")}
    raise ValueError("The parent has no complete answer followed by another request")


def history_prompt(history: list[dict]) -> str:
    visible = [{"action_index": item["action_index"], "action": item["action"],
                "before": item["before"], "after": item["after"]} for item in history]
    return (
        f"This is a new-session continuation after {len(history)} prior game actions. "
        "The environment has been restored to the final recorded position. "
        "The action budget below is additional to those prior actions. "
        "Your saved notes have been carried over; read them before acting. "
        "The previous session's private reasoning is not available. "
        "Here is its recorded action and observation history:\n"
        + json.dumps(visible, separators=(",", ":")) + "\n\n"
    )
