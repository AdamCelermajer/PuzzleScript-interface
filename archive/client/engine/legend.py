from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from client.engine.prompts import PromptStore


def normalize_legend(value: Any) -> dict[int, str]:
    """Normalize adapter or persisted legend data to integer-value labels."""
    if not isinstance(value, dict):
        try:
            value = vars(value)
        except TypeError:
            return {}
    legend: dict[int, str] = {}
    for raw_key, raw_description in value.items():
        try:
            key = int(raw_key)
        except (TypeError, ValueError):
            continue
        description = str(raw_description).strip()
        if description:
            legend[key] = description
    return dict(sorted(legend.items()))


def format_legend(legend: dict[int, str] | None) -> str:
    normalized = normalize_legend(legend or {})
    if not normalized:
        return "- unknown"
    return "\n".join(
        f"{value} = {description}"
        for value, description in normalized.items()
    )


class LegendStore:
    """Persists the run's simple numeric-value legend."""

    def __init__(self, path: str | Path, load_existing: bool = True) -> None:
        self.path = Path(path)
        self.legend: dict[int, str] = {}
        if load_existing:
            self._load()

    def all(self) -> dict[int, str]:
        return dict(self.legend)

    def save(self, legend: dict[int, str]) -> dict[int, str]:
        self.legend = normalize_legend(legend)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {str(key): value for key, value in self.legend.items()}
        self.path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return self.all()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.legend = normalize_legend(data)


class LegendInferer:
    """Infers numeric tile descriptions from the first grid and rendered frame."""

    def __init__(
        self, llm_client, prompt_store: PromptStore | None = None
    ) -> None:
        self.llm_client = llm_client
        self.prompt_store = prompt_store or PromptStore()

    def infer(self, state) -> dict[int, str]:
        values = sorted(state.symbols())
        grid_text = "\n".join(state.rows())
        system = (
            f"{self.prompt_store.get('legend')}\n\n"
            'Output only JSON: {"legend": {"0": "description"}}.'
        )
        prompt = (
            f"Numeric values to describe: {', '.join(str(value) for value in values)}\n\n"
            f"First numeric grid:\n{grid_text}\n\n"
            "Return one entry for every value using only: value = description."
        )
        images = [state.image.data_url] if state.image is not None else []
        data = self.llm_client.call_json(
            system,
            prompt,
            image_data_urls=images,
            purpose="legend inference",
        )
        legend = normalize_legend(data.get("legend", data))
        return {
            value: legend.get(value, f"Tile {value}")
            for value in values
        }
