from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from avo.core.tool_gateway import AvoToolGateway


@dataclass(frozen=True)
class AgentRunResult:
    finish_reason: str
    terminal: bool
    turns: int
    final_response: str
    transcript_path: Path


class AgentBackend(Protocol):
    """Provider-neutral persistent-agent boundary."""

    def run(
        self,
        gateway: AvoToolGateway,
        workspace: str | Path,
    ) -> AgentRunResult: ...
