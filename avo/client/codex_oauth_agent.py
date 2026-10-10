from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from avo.analysis.model_proxy import CodexRequestProxy
from avo.analysis.run_trace import RunTraceRecorder
from avo.client.model_provider import resolve_model
from avo.client.openrouter_chat import provider_routing
from avo.isolation import IsolatedRuntime, IsolationError, runtime_root
from avo.core.agent_backend import AgentGateway, AgentRunResult, AgentToolServer
from avo.core.tool_gateway import FileToolServer
from studies.codex_agent.session import _find_codex_bin


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


REPORT_GRACE_SECONDS = 300.0

CONTINUE_INSTRUCTION = (
    "Continue the same AVO run. Use the status command documented in "
    "AGENT_INTERFACE.md, then keep using the tools. Do not return while "
    "the task remains active. "
    "Calling finish stops the run but does not make it successful."
)


@dataclass(frozen=True)
class CodexOAuthConfig:
    model: str = "gpt-5.6-sol"
    effort: str = "high"
    service_tier: str = ""
    codex_bin: str = ""
    prompt_path: str | Path = DEFAULT_PROMPT_PATH
    task_instructions: str = ""
    max_turns: int = 4
    analysis_dir: str | Path = ""
    session_role: str = "player"
    session_metadata: Mapping[str, Any] | None = None
    harness: str = "codex"
    provider: str = ""  # pinned OpenRouter provider slug; empty = OpenRouter routing


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
    config: CodexOAuthConfig,
    workspace_path: Path,
    transcript_path: Path,
    trace: RunTraceRecorder | None,
    run_turn: Callable[[int, str, float], str],
) -> tuple[int, str]:
    """AVO turn protocol shared by every harness.

    ``run_turn(turn_number, instruction, timeout_seconds)`` runs one autonomous
    agent turn and returns its final text. Budgets, finishing, and the final
    world-model report retries are identical for Codex and OpenRouter harnesses.
    """
    instruction = initial_instruction(config.session_role)
    final_response = ""
    turns = 0
    reporting = False
    report_instruction = ""
    report_attempts = 0
    finalizer = getattr(gateway, "finalization_instruction", None)
    # The optional last call reuses the outer session and its evidence.
    for turn_number in range(1, config.max_turns + 4):
        turns = turn_number
        remaining = float(gateway.handle("status")["budgets"]["wall_seconds_remaining"])
        if reporting:
            # The report turn has fixed grace: an exhausted search budget must not
            # also erase the required final report.
            remaining = REPORT_GRACE_SECONDS
        final_response = run_turn(turn_number, instruction, max(1.0, remaining))
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
        if status["budgets"]["wall_seconds_remaining"] <= 0:
            if not status["finished"]:
                gateway.handle("finish", {"reason": "wall-time budget exhausted"})
        elif status["task"]["terminal"]:
            if not status["finished"]:
                gateway.handle("finish", {"reason": "environment terminal"})
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
        gateway.handle(
            "finish",
            {"reason": f"agent turn budget exhausted ({config.max_turns})"},
        )
    return turns, final_response


