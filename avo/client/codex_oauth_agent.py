from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avo.analysis.run_trace import RunTraceRecorder
from avo.core.agent_backend import AgentRunResult
from avo.core.tool_gateway import AvoToolGateway, FileToolServer
from studies.codex_agent.session import _find_codex_bin


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "base_agent.txt"


@dataclass(frozen=True)
class CodexOAuthConfig:
    model: str = "gpt-5.6-sol"
    effort: str = "high"
    codex_bin: str = ""
    prompt_path: str | Path = DEFAULT_PROMPT_PATH
    task_instructions: str = ""
    max_turns: int = 4
    analysis_dir: str | Path = ""


class CodexOAuthAgent:
    """One persistent Codex thread controlling the generic AVO tool gateway."""

    def __init__(self, config: CodexOAuthConfig | None = None) -> None:
        self.config = config or CodexOAuthConfig()

    def _prompt(self) -> str:
        path = Path(self.config.prompt_path).resolve()
        sections = [path.read_text(encoding="utf-8").strip()]
        if self.config.task_instructions.strip():
            sections.append(self.config.task_instructions.strip())
        return "\n\n".join(sections)

    def run(
        self,
        gateway: AvoToolGateway,
        workspace: str | Path,
    ) -> AgentRunResult:
        try:
            from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox, TextInput
        except ImportError as exc:
            raise RuntimeError("The Codex SDK is not installed. Run `uv sync` first.") from exc

        workspace_path = Path(workspace).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        transcript_path = workspace_path / "agent_transcript.jsonl"
        trace = (
            RunTraceRecorder(Path(self.config.analysis_dir), workspace_path)
            if self.config.analysis_dir
            else None
        )
        server = FileToolServer(gateway, workspace_path)
        server.start()
        if trace is not None:
            trace.snapshot("workspace_initialized")

        codex_bin = _find_codex_bin(self.config.codex_bin)
        sdk_config = CodexConfig(codex_bin=codex_bin) if codex_bin else None
        final_response = ""
        turns = 0
        try:
            with Codex(sdk_config) as codex:
                thread = codex.thread_start(
                    base_instructions=self._prompt(),
                    sandbox=Sandbox.workspace_write,
                    approval_mode=ApprovalMode.deny_all,
                    cwd=str(workspace_path),
                    ephemeral=True,
                    model=self.config.model,
                )
                instruction = (
                    "Operate the AVO run autonomously now. Use the commands in "
                    "AGENT_INTERFACE.md and pursue MISSION.md. Do not merely explain "
                    "what you would do."
                )
                for turn_number in range(1, self.config.max_turns + 1):
                    turns = turn_number
                    turn = thread.turn(
                        [TextInput(instruction)],
                        effort=self.config.effort,
                    )
                    remaining = float(
                        gateway.handle("status")["budgets"]["wall_seconds_remaining"]
                    )
                    timer = threading.Timer(max(1.0, remaining), turn.interrupt)
                    timer.daemon = True
                    timer.start()
                    try:
                        if trace is None or not hasattr(turn, "stream"):
                            result = turn.run()
                        else:
                            from openai_codex._run import _collect_turn_result

                            events = trace.traced(turn.stream(), turn_number)
                            result = _collect_turn_result(events, turn_id=turn.id)
                    finally:
                        timer.cancel()
                    final_response = str(result.final_response or "")
                    with transcript_path.open("a", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(
                                {
                                    "turn": turn_number,
                                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                                    "response": final_response,
                                },
                                sort_keys=True,
                            )
                            + "\n"
                        )

                    if trace is not None:
                        trace.snapshot(f"turn:{turn_number}:transcript_written")

                    status = gateway.handle("status")
                    if status["budgets"]["wall_seconds_remaining"] <= 0:
                        if not status["finished"]:
                            gateway.handle("finish", {"reason": "wall-time budget exhausted"})
                        break
                    if status["task"]["terminal"]:
                        if not status["finished"]:
                            gateway.handle("finish", {"reason": "environment terminal"})
                        break
                    if status["finished"]:
                        break
                    instruction = (
                        "Continue the same AVO run. Check `python avo_tool.py status`, then "
                        "keep using the tools. Do not return while the task remains active. "
                        "Calling finish stops the run but does not make it successful."
                    )
                else:
                    gateway.handle(
                        "finish",
                        {"reason": f"agent turn budget exhausted ({self.config.max_turns})"},
                    )
        finally:
            server.stop()
            if trace is not None:
                trace.snapshot("run_finished")

        return AgentRunResult(
            finish_reason=gateway.finish_reason,
            terminal=gateway.terminal,
            turns=turns,
            final_response=final_response,
            transcript_path=transcript_path,
        )
