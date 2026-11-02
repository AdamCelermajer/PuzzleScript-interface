"""AVO console and notebook routes formerly served by Vite middleware.

`/avo/*` reads saved campaign artifacts (path-traversal and link safe); the live
frame view replays saved evidence in an isolated Node worker. `/notes` and
`/pseudocode` save allowlisted Markdown files. Errors keep the `{"error": ...}`
shape the browser already reads.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import shutil
import subprocess
import threading
from collections import OrderedDict
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from workbench.catalog import ROOT

MAX_ARTIFACT_BYTES = 512 * 1024
MAX_MARKDOWN_BYTES = 1024 * 1024
NOTES_FILES = {"workbench-notes.md", "todo.md", "benchmark-positioning.md"}
SKIPPED_PARTS = {".sandboxes", ".avo_rpc", "__pycache__", "model_requests", "workspace_blobs"}
READABLE = {".json", ".jsonl", ".md", ".txt", ".py", ".toml", ".yaml", ".yml", ".log"}
WORKER = Path(__file__).with_name("avo_replay_worker.cjs")


class RouteError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def send(payload, status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


def guarded(fallback: str, action: Callable[[], object]) -> JSONResponse:
    try:
        return send(action())
    except RouteError as exc:
        return send({"error": str(exc)}, exc.status)
    except Exception as exc:  # Same contract as the Vite bridge: a JSON error, never a crash page.
        return send({"error": str(exc) or fallback}, 500)


# ------------------------------------------------------------------ files

def read_json_safe(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def read_json_lines(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def file_modified_ms(path: Path) -> float:
    try:
        return path.stat().st_mtime * 1000
    except OSError:
        return 0


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def inside_real(base, target) -> bool:
    """`target` stays under `base` after resolving links (the base itself may be linked)."""
    real_base, real_target = os.path.realpath(base).lower(), os.path.realpath(target).lower()
    return real_target == real_base or real_target.startswith(real_base.rstrip(os.sep) + os.sep)


def resolve_avo_run(root: Path, run_id) -> Path | None:
    """Port of website/run-paths.js: approved roots, no links, a real campaign."""
    import re
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", run_id):
        return None
    if any(part in {"", ".", ".."} for part in run_id.split("/")):
        return None
    base = os.path.abspath(root)
    candidate = os.path.normpath(os.path.join(base, run_id) if "/" in run_id
                                 else os.path.join(base, "avo", "output", "evolution", run_id))
    roots = [os.path.normpath(os.path.join(base, *b.split("/"))) for b in ("avo/output", "output")]
    if not any(candidate.startswith(r + os.sep) for r in roots):
        return None
    try:
        cursor = Path(base)
        for part in Path(os.path.relpath(candidate, base)).parts:
            cursor = cursor / part
            if _linked(cursor):
                return None
        if os.path.realpath(candidate).lower() != os.path.join(os.path.realpath(base), os.path.relpath(candidate, base)).lower():
            return None
        if not (Path(candidate) / "evolution_config.json").is_file():
            return None
    except OSError:
        return None
    return Path(candidate)


def safe_resolve(base: Path, request_path: str) -> Path | None:
    relative = unquote(request_path).lstrip("/")
    target = Path(os.path.normpath(os.path.join(base, relative)))
    if target != base and not str(target).startswith(str(base) + os.sep):
        return None
    if not inside_real(base, target):
        return None  # A link inside the run must not expose another directory.
    return target


# ---------------------------------------------------------- evidence summary

_summaries: OrderedDict = OrderedDict()
_summary_lock = threading.Lock()


def evidence_summary(path: Path, recent_limit: int = 0) -> dict:
    """Port of website/evidence-summary.mjs, cached by file size and mtime."""
    empty = {"actions": 0, "levels": 0, "events": 0, "last_event": "", "last_transition": None, "recent": []}
    try:
        stat = path.stat()
    except OSError:
        return empty
    key = str(path)
    with _summary_lock:
        saved = _summaries.get(key)
        if saved and saved["size"] == stat.st_size and saved["mtime"] == stat.st_mtime_ns and saved["recent_limit"] >= recent_limit:
            _summaries.move_to_end(key)
            return saved["summary"]
    summary = {**empty, "recent": []}
    for event in read_json_lines(path):
        summary["events"] += 1
        summary["last_event"] = event.get("type") or ""
        if event.get("type") == "transition":
            summary["actions"] += 1
            summary["last_transition"] = event
            level = (((event.get("payload") or {}).get("after") or {}).get("progress") or {}).get("levels_completed")
            if isinstance(level, (int, float)) and not isinstance(level, bool):
                summary["levels"] = max(summary["levels"], level)
        if recent_limit:
            summary["recent"].append(event)
            if len(summary["recent"]) > recent_limit:
                summary["recent"].sort(key=lambda e: str(e.get("recorded_at") or ""))
                summary["recent"].pop(0)
    with _summary_lock:
        _summaries[key] = {"size": stat.st_size, "mtime": stat.st_mtime_ns, "recent_limit": recent_limit, "summary": summary}
        _summaries.move_to_end(key)
        while len(_summaries) > 128:
            _summaries.popitem(last=False)
    return summary


def dig(value, *keys):
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def level_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def evaluation_levels(evaluation) -> int | None:
    return (level_count(dig(evaluation, "score", "environment_task", "score", "win_levels"))
            or level_count(dig(evaluation, "score", "win_levels"))
            or level_count(dig(evaluation, "score", "research_score", "win_levels")))


def first(*values):
    return next((v for v in values if v is not None), None)


# ------------------------------------------------------------------ run snapshot

def avo_runs(root: Path, catalog_runs: Callable[[], list[dict]]) -> list[dict]:
    return [{"run_id": run["id"], "modified": run.get("modified"), "status": run.get("status"),
             "can_resume": run.get("can_resume"), "resumed_as": run.get("resumed_as"),
             "label": f"{run.get('game_id') or 'AVO'} · {run.get('batch')} · {'/'.join(run['id'].split('/')[-2:])}"}
            for run in catalog_runs() if run.get("kind") == "avo" and resolve_avo_run(root, run["id"])]


def avo_snapshot(root: Path, run_id, catalog_runs: Callable[[], list[dict]]) -> dict:
    path = resolve_avo_run(root, run_id)
    if path is None:
        raise RouteError(400, "Invalid AVO run")
    if not path.is_dir():
        raise RouteError(404, "AVO run not found")
    config, lineage = read_json_safe(path / "evolution_config.json"), read_json_safe(path / "lineage.json")
    entries = lineage.get("candidates") if isinstance(lineage.get("candidates"), list) else []
    evaluations = lineage.get("evaluations") if isinstance(lineage.get("evaluations"), list) else []
    candidate_ids = [e.get("candidate_id") for e in entries if isinstance(e, dict) and e.get("candidate_id")]
    current_id = candidate_ids[-1] if candidate_ids else ""
    current = path / current_id if current_id else path
    research = evidence_summary(current / "research/evidence.jsonl", 12)
    fresh = evidence_summary(current / "evaluation/evidence.jsonl", 12)
    summary = read_json_safe(current / "summary.json")
    solver_evaluation = read_json_safe(current / "evaluation/solver_evaluation.json")
    solver_archived = bool(file_modified_ms(current / "solver/solver.py"))
    latest = evaluations[-1] if evaluations and isinstance(evaluations[-1], dict) else {}
    # Research score (frameworks/avo/research_score.py): no solver, so no fresh evaluation phase.
    score = "research" if config.get("fitness") == "research" else "solver"
    if score == "research":
        phase = ("evaluated" if summary else "research" if research["events"]
                 else "pending" if current_id else "initializing")
    else:
        phase = ("evaluated" if summary else "finishing_evaluation" if solver_evaluation
                 else "fresh_evaluation" if fresh["events"] else "starting_fresh_evaluation" if solver_archived
                 else "research" if research["events"] else "pending" if current_id else "initializing")
    activity = max([0] + [file_modified_ms(p) for p in (
        path / "evolution_config.json", path / "lineage.json", path / "optimizer_analysis/conversation.jsonl",
        current / "summary.json", current / "research/evidence.jsonl", current / "research/analysis/conversation.jsonl",
        current / "evaluation/evidence.jsonl", current / "solver/solver.py")])

    def side(summary_: dict) -> dict:
        last = summary_["last_transition"]
        return {"actions": summary_["actions"], "levels": summary_["levels"],
                "last_activity": (last or {}).get("recorded_at") or None,
                "revision": first((last or {}).get("sequence"), 0),
                "fallback_frame": dig(last, "payload", "after", "payload", "frame") or []}

    candidates = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        candidate_id = entry.get("candidate_id")
        evaluation = next((e for e in evaluations if isinstance(e, dict) and e.get("candidate_id") == candidate_id), {})
        candidate_summary = read_json_safe(path / str(candidate_id) / "summary.json")
        candidate_research = research if candidate_id == current_id else evidence_summary(path / str(candidate_id) / "research/evidence.jsonl")
        candidate_evaluation = fresh if candidate_id == current_id else evidence_summary(path / str(candidate_id) / "evaluation/evidence.jsonl")
        candidates.append({
            "candidate_id": candidate_id, "parent_ids": entry.get("parent_ids") or entry.get("parents") or [],
            "evaluated": bool(candidate_summary or evaluation),
            "fitness": first(evaluation.get("fitness"), candidate_summary.get("fitness")),
            "actions_to_best": dig(evaluation, "score", "actions_to_best"),  # research score's tie-break
            "research_budget": dig(evaluation, "score", "research_moves_budget"),  # AVO3: moves this attempt had
            "success": first(evaluation.get("success"), candidate_summary.get("success")),
            "win_levels": first(evaluation_levels(evaluation),
                                dig(candidate_evaluation["last_transition"], "payload", "after", "progress", "win_levels")),
            "research": side(candidate_research), "evaluation": side(candidate_evaluation)})

    recent = sorted(research["recent"] + fresh["recent"], key=lambda e: str(e.get("recorded_at") or ""))[-12:]
    recent_activity = []
    for event in recent:
        transition = event.get("type") == "transition"
        after = dig(event, "payload", "after") or {}
        recent_activity.append({
            "type": event.get("type"), "recorded_at": event.get("recorded_at"),
            "action": dig(event, "payload", "action", "id"),
            "title": dig(event, "payload", "action", "id") if transition else str(event.get("type") or "").replace("_", " "),
            "detail": (f"{after.get('status') or 'state'} · level {first(dig(after, 'progress', 'levels_completed'), 0)}"
                       if transition else f"event {'' if event.get('sequence') is None else event.get('sequence')}".strip())})
    last_transition = sorted([t for t in (research["last_transition"], fresh["last_transition"]) if t],
                             key=lambda e: str(e.get("recorded_at") or ""))
    last_transition = last_transition[-1] if last_transition else None
    canonical = path.relative_to(os.path.abspath(root)).as_posix()
    record = next((r for r in catalog_runs() if r.get("id") == canonical), None) or {}
    final_summary = read_json_safe(path / "evolution_summary.json")
    # AVO3: research moves per attempt; the current attempt's budget is the next rung.
    schedule = [v for v in (config.get("research_moves_schedule") or []) if isinstance(v, int)]
    research_budget = (schedule[min(len(evaluations), len(schedule) - 1)] if schedule
                       else dig(config, "player", "max_environment_steps"))
    return {
        "run_id": run_id, "game_id": dig(config, "profile_settings", "game_id") or "",
        "agent_backend": "opencode" if config.get("agent_backend") == "opencode" else "codex",
        "harness": record.get("harness"), "variant": record.get("variant"), "score": score,
        "player_model": dig(config, "player", "model") or "", "optimizer_model": config.get("optimizer_model") or "",
        "current": current_id or None, "phase": phase, "active": record.get("status") == "running",
        "process_status": record.get("status") or "unconfirmed", "can_resume": bool(record.get("can_resume")),
        "resumed_as": record.get("resumed_as") or None, "finalized": bool(final_summary),
        "world_model_available": bool(file_modified_ms(path / "world_model.md")),
        "hypotheses_registered": len(candidate_ids), "hypotheses_evaluated": len(evaluations),
        "max_hypotheses": config.get("max_evaluations"),
        "win_levels": first(evaluation_levels(latest), dig(last_transition, "payload", "after", "progress", "win_levels"),
                            dig(config, "initial_observation", "progress", "win_levels")),
        "research": {**{k: research[k] for k in ("actions", "levels", "events", "last_event", "last_transition")},
                     "budget": research_budget},
        "research_schedule": schedule,
        "final_solver": read_json_safe(path / "final_solver" / "summary.json") or None,
        "fresh_evaluation": {**{k: fresh[k] for k in ("actions", "levels", "events", "last_event", "last_transition")},
                             "budget": config.get("fresh_solver_max_environment_steps")},
        "last_transition": ({"sequence": last_transition.get("sequence"), "action": dig(last_transition, "payload", "action"),
                             "after": dig(last_transition, "payload", "after")} if last_transition else None),
        "latest_fitness": latest.get("fitness"), "latest_success": latest.get("success"),
        "last_activity": datetime.fromtimestamp(activity / 1000).astimezone().isoformat() if activity else None,
        "candidates": candidates,
        "frame_sessions": [
            {"candidate_id": c["candidate_id"], "phase": phase_name, "actions": c[phase_name]["actions"],
             "levels": c[phase_name]["levels"], "last_activity": c[phase_name]["last_activity"],
             "revision": c[phase_name]["revision"], "fallback_frame": c[phase_name]["fallback_frame"]}
            for c in candidates for phase_name in ("research", "evaluation") if c[phase_name]["actions"]],
        "recent_activity": recent_activity,
    }


# ------------------------------------------------------------------ frames

def parse_step(value):
    if value is None:
        return None
    text = value.strip()
    try:
        number = float(text) if text else 0.0  # JavaScript Number('') is 0.
    except ValueError:
        number = float("nan")
    return int(number) if number == number and number.is_integer() else number


def select_evidence_frame(events: list[dict], requested_step=None) -> dict:
    transitions = [e for e in events if e.get("type") == "transition"]
    total = len(transitions)
    step = total if requested_step is None else requested_step
    if not isinstance(step, int) or step < 0 or step > total:
        raise RouteError(400, "Replay step is outside the saved action history")
    event = transitions[step - 1] if step else next((e for e in events if e.get("type") == "episode_started"), None)
    observation = (dig(event, "payload", "after") if step
                   else dig(event, "payload", "observation") or dig(transitions[0] if transitions else None, "payload", "before"))
    if not observation:
        raise RouteError(404, "No saved observation for this step")
    return {"step": step, "total_actions": total, "observation": observation, "transition": {
        "sequence": (event or {}).get("sequence"), "recorded_at": (event or {}).get("recorded_at"),
        "action": dig(event, "payload", "action") if step else None, "status": observation.get("status") or "",
        "progress": observation.get("progress") or {}, "episode": dig(event, "payload", "episode")}}


def _reasoning_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(t for t in map(_reasoning_text, value) if t)
    if isinstance(value, dict):
        return _reasoning_text(first(value.get("text"), value.get("content"), value.get("summary")))
    return ""


def _time(value) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def reasoning_at_action(evidence: list[dict], conversation: list[dict], requested_step, phase: str) -> dict:
    """Timestamps establish proximity, not a one-to-one cause."""
    selected = select_evidence_frame(evidence, requested_step)
    step = selected["step"]
    if not step:
        return {"status": "initial"}
    if phase == "evaluation":
        return {"status": "offline_solver"}
    action_time = _time(selected["transition"]["recorded_at"])
    if action_time is None:
        return {"status": "unavailable"}
    transitions = [e for e in evidence if e.get("type") == "transition"]
    previous = _time(transitions[step - 2].get("recorded_at")) if step > 1 else None
    previous = previous if previous is not None else float("-inf")
    matching = []
    for event in conversation:
        if event.get("type") != "reasoning" and event.get("role") != "assistant_reasoning":
            continue
        item = event.get("item") or {}
        text = _reasoning_text(first(item.get("content"), item.get("summary"), event.get("content")))
        moment = _time(event.get("recorded_at"))
        if moment is not None and moment <= action_time and text.strip():
            matching.append((moment, event, text))
    if not matching:
        return {"status": "unavailable"}
    moment, event, text = sorted(matching, key=lambda m: m[0])[-1]
    return {"status": "captured", "text": text, "recorded_at": event.get("recorded_at"),
            "turn": event.get("turn"), "new_since_previous_action": moment > previous}


class ReplayWorker:
    """One persistent Node process holding incremental replay sessions."""

    def __init__(self, root: Path):
        self.root, self.lock, self.process, self.lines, self.ids = root, threading.Lock(), None, None, count(1)

    def _start(self):
        node = shutil.which("node")
        if not node:
            raise RouteError(503, "Node.js is required for live frame replay")
        self.process = subprocess.Popen([node, str(WORKER)], cwd=self.root, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.lines = queue.Queue()
        threading.Thread(target=self._read, args=(self.process, self.lines), daemon=True).start()

    @staticmethod
    def _read(process, lines):
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    def replay(self, game_id: str, key: str, evidence: Path, reset: bool = False) -> dict:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self._start()
            request_id = next(self.ids)
            message = {"id": request_id, "game_id": game_id, "key": key, "evidence_path": str(evidence), "reset": reset}
            try:
                self.process.stdin.write((json.dumps(message) + "\n").encode())
                self.process.stdin.flush()
                while True:
                    line = self.lines.get(timeout=120)
                    if line is None:
                        raise RouteError(500, "Replay worker exited")
                    reply = json.loads(line)
                    if reply.get("id") == request_id:
                        break
            except (OSError, queue.Empty, ValueError) as exc:
                self.close()
                raise RouteError(500, f"Replay worker failed: {exc}") from exc
        if not reply.get("ok"):
            raise RouteError(int(reply.get("status") or 500), reply.get("error") or "Could not render AVO frame")
        return reply

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
        self.process = None


def final_grid(frame):
    return frame[-1] if isinstance(frame, list) and frame and isinstance(frame[-1], list) else None


def avo_frame(root: Path, worker: ReplayWorker, run_id, candidate_id, phase, step_text, retried: bool = False) -> dict:
    import re
    path = resolve_avo_run(root, run_id)
    if path is None or not re.fullmatch(r"x_\d+", str(candidate_id or "")) or phase not in {"research", "evaluation"}:
        raise RouteError(400, "Invalid AVO frame session")
    config = read_json_safe(path / "evolution_config.json")
    game_id = str(dig(config, "profile_settings", "game_id") or "")
    if not game_id:
        raise RouteError(422, "Run does not identify a PuzzleScript game")
    evidence_path = path / candidate_id / phase / "evidence.jsonl"
    events = read_json_lines(evidence_path)
    step = parse_step(step_text)
    selected = select_evidence_frame(events, step)
    conversation = read_json_lines(path / candidate_id / "research/analysis/conversation.jsonl") if phase == "research" else []
    reasoning = reasoning_at_action(events, conversation, step, phase)
    stored = {"sequence": selected["transition"]["sequence"], "recorded_at": selected["transition"]["recorded_at"],
              "payload": {"after": selected["observation"], "action": selected["transition"]["action"],
                          "episode": selected["transition"]["episode"]}}
    position = {"step": selected["step"], "total_actions": selected["total_actions"]}
    transition = {"sequence": stored["sequence"], "recorded_at": stored["recorded_at"],
                  "action": stored["payload"]["action"] or None, "status": selected["observation"].get("status") or "",
                  "progress": selected["observation"].get("progress") or {}, "episode": stored["payload"]["episode"]}
    phase_root = Path(os.path.normpath(path / candidate_id / phase))
    rendered = dig(selected["observation"], "metadata", "rendered_frame") or {}
    frame_path = None
    if isinstance(rendered, dict) and rendered.get("artifact_path"):
        frame_path = Path(os.path.normpath(phase_root / str(rendered["artifact_path"])))
    elif isinstance(rendered, dict) and rendered.get("path"):
        frame_path = Path(os.path.abspath(str(rendered["path"])))
    if frame_path is not None and str(frame_path).startswith(str(phase_root) + os.sep):
        try:
            png = frame_path.read_bytes() if inside_real(phase_root, frame_path) else b""
            if png[:8] == b"\x89PNG\r\n\x1a\n":
                return {"candidate_id": candidate_id, "phase": phase, **position, "reasoning": reasoning,
                        "replay_exact": True, "source": "stored_observation_png",
                        "rendered_frame": {"data_url": "data:image/png;base64," + base64.b64encode(png).decode(),
                                           "mime_type": "image/png", "width": rendered.get("width"),
                                           "height": rendered.get("height")},
                        "fallback_frame": dig(selected["observation"], "payload", "frame") or [],
                        "transition": transition}
        except OSError:
            pass  # Older or partially written traces fall back to replay below.
    # Historical playback uses saved observations only; it never drives a live game.
    if step is not None:
        return {"candidate_id": candidate_id, "phase": phase, **position, "reasoning": reasoning, "replay_exact": True,
                "source": "stored_observation_grid", "rendered_frame": None,
                "fallback_frame": dig(selected["observation"], "payload", "frame") or [],
                "transition": selected["transition"]}
    replay = worker.replay(game_id, f"{run_id}/{candidate_id}/{phase}", evidence_path, reset=retried)
    stored_frame = dig(selected["observation"], "payload", "frame")
    exact = json.dumps(final_grid(replay.get("frame"))) == json.dumps(final_grid(stored_frame))
    if not exact and not retried:
        return avo_frame(root, worker, run_id, candidate_id, phase, step_text, retried=True)
    return {"candidate_id": candidate_id, "phase": phase, **position, "reasoning": reasoning, "replay_exact": exact,
            "source": "isolated_runtime_replay", "rendered_frame": replay.get("rendered_frame") if exact else None,
            "fallback_frame": stored_frame or [], "transition": transition}


# ------------------------------------------------------------------ logs

def text_from_content(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(t for t in map(text_from_content, value) if t)
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("text"), str):
        return value["text"]
    if isinstance(value.get("content"), str):
        return value["content"]
    return ""


def _js(value) -> str:
    return "" if value is None else str(value)


def normalize_conversation_event(event: dict, index: int, actor: str) -> dict:
    import re
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    kind = str(event.get("type") or item.get("type") or "conversation")
    role = str(event.get("role") or "unknown")
    common = {"id": f"{actor}-conversation-{index}", "actor": actor, "turn": event.get("turn"),
              "recorded_at": event.get("recorded_at")}
    if kind == "commandExecution":
        actions = "\n".join(str((a or {}).get("command") or "") for a in item.get("commandActions") or []
                            if (a or {}).get("command")) if isinstance(item.get("commandActions"), list) else ""
        command = actions or text_from_content(item.get("command")) or str(item.get("command") or "Command execution")
        line = command.splitlines()[0] if command else ""
        tool = re.search(r"avo_tool\.py\s+([A-Za-z0-9_-]+)", line, re.I)
        meta = [_js(item.get("status")), "" if item.get("exitCode") is None else f"exit {item['exitCode']}",
                "" if item.get("durationMs") is None else f"{item['durationMs']} ms"]
        return {**common, "role": "tool", "category": "tools", "kind": kind,
                "title": f"avo_tool · {tool.group(1)}" if tool else "Command", "summary": line[:240],
                "meta": " · ".join(m for m in meta if m), "input": command,
                "body": str(item.get("aggregatedOutput") or ""), "raw": event}
    if kind == "fileChange":
        changes = first(item.get("changes"), item.get("content"), [])
        return {**common, "role": "tool", "category": "tools", "kind": kind, "title": "File changes",
                "summary": item.get("status") or "Workspace updated", "meta": item.get("status") or "",
                "body": changes if isinstance(changes, str) else json.dumps(changes, indent=2), "raw": event}
    category = "reasoning" if kind == "reasoning" or role == "assistant_reasoning" else "conversation"
    body = (text_from_content(event.get("content")) or text_from_content(item.get("content"))
            or text_from_content(item.get("summary")) or text_from_content(item))
    title = ("Model reasoning" if category == "reasoning" else "Instruction to agent" if role == "user"
             else "Agent response" if role == "assistant" else f"{role} message")
    summary = next((line for line in body.splitlines() if line), "")[:180] or kind
    return {**common, "role": role, "category": category, "kind": kind, "title": title, "summary": summary,
            "body": body, "raw": event}


def normalize_conversation_events(events: list[dict], actor: str) -> list[dict]:
    seen, result = set(), []
    for index, event in enumerate(events):
        entry = normalize_conversation_event(event, index, actor)
        if entry["category"] == "reasoning" and not entry["body"].strip():
            continue
        if entry["category"] == "conversation" and entry["role"] == "user":
            key = f"{_js(entry['turn'])}:{entry['body'].strip()}"
            if key in seen:
                continue
            seen.add(key)
        result.append(entry)
    return result


def open_code_conversation(events: list[dict]) -> list[dict]:
    """Read-only compatibility for archived OpenCode runner logs."""
    parts, roles = {}, {}
    for event in events:
        payload = event.get("payload") or {}
        info = payload.get("info") or {}
        if info.get("id") and info.get("role"):
            roles[info["id"]] = info["role"]
        part = payload.get("part") or {}
        if part.get("id") and part.get("type") in {"tool", "text", "reasoning"}:
            parts[part["id"]] = {"event": event, "part": dict(part)}
        elif event.get("method") == "message.part.delta":
            entry = parts.get(payload.get("partID"))
            if entry and payload.get("field") == "text":
                entry["part"]["text"] = (entry["part"].get("text") or "") + (payload.get("delta") or "")
                entry["event"] = event
    result = []
    for entry in parts.values():
        event, part = entry["event"], entry["part"]
        if roles.get(part.get("messageID")) == "user":
            continue
        common = {"recorded_at": event.get("recorded_at"), "turn": event.get("turn"), "role": "assistant", "native": event}
        if part.get("type") != "tool":
            result.append({**common, "type": part["type"], "content": part.get("text") or "", "item": part})
            continue
        state = part.get("state") or {}
        timing = state.get("time") or {}
        result.append({**common, "role": "tool", "type": "commandExecution", "item": {
            "command": ((state.get("input") or {}).get("command") or "bash") if part.get("tool") == "bash"
            else f"{part.get('tool')} {json.dumps(state.get('input') or {}, separators=(',', ':'))}",
            "aggregatedOutput": state.get("output") or state.get("error") or "", "status": state.get("status"),
            "durationMs": timing["end"] - timing["start"] if timing.get("end") and timing.get("start") else None}})
    return result


def agent_event_entry(event: dict, index: int, actor: str) -> dict | None:
    """Map one `agent-event-v1` record onto the console's log entry shape."""
    kind = str(event.get("type") or "message")
    text, output = str(event.get("text") or ""), str(event.get("output") or "")
    common = {"id": f"{actor}-agent-{index}", "actor": actor, "turn": event.get("turn"),
              "recorded_at": event.get("t"), "kind": kind, "raw": event}
    if kind in {"command", "tool", "file_change"}:
        title = ("Command" if kind == "command" else "File changes" if kind == "file_change"
                 else f"Tool · {event.get('tool') or 'tool'}")
        meta = "" if event.get("exit_code") is None else f"exit {event['exit_code']}"
        return {**common, "role": "tool", "category": "tools", "title": title,
                "summary": (text.splitlines() or [""])[0][:240], "meta": meta, "input": text, "body": output}
    if kind == "reasoning":
        return {**common, "role": "assistant_reasoning", "category": "reasoning", "title": "Model reasoning",
                "summary": next((l for l in text.splitlines() if l), "")[:180] or kind, "body": text} if text.strip() else None
    if kind in {"message", "error", "image"}:
        title = "Error" if kind == "error" else "Image" if kind == "image" else "Agent response"
        return {**common, "role": "assistant", "category": "conversation", "title": title,
                "summary": next((l for l in text.splitlines() if l), "")[:180] or kind, "body": text}
    return None  # usage / turn_end carry no readable content.


