from __future__ import annotations

import base64
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event
import time
from typing import Callable, Protocol

from client.arc.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid
from frameworks import levels
from frameworks.baseline import prompt as baseline_prompt
from frameworks.world_model import Snapshots


class CodexEnv(Protocol):
    def reset(self) -> FrameData: ...

    def step(self, action: GameAction) -> FrameData: ...


class CodexSession(Protocol):
    def next_action(
        self,
        prompt: str,
        image_path: str | Path | None = None,
    ) -> dict[str, str]: ...


@dataclass(frozen=True)
class CodexRunResult:
    status: str
    reason: str
    solved: bool
    actions: list[GameAction]
    output_dir: Path
    transcript_path: Path
    transitions_path: Path
    final_frame: FrameData
    decisions: int
    workspace_operations: int
    world_model_path: Path | None


@dataclass
class CodexAgentRunner:
    env: CodexEnv
    session: CodexSession
    output_dir: str | Path
    max_steps: int = 50
    max_decisions: int | None = None
    event_sink: Callable[[str], None] | None = None
    decision_sink: Callable[[dict], None] | None = None
    transition_sink: Callable[[dict], None] | None = None
    stop_event: Event | None = None
    actions: list[GameAction] = field(default_factory=list)
    workspace_enabled: bool = False
    continuation_from: str | Path | None = None
    max_wall_seconds: float = 0  # 0 = unlimited
    stop_after_levels: int = 0  # end once this many levels are done, before the next one is shown
    start_level: int = 1  # the level env opens at; stop_after_levels counts from it
    memento: bool = False  # every turn is a fresh session, so the first message must not promise "this same session"

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir = self.output_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.output_dir / "transcript.jsonl"
        self.transitions_path = self.output_dir / "transitions.jsonl"
        self.workspace_operation_count = 0
        if self.max_decisions is None:
            self.max_decisions = max(self.max_steps + 5, self.max_steps * 2)
        if self.stop_event is None:
            self.stop_event = Event()

    def run(self) -> CodexRunResult:
        self._emit(f"Codex agent output: {self.output_dir}")
        frame = self.env.reset()
        prior_history = []
        if self.continuation_from:
            from frameworks.baseline.continuation import load_parent, restore_game
            _, prior_history = load_parent(self.continuation_from)
            frame = restore_game(self.env, frame, prior_history)
            (self.output_dir / "restoration.json").write_text(json.dumps({
                "parent": str(Path(self.continuation_from).resolve()),
                "restoration_replay_actions": len(prior_history),
                "all_transitions_verified": True, "same_codex_conversation": False,
                "additional_action_budget": self.max_steps,
            }, indent=2), encoding="utf-8")
        solved = self._is_solved(frame)
        decisions = 0
        feedback = ""  # why the last reply moved nothing; empty after a played action
        last = ""  # what the last played action did (the observation's "Last action" line)
        stopped = False
        wall_deadline = time.monotonic() + self.max_wall_seconds if self.max_wall_seconds else None
        wall_exhausted = False
        target_reached = False
        source = getattr(self.session, "world_model_path", None)  # the file the player keeps, if any
        snapshots = Snapshots(source, self.output_dir) if source is not None else None
        # Each snapshot point (every 100 actions, each level) copies the world model after the next turn.
        pending: tuple[int, int, int] | None = None

        while (
            not solved
            and len(self.actions) < self.max_steps
            and decisions < int(self.max_decisions or 0)
        ):
            if self.stop_event.is_set():
                stopped = True
                break
            if wall_deadline is not None and time.monotonic() >= wall_deadline:
                wall_exhausted = True
                break
            image_path = self._save_frame_image(frame, decisions)
            prompt = self._turn_prompt(frame, feedback, last, initial=(decisions == 0))
            if prior_history and decisions == 0:
                from frameworks.baseline.continuation import history_prompt
                prompt = history_prompt(prior_history) + prompt
            if hasattr(self.session, "available_actions"):  # act.py checks against these
                self.session.available_actions = baseline_prompt.available(frame)
            try:
                response = self.session.next_action(prompt, image_path=image_path)
            except ValueError as exc:
                decisions += 1
                hint = (getattr(self.session, "action_hint", "")
                        or 'Return one available action name or JSON with an "action" field.')
                feedback = (
                    f"Your last reply could not be used: {exc}. The game has not advanced. "
                    f"{hint} "
                    "Do not repeat note updates just to correct the reply format."
                )
                last = ""
                self._emit(f"Decision {decisions}: reply correction; game unchanged.")
                self._append_transcript(decision=decisions, frame=frame, prompt=prompt,
                    response={"error": str(exc)}, result={"accepted": False, "reason": feedback})
                continue
            finally:
                if pending is not None and snapshots is not None:
                    snapshots.after_action(*pending)
                    pending = None
            decisions += 1

            operation = str(response.get("operation", "ACT")).upper()
            action_name = response.get("action", "NONE")
            note = response.get("note", "")
            if self.decision_sink is not None:
                self.decision_sink(
                    {
                        "operation": operation,
                        "action": action_name,
                        "note": note,
                        "decision": decisions,
                    }
                )
            self._emit(
                f"Decision {decisions}: {operation}"
                + (f" {action_name}" if operation == "ACT" else "")
                + (f" | {note}" if note else "")
            )
            if self.stop_event.is_set():
                stopped = True
                break
            last = ""

            if operation == "FINISH" or action_name == "FINISH":
                feedback = (
                    "FINISH was rejected because the ARC environment still reports "
                    "the game as unsolved. Choose a game action."
                )
                self._append_transcript(
                    decision=decisions,
                    frame=frame,
                    prompt=prompt,
                    response=response,
                    result={"accepted": False, "reason": feedback},
                )
                continue

            if operation != "ACT":
                feedback = f"Unsupported operation {operation}. Choose a valid operation."
                self._append_transcript(
                    decision=decisions,
                    frame=frame,
                    prompt=prompt,
                    response=response,
                    result={"accepted": False, "reason": feedback},
                )
                continue

            action = GameAction[action_name]
            available = list(getattr(frame, "available_actions", []) or [])
            if available and action not in available and action is not GameAction.RESET:
                feedback = (
                    f"{action.name} is not available in this game. The game has not advanced. "
                    f"Choose one of: {', '.join(baseline_prompt.available(frame))}."
                )
                self._append_transcript(decision=decisions, frame=frame, prompt=prompt,
                    response=response, result={"accepted": False, "reason": feedback})
                continue
            before_grid = last_grid(frame.frame)
            next_frame = self.env.reset() if action is GameAction.RESET else self.env.step(action)
            after_grid = last_grid(next_frame.frame)
            self.actions.append(action)
            solved = self._is_solved(next_frame)
            feedback = ""
            last = baseline_prompt.change(action.name, before_grid, after_grid, frame.levels_completed, next_frame)
            transition = {
                "id": f"T{len(self.actions):06d}",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "decision": decisions,
                "action_index": len(self.actions),
                "action": action.name,
                "before": {
                    "grid": before_grid,
                    "state": getattr(frame.state, "value", str(frame.state)),
                    "levels_completed": frame.levels_completed,
                    "win_levels": frame.win_levels,
                },
                "after": {
                    "grid": after_grid,
                    "state": getattr(
                        next_frame.state,
                        "value",
                        str(next_frame.state),
                    ),
                    "levels_completed": next_frame.levels_completed,
                    "win_levels": next_frame.win_levels,
                },
                "changed": before_grid != after_grid,
                "changed_cells": self._changed_cells(before_grid, after_grid),
                "note": note,
            }
            self._append_transcript(
                decision=decisions,
                frame=frame,
                prompt=prompt,
                response=response,
                result={
                    "accepted": True,
                    "action": action.name,
                    "changed": before_grid != after_grid,
                    "state": getattr(next_frame.state, "value", str(next_frame.state)),
                    "levels_completed": next_frame.levels_completed,
                    "win_levels": next_frame.win_levels,
                },
            )
            self._append_jsonl(self.transitions_path, transition)
            if self.transition_sink is not None:
                self.transition_sink(transition)
            if snapshots is not None:
                pending = (len(self.actions), frame.levels_completed, next_frame.levels_completed)
            frame = next_frame
            target = levels.stop_target(self.start_level, self.stop_after_levels)
            if not solved and target and frame.levels_completed >= target:
                target_reached = True  # the agent never gets a turn on the next level
                break

        if stopped:
            status = "cancelled"
            reason = "stop_requested"
            self._emit("Codex run stopped by request.")
        elif solved:
            status = "completed"
            reason = "task_goal_reached"
            self._emit("World completed successfully!")
        elif target_reached:
            status = "completed"
            reason = "level_target_reached"
            self._emit("Level target reached.")
        elif wall_exhausted:
            status = "completed"
            reason = "wall_budget_exhausted"
            self._emit("Wall-clock budget reached.")
        elif len(self.actions) >= self.max_steps:
            status = "completed"
            reason = "step_budget_exhausted"
            self._emit("Max steps reached.")
        else:
            status = "completed"
            reason = "decision_budget_exhausted"
            self._emit("Max decisions reached.")

        note_tool_count = getattr(self.session, "note_tool_count", None)
        if callable(note_tool_count):
            self.workspace_operation_count = int(note_tool_count())
        world_model_path = self._save_world_model(reason, frame)
        if snapshots is not None:
            if pending is not None:  # play ended before the next turn: the final report is that update
                snapshots.after_action(*pending)
            snapshots.final()
        result = CodexRunResult(
            status=status,
            reason=reason,
            solved=solved,
            actions=list(self.actions),
            output_dir=self.output_dir,
            transcript_path=self.transcript_path,
            transitions_path=self.transitions_path,
            final_frame=frame,
            decisions=decisions,
            workspace_operations=self.workspace_operation_count,
            world_model_path=world_model_path,
        )
        self._write_result(result)
        return result

    def _turn_prompt(self, frame: FrameData, feedback: str, last: str, *, initial: bool) -> str:
        """The turn message: the observation (frameworks/baseline/prompt.py), after why the last reply
        moved nothing when it did not; the first one opens the game."""
        if initial:
            return baseline_prompt.first_message(self.max_steps, self.start_level, frame)
        observation = baseline_prompt.observation(frame, len(self.actions), self.max_steps, last)
        return f"{feedback}\n\n{observation}" if feedback else observation

    def _save_world_model(self, reason: str, frame: FrameData) -> Path | None:
        """Ask for the end-of-game world model and copy the file the player wrote to world_model.md."""
        method = getattr(self.session, "final_world_model", None)
        if method is None:
            return None
        try:
            source = method(reason=reason, levels=frame.levels_completed, total=frame.win_levels)
        except Exception as exc:
            self._emit(f"Final world model failed: {type(exc).__name__}: {exc}")
            return None
        if source is None or not Path(source).is_file():
            return None
        target = self.output_dir / "world_model.md"
        shutil.copyfile(source, target)
        return target

    def _write_result(self, result: CodexRunResult) -> None:
        payload = {
            "status": result.status,
            "reason": result.reason,
            "solved": result.solved,
            "actions": [action.name for action in result.actions],
            "action_count": len(result.actions),
            "decisions": result.decisions,
            "workspace_enabled": self.workspace_enabled,
            "workspace_operations": result.workspace_operations,
            "final_state": getattr(
                result.final_frame.state,
                "value",
                str(result.final_frame.state),
            ),
            "levels_completed": result.final_frame.levels_completed,
            "win_levels": result.final_frame.win_levels,
            "world_model": str(result.world_model_path) if result.world_model_path else None,
            "transcript": str(result.transcript_path),
            "transitions": str(result.transitions_path),
            "agent_events": str(
                getattr(self.session, "session_log_path", "") or ""
            )
            or None,
            **levels.result_fields(self.transitions_path, str(getattr(self.env, "game_id", "")),
                                   self.start_level, self.stop_after_levels),
        }
        (self.output_dir / "result.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _save_frame_image(
        self,
        frame: FrameData,
        index: int,
    ) -> Path | None:
        rendered = getattr(frame, "rendered_frame", None)
        data_url = str(getattr(rendered, "data_url", "") or "")
        prefix = "data:image/png;base64,"
        if not data_url.startswith(prefix):
            return None
        target = self.frames_dir / f"{index:03d}.png"
        target.write_bytes(base64.b64decode(data_url[len(prefix) :]))
        return target

    def _append_transcript(
        self,
        *,
        decision: int,
        frame: FrameData,
        prompt: str,
        response: dict,
        result: dict,
    ) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "decision": decision,
            "frame": {
                "state": getattr(frame.state, "value", str(frame.state)),
                "levels_completed": frame.levels_completed,
                "win_levels": frame.win_levels,
                "grid": last_grid(frame.frame),
            },
            "prompt": prompt,
            "response": response,
            "result": result,
        }
        with self.transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    @staticmethod
    def _changed_cells(
        before: list[list[int]],
        after: list[list[int]],
    ) -> list[dict[str, int]]:
        changes = []
        for row_index, (before_row, after_row) in enumerate(zip(before, after)):
            for col_index, (before_value, after_value) in enumerate(
                zip(before_row, after_row)
            ):
                if before_value != after_value:
                    changes.append(
                        {
                            "row": row_index,
                            "col": col_index,
                            "before": before_value,
                            "after": after_value,
                        }
                    )
        return changes

    @staticmethod
    def _append_jsonl(path: Path, record: dict) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    def _is_solved(self, frame: FrameData) -> bool:
        return (
            frame.state == GameState.WIN
            or bool(frame.win_levels and frame.levels_completed >= frame.win_levels)
        )

    def _emit(self, message: str) -> None:
        if self.event_sink is not None:
            self.event_sink(message)
