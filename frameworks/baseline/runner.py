from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event
import time
from typing import Callable, Protocol

from client.arc.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid


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
        feedback = "This is the initial frame. Solve the game."
        stopped = False
        wall_deadline = time.monotonic() + self.max_wall_seconds if self.max_wall_seconds else None
        wall_exhausted = False

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
            prompt = self._turn_prompt(frame, feedback, initial=(decisions == 0))
            if prior_history and decisions == 0:
                from frameworks.baseline.continuation import history_prompt
                prompt = history_prompt(prior_history) + prompt
            try:
                response = self.session.next_action(prompt, image_path=image_path)
            except ValueError as exc:
                decisions += 1
                feedback = (
                    f"Your last reply could not be used: {exc}. The game has not advanced. "
                    'Return one available action name or JSON with an "action" field. '
                    "Do not repeat note updates just to correct the reply format."
                )
                self._emit(f"Decision {decisions}: reply correction; game unchanged.")
                self._append_transcript(decision=decisions, frame=frame, prompt=prompt,
                    response={"error": str(exc)}, result={"accepted": False, "reason": feedback})
                continue
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
            if available and action not in available:
                feedback = (
                    f"{action.name} is not available in this game. The game has not advanced. "
                    f"Choose one of: {', '.join(item.name for item in available)}."
                )
                self._append_transcript(decision=decisions, frame=frame, prompt=prompt,
                    response=response, result={"accepted": False, "reason": feedback})
                continue
            before_grid = last_grid(frame.frame)
            next_frame = self.env.step(action)
            after_grid = last_grid(next_frame.frame)
            self.actions.append(action)
            solved = self._is_solved(next_frame)
            feedback = self._action_feedback(
                action,
                before_grid,
                after_grid,
                next_frame,
            )
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
            frame = next_frame

        if stopped:
            status = "cancelled"
            reason = "stop_requested"
            self._emit("Codex run stopped by request.")
        elif solved:
            status = "completed"
            reason = "task_goal_reached"
            self._emit("World completed successfully!")
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
        world_model_path = self._save_world_model()
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

    def _turn_prompt(
        self,
        frame: FrameData,
        feedback: str,
        *,
        initial: bool,
    ) -> str:
        introduction = ""
        if initial:
            introduction = (
                "Solve this unknown puzzle game. You will receive one current frame "
                "per turn. Reply with exactly one action, observe the next frame, and "
                "continue in this same session until the environment reports a win.\n"
                "Use FINISH only after the environment reports WIN.\n\n"
            )
        grid = last_grid(frame.frame)
        rows = "\n".join(" ".join(str(cell) for cell in row) for row in grid)
        available = ", ".join(
            action.name for action in getattr(frame, "available_actions", []) or []
        )
        encoding = ""
        if (getattr(frame, "projection", None) or {}).get("mode") == "visible-cell-v1":
            encoding = "Grid encoding: one cell per visible game tile; identical rendered textures share an anonymous ID. Hidden object differences are not encoded.\n"
        if (getattr(frame, "projection", None) or {}).get("mode") == "object-cell-v1":
            encoding = "Grid encoding: one cell per visible game tile; values are anonymous object-combination IDs.\n"
        if (getattr(frame, "projection", None) or {}).get("mode") == "visible-cell-hex-v2":
            encoding = (
                "Grid encoding: each visible tile is a 2x2 block [[a,b],[c,d]]. "
                "Its opaque pattern ID is 4096*a+256*b+16*c+d. "
                "Group these blocks to recover the tile board; the PNG shows the same visible board.\n"
            )
        return (
            f"{introduction}"
            f"Transition feedback:\n{feedback}\n\n"
            "Current frame:\n"
            f"state={getattr(frame.state, 'value', str(frame.state))}\n"
            f"levels_completed={frame.levels_completed}/{frame.win_levels}\n"
            f"available_actions={available or 'unknown'}\n"
            f"actions_used={len(self.actions)}/{self.max_steps}\n"
            f"{encoding}"
            f"grid:\n{rows}\n\n"
            "Choose the single next action."
        )

    def _save_world_model(self) -> Path | None:
        method = getattr(self.session, "final_world_model", None)
        if method is None:
            return None
        target = self.output_dir / "world_model.json"
        try:
            payload = method()
        except Exception as exc:
            payload = {"error": f"{type(exc).__name__}: {exc}"}
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
        }
        (self.output_dir / "result.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _action_feedback(
        self,
        action: GameAction,
        before: list[list[int]],
        after: list[list[int]],
        frame: FrameData,
    ) -> str:
        changes = self._changed_cells(before, after)
        diff = ", ".join(
            f"({item['row']},{item['col']}):{item['before']}->{item['after']}"
            for item in changes[:40]
        ) or "none"
        return (
            f"Previous action {action.name}. "
            f"Frame changed={before != after}. "
            f"Changed cells={diff}. "
            f"Environment state={getattr(frame.state, 'value', str(frame.state))}; "
            f"levels={frame.levels_completed}/{frame.win_levels}."
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