def normalize_workspace_event(event: dict, index: int, actor: str) -> dict:
    added, modified = list((event.get("added") or {}).keys()), list((event.get("modified") or {}).keys())
    deleted = event.get("deleted") if isinstance(event.get("deleted"), list) else []
    return {"id": f"{actor}-workspace-{index}", "actor": actor, "turn": None, "recorded_at": event.get("recorded_at"),
            "category": "workspace", "kind": "workspace_snapshot", "title": event.get("cause") or "Workspace snapshot",
            "summary": f"{len(added)} added · {len(modified)} modified · {len(deleted)} deleted",
            "body": "\n".join(str(n) for n in added + modified + deleted), "raw": event}


def normalize_evidence_event(event: dict, index: int, actor: str, phase: str) -> dict:
    kind = str(event.get("type") or "evidence")
    payload = event.get("payload") or {}
    transition = kind == "transition"
    action = dig(payload, "action", "id") or dig(payload, "requested_action", "id") or ""
    after = payload.get("after") or payload.get("observation") or {}
    level = dig(after, "progress", "levels_completed")
    number = first(event.get("sequence"), index + 1)
    return {"id": f"{actor}-{phase}-{index}", "actor": actor, "turn": None, "recorded_at": event.get("recorded_at"),
            "category": "environment", "kind": kind,
            "title": f"{action or 'Action'} → {after.get('status') or 'observation'}" if transition else kind.replace("_", " "),
            "summary": " · ".join(s for s in (f"{phase} #{number}", "" if level is None else f"level {level}") if s)
            if transition else f"{phase} evidence #{number}",
            "body": json.dumps({"action": payload.get("action"), "status": after.get("status"),
                                "progress": after.get("progress"), "metadata": after.get("metadata")}, indent=2) if transition else "",
            "raw": event}


