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
    final_frame: FrameData
    decisions: int


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

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir = self.output_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.output_dir / "transcript.jsonl"
        if self.max_decisions is None:
            self.max_decisions = max(self.max_steps + 5, self.max_steps * 2)
        if self.stop_event is None:
            self.stop_event = Event()

    def run(self) -> CodexRunResult:
        self._emit(f"Codex agent output: {self.output_dir}")
        frame = self.env.reset()
        solved = self._is_solved(frame)
        decisions = 0
        feedback = "This is the initial frame. Solve the game."
        stopped = False

        while (
            not solved
            and len(self.actions) < self.max_steps
            and decisions < int(self.max_decisions or 0)
        ):
            if self.stop_event.is_set():
                stopped = True
                break
            image_path = self._save_frame_image(frame, decisions)
            prompt = self._turn_prompt(frame, feedback, initial=(decisions == 0))
            response = self.session.next_action(prompt, image_path=image_path)
            decisions += 1

            action_name = response["action"]
            note = response.get("note", "")
            if self.decision_sink is not None:
                self.decision_sink(
                    {
                        "action": action_name,
                        "note": note,
                        "decision": decisions,
                    }
                )
            self._emit(
                f"Decision {decisions}: {action_name}"
                + (f" | {note}" if note else "")
            )
            if self.stop_event.is_set():
                stopped = True
                break

            if action_name == "FINISH":
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

            action = GameAction[action_name]
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
            if self.transition_sink is not None:
                self.transition_sink(
                    {
                        "id": f"T{len(self.actions):06d}",
                        "action": action.name,
                        "before": {"grid": before_grid},
                        "after": {"grid": after_grid},
                        "note": note,
                    }
                )
            frame = next_frame

        if stopped:
            status = "cancelled"
            reason = "stop_requested"
            self._emit("Codex run stopped by request.")
        elif solved:
            status = "completed"
            reason = "task_goal_reached"
            self._emit("World completed successfully!")
        elif len(self.actions) >= self.max_steps:
            status = "completed"
            reason = "step_budget_exhausted"
            self._emit("Max steps reached.")
        else:
            status = "completed"
            reason = "decision_budget_exhausted"
            self._emit("Max decisions reached.")

        return CodexRunResult(
            status=status,
            reason=reason,
            solved=solved,
            actions=list(self.actions),
            output_dir=self.output_dir,
            transcript_path=self.transcript_path,
            final_frame=frame,
            decisions=decisions,
        )

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
                "Action meanings: ACTION1=Up, ACTION2=Down, ACTION3=Left, "
                "ACTION4=Right, ACTION5=Space/Action, ACTION7=Undo. "
                "Use FINISH only after the environment reports WIN.\n\n"
            )
        grid = last_grid(frame.frame)
        rows = "\n".join(" ".join(str(cell) for cell in row) for row in grid)
        available = ", ".join(
            action.name for action in getattr(frame, "available_actions", []) or []
        )
        return (
            f"{introduction}"
            f"Transition feedback:\n{feedback}\n\n"
            "Current frame:\n"
            f"game_id={frame.game_id}\n"
            f"state={getattr(frame.state, 'value', str(frame.state))}\n"
            f"levels_completed={frame.levels_completed}/{frame.win_levels}\n"
            f"available_actions={available or 'unknown'}\n"
            f"actions_used={len(self.actions)}/{self.max_steps}\n"
            f"grid:\n{rows}\n\n"
            "Choose the single next action."
        )

    def _action_feedback(
        self,
        action: GameAction,
        before: list[list[int]],
        after: list[list[int]],
        frame: FrameData,
    ) -> str:
        changes = []
        for row_index, (before_row, after_row) in enumerate(zip(before, after)):
            for col_index, (before_value, after_value) in enumerate(
                zip(before_row, after_row)
            ):
                if before_value != after_value:
                    changes.append(
                        f"({row_index},{col_index}):{before_value}->{after_value}"
                    )
        diff = ", ".join(changes[:40]) or "none"
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

    def _is_solved(self, frame: FrameData) -> bool:
        return (
            frame.state == GameState.WIN
            or bool(frame.win_levels and frame.levels_completed >= frame.win_levels)
        )

    def _emit(self, message: str) -> None:
        if self.event_sink is not None:
            self.event_sink(message)
