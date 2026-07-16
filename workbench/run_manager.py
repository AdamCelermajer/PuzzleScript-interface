from __future__ import annotations

import os
import json
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import requests

from client.arc.arcade_env import ArcadeEnv
from client.engine.architecture import EngineArchitecture, game_rules_path
from client.engine.llm_client import Config, LlmClient
from client.engine.memory import ActionEdge, EngineMemory, StateNode
from client.engine.prompts import PromptStore
from client.engine.utils import last_grid
from client.runtime.runner import RuleReasoningLoop
from workbench.models import DEFAULT_MODEL, PROVIDER_ID, validate_model_selection


ACTIVE_STATUSES = {"starting", "running", "stopping"}
ARTIFACT_NAMES = (
    "timeline.jsonl",
    "rules.json",
    "natural_rules.json",
    "rule_failures.jsonl",
    "rule_attempt.jsonl",
    "llm_attempt.jsonl",
    "legend.json",
    "run_config.json",
    "prompts.json",
)


def default_rules_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "client" / "rules"


def public_error_message(exc: Exception) -> str:
    message = str(exc)
    if "LLM provider error" in message:
        status = re.search(r"(?:Error code:|status(?: code)?)\s*(\d{3})", message)
        suffix = f" ({status.group(1)})" if status else ""
        return (
            f"LLM provider error{suffix}. "
            "Check the server-side provider account and configuration."
        )
    return message


class WorkbenchRun:
    def __init__(self, run_id: str, config: dict[str, Any]) -> None:
        self.run_id = run_id
        self.config = config
        self.status = "starting"
        self.reason = ""
        self.error = ""
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.finished_at = ""
        self.events: list[str] = []
        self.frame_data: Any | None = None
        self.render_step = 0
        self.engine: EngineArchitecture | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._lock = threading.RLock()

    def push_event(self, message: str) -> None:
        cleaned = " ".join(str(message).split())
        if not cleaned:
            return
        with self._lock:
            self.events.append(cleaned)
            self.events = self.events[-250:]

    def render(self, steps: int, frame_data: Any) -> None:
        with self._lock:
            self.render_step = int(steps)
            self.frame_data = frame_data

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            engine = self.engine
            frame = self._frame_snapshot()
            natural_rules = []
            logical_rules = []
            failures = []
            rule_attempts = []
            legend = {}
            timeline = []
            task_goal = ""
            subgoal = ""
            active_plan = None
            decision = None
            if engine is not None:
                natural_rules = [
                    rule.to_data() for rule in engine.natural_rule_library.all()
                ]
                logical_rules = [
                    rule.to_data()
                    for rule in engine.logical_rulebook.generalized_rules
                ]
                failures = engine.failure_log.recent(50)
                rule_attempt_log = getattr(engine, "rule_attempt_log", None)
                if rule_attempt_log is not None:
                    rule_attempts = rule_attempt_log.recent(50)
                legend_store = getattr(engine, "legend_store", None)
                if legend_store is not None:
                    legend = {
                        str(key): value for key, value in legend_store.all().items()
                    }
                timeline = [
                    record.to_data()
                    for record in engine.memory.recent_transitions(50)
                ]
                goal = engine.goal_manager.game_goal
                current_subgoal = engine.goal_manager.subgoal
                task_goal = goal.description if goal else ""
                subgoal = current_subgoal.description if current_subgoal else ""
                selector = engine.action_selector
                if selector.active_plan is not None:
                    plan = selector.active_plan
                    active_plan = {
                        "actions": [action.name for action in plan.actions],
                        "next_index": plan.index,
                        "remaining": [
                            action.name for action in plan.actions[plan.index :]
                        ],
                        "exploratory": plan.exploratory,
                        "goal": plan.goal.description,
                    }
                if selector.last_decision is not None:
                    item = selector.last_decision
                    decision = {
                        "action": item.action.name,
                        "source": item.source,
                        "plan": [action.name for action in item.plan],
                        "remaining_actions": [
                            action.name for action in item.remaining_actions
                        ],
                        "subgoal": item.subgoal,
                        "exploratory": item.exploratory,
                        "prediction_count": len(item.predictions),
                    }
            return {
                "run_id": self.run_id,
                "status": self.status,
                "reason": self.reason,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "config": dict(self.config),
                "progress": {
                    "step": self.render_step,
                    "state": frame.get("state", "NOT_STARTED"),
                    "levels_completed": frame.get("levels_completed", 0),
                    "win_levels": frame.get("win_levels", 0),
                    "last_action": frame.get("last_action", ""),
                },
                "frame": frame,
                "reasoning": {
                    "task_goal": task_goal,
                    "subgoal": subgoal,
                    "active_plan": active_plan,
                    "decision": decision,
                },
                "natural_rules": natural_rules,
                "logical_rules": logical_rules,
                "failures": failures,
                "rule_attempts": rule_attempts,
                "legend": legend,
                "timeline": timeline,
                "events": list(self.events),
            }

    def _frame_snapshot(self) -> dict[str, Any]:
        frame_data = self.frame_data
        if frame_data is None:
            return {
                "grid": [],
                "state": "NOT_STARTED",
                "levels_completed": 0,
                "win_levels": 0,
                "last_action": "",
                "rendered_frame": None,
            }
        frames = getattr(frame_data, "frame", []) or []
        grid = last_grid(frames)
        if hasattr(grid, "tolist"):
            grid = grid.tolist()
        grid = [
            [int(value) for value in (row.tolist() if hasattr(row, "tolist") else row)]
            for row in grid
        ]
        state = getattr(frame_data, "state", "")
        state_name = getattr(state, "name", str(state or "UNKNOWN"))
        action_input = getattr(frame_data, "action_input", None)
        action_id = getattr(action_input, "id", None) if action_input else None
        if action_id is None and action_input is not None:
            action_id = getattr(action_input, "action", None)
        last_action = getattr(action_id, "name", str(action_id or ""))
        rendered = getattr(frame_data, "rendered_frame", None)
        if isinstance(rendered, dict):
            rendered_snapshot = {
                "mime_type": rendered.get("mime_type", ""),
                "data_url": rendered.get("data_url", ""),
                "width": rendered.get("width"),
                "height": rendered.get("height"),
            }
        elif rendered is not None:
            rendered_snapshot = {
                "mime_type": getattr(rendered, "mime_type", ""),
                "data_url": getattr(rendered, "data_url", ""),
                "width": getattr(rendered, "width", None),
                "height": getattr(rendered, "height", None),
            }
        else:
            rendered_snapshot = None
        return {
            "grid": grid,
            "state": state_name,
            "levels_completed": int(getattr(frame_data, "levels_completed", 0)),
            "win_levels": int(getattr(frame_data, "win_levels", 0)),
            "last_action": last_action,
            "rendered_frame": rendered_snapshot,
        }


