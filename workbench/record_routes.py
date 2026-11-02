"""One run's files: its record (config, result, agent events, prompts), timeline, notes history,
Harness² coach sessions, AVO submissions and single artifacts."""
from __future__ import annotations

import bisect
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse

from workbench.catalog import last_record, normalized_spec, read_json, read_run_spec, run_path
from workbench.session_view import attach_diffs, session_prompts


RECORD_FILES = ("run_spec.json", "run_config.json", "result.json", "error.json", "restoration.json", "transitions.jsonl",
                "transcript.jsonl", "codex_session.jsonl", "model_session.jsonl", "isolation_manifest.json",
                "agent_events.jsonl", "analysis/agent_events.jsonl", "system_prompt.txt", "turns.jsonl", "session.json",
                "world_model.md", "solver.py", "player.log", "launcher.json", "adoption.json", "harness2_config.json")
AGENT_EVENT_FIELDS = ("schema", "t", "session", "role", "turn", "type", "text", "output", "exit_code", "tool",
                      "usage", "harness", "model")


def agent_events_path(path: Path) -> Path | None:
    return next((p for p in (path / "agent_events.jsonl", path / "analysis/agent_events.jsonl") if p.is_file()), None)


def read_agent_events(path: Path, limit: int) -> dict:
    """Tail of a normalized `agent-event-v1` log; malformed lines are counted, not fatal."""
    from collections import deque
    events, total, invalid = deque(maxlen=limit or None), 0, 0
    file_edits: dict = {}  # turn -> file edits seen so far, to find each one in the raw turn record
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                invalid += 1
                continue
            if not isinstance(item, dict) or not item.get("type"):
                invalid += 1
                continue
            total += 1
            index = None
            if item.get("type") == "file_change":
                index = file_edits.get(item.get("turn"), 0)
                file_edits[item.get("turn")] = index + 1
            if limit:
                event = {key: item.get(key) for key in AGENT_EVENT_FIELDS}
                event["schema"] = event["schema"] or "agent-event-v1"
                for key in ("text", "output"):
                    if isinstance(event[key], str) and len(event[key]) > 16000:
                        event[key] = event[key][:16000] + "\n[truncated]"
                if index is not None:
                    event["_turn"], event["_file_index"] = item.get("turn"), index
                events.append(event)
    events = list(events)
    try:
        attach_diffs(path.parent, events)
    except (OSError, ValueError) as exc:  # a diff is a convenience; the timeline must still load
        for event in events:
            if event.get("type") == "file_change":
                event["diff_note"] = f"diff unavailable: {exc}"
    for event in events:
        event.pop("_turn", None)
        event.pop("_file_index", None)
    return {"total": total, "invalid_lines": invalid, "truncated": total > len(events), "events": events}