def normalize_raw_event(event: dict, index: int, actor: str) -> dict:
    method = str(event.get("method") or "SDK event")
    item_type = dig(event, "payload", "item", "type")
    return {"id": f"{actor}-raw-{index}", "actor": actor, "turn": event.get("turn"), "recorded_at": event.get("recorded_at"),
            "category": "raw", "kind": method, "title": method,
            "summary": f"item: {item_type}" if item_type else f"turn {event['turn_id']}" if event.get("turn_id") else "App-server notification",
            "body": "", "raw": event}


def request_events(path: Path, actor: str) -> list[dict]:
    import re
    try:
        files = sorted(e for e in os.scandir(path) if e.is_file(follow_symlinks=False) and re.fullmatch(r"request-.*\.json", e.name))
    except OSError:
        return []
    result = []
    for index, entry in enumerate(sorted(files, key=lambda e: e.name)):
        stat = entry.stat()
        event = read_json_safe(Path(entry.path))
        request = event.get("request") or {}
        effort = dig(request, "reasoning", "effort")
        tools = (len(request["tools"]) if isinstance(request.get("tools"), list)
                 else sum(1 for i in request["input"] if isinstance(i, dict) and i.get("type") == "function_call")
                 if isinstance(request.get("input"), list) else 0)
        result.append({"id": f"{actor}-request-{index}", "actor": actor, "turn": None,
                       "recorded_at": event.get("recorded_at") or datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                       "category": "requests", "kind": "model_request",
                       "title": f"{request.get('model') or 'model'} request #{first(event.get('sequence'), index + 1)}",
                       "summary": " · ".join(s for s in (f"reasoning {effort}" if effort else "", f"{stat.st_size} bytes",
                                                         f"{tools} tool items" if tools else "") if s),
                       "body": entry.name,
                       "raw": {**event, "raw_body_base64": "[recorded on disk; omitted from duplicate UI view]"}})
    return result


