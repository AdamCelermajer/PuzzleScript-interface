"""AVO turn protocol and the one harness-agnostic agent backend (``CliAgent``).

``drive_turns`` owns budgets, finishing and the final world-model report retries;
``CliAgent`` runs those turns in one persistent ``harnesses`` session (codex,
claude-code, opencode, antigravity or bare) controlling the AVO tool gateway.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from frameworks.avo.core.agent_backend import AgentGateway, AgentRunResult, AgentToolServer
from frameworks.avo.core.tool_gateway import FileToolServer
from harnesses.base import HarnessError

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "base_agent.txt"

INNER_RUN_INSTRUCTION = (
    "Operate the AVO run autonomously now. Use AGENT_INTERFACE.md and pursue "
    "MISSION.md. Switch the solver into a bounded discovery phase. Use the nearest "
    "reproducible checkpoint, or replay a recorded action prefix, and locate the "
    "earliest predicted-versus-observed transition mismatch. Treat every rule, "
    "state key, and plan as falsifiable. Build a frontier from real transitions "
    "for every legal action; encode untried outcomes as unknown, never as walls, "
    "no-ops, or inferred equivalences. Preserve histories when identical observations "
    "may conceal different latent states: replay distinct histories, apply the same "
    "probe, and add the smallest temporal feature or belief-state distinction that "
    "predicts different successors. Audit state cloning and visited-set pruning "
    "against that distinction. Choose experiments by expected information gain, "
    "prioritizing contradiction, unknown-frontier expansion, and state-alias "
    "disambiguation before predicted progress. Record each experiment signature and "
    "outcome; do not repeat it unless the model or context changed. Track model-only "
    "work, real exploratory actions, and goal-directed actions separately; only real "
    "actions consume the environment budget. Invalidate plans at their first "
    "discrepancy. Resume receding-horizon search only after a reproducible, "
    "graph-changing model update; otherwise take the best untried frontier action. "
    "Do not merely explain what you would do."
)
# AVO's research score (frameworks/avo/research_score.py) has no solver.
RESEARCH_RUN_INSTRUCTION = INNER_RUN_INSTRUCTION.replace(
    "Switch the solver into a bounded discovery phase.", "Start with a bounded discovery phase."
)

REPORT_GRACE_SECONDS = 300.0

CONTINUE_INSTRUCTION = (
    "Continue the same AVO run. Use the status command documented in "
    "AGENT_INTERFACE.md, then keep using the tools. Do not return while "
    "the task remains active. "
    "Calling finish stops the run but does not make it successful."
)

ROLE_NAMES = {"inner_player": "player", "outer_optimizer": "optimizer"}


@dataclass(frozen=True)
class AgentConfig:
    model: str = "gpt-5.6-sol"
    effort: str = "high"
    prompt_path: str | Path = DEFAULT_PROMPT_PATH
    task_instructions: str = ""
    max_turns: int = 4
    analysis_dir: str | Path = ""
    session_role: str = "player"
    session_metadata: Mapping[str, Any] | None = None
    harness: str = "codex"
    provider: str = ""  # pinned OpenRouter upstream slug (opencode/bare); empty = OpenRouter routing
    first_instruction: str = ""  # replaces the role's opening instruction when set


def initial_instruction(session_role: str) -> str:
    if session_role == "inner_player":
        return INNER_RUN_INSTRUCTION
    return (
        "Operate the AVO run autonomously now. Use the commands in "
        "AGENT_INTERFACE.md and pursue MISSION.md. Do not merely explain "
        "what you would do."
    )


def drive_turns(
    gateway: AgentGateway,
    config: AgentConfig,
    workspace_path: Path,
    transcript_path: Path,
    run_turn: Callable[[int, str, float | None], str],
) -> tuple[int, str]:
    """AVO turn protocol shared by every harness.

    ``run_turn(turn_number, instruction, timeout_seconds)`` runs one autonomous
    agent turn and returns its final text. Budgets, finishing, and the final
    world-model report retries are identical for every harness.
    """
    instruction = config.first_instruction or initial_instruction(config.session_role)
    final_response = ""
    turns = 0
    reporting = False
    report_instruction = ""
    report_attempts = 0
    finalizer = getattr(gateway, "finalization_instruction", None)
    # The optional last call reuses the outer session and its evidence.
    for turn_number in range(1, config.max_turns + 4):
        turns = turn_number
        remaining = gateway.handle("status")["budgets"]["wall_seconds_remaining"]
        if reporting:
            # The report turn has fixed grace: an exhausted search budget must not
            # also erase the required final report.
            remaining = REPORT_GRACE_SECONDS
        final_response = run_turn(turn_number, instruction, None if remaining is None else max(1.0, remaining))
        with transcript_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"turn": turn_number, "recorded_at": datetime.now(timezone.utc).isoformat(),
                                     "response": final_response}, sort_keys=True) + "\n")

        status = gateway.handle("status")
        if reporting:
            report = workspace_path / "world_model.md"
            if report.is_file() and not report.is_symlink() and report.read_text(encoding="utf-8").strip():
                break
            report_attempts += 1
            if report_attempts < 3:
                instruction = (
                    "The required world_model.md was not saved in the preceding turn. "
                    "This is the final report; do not run more evaluations.\n\n"
                    + report_instruction
                )
                continue
            break
        if status["budgets"]["wall_seconds_remaining"] is not None and status["budgets"]["wall_seconds_remaining"] <= 0:
            if not status["finished"]:
                gateway.handle("finish", {"reason": "wall-time budget exhausted"})
        elif status["task"]["terminal"]:
            if not status["finished"]:
                gateway.handle("finish", {"reason": "environment terminal"})
        elif (status["budgets"].get("environment_steps_remaining") == 0
              and "solver_self_checks_used" not in status["budgets"]):
            # Research score (no solver): with no moves left there is nothing more to do in this attempt.
            if not status["finished"]:
                gateway.handle("finish", {"reason": "environment step budget exhausted"})
        if turn_number >= config.max_turns and not gateway.handle("status")["finished"]:
            gateway.handle("finish", {"reason": f"agent turn budget exhausted ({config.max_turns})"})
        if gateway.handle("status")["finished"]:
            final_instruction = finalizer() if callable(finalizer) else None
            if final_instruction:
                instruction = final_instruction
                report_instruction = final_instruction
                reporting = True
                continue
            break
        instruction = CONTINUE_INSTRUCTION
    else:
        gateway.handle("finish", {"reason": f"agent turn budget exhausted ({config.max_turns})"})
    return turns, final_response


class CliAgent:
    """One persistent harness session controlling the generic AVO tool gateway."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        from harnesses.registry import resolve_model_for

        self.config = config or AgentConfig()
        provider, _ = resolve_model_for(self.config.harness, self.config.model)
        if self.config.provider and provider != "openrouter":
            raise ValueError("Provider pinning is only supported for OpenRouter models")

    def _prompt(self) -> str:
        sections = [Path(self.config.prompt_path).resolve().read_text(encoding="utf-8").strip()]
        if self.config.task_instructions.strip():
            sections.append(self.config.task_instructions.strip())
        return "\n\n".join(sections)

    def run(self, gateway: AgentGateway, workspace: str | Path, *,
            tool_server: AgentToolServer | None = None) -> AgentRunResult:
        from harnesses.registry import create_session

        workspace_path = Path(workspace).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        transcript_path = workspace_path / "agent_transcript.jsonl"
        analysis = Path(self.config.analysis_dir or tempfile.mkdtemp(prefix="avo-analysis-")).resolve()
        session = create_session(self.config.harness)
        server = tool_server or FileToolServer(gateway, workspace_path)  # type: ignore[arg-type]
        server.start()
        try:
            session.start(workspace_path, self._prompt(), self.config.model, self.config.effort,
                          ROLE_NAMES.get(self.config.session_role, self.config.session_role), analysis,
                          provider=self.config.provider)
            if self.config.session_metadata:
                (analysis / "session_metadata.json").write_text(
                    json.dumps(dict(self.config.session_metadata), indent=2, default=str), encoding="utf-8")

            def run_turn(turn_number: int, instruction: str, timeout: float | None) -> str:
                result = session.turn(instruction, timeout=timeout)
                worked = any(event["type"] in {"message", "command", "tool", "file_change"} for event in result.events)
                if result.error and not result.timed_out and not worked:
                    raise HarnessError(f"{self.config.harness} turn {turn_number} failed: {result.error}")
                return result.text

            turns, final_response = drive_turns(gateway, self.config, workspace_path, transcript_path, run_turn)
        finally:
            server.stop()
            session.close()
        return AgentRunResult(finish_reason=gateway.finish_reason, terminal=gateway.terminal, turns=turns,
                              final_response=final_response, transcript_path=transcript_path)
