from __future__ import annotations

import copy
import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


ACTIVE_STATUSES = {"starting", "running", "stopping"}
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GAMES_DIR = REPO_ROOT / "puzzlescript_interface" / "games"
DEFAULT_WORKER = Path(__file__).resolve().parent / "stateful_solve_game.js"


def _display_title(game_id: str) -> str:
    stem = game_id.removeprefix("ps_")
    if "-v" in stem:
        stem = stem.rsplit("-v", 1)[0]
    return stem.replace("_", "-")


class OptimalPathRun:
    def __init__(self, run_id: str, config: dict[str, Any]) -> None:
        self.run_id = run_id
        self.config = dict(config)
        self.status = "starting"
        self.error = ""
        self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.finished_at = ""
        self.progress: dict[str, Any] = {
            "elapsedMs": 0,
            "timeoutMs": int(config["timeout_seconds"] * 1000),
            "timeFraction": 0,
            "expandedStates": 0,
            "uniqueStates": 1,
            "frontierStates": 1,
            "transitions": 0,
            "maxDepthDiscovered": 0,
            "currentDepth": 0,
            "transitionsPerSecond": 0,
            "maxStates": int(config["max_states"]),
            "stateFraction": 0,
        }
        self.result: dict[str, Any] | None = None
        self.replay: list[dict[str, Any]] = []
        self.events: list[str] = []
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self._lock = threading.RLock()

    def push_event(self, message: str) -> None:
        cleaned = " ".join(str(message).split())
        if not cleaned:
            return
        with self._lock:
            self.events.append(cleaned)
            self.events = self.events[-40:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "status": self.status,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "config": dict(self.config),
                "progress": dict(self.progress),
                "result": copy.deepcopy(self.result),
                "replay": copy.deepcopy(self.replay),
                "events": list(self.events),
            }


class OptimalPathManager:
    def __init__(
        self,
        *,
        games_dir: str | Path = DEFAULT_GAMES_DIR,
        worker_path: str | Path = DEFAULT_WORKER,
        node_executable: str = "node",
    ) -> None:
        self.games_dir = Path(games_dir).resolve()
        self.worker_path = Path(worker_path).resolve()
        self.node_executable = node_executable
        self.runs: dict[str, OptimalPathRun] = {}
        self.current_run_id = ""
        self._lock = threading.RLock()

    def games(self) -> list[dict[str, str]]:
        return [
            {"game_id": path.parent.name, "title": _display_title(path.parent.name)}
            for path in sorted(self.games_dir.glob("*/script.txt"))
        ]

    def start(self, config: dict[str, Any]) -> OptimalPathRun:
        game_path = self._game_path(config["game_id"])
        normalized = {
            **config,
            "game_id": game_path.parent.name,
            "game_path": str(game_path),
            "search_mode": "semantic",
            "whole_game": True,
        }
        with self._lock:
            current = self.runs.get(self.current_run_id)
            if current is not None and current.status in ACTIVE_STATUSES:
                raise RuntimeError("An optimal-path search is already active")
            run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
            run = OptimalPathRun(run_id, normalized)
            self.runs[run_id] = run
            self.current_run_id = run_id
            run.thread = threading.Thread(
                target=self._execute,
                args=(run,),
                daemon=True,
                name=f"optimal-path-{run_id}",
            )
            run.thread.start()
            return run

    def current(self) -> OptimalPathRun | None:
        with self._lock:
            return self.runs.get(self.current_run_id)

    def get(self, run_id: str) -> OptimalPathRun:
        with self._lock:
            try:
                return self.runs[run_id]
            except KeyError as exc:
                raise KeyError("Optimal-path run not found") from exc

    def stop(self, run_id: str) -> OptimalPathRun:
        run = self.get(run_id)
        run.stop_event.set()
        with run._lock:
            if run.status in {"starting", "running"}:
                run.status = "stopping"
                run.push_event("Stop requested.")
            process = run.process
        if process is not None and process.poll() is None:
            process.terminate()
        return run

    def _game_path(self, game_id: str) -> Path:
        candidate = (self.games_dir / game_id / "script.txt").resolve()
        if candidate.parent.parent != self.games_dir or not candidate.is_file():
            raise KeyError(f"Unknown PuzzleScript game: {game_id}")
        return candidate

    def _command(self, run: OptimalPathRun) -> list[str]:
        return [
            self.node_executable,
            "--max-old-space-size=1536",
            str(self.worker_path),
            "--gamePath",
            run.config["game_path"],
            "--gameId",
            run.config["game_id"],
            "--timeoutMs",
            str(int(run.config["timeout_seconds"] * 1000)),
            "--maxStates",
            str(run.config["max_states"]),
            "--visitedMode",
            "semantic",
            "--progressJsonl",
            "true",
            "--renderReplay",
            "true",
            "--wholeGame",
            "true",
        ]

    def _execute(self, run: OptimalPathRun) -> None:
        process: subprocess.Popen[str] | None = None
        try:
            run.status = "running"
            run.push_event("Started semantic breadth-first search.")
            process = subprocess.Popen(
                self._command(run),
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            with run._lock:
                run.process = process
            if run.stop_event.is_set() and process.poll() is None:
                process.terminate()

            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    run.push_event(line[-300:])
                    continue
                if payload.get("kind") == "progress":
                    with run._lock:
                        run.progress.update(payload.get("progress") or {})
                elif payload.get("kind") == "result":
                    self._accept_result(run, payload.get("result") or {})

            return_code = process.wait()
            assert process.stderr is not None
            stderr = process.stderr.read().strip()
            if run.stop_event.is_set():
                run.status = "cancelled"
                run.push_event("Search cancelled.")
            elif return_code != 0:
                raise RuntimeError(stderr or f"Solver exited with code {return_code}")
            elif run.result is None:
                raise RuntimeError("Solver ended without returning a result")
        except Exception as exc:
            if run.stop_event.is_set():
                run.status = "cancelled"
            else:
                run.status = "failed"
                run.error = str(exc)
                run.push_event(f"Search failed: {exc}")
        finally:
            if process is not None:
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
            with run._lock:
                run.process = None
                run.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")

    def _accept_result(self, run: OptimalPathRun, result: dict[str, Any]) -> None:
        replay = result.pop("replay", [])
        with run._lock:
            run.result = result
            run.replay = replay
            run.progress.update({
                "elapsedMs": result.get("searchMs", run.progress["elapsedMs"]),
                "timeFraction": min(
                    1,
                    result.get("searchMs", 0) / run.progress["timeoutMs"],
                ),
                "expandedStates": result.get("expandedStates", 0),
                "uniqueStates": result.get("uniqueStates", 0),
                "frontierStates": result.get("frontierStates", 0),
                "transitions": result.get("transitions", 0),
                "maxDepthDiscovered": result.get("maxDepthDiscovered", 0),
                "transitionsPerSecond": result.get("searchTransitionsPerSecond", 0),
            })
            if result.get("solved"):
                run.status = "solved"
                run.push_event(
                    f"Solved all {result.get('totalLevels', 0)} levels in "
                    f"{result.get('solutionDepth', 0)} actions; replay verified."
                )
            else:
                run.status = "not_found"
                run.push_event(f"Search ended: {result.get('status', 'not_found')}.")