def avo_logs(root: Path, run_id, scope, stream, page, limit, search) -> dict:
    import re
    run_root = resolve_avo_run(root, run_id)
    if run_root is None:
        raise RouteError(400, "Invalid AVO run")
    candidate = scope if isinstance(scope, str) and re.fullmatch(r"x_\d+", scope) else None
    if scope != "outer" and not candidate:
        raise RouteError(400, "Invalid trace actor")
    actor = "Outer optimizer" if scope == "outer" else candidate
    analysis = run_root / "optimizer_analysis" if scope == "outer" else run_root / candidate / "research/analysis"
    candidate_root = run_root / candidate if candidate else None
    selected = stream or "session"
    session = read_json_safe(analysis / "session.json")
    open_code = session.get("backend") == "opencode"
    agent_events = analysis / "agent_events.jsonl"
    use_agent_events = agent_events.is_file() and not (analysis / "conversation.jsonl").is_file()
    entries: list[dict] = []
    if selected in {"all", "session", "conversation", "reasoning", "tools"}:
        if use_agent_events:
            mapped = (agent_event_entry(e, i, actor) for i, e in enumerate(read_json_lines(agent_events)))
            entries += [e for e in mapped if e]
        else:
            events = read_json_lines(analysis / "conversation.jsonl")
            if open_code:
                events = [e for e in events if e.get("source") == "client_turn_input"] + \
                    open_code_conversation(read_json_lines(analysis / "opencode_events.jsonl"))
            entries += normalize_conversation_events(events, actor)
    if selected in {"all", "workspace"}:
        entries += [normalize_workspace_event(e, i, actor) for i, e in enumerate(read_json_lines(analysis / "workspace_changes.jsonl"))]
    if candidate_root and selected in {"all", "environment"}:
        entries += [normalize_evidence_event(e, i, actor, "research")
                    for i, e in enumerate(read_json_lines(candidate_root / "research/evidence.jsonl"))]
        entries += [normalize_evidence_event(e, i, actor, "fresh evaluation")
                    for i, e in enumerate(read_json_lines(candidate_root / "evaluation/evidence.jsonl"))]
    if selected in {"all", "requests"}:
        entries += request_events(analysis / "model_requests", actor)
    if selected == "raw":
        if use_agent_events:
            raw = [e for turn in sorted((analysis / "raw").glob("turn-*.jsonl"),
                                        key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
                   for e in read_json_lines(turn)]
        else:
            raw = read_json_lines(analysis / ("opencode_events.jsonl" if open_code else "app_server_events.jsonl"))
        entries += [normalize_raw_event(e, i, actor) for i, e in enumerate(raw)]
    if selected == "session":
        entries = [e for e in entries if e["category"] in {"conversation", "tools"}]
    elif selected in {"conversation", "reasoning", "tools", "workspace", "environment", "requests"}:
        entries = [e for e in entries if e["category"] == selected]
    needle = str(search or "").strip().lower()
    if needle:
        entries = [e for e in entries if needle in " ".join(_js(e.get(k)) for k in
                                                             ("title", "summary", "meta", "input", "body", "kind")).lower()]
    entries.sort(key=lambda e: (_js(e.get("recorded_at")), e["id"]))

    def number(value, default):
        try:
            parsed = float(value)
            return parsed if parsed == parsed else default
        except (TypeError, ValueError):
            return default
    safe_limit = int(max(10, min(number(limit, 60) or 60, 120)))
    safe_page = int(max(0, number(page, 0) or 0))
    end = max(0, len(entries) - safe_page * safe_limit)
    start = max(0, end - safe_limit)
    return {"actor": actor, "stream": selected, "page": safe_page, "total": len(entries), "has_more": start > 0,
            "entries": entries[start:end]}


# ------------------------------------------------------------------ artifacts

def artifact_role(relative: str) -> str:
    import re
    parts = relative.split("/")
    if parts[0] == "optimizer_analysis":
        return "Outer optimizer"
    if not re.fullmatch(r"x_\d+", parts[0]):
        return "Run record"
    if len(parts) == 2 and parts[1] == "summary.json":
        return "Summary"
    if len(parts) > 1 and parts[1] == "solver":
        return "Completed solver"
    if len(parts) > 1 and parts[1] == "evaluation":
        return "Fresh evaluation"
    if len(parts) > 2 and parts[1] == "research" and parts[2] == "self_check":
        return "Self-checks"
    if len(parts) > 1 and parts[1] == "research":
        return "Research"
    return "Strategy and seed"


def list_artifacts(root: Path, run_id) -> list[dict]:
    run_root = resolve_avo_run(root, run_id)
    if run_root is None:
        raise RouteError(400, "Invalid AVO run")
    if not run_root.is_dir():
        raise RouteError(404, "AVO run not found")
    result = []

    def walk(current: Path):
        try:
            entries = list(os.scandir(current))
        except OSError:
            return
        for entry in entries:
            if entry.name in SKIPPED_PARTS:
                continue
            path = Path(entry.path)
            if _linked(path):
                continue
            if entry.is_dir(follow_symlinks=False):
                walk(path)
                continue
            if not entry.is_file(follow_symlinks=False) or path.suffix.lower() not in READABLE:
                continue
            stat = entry.stat(follow_symlinks=False)
            relative = path.relative_to(run_root).as_posix()
            result.append({"path": relative, "name": entry.name, "role": artifact_role(relative), "size": stat.st_size,
                           "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()})
    walk(run_root)
    return sorted(result, key=lambda a: a["path"])


def read_artifact(root: Path, run_id, relative) -> dict:
    run_root = resolve_avo_run(root, run_id)
    if run_root is None or not isinstance(relative, str):
        raise RouteError(400, "Invalid artifact path")
    target = safe_resolve(run_root, relative)
    if (target is None or any(p in SKIPPED_PARTS for p in target.relative_to(run_root).parts)
            or target.suffix.lower() not in READABLE):
        raise RouteError(403, "Artifact is not readable here")
    if not target.is_file():
        raise RouteError(404, "Artifact not found")
    size = target.stat().st_size
    with target.open("rb") as stream:
        data = stream.read(min(size, MAX_ARTIFACT_BYTES))
    return {"path": relative, "size": size, "truncated": size > len(data), "content": data.decode("utf-8", errors="replace")}


# ------------------------------------------------------------------ markdown

async def markdown_payload(request: Request) -> dict:
    body = await request.body()
    if len(body) > MAX_MARKDOWN_BYTES:
        raise RouteError(413, "Markdown exceeds the 1 MB limit")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RouteError(400, "Request body must be valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("file"), str) or not isinstance(payload.get("markdown"), str):
        raise RouteError(400, "Both file and markdown are required")
    return payload


def write_markdown(base: Path, file: str, markdown: str, label: str) -> None:
    target = safe_resolve(Path(os.path.abspath(base)), file)
    if target is None or target.suffix.lower() != ".md":
        raise RouteError(400, f"Invalid {label} Markdown path")
    with open(target, "w", encoding="utf-8", newline="") as stream:
        stream.write(markdown)


def add_routes(router: APIRouter, root: Path, catalog_runs: Callable[[], list[dict]]) -> ReplayWorker:
    worker = ReplayWorker(root)

    @router.get("/avo/runs")
    def runs():
        return guarded("Could not list AVO runs", lambda: {"runs": avo_runs(root, catalog_runs)})

    @router.get("/avo/run")
    def run(run: str | None = None):
        return guarded("Could not read AVO run", lambda: avo_snapshot(root, run, catalog_runs))

    @router.get("/avo/frame")
    def frame(run: str | None = None, candidate: str | None = None, phase: str | None = None, step: str | None = None):
        return guarded("Could not render AVO frame", lambda: avo_frame(root, worker, run, candidate, phase, step))

    @router.get("/avo/logs")
    def logs(run: str | None = None, scope: str | None = None, stream: str | None = None, page: str | None = None,
             limit: str | None = None, search: str | None = None):
        return guarded("Could not read AVO logs", lambda: avo_logs(root, run, scope, stream, page, limit, search))

    @router.get("/avo/artifacts")
    def artifacts(run: str | None = None):
        return guarded("Could not list AVO artifacts", lambda: {"artifacts": list_artifacts(root, run)})

    @router.get("/avo/artifact")
    def artifact(run: str | None = None, path: str | None = Query(None)):
        return guarded("Could not read AVO artifact", lambda: read_artifact(root, run, path))

    @router.get("/notes")
    def read_notes():
        folder = root / "docs/notes"
        return {"files": [{"file": name, "markdown": (folder / name).read_text(encoding="utf-8")
                           if (folder / name).is_file() else ""} for name in sorted(NOTES_FILES)]}

    @router.post("/notes")
    async def save_notes(request: Request):
        try:
            payload = await markdown_payload(request)
            if payload["file"] not in NOTES_FILES:
                raise RouteError(403, "Only notebook files listed by the Notes page can be saved")
            write_markdown(root / "docs/notes", payload["file"], payload["markdown"], "notes")
        except RouteError as exc:
            return send({"error": str(exc)}, exc.status)
        except OSError as exc:
            return send({"error": str(exc) or "Could not save notes"}, 500)
        return send({"saved": True})

    @router.post("/pseudocode")
    async def save_pseudocode(request: Request):
        try:
            payload = await markdown_payload(request)
            manifest = json.loads((root / "docs/pseudocode/manifest.json").read_text(encoding="utf-8"))
            if not any(isinstance(item, dict) and item.get("file") == payload["file"] for item in manifest):
                raise RouteError(403, "Only pseudocode files listed in the manifest can be saved")
            write_markdown(root / "docs/pseudocode", payload["file"], payload["markdown"], "pseudocode")
        except RouteError as exc:
            return send({"error": str(exc)}, exc.status)
        except (OSError, ValueError) as exc:
            return send({"error": str(exc) or "Could not save Markdown"}, 500)
        return send({"saved": True, "file": payload["file"]})

    return worker
