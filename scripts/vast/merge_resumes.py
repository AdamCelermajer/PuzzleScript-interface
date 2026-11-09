"""Join a batch and its resumes into one new batch: each game and driver becomes one run from the first move to the last,
with calls, turns and player files numbered straight through. The original folders are not changed: files are hard-linked,
and only what must be renumbered is written anew. merged_from.json in each run says where its conversation restarted.

    uv run python scripts/vast/merge_resumes.py BATCH RESUME_BATCH [RESUME_BATCH ...]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKBENCH = ROOT / "output" / "workbench"
IMAGE = re.compile(r"(\d{4})-image-(\d+)")
JOINED = ("sent.jsonl", "turns.jsonl", "agent_events.jsonl", "transcript.jsonl")
FROM_LAST = ("transitions.jsonl", "result.json", "session.json", "system_prompt.txt", "isolation_manifest.json", "world_model.md", "solver.py")
FROM_FIRST = ("run_config.json", "run_spec.json", "launcher.json")


def link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def link_tree(source: Path, target: Path) -> None:
    """Every file below source, skipping what target already holds."""
    for item in source.rglob("*"):
        if item.is_file() and not item.is_symlink():
            destination = target / item.relative_to(source)
            if not destination.exists():
                link(item, destination)


def merge_calls(part: Path, out: Path, call_offset: int, turn_offset: int) -> int:
    """Copy one part's calls, moved up by the offsets. Returns the highest call number written."""
    calls = part / "calls"
    highest = call_offset
    if not calls.is_dir():
        return highest
    moved = lambda m: f"{int(m.group(1)) + call_offset:04d}-image-{m.group(2)}"
    (out / "calls").mkdir(parents=True, exist_ok=True)
    for item in sorted(calls.iterdir()):
        match = re.match(r"(\d{4})(.*)", item.name)
        if not match:
            continue
        number = int(match.group(1)) + call_offset
        highest = max(highest, number)
        target = out / "calls" / f"{number:04d}{match.group(2)}"
        if item.name.endswith(".json"):
            record = json.loads(IMAGE.sub(moved, item.read_text(encoding="utf-8")))
            record["call"] = number
            if isinstance(record.get("turn"), int):
                record["turn"] += turn_offset
            target.write_text(json.dumps(record), encoding="utf-8")
        else:
            link(item, target)
    return highest


def merge_raw(part: Path, out: Path, turn_offset: int) -> int:
    """raw/turn-N.* moved up by the offset. Returns the highest turn written."""
    highest = turn_offset
    if not (part / "raw").is_dir():
        return highest
    for item in (part / "raw").iterdir():
        match = re.fullmatch(r"turn-(\d+)(\..+)", item.name)
        if match:
            number = int(match.group(1)) + turn_offset
            highest = max(highest, number)
            link(item, out / "raw" / f"turn-{number}{match.group(2)}")
    return highest


def merge_notes_history(part: Path, out: Path, turn_offset: int) -> None:
    source = part / "notes_history"
    if not source.is_dir():
        return
    for item in source.iterdir():
        match = re.fullmatch(r"turn-(\d+)", item.name)
        if match and item.is_dir():
            link_tree(item, out / "notes_history" / f"turn-{int(match.group(1)) + turn_offset:04d}")
        elif item.is_file():
            target = out / "notes_history" / item.name
            if not target.exists():
                link(item, target)


def join_lines(part: Path, out: Path, name: str, turn_offset: int) -> None:
    source = part / name
    if not source.is_file():
        return
    with (out / name).open("a", encoding="utf-8") as stream:
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row.get("turn"), int):
                row["turn"] += turn_offset
            stream.write(json.dumps(row) + "\n")


