from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable, Protocol

from client.arc.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid


class AvoEnv(Protocol):
    def reset(self) -> FrameData: ...

    def step(self, action: GameAction) -> FrameData: ...


class AvoSession(Protocol):
    def next_plan(
        self,
        prompt: str,
        image_path: str | Path | None = None,
    ) -> dict[str, object]: ...

    def supervise(self, prompt: str) -> dict[str, str]: ...


@dataclass(frozen=True)
class AvoRunResult:
    status: str
    reason: str
    solved: bool
    actions: list[GameAction]
    decisions: int
    supervisor_calls: int
    output_dir: Path
    transcript_path: Path
    trajectory_path: Path
    final_frame: FrameData


@dataclass
class AvoAgentRunner:
    env: AvoEnv
    session: AvoSession
    output_dir: str | Path
    workspace_dir: str | Path | None = None
    max_steps: int = 100
    max_decisions: int | None = None
    max_batch_actions: int = 20
    supervise_after_stalls: int = 3
    use_visual: bool = False
    event_sink: Callable[[str], None] | None = None
    decision_sink: Callable[[dict], None] | None = None
    transition_sink: Callable[[dict], None] | None = None
    stop_event: Event | None = None
    actions: list[GameAction] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = Path(self.workspace_dir or self.output_dir / "workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.helpers_dir = self.workspace / "helpers"
        self.helpers_dir.mkdir(exist_ok=True)
        for helper_name in ("solver.py", "scratch.py"):
            helper_path = self.helpers_dir / helper_name
            if not helper_path.exists():
                helper_path.write_text(
                    "# AVO helper slot; the agent may replace this content.\n",
                    encoding="utf-8",
                )
        self.frames_dir = self.workspace / "frames"
        self.frames_dir.mkdir(exist_ok=True)
        self.transcript_path = self.output_dir / "transcript.jsonl"
        self.trajectory_path = self.workspace / "trajectory.jsonl"
        self.state_path = self.workspace / "current_state.json"
        self.knowledge_path = self.workspace / "KNOWLEDGE.md"
        self.working_path = self.workspace / "WORKING.md"
        if not self.knowledge_path.exists():
            self.knowledge_path.write_text(
                "# Durable game knowledge\n\nNo mechanics confirmed yet.\n",
                encoding="utf-8",
            )
        if not self.working_path.exists():
            self.working_path.write_text(
                "# Current-level working state\n\nNo plan yet.\n",
                encoding="utf-8",
            )
        if self.max_decisions is None:
            self.max_decisions = max(self.max_steps, self.max_steps * 2)
        if self.stop_event is None:
            self.stop_event = Event()

    def run(self) -> AvoRunResult:
        self._emit(f"AVO output: {self.output_dir}")
        frame = self.env.reset()
        self._write_state(frame, previous_batch=None)
        solved = self._is_solved(frame)
        decisions = 0
        supervisor_calls = 0
        consecutive_stalls = 0
        supervisor_advice = ""
        previous_batch: dict | None = None
        stopped = False

        while (
            not solved
            and len(self.actions) < self.max_steps
            and decisions < int(self.max_decisions or 0)
        ):
            if self.stop_event.is_set():
                stopped = True
                break

            if (
                self.supervise_after_stalls > 0
                and consecutive_stalls >= self.supervise_after_stalls
            ):
                review = self.session.supervise(self._supervisor_prompt())
                supervisor_calls += 1
                supervisor_advice = review.get("advice", "")
                self._append_transcript(
                    {
                        "type": "supervisor",
                        "timestamp": self._timestamp(),
                        "diagnosis": review.get("diagnosis", ""),
                        "advice": supervisor_advice,
                    }
                )
                self._emit(f"Supervisor: {supervisor_advice or review.get('diagnosis', '')}")
                consecutive_stalls = 0

            image_path = self._save_frame_image(frame, decisions)
            prompt = self._turn_prompt(
                frame,
                previous_batch=previous_batch,
                supervisor_advice=supervisor_advice,
                initial=(decisions == 0),
            )
            plan = self.session.next_plan(prompt, image_path=image_path)
            decisions += 1
            supervisor_advice = ""

            requested = [str(name).strip().upper() for name in plan.get("actions", [])]
            requested = requested[: max(1, self.max_batch_actions)]
            if self.decision_sink is not None:
                self.decision_sink(
                    {
                        "decision": decisions,
                        "actions": requested,
                        "prediction": plan.get("prediction", ""),
                        "note": plan.get("note", ""),
                        "confidence": plan.get("confidence", "low"),
                    }
                )
            self._emit(
                f"Decision {decisions}: {requested} "
                f"confidence={plan.get('confidence', 'low')}"
            )

            batch_result = self._execute_batch(frame, requested, plan)
            frame = batch_result["frame"]
            solved = self._is_solved(frame)
            executed = batch_result["transitions"]
            if executed and all(not item["changed"] for item in executed):
                consecutive_stalls += len(executed)
            elif executed:
                consecutive_stalls = 0
            else:
                consecutive_stalls += 1

            previous_batch = {
                "requested_actions": requested,
                "prediction": plan.get("prediction", ""),
                "transitions": [
                    self._transition_summary(transition) for transition in executed
                ],
                "error": batch_result.get("error", ""),
            }
            self._write_state(frame, previous_batch=previous_batch)
            self._append_transcript(
                {
                    "type": "decision",
                    "timestamp": self._timestamp(),
                    "decision": decisions,
                    "plan": plan,
                    "result": previous_batch,
                }
            )

        if stopped:
            status = "cancelled"
            reason = "stop_requested"
        elif solved:
            status = "completed"
            reason = "task_goal_reached"
        elif len(self.actions) >= self.max_steps:
            status = "completed"
            reason = "step_budget_exhausted"
        else:
            status = "completed"
            reason = "decision_budget_exhausted"

        self._emit(
            f"AVO finished: solved={solved} reason={reason} actions={len(self.actions)}"
        )
        return AvoRunResult(
            status=status,
            reason=reason,
            solved=solved,
            actions=list(self.actions),
            decisions=decisions,
            supervisor_calls=supervisor_calls,
            output_dir=self.output_dir,
            transcript_path=self.transcript_path,
            trajectory_path=self.trajectory_path,
            final_frame=frame,
        )

    def _execute_batch(
        self,
        frame: FrameData,
        requested: list[str],
        plan: dict[str, object],
    ) -> dict:
        transitions: list[dict] = []
        error = ""
        for action_name in requested:
            if len(self.actions) >= self.max_steps or self.stop_event.is_set():
                break
            try:
                action = GameAction[action_name]
            except KeyError:
                error = f"unsupported action {action_name}"
                break
            available = set(getattr(frame, "available_actions", []) or [])
            if action != GameAction.RESET and available and action not in available:
                error = f"action {action_name} is not currently available"
                break

            before_grid = last_grid(frame.frame)
            before_levels = frame.levels_completed
            before_state = frame.state
            next_frame = (
                self.env.reset()
                if action == GameAction.RESET
                else self.env.step(action)
            )
            after_grid = last_grid(next_frame.frame)
            transition = {
                "id": f"T{len(self.actions) + 1:06d}",
                "action": action.name,
                "before": {
                    "grid": before_grid,
                    "state": getattr(before_state, "value", str(before_state)),
                    "levels_completed": before_levels,
                },
                "after": {
                    "grid": after_grid,
                    "state": getattr(next_frame.state, "value", str(next_frame.state)),
                    "levels_completed": next_frame.levels_completed,
                },
                "changed": before_grid != after_grid,
                "diff": self._grid_diff(before_grid, after_grid),
                "prediction": str(plan.get("prediction", "")),
                "note": str(plan.get("note", "")),
            }
            self.actions.append(action)
            transitions.append(transition)
            self._append_trajectory(transition)
            if self.transition_sink is not None:
                self.transition_sink(transition)
            frame = next_frame

            if (
                self._is_solved(frame)
                or frame.state == GameState.GAME_OVER
                or frame.levels_completed != before_levels
            ):
                break
        return {"frame": frame, "transitions": transitions, "error": error}

    def _turn_prompt(
        self,
        frame: FrameData,
        *,
        previous_batch: dict | None,
        supervisor_advice: str,
        initial: bool,
    ) -> str:
        prefix = ""
        if initial:
            prefix = (
                "Begin solving this unknown game. The harness has initialized "
                "current_state.json, trajectory.jsonl, KNOWLEDGE.md, WORKING.md, "
                "and helpers/. Build only from observed evidence.\n\n"
            )
        previous = (
            json.dumps(previous_batch, separators=(",", ":"), default=str)
            if previous_batch
            else "none"
        )
        advice = supervisor_advice or "none"
        return (
            f"{prefix}"
            f"Environment actions used: {len(self.actions)}/{self.max_steps}.\n"
            f"Current level progress: {frame.levels_completed}/{frame.win_levels}; "
            f"state={getattr(frame.state, 'value', str(frame.state))}.\n"
            f"Previous batch result: {previous}\n"
            f"Supervisor advice: {advice}\n"
            "Read the workspace state and trajectory, update durable knowledge and "
            "helpers as warranted, then return the next action plan."
        )

    def _supervisor_prompt(self) -> str:
        trajectory = self._recent_trajectory(last_n=12, include_grids=False)
        knowledge = self.knowledge_path.read_text(encoding="utf-8")[-6000:]
        working = self.working_path.read_text(encoding="utf-8")[-4000:]
        return (
            "The main agent has produced repeated no-change actions. Diagnose the "
            "trajectory and redirect it without assuming the game's identity.\n\n"
            f"Recent trajectory:\n{json.dumps(trajectory, default=str)}\n\n"
            f"Durable knowledge:\n{knowledge}\n\n"
            f"Working notes:\n{working}"
        )

    def _write_state(self, frame: FrameData, previous_batch: dict | None) -> None:
        payload = {
            "game": "unknown-game",
            "state": getattr(frame.state, "value", str(frame.state)),
            "levels_completed": frame.levels_completed,
            "win_levels": frame.win_levels,
            "available_actions": [
                action.name for action in getattr(frame, "available_actions", []) or []
            ],
            "actions_used": len(self.actions),
            "action_budget": self.max_steps,
            "grid": last_grid(frame.frame),
            "previous_batch": previous_batch,
        }
        self.state_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )

    def _append_trajectory(self, transition: dict) -> None:
        with self.trajectory_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(transition, default=str) + "\n")

    def _recent_trajectory(
        self,
        *,
        last_n: int,
        include_grids: bool,
    ) -> list[dict]:
        if not self.trajectory_path.exists():
            return []
        records = [
            json.loads(line)
            for line in self.trajectory_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ][-last_n:]
        if include_grids:
            return records
        for record in records:
            for side in ("before", "after"):
                if isinstance(record.get(side), dict):
                    record[side] = {
                        key: value
                        for key, value in record[side].items()
                        if key != "grid"
                    }
        return records

    def _save_frame_image(self, frame: FrameData, index: int) -> Path | None:
        if not self.use_visual:
            return None
        rendered = getattr(frame, "rendered_frame", None)
        data_url = str(getattr(rendered, "data_url", "") or "")
        prefix = "data:image/png;base64,"
        if not data_url.startswith(prefix):
            return None
        target = self.frames_dir / f"{index:04d}.png"
        target.write_bytes(base64.b64decode(data_url[len(prefix) :]))
        return target

    @staticmethod
    def _transition_summary(transition: dict) -> dict:
        summary = dict(transition)
        for side in ("before", "after"):
            if isinstance(summary.get(side), dict):
                summary[side] = {
                    key: value
                    for key, value in summary[side].items()
                    if key != "grid"
                }
        return summary

    def _grid_diff(
        self,
        before: list[list[int]],
        after: list[list[int]],
        limit: int = 80,
    ) -> list[dict]:
        changes: list[dict] = []
        height = max(len(before), len(after))
        for row_index in range(height):
            before_row = before[row_index] if row_index < len(before) else []
            after_row = after[row_index] if row_index < len(after) else []
            width = max(len(before_row), len(after_row))
            for col_index in range(width):
                old = before_row[col_index] if col_index < len(before_row) else None
                new = after_row[col_index] if col_index < len(after_row) else None
                if old != new:
                    changes.append(
                        {"row": row_index, "col": col_index, "before": old, "after": new}
                    )
                    if len(changes) >= limit:
                        return changes
        return changes

    def _append_transcript(self, record: dict) -> None:
        with self.transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    def _is_solved(self, frame: FrameData) -> bool:
        return (
            frame.state == GameState.WIN
            or bool(frame.win_levels and frame.levels_completed >= frame.win_levels)
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _emit(self, message: str) -> None:
        if self.event_sink is not None:
            self.event_sink(message)
