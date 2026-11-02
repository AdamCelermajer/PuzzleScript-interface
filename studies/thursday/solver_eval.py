"""Plays a run's end-of-run solver.py against the real game, one level at a time.

For each level k, a fresh game session first replays the run's own recorded actions up to the
start of level k. Tile ids are assigned per session in order of first appearance
(puzzlescript_interface/runtime/rendered_frame.js), so this gives the session exactly the ids the
run saw, which the solver was written against. A level the run never reached is reached by
playing the optimal solutions of the levels in between (prefix "run+optimal"); its new tiles then
get ids in that order. Then solver.next_action(grid, levels_completed) is called, in its own
process with a per-call timeout, until the level is completed or --max-steps actions are used.
For a run that stopped after level 3, level 4 is the held-out level.

Needs the local game service (npm run local); this script never starts or restarts it.

    python -m studies.thursday.solver_eval RUN [RUN ...] [--levels 1 2 3 4] [--max-steps 300]
"""
from __future__ import annotations

import argparse
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from client.arc.arcade_env import ArcadeEnv
from client.arc.types import GameAction
from client.engine.utils import last_grid
from studies.thursday.metrics import OUT, find_runs
from studies.thursday.modality import ROOT, load_transitions, optimum, optimum_moves

GAME_ID = "ps_modality-v1"
WORKER = Path(__file__).with_name("solver_worker.py")
ACTIONS = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7"}


def service_up(backend: str) -> bool:
    try:
        with urllib.request.urlopen(f"{backend}/api/games", timeout=5) as response:
            return response.status == 200
    except OSError:
        return False


def act(env: ArcadeEnv, action: str):
    return env.reset() if action == "RESET" else env.step(GameAction[action])


class Solver:
    """solver.py in a subprocess; next_action calls time out instead of hanging the evaluation."""

    def __init__(self, folder: Path) -> None:
        self.stderr = (folder / "solver_stderr.txt").open("w", encoding="utf-8")
        self.process = subprocess.Popen([sys.executable, "-I", str(WORKER), str(folder / "solver.py")], cwd=folder,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, encoding="utf-8", bufsize=1)
        self.replies: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.process.stdout:
            self.replies.put(line)

    def next_action(self, grid: list[list[int]], levels: int, timeout: float) -> dict:
        try:
            self.process.stdin.write(json.dumps({"grid": grid, "levels": levels}) + "\n")
            self.process.stdin.flush()
            return json.loads(self.replies.get(timeout=timeout))
        except queue.Empty:
            return {"timeout": True}
        except (OSError, ValueError) as exc:
            return {"error": f"worker: {type(exc).__name__}: {exc}"}

    def close(self) -> None:
        self.process.kill()
        self.process.wait()
        self.stderr.close()


def solver_folder(run: Path) -> Path | None:
    """A scratch copy of the run's working folder (the solver may import its own helpers), without game.py."""
    solver = run / "solver.py"
    if not solver.is_file():
        return None
    folder = Path(tempfile.mkdtemp(prefix="solver-eval-"))
    if (run / "workspace").is_dir():
        shutil.copytree(run / "workspace", folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".game", "game.py", "frame.png"))
    shutil.copyfile(solver, folder / "solver.py")
    return folder


def evaluate_level(run: Path, folder: Path, k: int, backend: str, max_steps: int, timeout: float) -> dict:
    transitions = load_transitions(run)
    actions = [t["action"] for t in transitions]
    level_at = [t["action_index"] for t in transitions
                if t["after"]["levels_completed"] > t["before"]["levels_completed"]]
    if k - 1 <= len(level_at):
        prefix, source = (actions[:level_at[k - 2]] if k > 1 else []), "run"
    else:
        prefix = actions[:level_at[-1]] if level_at else []
        prefix += [a for index in range(len(level_at), k - 1) for a in optimum(index)]
        source = "run+optimal"
    env = ArcadeEnv(game_id=GAME_ID, backend_url=backend)
    frame = env.reset()
    for action in prefix:
        frame = act(env, action)
    row = {"level": k, "prefix": source, "prefix_actions": len(prefix), "optimum": optimum_moves()[k - 1],
           "solved": False, "steps": 0, "ended": "", "detail": ""}
    if frame.levels_completed != k - 1:
        row["ended"] = f"prefix reached {frame.levels_completed} levels, not {k - 1}"
        return row
    if source == "run" and transitions:
        recorded = transitions[level_at[k - 2] - 1]["after"]["grid"] if k > 1 else transitions[0]["before"]["grid"]
        row["ids_match"] = last_grid(frame.frame) == recorded
    solver = Solver(folder)
    try:
        while row["steps"] < max_steps:
            reply = solver.next_action(last_grid(frame.frame), frame.levels_completed, timeout)
            if reply.get("timeout"):
                row["ended"] = f"timeout ({timeout:g} s per call)"
                break
            if "error" in reply:
                row["ended"], row["detail"] = "solver error", reply["error"][:200]
                break
            action = str(reply.get("action", "")).strip().upper()
            if action not in ACTIONS and action != "RESET":
                row["ended"], row["detail"] = "invalid action", action[:40]
                break
            frame = act(env, action)
            row["steps"] += 1
            if frame.levels_completed >= k:
                row["solved"], row["ended"] = True, "solved"
                break
        else:
            row["ended"] = f"step limit {max_steps}"
    finally:
        solver.close()
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3, 4])
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--timeout", type=float, default=120, help="seconds per next_action call")
    parser.add_argument("--out", type=Path, default=OUT / "solver_eval")
    args = parser.parse_args(argv)
    if not service_up(args.backend_url):
        print(f"The game service at {args.backend_url} is not answering. Start it yourself (npm run local); "
              "this script does not start or restart it.")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    print("| run | level | prefix | ids match | solved | steps | optimum | ended |\n|---|---|---|---|---|---|---|---|")
    for run in find_runs(args.paths):
        run = run.resolve()
        folder = solver_folder(run)
        if folder is None:
            print(f"| {run.name} | – | – | – | – | – | – | no solver.py |")
            continue
        rows = []
        try:
            for k in args.levels:
                row = evaluate_level(run, folder, k, args.backend_url, args.max_steps, args.timeout)
                rows.append(row)
                print(f"| {run.name} | {k} | {row['prefix']} ({row['prefix_actions']}) | {row.get('ids_match', '–')} | "
                      f"{'yes' if row['solved'] else 'no'} | {row['steps']} | {row['optimum']} | "
                      f"{row['ended']}{(': ' + row['detail']) if row['detail'] else ''} |")
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        name = (run.relative_to(ROOT) if run.is_relative_to(ROOT) else run).as_posix().replace("/", "__")
        (args.out / f"{name}.json").write_text(json.dumps({"run": run.as_posix(), "levels": rows}, indent=2),
                                               encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
