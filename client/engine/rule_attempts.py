from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RuleAttemptLog:
    """Append-only audit log for every raw logical-rule compiler response."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, **record: Any) -> dict[str, Any]:
        item = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **record,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item) + "\n")
        return item

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        items = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(json.loads(line))
        return items

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.all()[-max(0, int(limit)) :]
