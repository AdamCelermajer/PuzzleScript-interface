"""Read-only views of a Harness² run's coach (improver) sessions and the harnesses they wrote."""
from __future__ import annotations

import json
from pathlib import Path

# Words the upstream mission uses for each stage (harness2.core.prompts).
STAGES = (("integration judge", "compose"), ("INVARIANT", "INV"), ("DOMAIN", "DOM"),
          ("EXPERIENCE", "reflect"), ("Choose exactly one", "select"))
EDIT_LIMIT = 40_000


def _stage(session: Path) -> str | None:
    mission = session / "mission.md"
    text = mission.read_text(encoding="utf-8", errors="replace") if mission.is_file() else ""
    if not text and (session / "agent_events.jsonl").is_file():
        # Sessions recorded before mission.md was saved: the first read of MISSION.md carries it.
        for line in (session / "agent_events.jsonl").open(encoding="utf-8", errors="replace"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "tool" and "MISSION.md" in str(event.get("text") or ""):
                text = str(event.get("output") or "")
                break
    return next((stage for word, stage in STAGES if word in text), None)


def coach_sessions(run: Path) -> list[dict]:
    rows = []
    for session in sorted((run / "improver" / "sessions").glob("*"), key=lambda p: p.stat().st_mtime):
        events = session / "agent_events.jsonl"
        if not events.is_file():
            continue
        counts: dict[str, int] = {}
        length_cap = False
        for line in events.open(encoding="utf-8", errors="replace"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            counts[event.get("type", "")] = counts.get(event.get("type", ""), 0) + 1
        raw = session / "raw" / "turn-1.jsonl"
        if raw.is_file():
            length_cap = '"reason":"length"' in raw.read_text(encoding="utf-8", errors="replace")
        manifest = json.loads((session / "session.json").read_text(encoding="utf-8")) if (session / "session.json").is_file() else {}
        rows.append({"id": session.name, "stage": _stage(session), "model": manifest.get("model"),
                     "started_at": manifest.get("started_at"), "finished": counts.get("turn_end", 0) > 0,
                     "file_changes": counts.get("file_change", 0), "events": sum(counts.values()),
                     "length_cap": length_cap})
    return rows


def _files(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8", errors="replace")[:EDIT_LIMIT]
            for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "README.md" and p.stat().st_size}


def harness_edits(run: Path) -> dict[str, dict[str, str]]:
    """Non-empty files of every written harness (inv1, dom1, agg1, c1…), not the empty base.

    A stage's harness lands in harnesses/<label> when its rollout starts; until then the
    coach's harvested folder (improver/<label>.a<n>.<hash>.workspace) already holds it.
    """
    edits = {}
    for folder in sorted((run / "improver").glob("*.workspace")):
        edits[folder.name.split(".")[0]] = _files(folder)
    for folder in sorted((run / "harnesses").glob("*")):
        if folder.name != "base" and folder.is_dir():
            edits[folder.name] = _files(folder)
    return dict(sorted(edits.items()))
