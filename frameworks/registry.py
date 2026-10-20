"""Every framework the launcher, container entry and workbench know about."""
from __future__ import annotations

from frameworks.avo.framework import AVO
from frameworks.base import Framework
from frameworks.baseline.framework import BASELINE
from frameworks.harness2.framework import HARNESS2

FRAMEWORKS: dict[str, Framework] = {framework.id: framework for framework in (BASELINE, AVO, HARNESS2)}
FRAMEWORK_IDS = tuple(FRAMEWORKS)


def get_framework(framework_id: str) -> Framework:
    try:
        return FRAMEWORKS[framework_id]
    except KeyError:
        raise ValueError(f"Unknown framework {framework_id!r}; choose one of {', '.join(FRAMEWORK_IDS)}") from None


def list_frameworks() -> list[dict]:
    return [framework.describe() for framework in FRAMEWORKS.values()]
