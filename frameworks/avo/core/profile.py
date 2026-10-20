from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from frameworks.avo.core.framework import EnvironmentContract, JsonValue, Observation, Transition


@dataclass(frozen=True)
class TaskEvaluation:
    terminal: bool
    success: bool
    fitness: float
    score: Mapping[str, JsonValue]


class EnvironmentProfile(Protocol):
    profile_id: str
    objective: str
    environment: EnvironmentContract

    def evaluate(
        self,
        history: Sequence[Transition],
        current: Observation,
    ) -> TaskEvaluation: ...


@dataclass(frozen=True)
class LoadedProfile:
    implementation: EnvironmentProfile
    prompt: str
    settings: Mapping[str, Any]
    manifest_path: Path
    prompt_path: Path
    manifest_hash: str
    prompt_hash: str


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_profile_manifest(specifier: str | Path) -> Path:
    supplied = Path(specifier)
    if supplied.is_file():
        return supplied.resolve()
    bundled = Path(__file__).resolve().parents[1] / "environments" / str(specifier) / "profile.toml"
    if bundled.is_file():
        return bundled.resolve()
    raise FileNotFoundError(f"Unknown AVO environment profile: {specifier}")


def load_profile(
    specifier: str | Path,
    overrides: Mapping[str, Any] | None = None,
) -> LoadedProfile:
    manifest_path = resolve_profile_manifest(specifier)
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    factory_path = str(manifest.get("factory", ""))
    module_name, separator, function_name = factory_path.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError("Profile factory must use 'python.module:function' format")

    settings = dict(manifest.get("defaults", {}))
    settings.update(dict(overrides or {}))
    factory = getattr(import_module(module_name), function_name)
    implementation = factory(settings)
    expected_id = str(manifest.get("id", "")).strip()
    if not expected_id or implementation.profile_id != expected_id:
        raise ValueError("Profile manifest ID does not match its implementation")

    prompt_path = (manifest_path.parent / str(manifest["prompt"])).resolve()
    return LoadedProfile(
        implementation=implementation,
        prompt=prompt_path.read_text(encoding="utf-8").strip(),
        settings=settings,
        manifest_path=manifest_path,
        prompt_path=prompt_path,
        manifest_hash=_hash(manifest_path),
        prompt_hash=_hash(prompt_path),
    )
