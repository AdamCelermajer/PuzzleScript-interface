from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


class AgentGateway(Protocol):
    finish_reason: str

    @property
    def terminal(self) -> bool: ...

    def handle(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any: ...


class AgentToolServer(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


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
        gateway: AgentGateway,
        workspace: str | Path,
    ) -> AgentRunResult: ...