def merge_agent_files(parts: list[Path], out: Path, turn_offsets: list[int]) -> None:
    """The player's files, version by version. A resume's "at the start" repeats the parent's last version, so it is left out."""
    latest: dict[str, int] = {}
    rows = []
    for k, part in enumerate(parts):
        index = part / "agent_files" / "index.jsonl"
        if not index.is_file():
            continue
        for line in index.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if k and row.get("label") == "at the start":
                continue
            turn_based = str(row.get("label", "")).startswith("after turn")
            at = int(row.get("at") or 0) + (turn_offsets[k] if turn_based else 0)
            at = max(at, latest.get(row["path"], -1) + 1)
            latest[row["path"]] = at
            row["at"] = at
            if turn_based:
                row["label"] = f"after turn {at}"
            if row.get("file"):
                link(part / "agent_files" / row["file"], out / "agent_files" / f"part-{k + 1}" / row["file"])
                row["file"] = f"part-{k + 1}/{row['file']}"
            rows.append(row)
    if rows:
        (out / "agent_files").mkdir(parents=True, exist_ok=True)
        (out / "agent_files" / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def merge_run(parts: list[Path], out: Path) -> dict:
    out.mkdir(parents=True)
    call_offset, turn_offset, offsets, restarts = 0, 0, [], []
    for k, part in enumerate(parts):
        offsets.append(turn_offset)
        if k:
            moves = len((parts[k - 1] / "transitions.jsonl").read_text(encoding="utf-8").splitlines())
            error = json.loads((parts[k - 1] / "error.json").read_text(encoding="utf-8")) if (parts[k - 1] / "error.json").is_file() else {}
            restarts.append({"after_move": moves, "first_call": call_offset + 1, "first_turn": turn_offset + 1, "why": error.get("message") or "the run stopped"})
        highest_call = merge_calls(part, out, call_offset, turn_offset)
        highest_turn = merge_raw(part, out, turn_offset)
        merge_notes_history(part, out, turn_offset)
        for name in JOINED:
            join_lines(part, out, name, turn_offset)
        call_offset, turn_offset = highest_call, highest_turn
    merge_agent_files(parts, out, offsets)
    last = parts[-1]
    for name in FROM_LAST:
        if (last / name).is_file():
            link(last / name, out / name)
    for name in FROM_FIRST:
        if (parts[0] / name).is_file():
            link(parts[0] / name, out / name)
    for name in ("frames", "workspace"):
        if (last / name).is_dir():
            link_tree(last / name, out / name)
    for part in reversed(parts):
        if (part / "world_model_snapshots").is_dir():
            link_tree(part / "world_model_snapshots", out / "world_model_snapshots")
    record = {"parts": [p.relative_to(ROOT).as_posix() for p in parts], "restarts": restarts,
              "note": "One game played across these folders. Each restart began a new conversation with the same board, files and move count."}
    (out / "merged_from.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main(argv: list[str]) -> None:
    batch = WORKBENCH / argv[0]
    job = json.loads((batch / "job.json").read_text(encoding="utf-8"))
    resumes = [json.loads((WORKBENCH / name / "job.json").read_text(encoding="utf-8")) | {"_name": name} for name in argv[1:]]
    resumes.sort(key=lambda r: r["_name"])
    target = WORKBENCH / f"{argv[0].rsplit('-', 1)[0]}-merged"
    if target.exists():
        raise SystemExit(f"{target} already exists")
    rows, archived = [], []
    for row in job["runs"]:
        parts = [Path(row["output"])]
        for resume in resumes:
            for other in resume["runs"]:
                if other["game_id"] == row["game_id"] and other["options"]["driver"] == row["options"]["driver"]:
                    parts.append(Path(other["output"]))
                    archived.append(other["id"])
        archived.append(row["id"])
        out = target / parts[0].name
        record = merge_run(parts, out)
        moves = len((out / "transitions.jsonl").read_text(encoding="utf-8").splitlines())
        rows.append({**{k: v for k, v in row.items() if k not in ("pid", "returncode")}, "id": out.relative_to(ROOT).as_posix(), "output": str(out),
                     "status": "completed", "returncode": 0})
        print(out.name, row["game_id"], row["options"]["driver"], "parts", len(parts), "moves", moves, "restarts", [r["after_move"] for r in record["restarts"]])
    manifest = {**job, "status": "completed", "heartbeat": time.time(), "runs": rows, "merged_from": [argv[0], *argv[1:]],
                "config": {**job["config"], "label": job["config"].get("label", "") + " (merged)"}}
    manifest.pop("worker_pid", None)
    (target / "job.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("batch:", target.relative_to(ROOT).as_posix())
    print(json.dumps({"archive": archived}))


if __name__ == "__main__":
    main(sys.argv[1:])
