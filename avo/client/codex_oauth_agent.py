from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from avo.analysis.model_proxy import CodexRequestProxy
from avo.analysis.run_trace import RunTraceRecorder
from avo.analysis.request_guard import RequestGuard
from avo.client.model_provider import resolve_model
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
        if self.config.session_role == "inner_player":
            return INNER_RUN_INSTRUCTION
        return (
            "Operate the AVO run autonomously now. Use the commands in "
            "AGENT_INTERFACE.md and pursue MISSION.md. Do not merely explain "
            "what you would do."
        )

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
            runtime.preflight()
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
                          "provider_model": self.provider_model},
            )
        request_proxy = None
        if trace is not None:
            request_proxy = CodexRequestProxy(
                trace.transport_root,
                session_id=str(trace.session_id),
                session_role=self.config.session_role,
                guard=RequestGuard(forbidden_roots=(runtime.personal_codex, runtime.private, runtime.artifacts),
                                    public_helper_root=runtime.private / 'tmp' / 'arg0'),
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
                instruction = self._initial_instruction()
                reporting = False
                finalizer = getattr(gateway, "finalization_instruction", None)
                # The optional last call reuses the outer session and its evidence.
                for turn_number in range(1, self.config.max_turns + 2):
                    turns = turn_number
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
                    remaining = float(
                        gateway.handle("status")["budgets"]["wall_seconds_remaining"]
                    )
                    if reporting:
                        remaining = min(180.0, remaining)
                    timer = threading.Timer(max(1.0, remaining), turn.interrupt)
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
                    if getattr(server, "isolation_failure", None):
                        raise IsolationError(server.isolation_failure)
                    if request_proxy.guard.failure:
                        raise IsolationError(request_proxy.guard.failure)
                    if request_proxy.guard.requests_checked == 0:
                        raise IsolationError("Model transport capture is missing")
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
                    if reporting:
                        break
                    if status["budgets"]["wall_seconds_remaining"] <= 0:
                        if not status["finished"]:
                            gateway.handle("finish", {"reason": "wall-time budget exhausted"})
                        break
                    if status["task"]["terminal"]:
                        if not status["finished"]:
                            gateway.handle("finish", {"reason": "environment terminal"})
                    if turn_number >= self.config.max_turns and not status["finished"]:
                        gateway.handle("finish", {"reason": f"agent turn budget exhausted ({self.config.max_turns})"})
                    if gateway.handle("status")["finished"]:
                        final_instruction = finalizer() if callable(finalizer) else None
                        if final_instruction:
                            instruction = final_instruction
                            reporting = True
                            continue
                        break
                    instruction = (
                        "Continue the same AVO run. Use the status command documented in "
                        "AGENT_INTERFACE.md, then keep using the tools. Do not return while "
                        "the task remains active. "
                        "Calling finish stops the run but does not make it successful."
                    )
                else:
                    gateway.handle(
                        "finish",
                        {"reason": f"agent turn budget exhausted ({self.config.max_turns})"},
                    )
        except BaseException as exc:
            run_error = exc
            if request_proxy is not None and request_proxy.guard is not None and request_proxy.guard.failure:
                raise IsolationError(request_proxy.guard.failure) from exc
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

        if request_proxy is None or request_proxy.guard is None or request_proxy.guard.failure or request_proxy.guard.requests_checked == 0:
            raise IsolationError("No complete validated model-request capture; run is infrastructure-invalid")

        return AgentRunResult(
            finish_reason=gateway.finish_reason,
            terminal=gateway.terminal,
            turns=turns,
            final_response=final_response,
            transcript_path=transcript_path,
        )
