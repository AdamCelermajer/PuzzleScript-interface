"""Baseline with ``driver=agent``: one coding-agent session that drives the game itself.

The other driver (``run.py``, ``driver=controller``) sends one frame per call and gets one action
back. Here, as in the Harness² paper, the agent gets one task and one working folder that persists
for the whole run (Harness² places its candidate harness, AGENTS.md, .opencode/, scripts/, there
first; this is Harness²'s player). It is told what the controller-driven player is told, word for word
(frameworks/baseline/prompt.py), but for the line on how to move. The game is a command in that folder,
``game.py do ACTION`` (RESET is one more action) in a folder of its own, outside the agent's, offered
as the ``do`` tool to a harness that takes tools (others get its path), and answered by a small server in
this process: it owns the game
session and the action budget, and records every move in the baseline shape (transitions.jsonl,
frames/, result.json) so the run page replays it. world_model.md, if the agent writes one, is copied
after every 100 actions, each completed level and the end (frameworks/world_model.py). If it ends
its turn with actions left, it is told to continue in the same session; at the end, with the game
closed, it writes world_model.md as a final report.
A turn the provider fails is followed by another turn (a fresh session in the same folder when
the conversation itself cannot go on, e.g. a full context); three failed turns in a row end the
run. With ``--stop-after-levels N`` the game ends once N levels are completed and the next level
is never shown: not printed, not in frame.png, and its record is written only after the session.
``--start-level k`` opens the game at level k (frameworks/levels.py); N then counts from k, so
``--start-level k --stop-after-levels 1`` is the one-level task, scored in result.json's ``levels``.
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

from game.arcade_env import ArcadeEnv
from game.types import FrameData, GameAction, GameState
from game.grid import last_grid
from frameworks import levels, world_model
from frameworks.baseline import prompt as baseline_prompt
from harnesses.registry import HARNESS_IDS, create_session

RPC_DIR = ".game"
# Consecutive agent turns without a game action before the rollout ends as idle.
IDLE_TURNS = 2
# Provider errors worth retrying when the turn did no work.
TRANSIENT = ("unavailable", "temporarily", "at capacity", "rate limit", "429", "502", "503", "504",
             "timed out", "timeout", "connection", "stream disconnected", "overloaded")
# Failed turns in a row (no work done, after those retries) before the run ends with an error.
FAILED_TURNS = 3
# Errors after which the conversation itself cannot go on, so the player continues in a fresh session
# in the same folder. NanoGPT answers a full context with the generic "Invalid request parameters"
# (20 Oct, Harness² rollout "final": 261k of the 27B's 262k tokens before the failing request).
SESSION_ENDED = ("invalid request parameters", "context length", "context window", "maximum context",
                 "too many tokens", "prompt is too long")

GAME_CLI = r'''"""The game. Usage: python game.py do ACTION"""
import json, sys, time, uuid
from pathlib import Path

if len(sys.argv) < 2 or sys.argv[1] != "do" or (sys.argv[1] == "do") != (len(sys.argv) == 3):
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

CONTINUE_PROMPT = ("The game is not finished: levels {levels}/{total}, {left} of {budget} actions left. "
                   "Keep playing.")
FAILED_PROMPT = ("The last reply failed; continue playing the game: levels {levels}/{total}, "
                 "{left} of {budget} actions left. Keep playing.")
RESTART_PROMPT = ("This is a new session: the previous conversation could not continue. Your folder is as you left "
                  "it. The game is still running: levels {levels}/{total}, {left} of {budget} actions left. "
                  "Keep playing.\n\n{observation}")


class GameServer:
    """Answers game.py requests: one game session, one action budget, the full record."""

    def __init__(self, env, workspace: Path, output_dir: Path, max_steps: int, max_wall_seconds: float = 0,
                 stop_after_levels: int = 0) -> None:
        self.env, self.workspace, self.output = env, workspace, output_dir
        self.max_steps, self.deadline = max_steps, (time.monotonic() + max_wall_seconds) if max_wall_seconds else None
        self.stop_after_levels = stop_after_levels
        self.actions: list[str] = []
        self.closed = False  # set once play is over and only the final reports remain
        self._withheld: tuple[dict, bytes | None] | None = None  # the move that reached the level target
        self.frames = output_dir / "frames"
        self.frames.mkdir(parents=True, exist_ok=True)
        self.snapshots = world_model.Snapshots(workspace / world_model.NAME, output_dir)
        # Outside the agent's folder: only the model plays, through the do tool.
        self.home = Path(tempfile.mkdtemp(prefix="game-"))
        self.script = self.home / "game.py"
        self.rpc = self.home / RPC_DIR
        self.rpc.mkdir(parents=True, exist_ok=True)
        self.script.write_text(GAME_CLI, encoding="utf-8")
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
    def level_target_reached(self) -> bool:
        return bool(self.stop_after_levels) and self.frame.levels_completed >= self.stop_after_levels

    @property
    def finished(self) -> bool:
        return self.solved or self.level_target_reached or len(self.actions) >= self.max_steps or self.out_of_time

    @property
    def reason(self) -> str:
        if self.solved:
            return "task_goal_reached"
        if self.level_target_reached:
            return "level_target_reached"
        if len(self.actions) >= self.max_steps:
            return "step_budget_exhausted"
        return "wall_budget_exhausted" if self.out_of_time else "agent_stopped"

    def _status(self) -> str:
        f = self.frame
        if self.level_target_reached:  # the frame is the next level, which stays unseen
            return (f"state=OVER levels={f.levels_completed}/{f.win_levels} actions_used={len(self.actions)}/"
                    f"{self.max_steps}\nThe game is over: the level target is reached.")
        return baseline_prompt.observation(f, len(self.actions), self.max_steps)

    def _png(self) -> bytes | None:
        data_url = str(getattr(self.frame.rendered_frame, "data_url", "") or "")
        prefix = "data:image/png;base64,"
        return base64.b64decode(data_url[len(prefix):]) if data_url.startswith(prefix) else None

    def _save_picture(self) -> None:
        png = self._png()
        if png is not None:
            (self.workspace / "frame.png").write_bytes(png)
            (self.frames / f"{len(self.actions):03d}.png").write_bytes(png)

    def _record(self, record: dict) -> None:
        with (self.output / "transitions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")

    def release(self) -> None:
        """Record the move that reached the level target (its after-frame is the next level) once play is over."""
        if self._withheld is not None:
            record, png = self._withheld
            self._withheld = None
            self._record(record)
            if png is not None:
                (self.frames / f"{record['action_index']:03d}.png").write_bytes(png)

    # -- commands ---------------------------------------------------------------------
    def handle(self, command: str, action: str) -> tuple[bool, str]:
        if self.finished or self.closed:
            return False, f"The game session is over ({self.reason}). No more actions."
        try:
            game_action = GameAction[action.strip().upper()]
        except KeyError:
            return False, f"Unknown action {action!r}.\n{self._status()}"
        if game_action is GameAction.RESET:
            return self._act("RESET", self.env.reset)
        if self.frame.available_actions and game_action not in self.frame.available_actions:
            return False, f"{game_action.name} is not available.\n{self._status()}"
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
        if self.level_target_reached:
            self._withheld = (record, self._png())  # written by release(), after the session
        else:
            self._record(record)
            self._save_picture()
        self.snapshots.after_action(len(self.actions), before.levels_completed, self.frame.levels_completed)
        # Mirror the agent's notes so the run page shows them while it plays (as baseline+ does).
        if (self.workspace / "notes").is_dir():
            shutil.copytree(self.workspace / "notes", self.output / "workspace" / "notes", dirs_exist_ok=True)
        if self.level_target_reached:
            return True, (f"{name}: LEVEL COMPLETED ({self.frame.levels_completed}/{self.frame.win_levels}). "
                          "Level target reached; the game is over.")
        last = baseline_prompt.last_action(name, before.levels_completed, self.frame)
        return True, baseline_prompt.observation(self.frame, len(self.actions), self.max_steps, last)

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
         max_wall_seconds: float, harness_dir: Path | None, notes: bool = False, max_turns: int = 40,
         stop_after_levels: int = 0, start_level: int = 1) -> dict:
    """``env`` already opens at ``start_level``; ``stop_after_levels`` counts from it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="agent-player-"))
    if harness_dir is not None:
        shutil.copytree(harness_dir, workspace, dirs_exist_ok=True)
    server = GameServer(env, workspace, output_dir, max_steps, max_wall_seconds,
                        levels.stop_target(start_level, stop_after_levels)).start()

    def open_session(turn_number: int = 0):
        new = create_session(harness)
        new.game_tools = baseline_prompt.game_tools("agent", new, str(server.script))
        new.start(workspace, baseline_prompt.system_prompt("agent", bool(new.game_tools), str(server.script)), model,
                  effort, "player", output_dir, provider=provider)
        new.turn_number = turn_number  # raw/turn-<n>.jsonl keeps counting across sessions
        return new

    def status() -> dict:
        f = server.frame
        return {"levels": f.levels_completed, "total": f.win_levels, "left": max_steps - len(server.actions),
                "budget": max_steps}

    session = None
    turns, idle, error, failed_in_a_row = 0, 0, "", 0
    failed_turns: list[dict] = []
    try:
        session = open_session()
        instruction = baseline_prompt.first_message(max_steps, start_level, server.frame)
        while not server.finished and turns < max_turns and idle < IDLE_TURNS:
            used = len(server.actions)
            remaining = None if server.deadline is None else max(1.0, server.deadline - time.monotonic())
            result = _turn(session, instruction, remaining)
            turns += 1
            if result.error and not result.timed_out and not _worked(result):
                failed_in_a_row += 1
                restart = any(word in result.error.lower() for word in SESSION_ENDED)
                failed_turns.append({"turn": turns, "action_count": len(server.actions), "error": result.error,
                                     "new_session": restart and failed_in_a_row < FAILED_TURNS})
                if failed_in_a_row >= FAILED_TURNS:
                    raise RuntimeError(f"{harness} turn {turns} failed ({failed_in_a_row} in a row): {result.error}")
                if restart:
                    session.close()
                    if (output_dir / "session.json").is_file():  # keep the ended session's manifest
                        (output_dir / "session.json").replace(output_dir / f"session-{turns}.json")
                    session = open_session(session.turn_number)
                    instruction = RESTART_PROMPT.format(**status(), observation=server._status())
                else:
                    instruction = FAILED_PROMPT.format(**status())
                continue
            failed_in_a_row = 0
            idle = idle + 1 if len(server.actions) == used else 0
            instruction = CONTINUE_PROMPT.format(**status())
        reason = server.reason if server.finished else ("agent_idle" if idle >= IDLE_TURNS else "turn_budget_exhausted")
        # Missing reports leave the rollout's score intact; the coach then sees no world_model.md.
        server.closed = True
        _turn(session, baseline_prompt.REPORT_PROMPT.format(reason=reason, levels=server.frame.levels_completed,
                                                            total=server.frame.win_levels), 600)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        reason = "error"
    finally:
        server.stop()
        if session is not None:
            session.close()
        server.release()
        for name in (world_model.NAME, "solver.py"):
            if (workspace / name).is_file():
                shutil.copyfile(workspace / name, output_dir / name)
        server.snapshots.final()
        shutil.copytree(workspace, output_dir / "workspace", dirs_exist_ok=True)
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(server.home, ignore_errors=True)
    result = {"status": "error" if error else "completed", "reason": reason, "error": error or None,
              "solved": server.solved, "actions": server.actions, "action_count": len(server.actions),
              "agent_turns": turns, "final_state": getattr(server.frame.state, "value", str(server.frame.state)),
              "levels_completed": server.frame.levels_completed, "win_levels": server.frame.win_levels,
              "stop_after_levels": stop_after_levels or None, "failed_turns": failed_turns,
              "world_model": str(output_dir / "world_model.md") if (output_dir / "world_model.md").is_file() else None,
              "solver": str(output_dir / "solver.py") if (output_dir / "solver.py").is_file() else None,
              **levels.result_fields(output_dir / "transitions.jsonl", getattr(env, "game_id", ""), start_level,
                                     stop_after_levels)}
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
    parser.add_argument("--harness-dir", type=Path,
                        help="Files placed in the folder before the session (Harness² harness, Baseline start folder).")
    parser.add_argument("--start", default="", help="The Baseline start folder's name, recorded in run_config.json.")
    parser.add_argument("--start-level", type=int, default=1,
                        help="Open the game at this level (1-based, message screens not counted).")
    parser.add_argument("--stop-after-levels", type=int, default=0,
                        help="End the game once this many levels are completed, counted from the start level; "
                             "the next level stays unseen.")
    parser.add_argument("--notes", action="store_true",
                        help="Recorded only: since 2 Nov 2026 the shared baseline prompt always offers the folder for notes.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.start_level < 1:
        parser.error("--start-level must be 1 or more")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "run_config.json").write_text(json.dumps({
        "driver": "agent", "notes": args.notes, "condition": "baseline-plus" if args.notes else "baseline",
        "harness": args.harness,
        "provider": args.provider, "model": args.model, "reasoning_effort": args.effort, "game_id": args.game_id,
        "backend_url": args.backend_url, "max_steps": args.max_steps, "max_wall_seconds": args.max_wall_seconds,
        "start": args.start or None, "stop_after_levels": args.stop_after_levels or None,
        "start_level": args.start_level,
    }, indent=2), encoding="utf-8")
    try:  # a level beyond the game's last one, or a game service without start levels
        env = ArcadeEnv(game_id=args.game_id, backend_url=args.backend_url, start_level=args.start_level)
        result = play(env, output, harness=args.harness, model=args.model, effort=args.effort,
                      provider=args.provider, max_steps=args.max_steps, max_wall_seconds=args.max_wall_seconds,
                      harness_dir=args.harness_dir, notes=args.notes, stop_after_levels=args.stop_after_levels,
                      start_level=args.start_level)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(f"levels_completed={result['levels_completed']} actions={result['action_count']} reason={result['reason']}")


if __name__ == "__main__":
    main()