class RunManager:
    def __init__(
        self,
        *,
        rules_dir: str | Path | None = None,
        env_factory: Callable[..., object] = ArcadeEnv,
        llm_factory: Callable[..., object] = LlmClient,
        engine_factory: Callable[..., EngineArchitecture] = EngineArchitecture.from_config,
        loop_factory: Callable[..., RuleReasoningLoop] = RuleReasoningLoop,
        prompt_store: PromptStore | None = None,
    ) -> None:
        self.rules_dir = Path(rules_dir or default_rules_dir())
        self.env_factory = env_factory
        self.llm_factory = llm_factory
        self.engine_factory = engine_factory
        self.loop_factory = loop_factory
        self.prompt_store = prompt_store or PromptStore()
        self.runs: dict[str, WorkbenchRun] = {}
        self.current_run_id = ""
        self._lock = threading.RLock()

    def start(self, config: dict[str, Any]) -> WorkbenchRun:
        config = {
            "provider": PROVIDER_ID,
            "model": DEFAULT_MODEL,
            "reasoning_effort": "",
            **config,
        }
        config["prompt_versions"] = self.prompt_store.snapshot()["versions"]
        if config["provider"] != PROVIDER_ID:
            raise ValueError("provider must be openrouter")
        validate_model_selection(config["model"], config["reasoning_effort"])
        with self._lock:
            current = self.runs.get(self.current_run_id)
            if current is not None and current.status in ACTIVE_STATUSES:
                raise RuntimeError("A workbench run is already active")
            if config["memory_mode"] == "fresh":
                self._archive_current(config["game_id"])
            run_id = (
                datetime.now().strftime("%Y%m%dT%H%M%S")
                + "-"
                + uuid4().hex[:8]
            )
            run = WorkbenchRun(run_id, config)
            self.runs[run_id] = run
            self.current_run_id = run_id
            run.thread = threading.Thread(
                target=self._execute,
                args=(run,),
                daemon=True,
                name=f"workbench-{run_id}",
            )
            run.thread.start()
            return run

    def get(self, run_id: str) -> WorkbenchRun:
        with self._lock:
            try:
                return self.runs[run_id]
            except KeyError as exc:
                raise KeyError("Workbench run not found") from exc

    def current(self) -> WorkbenchRun | None:
        with self._lock:
            return self.runs.get(self.current_run_id)

    def has_active_run(self) -> bool:
        with self._lock:
            current = self.current()
            return current is not None and current.status in ACTIVE_STATUSES

    def stop(self, run_id: str) -> WorkbenchRun:
        run = self.get(run_id)
        run.stop_event.set()
        if run.status in {"starting", "running"}:
            run.status = "stopping"
            run.push_event("Stop requested; waiting for the current operation.")
        return run

    def local_games(self, base_url: str = "http://127.0.0.1:8000") -> list[dict]:
        response = requests.get(f"{base_url}/api/games", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _execute(self, run: WorkbenchRun) -> None:
        try:
            backend_url = (
                "http://127.0.0.1:8000"
                if run.config["backend"] == "puzzlescript"
                else "https://three.arcprize.org"
            )
            cfg = Config(
                game=run.config["game_id"],
                model=run.config["model"],
                reasoning_effort=run.config["reasoning_effort"],
                max_steps=run.config["max_steps"],
                server_url=backend_url,
                rules_dir=str(self.rules_dir),
                provide_legend=run.config.get("provide_legend", True),
                provide_end_goal=run.config.get("provide_end_goal", True),
                end_goal=run.config.get("end_goal", "complete the level"),
                prompt_dir=str(self.prompt_store.root),
                persist_llm_attempts=True,
            )
            config_path = game_rules_path(self.rules_dir, cfg.game) / "run_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(run.config, indent=2) + "\n",
                encoding="utf-8",
            )
            (config_path.parent / "prompts.json").write_text(
                json.dumps(self.prompt_store.snapshot(), indent=2) + "\n",
                encoding="utf-8",
            )
            env = self.env_factory(
                game_id=cfg.game,
                backend_url=backend_url,
                renderer=run.render,
            )
            llm = self.llm_factory(cfg, event_sink=run.push_event)
            engine = self.engine_factory(cfg, llm, event_sink=run.push_event)
            run.engine = engine
            loop = self.loop_factory(
                env,
                engine,
                event_sink=run.push_event,
                stop_event=run.stop_event,
                sleep_fn=lambda _seconds: time.sleep(0.15),
            )
            run.status = "running"
            result = loop.run(max_steps=cfg.max_steps, game_id=cfg.game)
            run.status = result.status
            run.reason = result.reason
        except Exception as exc:
            public_error = public_error_message(exc)
            run.status = "failed"
            run.reason = "unhandled_error"
            run.error = public_error
            run.push_event(f"Run failed: {public_error}")
        finally:
            run.finished_at = datetime.now().isoformat(timespec="seconds")

    def _archive_current(self, game_id: str) -> Path | None:
        base_path = game_rules_path(self.rules_dir, game_id)
        existing = [base_path / name for name in ARTIFACT_NAMES if (base_path / name).exists()]
        if not existing:
            return None
        archive = (
            base_path
            / "archive"
            / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}"
        )
        archive.mkdir(parents=True, exist_ok=False)
        for path in existing:
            shutil.move(str(path), archive / path.name)
        return archive

    def list_artifacts(self, game_id: str) -> list[dict[str, Any]]:
        base_path = game_rules_path(self.rules_dir, game_id)
        artifacts = []
        current_files = [name for name in ARTIFACT_NAMES if (base_path / name).exists()]
        if current_files:
            artifacts.append(self._artifact_summary("current", base_path, current_files))
        archive_root = base_path / "archive"
        if archive_root.exists():
            archive_dirs = sorted(
                (item for item in archive_root.iterdir() if item.is_dir()),
                key=lambda item: item.name,
                reverse=True,
            )
            for path in archive_dirs:
                files = [name for name in ARTIFACT_NAMES if (path / name).exists()]
                artifacts.append(self._artifact_summary(path.name, path, files))
        return artifacts

    def artifact_replay(self, game_id: str, artifact_id: str) -> dict[str, Any]:
        path = self._artifact_path(game_id, artifact_id)
        if not path.exists():
            raise KeyError("Artifact run not found")
        memory = EngineMemory(path / "timeline.jsonl")
        inbound_edges = {
            item.after_id: item
            for item in memory.timeline
            if isinstance(item, ActionEdge)
        }
        inbound_transitions = {
            item.after_id: f"T{int(item.id[1:]):06d}"
            for item in memory.timeline
            if isinstance(item, ActionEdge)
        }

        def prediction_payload(state, edge: ActionEdge | None) -> dict[str, Any]:
            if edge is None or not edge.prediction_recorded:
                return {"recorded": False, "result": "unavailable"}
            exact_match = state in edge.predictions
            displayed = None
            differences = []
            if edge.predictions:
                displayed = (
                    next(item for item in edge.predictions if item == state)
                    if exact_match
                    else min(
                        edge.predictions,
                        key=lambda item: len(item.changed_cells(state)),
                    )
                )
                differences = list(displayed.changed_cells(state))
            return {
                "recorded": True,
                "result": (
                    "exact_match"
                    if exact_match
                    else "no_prediction"
                    if not edge.predictions
                    else "mismatch"
                ),
                "states": [item.to_data() for item in edge.predictions],
                "displayed_state": displayed.to_data() if displayed else None,
                "rule_ids": list(edge.prediction_rule_ids),
                "decision_source": edge.decision_source,
                "closest_cell_differences": differences,
            }

        frames = [
            {
                "id": item.id,
                "action": (
                    inbound_edges[item.id].action.name
                    if item.id in inbound_edges
                    else "RESET"
                ),
                "transition_id": inbound_transitions.get(item.id, ""),
                "state": item.state.to_data(),
                "prediction": prediction_payload(item.state, inbound_edges.get(item.id)),
            }
            for item in memory.timeline
            if isinstance(item, StateNode)
        ]
        natural_rule_data = self._read_json(path / "natural_rules.json", {})
        logical_rule_data = self._read_json(path / "rules.json", {})
        return {
            "id": artifact_id,
            "game_id": game_id,
            "frames": frames,
            "legend": self._read_json(path / "legend.json", {}),
            "config": self._read_json(path / "run_config.json", {}),
            "natural_rules": natural_rule_data.get("rules", []),
            "logical_rules": logical_rule_data.get("rules", []),
            "rule_attempts": self._read_jsonl(path / "rule_attempt.jsonl"),
            "failures": self._read_jsonl(path / "rule_failures.jsonl"),
        }

    def delete_artifact(self, game_id: str, artifact_id: str) -> None:
        if artifact_id == "current":
            raise ValueError("Current artifacts cannot be deleted; start Fresh to archive them")
        if self.has_active_run():
            raise RuntimeError("Stop the active run before deleting an archive")
        path = self._artifact_path(game_id, artifact_id)
        if not path.exists():
            raise KeyError("Artifact run not found")
        shutil.rmtree(path)

    def _artifact_path(self, game_id: str, artifact_id: str) -> Path:
        base_path = game_rules_path(self.rules_dir, game_id)
        if artifact_id == "current":
            return base_path
        if (
            artifact_id in {".", ".."}
            or not re.fullmatch(r"[A-Za-z0-9._-]+", artifact_id)
        ):
            raise ValueError("Invalid artifact id")
        path = base_path / "archive" / artifact_id
        if path.parent.resolve() != (base_path / "archive").resolve():
            raise ValueError("Invalid artifact id")
        return path

    def _artifact_summary(
        self, artifact_id: str, path: Path, files: list[str]
    ) -> dict[str, Any]:
        memory = EngineMemory(path / "timeline.jsonl")
        return {
            "id": artifact_id,
            "label": "Current run" if artifact_id == "current" else artifact_id,
            "files": files,
            "frames": sum(
                isinstance(item, StateNode) for item in memory.timeline
            ),
            "transitions": len(memory.all()),
            "config": self._read_json(path / "run_config.json", {}),
        }

    def _read_json(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def health(self) -> dict[str, Any]:
        current = self.runs.get(self.current_run_id)
        return {
            "ok": True,
            "active_run_id": (
                current.run_id if current and current.status in ACTIVE_STATUSES else ""
            ),
            "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
            "arc_configured": bool(os.getenv("ARC_API_KEY")),
        }
