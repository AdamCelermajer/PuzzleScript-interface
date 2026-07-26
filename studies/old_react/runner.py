from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from client.arc.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid


class ReactEnv(Protocol):
    def reset(self) -> FrameData: ...

    def step(self, action: GameAction) -> FrameData: ...


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    content: object


@dataclass(frozen=True)
class ReactRunResult:
    solved: bool
    actions: list[GameAction]
    output_dir: Path
    transcript_path: Path
    final_frame: FrameData
    tool_calls: int


@dataclass
class ReactAgentRunner:
    env: ReactEnv
    llm_client: object
    output_dir: str | Path
    max_steps: int = 50
    max_tool_calls: int | None = None
    max_llm_errors: int = 3
    max_non_action_tools: int = 2
    max_probe_actions: int = 0
    python_timeout_seconds: float = 3.0
    event_sink: Callable[[str], None] | None = None
    probe_env_factory: Callable[[], ReactEnv] | None = None
    actions: list[GameAction] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    tool_history: list[dict] = field(default_factory=list)
    sequence_attempts: dict[str, dict] = field(default_factory=dict)
    no_op_actions: dict[str, dict] = field(default_factory=dict)
    probe_actions_used: int = 0
    non_action_tools_since_action: int = 0

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.output_dir / "transcript.jsonl"
        self.observations_path = self.output_dir / "observations.json"
        self.history_path = self.output_dir / "history.json"
        self.tool_history_path = self.output_dir / "tool_history.json"
        if self.max_tool_calls is None:
            self.max_tool_calls = max(1, self.max_steps * 6)

    def run(self) -> ReactRunResult:
        self._emit(f"React agent output: {self.output_dir}")
        frame = self.env.reset()
        self._record_frame("RESET", frame)

        solved = self._is_solved(frame)
        tool_calls = 0
        llm_errors = 0
        while not solved and len(self.actions) < self.max_steps:
            if tool_calls >= int(self.max_tool_calls or 0):
                self._emit("Stopping: max tool calls reached")
                break
            response = self._call_llm(frame)
            tool_calls += 1
            if response.get("tool") == "llm_error":
                llm_errors += 1
                result = ToolResult(False, response.get("args", {}))
                self._append_transcript(response=response, result=result)
                self.history.append(
                    {
                        "action": "LLM_ERROR",
                        "error": response.get("args", {}).get("error", "unknown"),
                    }
                )
                self._emit(f"LLM call error {llm_errors}/{self.max_llm_errors}")
                if llm_errors >= self.max_llm_errors:
                    self._emit("Stopping: too many invalid LLM JSON responses")
                    break
                continue
            llm_errors = 0
            tool_name = str(response.get("tool", "inspect_state")).strip()
            args = self._normalize_args(response.get("args", {}))
            response["args"] = args
            response["note"] = self._short_note(self._response_note(response))
            response.pop("thought", None)
            note = self._compact(response["note"], limit=120)
            if note:
                self._emit(f"Note: {note}")
            if (
                self.non_action_tools_since_action >= self.max_non_action_tools
                and tool_name not in {"take_action", "take_action_sequence", "finish"}
            ):
                response = {
                    "note": self._response_note(response),
                    "tool": "take_action_required",
                    "args": {
                        "requested_tool": tool_name,
                        "message": (
                            "Non-action tool budget is exhausted. Choose take_action "
                            "or take_action_sequence with movement actions."
                        ),
                    },
                }
                tool_name = "take_action_required"
                args = response["args"]
            self._emit(f"Tool: {tool_name} {self._compact(args, limit=180)}")
            result, frame = self._execute_tool(tool_name, args, frame)
            self._append_transcript(response=response, result=result)
            self._record_tool_call(response, result)
            self._emit(self._tool_result_event(tool_name, result))
            solved = self._is_solved(frame)
            if tool_name == "finish" and result.ok:
                break

        return ReactRunResult(
            solved=solved,
            actions=list(self.actions),
            output_dir=self.output_dir,
            transcript_path=self.transcript_path,
            final_frame=frame,
            tool_calls=tool_calls,
        )

    def _call_llm(self, frame: FrameData) -> dict:
        if not hasattr(self.llm_client, "call_json") and not hasattr(
            self.llm_client, "call_text"
        ):
            raise TypeError(
                "ReactAgentRunner requires llm_client.call_text or call_json"
            )
        try:
            if hasattr(self.llm_client, "call_text"):
                raw = self.llm_client.call_text(
                    self._system_prompt(),
                    self._user_prompt(frame),
                    image_data_urls=self._image_urls(frame),
                    purpose="react agent",
                )
                data = self._parse_tool_call(raw)
            else:
                data = self.llm_client.call_json(
                    self._system_prompt(),
                    self._user_prompt(frame),
                    purpose="react agent",
                )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return {
                "note": "The model response was not valid tool-call JSON.",
                "tool": "llm_error",
                "args": {"error": str(exc)},
            }
        if not isinstance(data, dict):
            return {
                "note": "The model response was not a JSON object.",
                "tool": "llm_error",
                "args": {"error": "response must be a JSON object"},
            }
        return data

    def _image_urls(self, frame: FrameData) -> list[str]:
        rendered = getattr(frame, "rendered_frame", None)
        data_url = getattr(rendered, "data_url", "") if rendered is not None else ""
        return [str(data_url)] if str(data_url).strip() else []

    def _normalize_args(self, args: object) -> dict:
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            text = args.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {"value": args}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        return {}

    def _parse_tool_call(self, raw_response: str) -> dict:
        text = str(raw_response or "").strip()
        if not text:
            raise ValueError("LLM returned empty content")

        decoder = json.JSONDecoder()
        candidates = [text]
        if "```" in text:
            candidates.extend(self._fenced_blocks(text))
        candidates.extend(text[index:] for index, char in enumerate(text) if char == "{")

        for candidate in candidates:
            cleaned = self._strip_json_fence(candidate)
            try:
                parsed, _ = decoder.raw_decode(cleaned)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        preview = text[:500].replace("\n", "\\n")
        raise ValueError(f"Could not parse tool-call JSON from response: {preview}")

    def _fenced_blocks(self, text: str) -> list[str]:
        blocks: list[str] = []
        parts = text.split("```")
        for index in range(1, len(parts), 2):
            block = parts[index]
            if block.lstrip().startswith("json"):
                block = block.lstrip()[4:]
            blocks.append(block.strip())
        return blocks

    def _strip_json_fence(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned

    def _system_prompt(self) -> str:
        return (
            "You are an experimental ReAct puzzle agent. "
            "You may create notes, helper programs, and private rule languages inside "
            "your run workspace. You only observe ARC/PuzzleScript frames and your own "
            "workspace/history. You are not given PuzzleScript source files, solution "
            "files, or prebuilt rule artifacts. When available, you also receive the "
            "current rendered screenshot as direct visual observation.\n\n"
            "Action meanings: ACTION1=Up, ACTION2=Down, ACTION3=Left, "
            "ACTION4=Right, ACTION5=Space/Action, ACTION7=Undo. "
            "To move the character, use take_action with ACTION1-4. "
            "For a planned path, use take_action_sequence with an actions list; "
            "each action in the sequence still counts against the step budget. "
            "Avoid ACTION7 unless you are intentionally reverting a bad move; "
            "normal exploration should use movement actions and compare the diffs. "
            "Do not spend repeated turns naming visual symbols; treat state, "
            "levels_completed, changed, and grid diffs as the authoritative feedback. "
            "inspect_state only repeats the current observation; do not call it "
            "again after it has already returned the same frame.\n\n"
            "Choose exactly one tool call per response. "
            "Do not use markdown, code fences, XML tags, or prose outside the JSON. "
            "Do not include chain-of-thought or hidden reasoning. The note field "
            "must be at most 12 words: an action label, observation, or empty string.\n"
            'Output one raw JSON object: {"note": "...", "tool": "<tool>", "args": {...}}\n'
            "Tools: inspect_state, list_files, read_file, write_file, run_python, "
            "take_action, take_action_sequence, probe_action_tree, finish."
        )

    def _user_prompt(self, frame: FrameData) -> str:
        state = self._frame_summary(frame)
        history = json.dumps(self.history[-8:], indent=2)
        tool_history = json.dumps(self.tool_history[-8:], indent=2)
        return (
            "Current frame:\n"
            f"{state}\n\n"
            "Action meanings:\n"
            f"{self._action_help()}\n\n"
            f"Main action budget used: {len(self.actions)}/{self.max_steps}; "
            f"remaining: {max(0, self.max_steps - len(self.actions))}\n\n"
            f"Non-action tools since last action: {self.non_action_tools_since_action}/"
            f"{self.max_non_action_tools}\n\n"
            "Recent tool calls and results:\n"
            f"{tool_history}\n\n"
            "Recent history:\n"
            f"{history}\n\n"
            "Workspace files:\n"
            f"{json.dumps(self._list_files(), indent=2)}\n\n"
            "Workspace data files are maintained automatically: observations.json "
            "is a summary object, history.json is the plain list of observed frames, "
            "and tool_history.json is the plain list of tool calls/results. Use "
            "run_python to read them when you need exact history.\n\n"
            f"Probe action budget: {self.probe_actions_used}/{self.max_probe_actions}. "
            "If probe_action_tree is available, it tests action sequences in fresh "
            "episodes and reports only observations from those probes. If probe budget "
            "is available and your plan is uncertain, probe before spending many real "
            "episode actions.\n\n"
            "Select the next tool call. If you already inspected this frame, "
            "take a movement action or create/run a concrete helper. When remaining "
            "actions are low, prefer a concrete take_action_sequence over more analysis."
        )

    def _execute_tool(
        self,
        tool_name: str,
        args: dict,
        frame: FrameData,
    ) -> tuple[ToolResult, FrameData]:
        if tool_name == "inspect_state":
            return ToolResult(True, self._frame_summary(frame)), frame
        if tool_name == "list_files":
            return ToolResult(True, self._list_files()), frame
        if tool_name == "read_file":
            return self._read_file(str(args.get("path", ""))), frame
        if tool_name == "write_file":
            return self._write_file(
                str(args.get("path", "")),
                str(args.get("content", "")),
            ), frame
        if tool_name == "run_python":
            return self._run_python(str(args.get("code", ""))), frame
        if tool_name == "take_action":
            return self._take_action(str(args.get("action", "")), frame)
        if tool_name == "take_action_sequence":
            return self._take_action_sequence(args.get("actions", []), frame)
        if tool_name == "probe_action_tree":
            return self._probe_action_tree(args), frame
        if tool_name == "finish":
            if not self._is_solved(frame):
                return (
                    ToolResult(
                        False,
                        {
                            "error": "finish rejected because ARC state is not solved",
                            "state": getattr(frame.state, "value", str(frame.state)),
                            "levels_completed": frame.levels_completed,
                            "win_levels": frame.win_levels,
                        },
                    ),
                    frame,
                )
            return ToolResult(True, {"message": str(args.get("message", "finished"))}), frame
        if tool_name == "take_action_required":
            return ToolResult(False, args), frame
        return ToolResult(False, {"error": f"unknown tool: {tool_name}"}), frame

    def _take_action(
        self,
        action_name: str,
        current_frame: FrameData,
    ) -> tuple[ToolResult, FrameData]:
        action_key = action_name.strip().upper()
        if action_key not in GameAction.__members__:
            return (
                ToolResult(False, {"error": f"unknown action: {action_name}"}),
                current_frame,
            )
        action = GameAction[action_key]
        if len(self.actions) >= self.max_steps:
            return (
                ToolResult(False, {"error": "step budget exhausted"}),
                current_frame,
            )
        before_grid = last_grid(current_frame.frame)
        no_op_key = self._action_key(before_grid, action.name)
        previous_no_op = self.no_op_actions.get(no_op_key)
        if previous_no_op is not None:
            return (
                ToolResult(
                    False,
                    {
                        "error": "known no-op action from same grid rejected",
                        "previous_result": previous_no_op,
                    },
                ),
                current_frame,
            )
        self._emit(f"Action: {action.name}")
        frame = self.env.step(action)
        after_grid = last_grid(frame.frame)
        self.actions.append(action)
        self.non_action_tools_since_action = 0
        self._record_frame(action.name, frame)
        diff = self._grid_diff(before_grid, after_grid)
        if before_grid == after_grid:
            self.no_op_actions[no_op_key] = {"action": action.name, "changed": False}
        return (
            ToolResult(
                True,
                {
                    "action": action.name,
                    "levels_completed": frame.levels_completed,
                    "state": getattr(frame.state, "value", str(frame.state)),
                    "changed": before_grid != after_grid,
                    "diff": diff,
                    "after_grid": after_grid,
                },
            ),
            frame,
        )

    def _take_action_sequence(
        self,
        action_names: object,
        current_frame: FrameData,
    ) -> tuple[ToolResult, FrameData]:
        if not isinstance(action_names, list):
            return (
                ToolResult(False, {"error": "actions must be a list"}),
                current_frame,
            )
        normalized_actions = [str(action) for action in action_names]
        start_grid = last_grid(current_frame.frame)
        attempt_key = self._sequence_key(start_grid, normalized_actions)
        previous_attempt = self.sequence_attempts.get(attempt_key)
        if previous_attempt is not None:
            return (
                ToolResult(
                    False,
                    {
                        "error": "repeated sequence from same grid rejected",
                        "previous_result": previous_attempt,
                    },
                ),
                current_frame,
            )
        transitions = []
        frame = current_frame
        for raw_action in normalized_actions:
            if len(self.actions) >= self.max_steps:
                transitions.append({"error": "step budget exhausted"})
                break
            result, frame = self._take_action(str(raw_action), frame)
            transitions.append(result.content)
            if not result.ok or self._is_solved(frame):
                break
        final_grid = last_grid(frame.frame)
        net_changed = start_grid != final_grid
        attempt_summary = {
            "actions": normalized_actions,
            "actions_executed": len(
                [item for item in transitions if isinstance(item, dict) and item.get("action")]
            ),
            "net_changed": net_changed,
            "solved": self._is_solved(frame),
        }
        self.sequence_attempts[attempt_key] = attempt_summary
        return (
            ToolResult(
                bool(transitions) and all(
                    isinstance(item, dict) and "error" not in item
                    for item in transitions
                ),
                {
                    "actions_executed": attempt_summary["actions_executed"],
                    "net_changed": net_changed,
                    "transitions": transitions,
                    "solved": self._is_solved(frame),
                },
            ),
            frame,
        )

    def _sequence_key(self, grid: list[list[int]], actions: list[str]) -> str:
        return json.dumps({"grid": grid, "actions": actions}, separators=(",", ":"))

    def _action_key(self, grid: list[list[int]], action: str) -> str:
        return json.dumps({"grid": grid, "action": action}, separators=(",", ":"))

    def _probe_action_tree(self, args: dict) -> ToolResult:
        if self.probe_env_factory is None:
            return ToolResult(False, {"error": "probe environment is not configured"})
        if self.probe_actions_used >= self.max_probe_actions:
            return ToolResult(False, {"error": "probe action budget exhausted"})
        actions = args.get("actions") or [
            "ACTION1",
            "ACTION2",
            "ACTION3",
            "ACTION4",
        ]
        if not isinstance(actions, list):
            return ToolResult(False, {"error": "actions must be a list"})
        actions = [str(action).strip().upper() for action in actions]
        max_depth = max(1, min(int(args.get("max_depth", 6)), 12))
        queue: list[list[str]] = [[]]
        visited: set[str] = set()
        probes = []
        best = None

        while queue and self.probe_actions_used < self.max_probe_actions:
            sequence = queue.pop(0)
            if sequence:
                outcome = self._probe_sequence(sequence)
                probes.append(outcome)
                if outcome.get("solved"):
                    return ToolResult(
                        True,
                        {
                            "solved": True,
                            "actions": sequence,
                            "probe_actions_used": self.probe_actions_used,
                            "outcome": outcome,
                        },
                    )
                if best is None or int(outcome.get("levels_completed", 0)) > int(
                    best.get("levels_completed", 0)
                ):
                    best = outcome
                state_key = json.dumps(
                    {
                        "grid": outcome.get("grid"),
                        "state": outcome.get("state"),
                        "levels_completed": outcome.get("levels_completed"),
                    },
                    separators=(",", ":"),
                )
                if state_key in visited:
                    continue
                visited.add(state_key)
            if len(sequence) >= max_depth:
                continue
            for action in actions:
                if action in GameAction.__members__:
                    queue.append([*sequence, action])

        return ToolResult(
            False,
            {
                "solved": False,
                "probe_actions_used": self.probe_actions_used,
                "probes_returned": len(probes[-10:]),
                "recent_probes": probes[-10:],
                "best": best,
            },
        )

    def _probe_sequence(self, sequence: list[str]) -> dict:
        env = self.probe_env_factory()
        frame = env.reset()
        for action_name in sequence:
            if self.probe_actions_used >= self.max_probe_actions:
                break
            action = GameAction[action_name]
            frame = env.step(action)
            self.probe_actions_used += 1
            if self._is_solved(frame):
                break
        return {
            "actions": sequence,
            "state": getattr(frame.state, "value", str(frame.state)),
            "levels_completed": frame.levels_completed,
            "win_levels": frame.win_levels,
            "solved": self._is_solved(frame),
            "grid": last_grid(frame.frame),
        }

    def _read_file(self, relative_path: str) -> ToolResult:
        target = self._workspace_path(relative_path)
        if target is None or not target.exists() or not target.is_file():
            return ToolResult(False, {"error": "file not found in workspace"})
        return ToolResult(True, target.read_text(encoding="utf-8"))

    def _write_file(self, relative_path: str, content: str) -> ToolResult:
        target = self._workspace_path(relative_path)
        if target is None:
            return ToolResult(False, {"error": "path escapes workspace"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(True, {"path": self._relative(target), "bytes": len(content)})

    def _run_python(self, code: str) -> ToolResult:
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", code],
                cwd=self.output_dir,
                capture_output=True,
                text=True,
                timeout=self.python_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, {"error": "python timed out"})
        return ToolResult(
            completed.returncode == 0,
            {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            },
        )

    def _workspace_path(self, relative_path: str) -> Path | None:
        if not relative_path.strip():
            return None
        root = self.output_dir.resolve()
        target = (root / relative_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def _list_files(self) -> list[str]:
        files = []
        for path in sorted(self.output_dir.rglob("*")):
            if path.is_file():
                files.append(self._relative(path))
        return files

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.output_dir.resolve()).as_posix()

    def _record_frame(self, action: str, frame: FrameData) -> None:
        self.history.append(
            {
                "action": action,
                "state": getattr(frame.state, "value", str(frame.state)),
                "levels_completed": frame.levels_completed,
                "win_levels": frame.win_levels,
                "available_actions": [
                    action.name for action in getattr(frame, "available_actions", []) or []
                ],
                "grid": last_grid(frame.frame),
            }
        )
        self._write_observations()

    def _grid_diff(
        self,
        before: list[list[int]],
        after: list[list[int]],
        limit: int = 40,
    ) -> list[dict]:
        changes: list[dict] = []
        height = max(len(before), len(after))
        for row_index in range(height):
            before_row = before[row_index] if row_index < len(before) else []
            after_row = after[row_index] if row_index < len(after) else []
            width = max(len(before_row), len(after_row))
            for col_index in range(width):
                before_value = before_row[col_index] if col_index < len(before_row) else None
                after_value = after_row[col_index] if col_index < len(after_row) else None
                if before_value != after_value:
                    changes.append(
                        {
                            "row": row_index,
                            "col": col_index,
                            "before": before_value,
                            "after": after_value,
                        }
                    )
                    if len(changes) >= limit:
                        return changes
        return changes

    def _record_tool_call(self, response: dict, result: ToolResult) -> None:
        tool_name = str(response.get("tool", ""))
        if tool_name not in {"take_action", "take_action_sequence"}:
            self.non_action_tools_since_action += 1
        self.tool_history.append(
            {
                "tool": tool_name,
                "args": self._compact(response.get("args", {}), limit=800),
                "note": self._compact(self._response_note(response), limit=500),
                "ok": result.ok,
                "result": self._compact(result.content, limit=1200),
            }
        )
        self._write_observations()

    def _response_note(self, response: dict) -> str:
        return str(response.get("note") or response.get("thought") or "")

    def _short_note(self, note: str, limit: int = 120) -> str:
        words = " ".join(str(note).split()).split()
        shortened = " ".join(words[:12])
        if len(shortened) > limit:
            shortened = shortened[: limit - 3].rstrip() + "..."
        return shortened

    def _write_observations(self) -> None:
        payload = {
            "actions": [action.name for action in self.actions],
            "history": self.history,
            "tool_history": self.tool_history,
            "action_meanings": self._action_help(),
        }
        self.observations_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        self.history_path.write_text(
            json.dumps(self.history, indent=2, default=str),
            encoding="utf-8",
        )
        self.tool_history_path.write_text(
            json.dumps(self.tool_history, indent=2, default=str),
            encoding="utf-8",
        )

    def _compact(self, value: object, limit: int) -> object:
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, default=str)
        else:
            text = str(value)
        if len(text) <= limit:
            return value
        return text[: limit - 3] + "..."

    def _frame_summary(self, frame: FrameData) -> str:
        grid = last_grid(frame.frame)
        rows = "\n".join(" ".join(str(cell) for cell in row) for row in grid)
        available = ", ".join(
            action.name for action in getattr(frame, "available_actions", []) or []
        )
        return (
            f"game_id={frame.game_id}\n"
            f"state={getattr(frame.state, 'value', str(frame.state))}\n"
            f"levels_completed={frame.levels_completed}/{frame.win_levels}\n"
            f"available_actions={available or '- none'}\n"
            f"action_meanings={self._action_help()}\n"
            f"grid:\n{rows}"
        )

    def _action_help(self) -> str:
        return (
            "ACTION1=Up, ACTION2=Down, ACTION3=Left, ACTION4=Right, "
            "ACTION5=Space/Action, ACTION7=Undo"
        )

    def _action_label(self, action_name: str) -> str:
        labels = {
            "ACTION1": "Up",
            "ACTION2": "Down",
            "ACTION3": "Left",
            "ACTION4": "Right",
            "ACTION5": "Space/Action",
            "ACTION7": "Undo",
        }
        key = str(action_name).strip().upper()
        label = labels.get(key, "")
        return f"{key} {label}".strip()

    def _tool_result_event(self, tool_name: str, result: ToolResult) -> str:
        status = "ok" if result.ok else "failed"
        content = result.content
        prefix = f"Tool result: {status}"
        if tool_name == "take_action" and isinstance(content, dict):
            changed = content.get("changed")
            diff_count = len(content.get("diff") or [])
            state = content.get("state", "?")
            levels = content.get("levels_completed", "?")
            return (
                f"{prefix} | {self._action_label(str(content.get('action', '')))} "
                f"changed={changed} diff_cells={diff_count} "
                f"state={state} levels={levels} actions={len(self.actions)}"
            )
        if tool_name == "take_action_sequence" and isinstance(content, dict):
            transitions = content.get("transitions") or []
            names = [
                self._action_label(str(item.get("action", "")))
                for item in transitions
                if isinstance(item, dict) and item.get("action")
            ]
            return (
                f"{prefix} | sequence={names} "
                f"executed={content.get('actions_executed', len(names))} "
                f"net_changed={content.get('net_changed')} "
                f"solved={content.get('solved')} actions={len(self.actions)}"
            )
        if isinstance(content, dict) and content.get("error"):
            return f"{prefix} | error={self._compact(content.get('error'), limit=140)}"
        return prefix + (f" | actions={len(self.actions)}" if self.actions else "")

    def _append_transcript(self, response: dict, result: ToolResult) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "response": response,
            "tool_result": {"ok": result.ok, "content": result.content},
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
