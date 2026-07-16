from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


PROMPT_DEFINITIONS: dict[str, str] = {
    "natural_rule": "Natural rule",
    "logic_compiler": "Logical compiler",
    "rule_revision": "Rule revision",
    "task_goal": "Task goal",
    "subgoal": "Subgoal",
    "action_plan": "Action plan",
    "legend": "Legend",
}


def default_prompt_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts"


class PromptStore:
    """Loads shipped prompt instructions plus optional local overrides."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or default_prompt_dir())
        self.defaults_dir = self.root / "defaults"
        self.overrides_dir = self.root / "overrides"

    def get(self, prompt_id: str) -> str:
        self._validate_id(prompt_id)
        override = self.overrides_dir / f"{prompt_id}.md"
        source = override if override.exists() else self.defaults_dir / f"{prompt_id}.md"
        if not source.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_id}")
        return source.read_text(encoding="utf-8").strip()

    def save(self, prompt_id: str, content: str) -> dict[str, Any]:
        self._validate_id(prompt_id)
        cleaned = str(content).strip()
        if not cleaned:
            raise ValueError("Prompt instructions cannot be blank")
        if len(cleaned.encode("utf-8")) > 100_000:
            raise ValueError("Prompt instructions exceed the 100 KB limit")
        self.overrides_dir.mkdir(parents=True, exist_ok=True)
        (self.overrides_dir / f"{prompt_id}.md").write_text(
            cleaned + "\n", encoding="utf-8"
        )
        return self.item(prompt_id)

    def reset(self, prompt_id: str) -> dict[str, Any]:
        self._validate_id(prompt_id)
        (self.overrides_dir / f"{prompt_id}.md").unlink(missing_ok=True)
        return self.item(prompt_id)

    def item(self, prompt_id: str) -> dict[str, Any]:
        content = self.get(prompt_id)
        customized = (self.overrides_dir / f"{prompt_id}.md").exists()
        return {
            "id": prompt_id,
            "label": PROMPT_DEFINITIONS[prompt_id],
            "content": content,
            "customized": customized,
            "version": hashlib.sha256(content.encode("utf-8")).hexdigest()[:12],
        }

    def catalog(self) -> list[dict[str, Any]]:
        return [self.item(prompt_id) for prompt_id in PROMPT_DEFINITIONS]

    def snapshot(self) -> dict[str, Any]:
        items = self.catalog()
        return {
            "versions": {item["id"]: item["version"] for item in items},
            "prompts": {item["id"]: item["content"] for item in items},
        }

    def _validate_id(self, prompt_id: str) -> None:
        if prompt_id not in PROMPT_DEFINITIONS:
            raise KeyError("Unknown prompt template")
