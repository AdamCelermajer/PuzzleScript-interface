"""Recorded model calls (harnesses/recorder.py): each call as sent and returned, and the Prompt build
page's view of a session as one conversation (workbench/prompt_build.py)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from workbench.catalog import run_path


def add_routes(router: APIRouter, root: Path, catalog_runs) -> None:
    call_rows: dict[tuple[str, int], dict] = {}  # (path, mtime) -> list row; call files never change once written

    def calls_folder(run: str, folder: str) -> Path:
        """A calls/ folder of the run: the player's (calls) or another session's (e.g. improver/sessions/x/calls)."""
        try:
            path = run_path(run, root)
            target = run_path(run + "/" + folder, root)
            if Path(folder).name != "calls" or not target.is_relative_to(path) or any(
                    p.startswith(".") or p == "workspace" for p in Path(folder).parts):
                raise ValueError("Not a calls folder")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return target

    def read_call(item: Path) -> dict:
        try:
            record = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return record if isinstance(record, dict) else {}

    @router.get("/record/calls/folders")
    def call_folders(run: str = Query(...)):
        """Every session of the run that recorded its model calls (harnesses/recorder.py)."""
        try:
            path = run_path(run, root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        folders = []
        for item in sorted(path.rglob("calls")):
            relative = item.relative_to(path)
            if (item.is_dir() and not item.is_symlink() and (item / "0001.json").is_file()
                    and not any(p.startswith(".") or p == "workspace" for p in relative.parts)):
                folders.append({"folder": relative.as_posix(), "calls": len(list(item.glob("[0-9][0-9][0-9][0-9].json")))})
        return {"folders": folders}

    @router.get("/record/calls")
    def calls(run: str = Query(...), folder: str = "calls"):
        """Every model call of one session, one row each."""
        from harnesses.recorder import view
        rows = []
        for item in sorted(calls_folder(run, folder).glob("[0-9][0-9][0-9][0-9].json")):
            key = (str(item), item.stat().st_mtime_ns)
            if key not in call_rows:
                record = read_call(item)
                response = record.get("response") or {}
                call_rows[key] = {
                    "call": record.get("call"), "turn": record.get("turn"), "started": record.get("started"),
                    "seconds": record.get("seconds"), "method": record.get("method"), "url": record.get("url"),
                    "status": record.get("status"), "error": record.get("error"),
                    "messages": len(view(record.get("request"))["messages"]), "images": len(record.get("images") or []),
                    "bytes": item.stat().st_size, "usage": response.get("usage") or None,
                    "tool_calls": [c.get("name") for c in response.get("tool_calls") or []],
                    "replied": bool(response.get("content"))}
            rows.append(call_rows[key])
        return {"calls": rows}

    @router.get("/record/calls/one")
    def one_call(run: str = Query(...), call: int = Query(..., ge=1, le=9999), folder: str = "calls"):
        """One call as saved, in one shape whatever the API, and how much of its context the previous
        call of the same session already sent unchanged."""
        from harnesses.recorder import view
        directory = calls_folder(run, folder)
        record = read_call(directory / f"{call:04d}.json")
        if not record:
            raise HTTPException(404, "No such call")
        shown = view(record.get("request"))
        previous = None
        for number in range(call - 1, 0, -1):  # the last model request before it (skips model lists)
            earlier = read_call(directory / f"{number:04d}.json")
            if earlier.get("method") == "POST":
                previous = view(earlier.get("request"))
                break
        from workbench.prompt_build import kept_messages
        same = kept_messages(previous["messages"], shown["messages"], directory) if previous is not None else 0
        return {**record, "view": shown, "previous_messages": len(previous["messages"]) if previous else None,
                "unchanged_messages": same, "system_changed": bool(previous) and previous["system"] != shown["system"]}

    build_folders: dict[str, tuple[float, list[Path]]] = {}  # run id -> (modified, its calls/ folders)
    MODES = {("baseline", "agent"): (0, "Baseline agentic"), ("baseline", "controller"): (1, "Baseline turn-based"),
             ("avo", None): (2, "AVO"), ("harness2", None): (3, "Harness²")}

    @router.get("/prompt-builds")
    def prompt_builds():
        """Runs with recorded model calls, newest first, each with its recorded sessions."""
        from workbench.prompt_build import call_folders, read_json as read_session
        rows = []
        for run in catalog_runs():
            modified = run.get("modified") or 0
            if run["id"] not in build_folders or build_folders[run["id"]][0] != modified:
                try:
                    build_folders[run["id"]] = (modified, call_folders(run_path(run["id"], root)))
                except ValueError:
                    continue
            folders = build_folders[run["id"]][1]
            if not folders:
                continue
            path = run_path(run["id"], root)
            mode = MODES.get((run.get("framework"), (run.get("options") or {}).get("driver", "controller")),
                             MODES.get((run.get("framework"), None), (9, run.get("framework") or "run")))
            rows.append({key: run.get(key) for key in ("id", "harness", "model", "game_id", "modified")} | {
                "mode": mode[1], "order": mode[0],
                "sessions": [{"folder": f.relative_to(path).as_posix(),
                              "role": read_session(f.parent / "session.json").get("role"),
                              "calls": len(list(f.glob("[0-9][0-9][0-9][0-9].json")))} for f in folders]})
        # Framework and mode first (the comparison that matters), newest run first within each.
        return {"runs": sorted(rows, key=lambda r: (r["order"], -(r["modified"] or 0)))}

    @router.get("/prompt-builds/one")
    def prompt_build(run: str = Query(...), folder: str = "calls"):
        """One recorded session as a conversation: system prompt, tools, then every message once, in order."""
        from workbench.prompt_build import transcript
        return transcript(calls_folder(run, folder).parent)

    @router.get("/record/calls/file")
    def call_file(run: str = Query(...), folder: str = "calls",
                  name: str = Query(..., pattern=r"^[0-9]{4}(-image-[0-9]+\.(png|jpeg|jpg|webp|gif)|\.response\.txt)$")):
        target = calls_folder(run, folder) / name
        if not target.is_file() or target.is_symlink():
            raise HTTPException(404, "No such file")
        return FileResponse(target, media_type="text/plain" if name.endswith(".txt") else None)