class CodexOAuthAgent:
    """One persistent Codex thread controlling the generic AVO tool gateway."""

    def __init__(self, config: CodexOAuthConfig | None = None) -> None:
        self.config = config or CodexOAuthConfig()
        self.provider, self.provider_model = resolve_model(self.config.model)
        if self.provider == "openrouter" and self.config.service_tier:
            raise ValueError("OpenRouter models do not support the Codex service tier setting")

    def _prompt(self) -> str:
        path = Path(self.config.prompt_path).resolve()
        sections = [path.read_text(encoding="utf-8").strip()]
        if self.config.task_instructions.strip():
            sections.append(self.config.task_instructions.strip())
        return "\n\n".join(sections)

    def _initial_instruction(self) -> str:
        return initial_instruction(self.config.session_role)

    def run(
        self,
        gateway: AgentGateway,
        workspace: str | Path,
        *,
        tool_server: AgentToolServer | None = None,
    ) -> AgentRunResult:
        artifacts = Path(self.config.analysis_dir) if self.config.analysis_dir else runtime_root() / ("a-" + uuid4().hex)
        codex_bin = _find_codex_bin(self.config.codex_bin)
        if not codex_bin:
            raise IsolationError("Codex runtime is unavailable")
        runtime = IsolatedRuntime(Path(workspace), artifacts, codex_bin)
        try:
            if self.provider == "openrouter":
                runtime.authenticate_openrouter()
            else:
                runtime.authenticate()
            return self._run(gateway, workspace, tool_server=tool_server, runtime=runtime)
        except IsolationError as exc:
            (runtime.artifacts / "infrastructure_invalid.json").write_text(
                json.dumps({"status": "infrastructure_invalid", "reason": str(exc)}, indent=2), encoding="utf-8"
            )
            raise
        finally:
            runtime.close()

    def _run(
        self,
        gateway: AgentGateway,
        workspace: str | Path,
        *,
        tool_server: AgentToolServer | None,
        runtime: IsolatedRuntime,
    ) -> AgentRunResult:
        try:
            from openai_codex import ApprovalMode, Codex, CodexConfig, TextInput
        except ImportError as exc:
            raise RuntimeError("The Codex SDK is not installed. Run `uv sync` first.") from exc

        workspace_path = Path(workspace).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        transcript_path = workspace_path / "agent_transcript.jsonl"
        trace = RunTraceRecorder(runtime.artifacts, workspace_path)
        server = tool_server or FileToolServer(gateway, workspace_path)  # type: ignore[arg-type]
        server.start()
        if trace is not None:
            trace.snapshot("workspace_initialized")

        codex_bin = _find_codex_bin(self.config.codex_bin)
        prompt = self._prompt()
        if trace is not None:
            trace.start_session(
                role=self.config.session_role,
                model=self.config.model,
                effort=self.config.effort,
                codex_bin=str(codex_bin or ""),
                base_instructions=prompt,
                ephemeral=True,
                metadata={**(self.config.session_metadata or {}), "model_provider": self.provider,
                          "provider_model": self.provider_model, "harness": "codex",
                          "openrouter_provider": self.config.provider or None},
            )
        request_proxy = None
        if trace is not None:
            request_proxy = CodexRequestProxy(
                trace.transport_root,
                session_id=str(trace.session_id),
                session_role=self.config.session_role,
                body_patch=({"provider": provider_routing(self.config.provider)}
                            if self.provider == "openrouter" and self.config.provider else None),
                **({"upstream_origin": "https://openrouter.ai", "base_path": "/api/v1"}
                   if self.provider == "openrouter" else {}),
            )
            try:
                request_proxy.start()
            except BaseException as exc:
                server.stop()
                trace.finish_session(
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
        config_overrides = [
            "features.memories=false",
            "memories.use_memories=false",
            "memories.generate_memories=false",
        ]
        if request_proxy is not None:
            if self.provider == "openrouter":
                config_overrides.extend([
                    'model_provider="openrouter"',
                    'model_providers.openrouter.name="OpenRouter"',
                    f'model_providers.openrouter.base_url="{request_proxy.model_base_url}"',
                    'model_providers.openrouter.env_key="OPENROUTER_API_KEY"',
                    'model_providers.openrouter.wire_api="responses"',
                    'model_providers.openrouter.requires_openai_auth=false',
                ])
            else:
                config_overrides.append(
                    f'openai_base_url="{request_proxy.model_base_url}"'
                )
        sdk_config = CodexConfig(
            codex_bin=codex_bin or None,
            config_overrides=tuple(config_overrides),
            cwd=str(workspace_path),
            env=runtime.env,
        )
        final_response = ""
        turns = 0
        run_error: BaseException | None = None
        try:
            with Codex(sdk_config) as codex:
                thread = codex.thread_start(
                    base_instructions=prompt,
                    # Omit the legacy sandbox override: it would supersede the
                    # isolated default_permissions profile with broad reads.
                    approval_mode=ApprovalMode.deny_all,
                    cwd=str(workspace_path),
                    ephemeral=True,
                    model=self.provider_model,
                    service_tier=self.config.service_tier or None,
                )
                if trace is not None:
                    trace.attach_thread(str(getattr(thread, "id", "")) or None)

                def run_turn(turn_number: int, instruction: str, timeout: float) -> str:
                    turn = thread.turn(
                        [TextInput(instruction)],
                        effort=self.config.effort,
                    )
                    if trace is not None:
                        trace.record_turn_input(
                            turn_number=turn_number,
                            turn_id=str(getattr(turn, "id", "")) or None,
                            instruction=instruction,
                            effort=self.config.effort,
                        )
                    timer = threading.Timer(timeout, turn.interrupt)
                    timer.daemon = True
                    timer.start()
                    try:
                        if trace is None or not hasattr(turn, "stream"):
                            result = turn.run()
                        else:
                            from openai_codex._run import _collect_turn_result

                            events = trace.traced(
                                turn.stream(),
                                turn_number,
                                str(getattr(turn, "id", "")) or None,
                            )
                            result = _collect_turn_result(events, turn_id=turn.id)
                    finally:
                        timer.cancel()
                    return str(result.final_response or "")

                turns, final_response = drive_turns(
                    gateway, self.config, workspace_path, transcript_path, trace, run_turn
                )
        except BaseException as exc:
            run_error = exc
            raise
        finally:
            if request_proxy is not None:
                request_proxy.stop()
            server.stop()
            if trace is not None:
                trace.snapshot("run_finished")
                trace.finish_session(
                    status="failed" if run_error is not None else "completed",
                    error=(
                        f"{type(run_error).__name__}: {run_error}"
                        if run_error is not None
                        else None
                    ),
                )

        return AgentRunResult(
            finish_reason=gateway.finish_reason,
            terminal=gateway.terminal,
            turns=turns,
            final_response=final_response,
            transcript_path=transcript_path,
        )
