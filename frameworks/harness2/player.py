"""Harness²'s player: one coding-agent session that drives the game itself.

As in the paper, the agent gets one task and one working folder that persists for the whole
rollout; the candidate harness (AGENTS.md, .opencode/, scripts/) is placed there first. The game
is a command in that folder, ``python game.py look | do ACTION | reset``, answered by a small
server in this process: it owns the game session and the action budget, and records every move
in the baseline shape (transitions.jsonl, frames/, result.json) so the run page replays it.
If the agent ends its turn with actions left, it is told to continue in the same session; at
the end it writes world_model.md.
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from client.arc.arcade_env import ArcadeEnv
from client.arc.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid
from harnesses.registry import HARNESS_IDS, create_session

RPC_DIR = ".game"
# Consecutive agent turns without a game action before the rollout ends as idle.
IDLE_TURNS = 2
# Provider errors worth retrying when the turn did no work.
TRANSIENT = ("unavailable", "temporarily", "at capacity", "rate limit", "429", "502", "503", "504",
             "timed out", "timeout", "connection", "stream disconnected", "overloaded")

GAME_CLI = r'''"""The game. Usage: python game.py look | python game.py do ACTION | python game.py reset"""
import json, sys, time, uuid
from pathlib import Path

if len(sys.argv) < 2 or sys.argv[1] not in ("look", "do", "reset") or (sys.argv[1] == "do") != (len(sys.argv) == 3):
    raise SystemExit(__doc__)
root = Path(__file__).resolve().parent / ".game"
name = uuid.uuid4().hex
(root / (name + ".tmp")).write_text(json.dumps({"command": sys.argv[1], "action": sys.argv[2] if len(sys.argv) > 2 else ""}))
(root / (name + ".tmp")).replace(root / (name + ".request"))
answer = root / (name + ".answer")
while not answer.exists():
    time.sleep(0.05)
time.sleep(0.02)
reply = json.loads(answer.read_text())
answer.unlink()
print(reply["text"])
sys.exit(0 if reply["ok"] else 1)
'''

SYSTEM_PROMPT = """You are playing an unknown puzzle game. Your working folder persists for the whole run: keep notes, write and run your own scripts here, as you find useful.

The game is played only through this command in your folder:

    python game.py look           show the current grid and status; saves the current picture as frame.png (view it with your file reader)
    python game.py do ACTION      take one game action (e.g. ACTION3); prints what changed and the new grid
    python game.py reset          restart the current level; costs one action

Actions are opaque names; learn what they do from what changes. Every `do` and `reset` uses one action from your budget. Complete as many levels as you can within the budget. Your own scripts may call `python game.py` too.

Learn about the game only through game.py. Do not search this machine, other folders or the network for the game's files, source code, solutions or server; that is not playing the game."""

REPORT_PROMPT = (
    "The game session has ended ({reason}; levels completed {levels}/{total}). Do not use game.py any more. "
    "Write world_model.md in your folder: the objects, what each action does, the rules you found, the goal, "
    "and what is still uncertain. Separate confirmed facts from guesses. Then reply 'done'."
)


