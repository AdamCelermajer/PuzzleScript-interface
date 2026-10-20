"""The Framework interface.

A framework is one agent method (baseline, AVO, ...); a harness is the coding CLI its
agents run on. The launcher, the container entry and the workbench read only this
interface, so a new framework is one folder with a ``framework.py`` plus one line in
``registry.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

OptionKind = Literal["int", "str", "bool"]


@dataclass(frozen=True)
class Option:
    """One framework setting. Stored under ``options`` in run_spec.json; the CLI flag is
    ``--name-with-dashes`` (``--name`` alone for a bool)."""

    name: str
    kind: OptionKind
    default: Any
    help: str = ""
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None

    @property
    def flag(self) -> str:
        return "--" + self.name.replace("_", "-")

    def check(self, value: Any) -> Any:
        """The value as this option's kind, or ValueError."""
        if value is None:
            return self.default
        if self.kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{self.flag} must be true or false")
            return value
        if self.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{self.flag} must be an integer")
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"{self.flag} must be >= {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"{self.flag} must be <= {self.maximum}")
            return value
        if not isinstance(value, str) or (self.choices and value not in self.choices):
            raise ValueError(f"{self.flag} must be one of {', '.join(self.choices)}" if self.choices
                             else f"{self.flag} must be a string")
        return value

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "flag": self.flag, "kind": self.kind, "default": self.default,
                "help": self.help, "choices": list(self.choices), "minimum": self.minimum,
                "maximum": self.maximum}


# Inside the container: (spec, resume, results dir, parent dir) -> [module, *arguments].
Entry = Callable[[dict, bool, Path, Path], list[str]]


@dataclass(frozen=True)
class Framework:
    id: str
    label: str
    description: str
    options: tuple[Option, ...]
    entry: Entry
    # A second agent role (AVO's optimizer) with its own model and effort.
    optimizer: bool = False
    # Subfolder of the run directory that holds the framework's own records ("" = the run directory).
    artifact: str = ""
    # How a stopped run restarts: "resume" continues in the same directory,
    # "continue" replays a finished parent into a new directory.
    restart: Literal["resume", "continue"] = "continue"
    # Host-side check before a restart; raises ValueError (resume: the run dir, continue: the parent dir).
    check_restart: Callable[[dict, Path], None] | None = None
    # Display name for one set of options, e.g. baseline with notes -> "Baseline+".
    variant: Callable[[dict], str] | None = None

    def check_options(self, given: dict[str, Any]) -> dict[str, Any]:
        """All options with defaults filled in; ValueError for unknown or invalid ones."""
        unknown = sorted(set(given) - {option.name for option in self.options})
        if unknown:
            raise ValueError(f"The {self.id} framework has no option {', '.join(unknown)}")
        return {option.name: option.check(given.get(option.name)) for option in self.options}

    def variant_label(self, options: dict[str, Any]) -> str:
        return self.variant(options) if self.variant else self.label

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "description": self.description,
                "options": [option.describe() for option in self.options], "optimizer": self.optimizer,
                "artifact": self.artifact, "restart": self.restart}
