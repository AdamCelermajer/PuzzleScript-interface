"""Agent harnesses: one persistent CLI (or in-process) session per agent role.

See ``harnesses/README.md`` and ``docs/architecture/revamp-contract.md`` sections 1-3.
"""
from harnesses.base import CliSession, TurnResult
from harnesses.registry import HARNESS_IDS, create_session, list_harnesses, resolve_model_for

__all__ = ["CliSession", "TurnResult", "HARNESS_IDS", "create_session", "list_harnesses", "resolve_model_for"]
