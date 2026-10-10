"""Generate a post-run report from archived outer history in an isolated container.

The campaign is mounted read-only at its original /results/campaign path. No game
backend is started, and candidate-management tools are closed before the model runs.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from avo.client.codex_oauth_agent import CodexOAuthAgent, CodexOAuthConfig
from avo.evolution.gateway import EvolutionBudget, EvolutionGateway, FINAL_WORLD_MODEL_PROMPT
from avo.evolution.store import EvolutionStore
from avo.evolution.tool_server import EvolutionFileToolServer
from avo.isolation import new_workspace

FINAL_PROMPT = FINAL_WORLD_MODEL_PROMPT


def archived_history(analysis: Path, session_id: str) -> list[dict]:
    records = []
    seen = set()
    for line in (analysis / "app_server_events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("session_id") != session_id or event.get("method") != "item/completed":
            continue
        item = event["payload"]["item"]
        key = item.get("id")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        records.append({"recorded_at": event.get("recorded_at"), "item": item})
    if not records:
        raise ValueError("No completed outer-session history was saved")
    return records


class ReportAgent(CodexOAuthAgent):
    def _initial_instruction(self) -> str:
        return FINAL_PROMPT


def restore_observations(analysis: Path, history: str, workspace: Path) -> list[str]:
    restored = []
    for digest in sorted(set(re.findall(r"observations/([a-f0-9]{64})\.png", history))):
        blob = analysis / "workspace_blobs" / digest
        content = blob.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Archived observation hash mismatch: {digest}")
        target = workspace / "observations" / (digest + ".png")
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(content)
        restored.append(target.name)
    return restored


def main() -> None:
    source = Path("/results/campaign")
    output = Path("/results/report")
    output.mkdir(exist_ok=False)
    analysis = source / "optimizer_analysis"
    session = json.loads((analysis / "session.json").read_text(encoding="utf-8"))
    prompt = json.loads((analysis / "prompt.json").read_text(encoding="utf-8"))["base_instructions"]
    history = archived_history(analysis, session["session_id"])
    workspace = new_workspace()
    serialized = "\n".join(json.dumps(item, ensure_ascii=False) for item in history) + "\n"
    # Recorded commands refer to the former workspace. Map that location only;
    # retain the recorded messages and tool outputs without summarizing them.
    normalized = serialized.replace(session["cwd"], str(workspace))
    restored = restore_observations(analysis, normalized, workspace)
    (workspace / "OUTER_HISTORY.jsonl").write_text(normalized, encoding="utf-8")
    prompt_path = output / "restored_prompt.txt"
    prompt_path.write_text(
        prompt
        + "\n\nYour saved outer-session history is in OUTER_HISTORY.jsonl. "
        "Read it to recover your prior work. Write world_model.md before any optional "
        "cross-checks. Do not inspect, list, or kill processes; the saved evidence is "
        "sufficient for this report.\n",
        encoding="utf-8",
    )
    store = EvolutionStore(source, workspace)
    initial = json.loads((source / "initial_observation.json").read_text(encoding="utf-8"))
    gateway = EvolutionGateway(store, None, mission=FINAL_PROMPT, initial_observation=initial,
                               budget=EvolutionBudget(max_wall_seconds=1800))
    gateway.finished = True
    gateway.finish_reason = "post-run world-model report"
    metadata = {
        "provenance": "reconstructed_from_saved_outer_history",
        "source_session_id": session["session_id"], "source_thread_id": session["thread_id"],
        "source_history_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        "history_items": len(history), "workspace_path_remapped": True,
        "restored_observations": restored,
        "model": session["model"], "effort": session["effort"], "prompt": FINAL_PROMPT,
        "best_evaluation": store.population_summary()["best"],
    }
    (output / "provenance.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    result = ReportAgent(CodexOAuthConfig(
        model=session["model"], effort=session["effort"], codex_bin="/usr/local/bin/codex",
        prompt_path=prompt_path, max_turns=1, analysis_dir=output / "analysis",
        session_role="outer_world_model_reconstruction", session_metadata=metadata,
    )).run(gateway, workspace, tool_server=EvolutionFileToolServer(gateway, workspace))
    report = workspace / "world_model.md"
    if not report.is_file() or report.is_symlink() or not report.read_text(encoding="utf-8").strip():
        raise RuntimeError("The reporting session did not save world_model.md")
    content = report.read_text(encoding="utf-8")
    (output / "world_model.md").write_text(content, encoding="utf-8")
    metadata.update(status="available", report_sha256=hashlib.sha256(content.encode()).hexdigest(),
                    turns=result.turns, generated_at=datetime.now(timezone.utc).isoformat())
    (output / "provenance.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"status": "available", "bytes": len(content.encode()), "history_items": len(history)}), flush=True)


if __name__ == "__main__":
    main()