def add_routes(router: APIRouter, root: Path) -> None:
    @router.get("/submission")
    def get_submission(run: str = Query(...), candidate: str = ""):
        from workbench.submissions import submission
        try:
            return submission(run, root, candidate)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/submission/file")
    def get_submission_file(run: str = Query(...), file: str = Query(...), download: bool = False):
        from workbench.submissions import submission_file
        try:
            target = submission_file(run, file, root)
            if download:
                return FileResponse(target, filename=target.name)
            if target.stat().st_size > 2_000_000:
                raise HTTPException(413, "File is too large to preview; use Download")
            return Response(target.read_text(encoding="utf-8", errors="replace"), media_type="text/plain",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/submission/download")
    def download_submission(run: str = Query(...), candidate: str = ""):
        import io
        import zipfile
        from workbench.submissions import submission, submission_file
        try:
            record = submission(run, root, candidate)
            if not record["solver_present"]:
                raise HTTPException(404, "No evaluated solver.py is available")
            if sum(f["size"] for f in record["files"]) > 128_000_000:
                raise HTTPException(413, "Submission exceeds the 128 MB download limit")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in record["files"]:
                    # Preserve the evaluated directory intact, including relative helper paths.
                    archive.write(submission_file(run, item["path"], root), "solver/" + item["name"])
                if record["world_model"]:
                    archive.write(submission_file(run, "world_model.md", root), "world_model.md")
                archive.writestr("submission_record.json", json.dumps(record, indent=2))
            return Response(buffer.getvalue(), media_type="application/zip",
                            headers={"Content-Disposition": 'attachment; filename="avo-submission.zip"'})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/record")
    def record(run: str = Query(...), events_limit: int = Query(500, ge=0, le=5000)):
        try:
            path = run_path(run, root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        spec = read_run_spec(path)
        if not (path / "run_config.json").is_file() and not spec:
            raise HTTPException(404, "Direct-player run not found")
        config = read_json(path / "run_config.json")
        names = [*RECORD_FILES]
        notes = []
        for note in (path / "workspace").glob("*.md"):
            if not note.is_symlink():
                notes.append(note.relative_to(path).as_posix())
        for note in (path / "workspace/notes").glob("*.md"):
            if not note.is_symlink():
                notes.append(note.relative_to(path).as_posix())
        for note in sorted((path / "world_model_snapshots").glob("*.md")):
            if not note.is_symlink():
                notes.append(note.relative_to(path).as_posix())
        events = agent_events_path(path)
        # Harness² keeps one direct-player run per rollout (base1, inv1, dom1, agg1, final).
        rollouts = sorted((p for p in (path / "rollouts").glob("*") if (p / "run_config.json").is_file()),
                          key=lambda p: (p / "run_config.json").stat().st_mtime)
        return {"id": run, "config": config, "run_spec": spec or None,
                "normalized": normalized_spec(path, config, False), "result": read_json(path / "result.json"),
                "error": read_json(path / "error.json"), "latest_transition": last_record(path / "transitions.jsonl"),
                # Normalized harness events when present; otherwise the legacy session files above.
                "agent_events": read_agent_events(events, events_limit) if events else None,
                "prompts": session_prompts(events.parent) if events else None,
                "files": [name for name in names + notes if (path / name).is_file()],
                "rollouts": [{"label": p.name, "result": read_json(p / "result.json") or None,
                              "latest_transition": last_record(p / "transitions.jsonl")} for p in rollouts],
                "adoption": read_json(path / "adoption.json") or None,
                "has_calls": any(path.rglob("calls/0001.json")),
                **harness2_views(path)}

    def harness2_views(path: Path) -> dict:
        if (path / "levels").is_dir() and (path / "harness2_config.json").is_file():
            from workbench.harness2_view import levels
            return {"levels": levels(path)}
        if not (path / "improver").is_dir() and not (path / "harnesses").is_dir():
            return {}
        from workbench.harness2_view import coach_sessions, harness_diffs, harness_edits
        return {"coach_sessions": coach_sessions(path), "harness_edits": harness_edits(path),
                "harness_diffs": harness_diffs(path)}

    @router.get("/harness2/session")
    def harness2_session(run: str = Query(...), session: str = Query(..., pattern=r"^[\w.-]+$"),
                         events_limit: int = Query(500, ge=1, le=5000)):
        try:
            events = run_path(run, root) / "improver" / "sessions" / session / "agent_events.jsonl"
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not events.is_file():
            raise HTTPException(404, "No such coach session")
        return {"agent_events": read_agent_events(events, events_limit), "prompts": session_prompts(events.parent)}

    @router.get("/record/timeline")
    def timeline(run: str = Query(...), index: int = Query(..., ge=1, le=100000)):
        try:
            path = run_path(run, root)
            with (path / "transitions.jsonl").open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                        if item.get("action_index") == index:
                            return {"transition": item}
                    except (ValueError, AttributeError):
                        continue
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError:
            pass
        raise HTTPException(404, "Transition not found")

    def history_files(folder: Path) -> dict[str, str]:
        files = {}
        for item in sorted(folder.rglob("*")):
            name = item.relative_to(folder).as_posix()
            if (item.is_file() and not item.is_symlink() and item.resolve().is_relative_to(folder.resolve())
                    and not any(p.startswith(".") for p in Path(name).parts)):
                files[name] = item.read_text(encoding="utf-8", errors="replace")[:200_000]
        return files

    @router.get("/record/notes_history")
    def notes_history(run: str = Query(...)):
        """The notes/ folder after every harness turn, with the move each turn produced."""
        try:
            path = run_path(run, root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        folders = {int(p.name[5:]): p for p in (path / "notes_history").glob("turn-*")
                   if re.fullmatch(r"turn-[0-9]{4,6}", p.name) and p.is_dir() and not p.is_symlink()}
        rows = {}
        for name in ("turns.jsonl", "transitions.jsonl"):
            try:
                lines = (path / name).read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            rows[name] = []
            for line in lines:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and isinstance(item.get("timestamp"), str):
                    rows[name].append(item)
        turns = {row.get("turn"): row for row in rows["turns.jsonl"]}
        # A move comes from the last game-action turn that ended before it was played: a decision's
        # retried turns and correction turns all come earlier, and the transition is written right after.
        game_turns = [row for row in rows["turns.jsonl"] if row.get("turn_kind") == "game_action"]
        stamps = [row["timestamp"] for row in game_turns]
        moves = {}
        for transition in rows["transitions.jsonl"]:
            produced = bisect.bisect_right(stamps, transition["timestamp"])
            if produced:
                moves.setdefault(game_turns[produced - 1].get("turn"), transition.get("action_index"))
        return {"turns": [{"turn": number, "kind": turns.get(number, {}).get("turn_kind"),
                           "timestamp": turns.get(number, {}).get("timestamp"), "action_index": moves.get(number),
                           "files": list(history_files(folders[number]))} for number in sorted(folders)]}

    @router.get("/record/notes_history/turn")
    def notes_history_turn(run: str = Query(...), turn: int = Query(..., ge=1, le=999999)):
        """One turn's notes, and a unified diff of each file that changed since the turn before."""
        import difflib
        try:
            folder = run_path(run, root) / "notes_history"
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        current = folder / f"turn-{turn:04d}"
        if not current.is_dir() or current.is_symlink():
            raise HTTPException(404, "No notes saved for this turn")
        earlier = sorted(int(p.name[5:]) for p in folder.glob("turn-*")
                         if re.fullmatch(r"turn-[0-9]{4,6}", p.name) and p.is_dir() and not p.is_symlink()
                         and int(p.name[5:]) < turn)
        previous = earlier[-1] if earlier else None
        files = history_files(current)
        old_files = history_files(folder / f"turn-{previous:04d}") if previous else {}
        diffs = {}
        for name in sorted({*files, *old_files}):
            old, new = old_files.get(name, ""), files.get(name, "")
            if old != new:
                before = f"turn-{previous}/{name}" if previous else "/dev/null"
                diffs[name] = "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), before,
                                                             f"turn-{turn}/{name}", lineterm="", n=3))
        return {"turn": turn, "previous": previous, "files": files, "diffs": diffs}

    @router.get("/record/file")
    def record_file(run: str = Query(...), file: str = Query(...)):
        try:
            path = run_path(run, root)
            target = run_path(run + "/" + file, root)
            allowed = set(RECORD_FILES)
            parts = Path(file).parts
            note = target.suffix == ".md" and (
                (len(parts) == 2 and parts[0] in {"workspace", "world_model_snapshots"})
                or (len(parts) == 3 and parts[:2] == ("workspace", "notes")))
            frame = re.fullmatch(r"frames/[0-9]{3,}\.png", file) is not None
            raw_turn = re.fullmatch(r"(?:analysis/)?raw/turn-[0-9]{1,6}\.jsonl", file) is not None
            if not target.is_relative_to(path) or not (file in allowed or note or frame or raw_turn):
                raise ValueError("Invalid artifact")
            if any(p.startswith(".") for p in Path(file).parts) or "model_requests" in Path(file).parts:
                raise ValueError("Artifact is not available here")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not target.is_file():
            raise HTTPException(404, "Artifact not found")
        if frame:
            return FileResponse(target, media_type="image/png")
        return FileResponse(target, filename=target.name)