class GameServer:
    """Answers game.py requests: one game session, one action budget, the full record."""

    def __init__(self, env, workspace: Path, output_dir: Path, max_steps: int, max_wall_seconds: float = 0) -> None:
        self.env, self.workspace, self.output = env, workspace, output_dir
        self.max_steps, self.deadline = max_steps, (time.monotonic() + max_wall_seconds) if max_wall_seconds else None
        self.actions: list[str] = []
        self.frames = output_dir / "frames"
        self.frames.mkdir(parents=True, exist_ok=True)
        self.rpc = workspace / RPC_DIR
        self.rpc.mkdir(parents=True, exist_ok=True)
        (workspace / "game.py").write_text(GAME_CLI, encoding="utf-8")
        self.frame: FrameData = env.reset()
        self._save_picture()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    # -- state ----------------------------------------------------------------------
    @property
    def solved(self) -> bool:
        f = self.frame
        return f.state == GameState.WIN or bool(f.win_levels and f.levels_completed >= f.win_levels)

    @property
    def out_of_time(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline

    @property
    def finished(self) -> bool:
        return self.solved or len(self.actions) >= self.max_steps or self.out_of_time

    @property
    def reason(self) -> str:
        if self.solved:
            return "task_goal_reached"
        if len(self.actions) >= self.max_steps:
            return "step_budget_exhausted"
        return "wall_budget_exhausted" if self.out_of_time else "agent_stopped"

    def _status(self) -> str:
        f = self.frame
        grid = "\n".join(" ".join(str(cell) for cell in row) for row in last_grid(f.frame))
        available = ", ".join(a.name for a in f.available_actions or []) or "unknown"
        return (f"state={getattr(f.state, 'value', f.state)} levels={f.levels_completed}/{f.win_levels} "
                f"actions_used={len(self.actions)}/{self.max_steps}\navailable_actions={available}\n"
                "grid (one number per visible tile; same picture = same number):\n" + grid)

    def _save_picture(self) -> None:
        data_url = str(getattr(self.frame.rendered_frame, "data_url", "") or "")
        prefix = "data:image/png;base64,"
        if data_url.startswith(prefix):
            png = base64.b64decode(data_url[len(prefix):])
            (self.workspace / "frame.png").write_bytes(png)
            (self.frames / f"{len(self.actions):03d}.png").write_bytes(png)

    # -- commands ---------------------------------------------------------------------
    def handle(self, command: str, action: str) -> tuple[bool, str]:
        if command == "look":
            return True, self._status() + "\npicture: frame.png"
        if self.finished:
            return False, f"The game session is over ({self.reason}). No more actions."
        if command == "reset":
            return self._act("RESET", self.env.reset)
        try:
            game_action = GameAction[action.strip().upper()]
        except KeyError:
            return False, f"Unknown action {action!r}. {self._status()}"
        if self.frame.available_actions and game_action not in self.frame.available_actions:
            return False, f"{game_action.name} is not available. {self._status()}"
        return self._act(game_action.name, lambda: self.env.step(game_action))

    def _act(self, name: str, call) -> tuple[bool, str]:
        before, before_grid = self.frame, last_grid(self.frame.frame)
        self.frame = call()
        self.actions.append(name)
        after_grid = last_grid(self.frame.frame)
        changed = [{"row": r, "col": c, "before": b, "after": a}
                   for r, (rb, ra) in enumerate(zip(before_grid, after_grid))
                   for c, (b, a) in enumerate(zip(rb, ra)) if b != a]
        side = lambda f, grid: {"grid": grid, "state": getattr(f.state, "value", str(f.state)),
                                "levels_completed": f.levels_completed, "win_levels": f.win_levels}
        record = {"id": f"T{len(self.actions):06d}", "timestamp": datetime.now().isoformat(timespec="seconds"),
                  "decision": len(self.actions), "action_index": len(self.actions), "action": name,
                  "before": side(before, before_grid), "after": side(self.frame, after_grid),
                  "changed": before_grid != after_grid, "changed_cells": changed, "note": ""}
        with (self.output / "transitions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        self._save_picture()
        if self.frame.levels_completed > before.levels_completed:
            what = f"LEVEL COMPLETED ({self.frame.levels_completed}/{self.frame.win_levels}). The grid below is the next level."
        elif len(before_grid) != len(after_grid) or (before_grid and len(before_grid[0]) != len(after_grid[0])):
            what = "The grid changed size."
        else:
            what = ("changed " + ", ".join(f"({c['row']},{c['col']}) {c['before']}->{c['after']}" for c in changed[:40])
                    if changed else "nothing changed")
        return True, f"{name}: {what}\n{self._status()}"

    # -- request loop -----------------------------------------------------------------
    def start(self) -> "GameServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _serve(self) -> None:
        while not self._stop.is_set():
            requests = sorted(self.rpc.glob("*.request"), key=lambda p: p.stat().st_mtime)
            if not requests:
                self._stop.wait(0.05)
                continue
            for path in requests:
                try:
                    request = json.loads(path.read_text(encoding="utf-8"))
                    path.unlink(missing_ok=True)
                    ok, text = self.handle(str(request.get("command", "")), str(request.get("action", "")))
                except Exception as exc:  # report to the agent; never kill the server
                    ok, text = False, f"game error: {type(exc).__name__}: {exc}"
                answer = path.with_suffix(".answer.tmp")
                answer.write_text(json.dumps({"ok": ok, "text": text}), encoding="utf-8")
                answer.replace(path.with_suffix(".answer"))


def _worked(result) -> bool:
    return any(event["type"] in {"command", "tool"} for event in result.events)


def _turn(session, instruction: str, timeout: float | None):
    """One agent turn, retried (same instruction, same session) after a provider hiccup that did no work."""
    for attempt in range(4):
        result = session.turn(instruction, timeout=timeout)
        error = (result.error or "").lower()
        if not error or result.timed_out or _worked(result) or not any(word in error for word in TRANSIENT):
            return result
        time.sleep(2 ** (attempt + 1))
    return result


def play(env, output_dir: Path, *, harness: str, model: str, effort: str, provider: str, max_steps: int,
         max_wall_seconds: float, harness_dir: Path | None, max_turns: int = 40) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="h2-player-"))
    if harness_dir is not None:
        shutil.copytree(harness_dir, workspace, dirs_exist_ok=True)
    server = GameServer(env, workspace, output_dir, max_steps, max_wall_seconds).start()
    session = create_session(harness)
    turns, idle, error = 0, 0, ""
    try:
        session.start(workspace, SYSTEM_PROMPT, model, effort, "player", output_dir, provider=provider)
        instruction = (f"Play the game now. You have {max_steps} actions. Start with `python game.py look`, "
                       "then keep playing until the game is solved or the actions run out.")
        while not server.finished and turns < max_turns and idle < IDLE_TURNS:
            used = len(server.actions)
            remaining = None if server.deadline is None else max(1.0, server.deadline - time.monotonic())
            result = _turn(session, instruction, remaining)
            turns += 1
            if result.error and not result.timed_out and not _worked(result):
                raise RuntimeError(f"{harness} turn {turns} failed: {result.error}")
            idle = idle + 1 if len(server.actions) == used else 0
            f = server.frame
            instruction = (f"The game is not finished: levels {f.levels_completed}/{f.win_levels}, "
                           f"{max_steps - len(server.actions)} of {max_steps} actions left. Keep playing with python game.py.")
        reason = server.reason if server.finished else ("agent_idle" if idle >= IDLE_TURNS else "turn_budget_exhausted")
        # A missing report leaves the rollout's score intact; the coach then sees no world_model.md.
        _turn(session, REPORT_PROMPT.format(reason=reason, levels=server.frame.levels_completed,
                                            total=server.frame.win_levels), 600)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        reason = "error"
    finally:
        server.stop()
        session.close()
        if (workspace / "world_model.md").is_file():
            shutil.copyfile(workspace / "world_model.md", output_dir / "world_model.md")
        shutil.copytree(workspace, output_dir / "workspace", dirs_exist_ok=True, ignore=shutil.ignore_patterns(RPC_DIR))
        shutil.rmtree(workspace, ignore_errors=True)
    result = {"status": "error" if error else "completed", "reason": reason, "error": error or None,
              "solved": server.solved, "actions": server.actions, "action_count": len(server.actions),
              "agent_turns": turns, "final_state": getattr(server.frame.state, "value", str(server.frame.state)),
              "levels_completed": server.frame.levels_completed, "win_levels": server.frame.win_levels,
              "world_model": str(output_dir / "world_model.md") if (output_dir / "world_model.md").is_file() else None}
    (output_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", choices=HARNESS_IDS, default="opencode")
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--provider", default="")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--max-wall-seconds", type=int, default=0)
    parser.add_argument("--harness-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "run_config.json").write_text(json.dumps({
        "executor": "harness2-agent", "harness": args.harness,
        "provider": args.provider, "model": args.model, "reasoning_effort": args.effort, "game_id": args.game_id,
        "backend_url": args.backend_url, "max_steps": args.max_steps, "max_wall_seconds": args.max_wall_seconds,
    }, indent=2), encoding="utf-8")
    result = play(ArcadeEnv(game_id=args.game_id, backend_url=args.backend_url), output, harness=args.harness,
                  model=args.model, effort=args.effort, provider=args.provider, max_steps=args.max_steps,
                  max_wall_seconds=args.max_wall_seconds, harness_dir=args.harness_dir)
    print(f"levels_completed={result['levels_completed']} actions={result['action_count']} reason={result['reason']}")


if __name__ == "__main__":
    main()
