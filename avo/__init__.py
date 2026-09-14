"""Self-contained general-purpose Agentic Variation Operator framework."""

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.core.framework import (
    Action,
    AvoLaboratory,
    Comparison,
    DeterministicSupervisor,
    EvidenceStore,
    Observation,
    Prediction,
)
from avo.core.profile import EnvironmentProfile, TaskEvaluation, load_profile
from avo.core.theory_package import (
    FilesystemTheoryCandidate,
    TheoryManifest,
)
from avo.core.tool_gateway import AvoToolGateway, GatewayBudget

__all__ = [
    "Action",
    "AvoLaboratory",
    "AvoToolGateway",
    "CodexOAuthAgent",
    "CodexOAuthConfig",
    "Comparison",
    "DeterministicSupervisor",
    "EnvironmentProfile",
    "EvidenceStore",
    "FilesystemTheoryCandidate",
    "GatewayBudget",
    "Observation",
    "Prediction",
    "TaskEvaluation",
    "TheoryManifest",
    "load_profile",
]
