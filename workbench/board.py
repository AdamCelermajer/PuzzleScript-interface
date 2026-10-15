"""Research board: one markdown card per task under docs/board/, presentable as slides.

Card format: `docs/board/<slug>.md` with a flat front matter block (parsed by the diary's
minimal parser, so nothing in a card can execute) and exactly the body sections
`## Question`, `## Current answer`, `## Evidence`, `## Next`.

    ---
    title: What are Max, Flash and 27B good and bad at?
    status: in-progress          # todo | in-progress | done | blocked
    order: 1
    due: 2026-10-22              # optional
    threads: [qwen-harness]
    links:
      - "Scorecard notes | docs/research/capability-scorecard-modality-20261015.md"
    runs: []
    artifact: docs/research/capability-scorecard-modality-20261015.json   # optional
    ---

Links are stored as "label | path_or_url" strings and exposed as {label, path_or_url}.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse, Response

from workbench.diary import DiaryError, atomic_write, split_text

ROOT = Path(__file__).resolve().parents[1]
BOARD_DIR = Path(os.environ.get("WORKBENCH_BOARD_DIR") or ROOT / "docs" / "board")
REPO_ROOT = ROOT

STATUSES = ("todo", "in-progress", "done", "blocked")
SECTIONS = ("Question", "Current answer", "Evidence", "Next")
SECTION_KEYS = {"Question": "question", "Current answer": "current_answer", "Evidence": "evidence", "Next": "next"}
FIELDS = ("title", "status", "order", "due", "threads", "links", "runs", "artifact")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
THREAD = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
FORBIDDEN = re.compile(r"[\[\]\"#\r\n]")
MAX_BODY = 40_000
DOC_SUFFIXES = {".md", ".txt", ".tex", ".json", ".bib"}

router = APIRouter(prefix="/api/workbench")
_write_lock = threading.Lock()


class BoardError(ValueError):
    pass


# --- validation -----------------------------------------------------------------

def repo_path(value: str, field: str) -> str:
    """A repo-relative path without traversal or drive letters."""
    path = value.strip().replace("\\", "/")
    parts = path.split("/")
    if not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path) or ".." in parts or "" in parts:
        raise BoardError(f"{field} must be a repo-relative path")
    return path


def is_url(value: str) -> bool:
    return re.match(r"^https?://", value) is not None


def parse_link(raw: str) -> dict:
    label, sep, target = raw.partition("|")
    label, target = label.strip(), target.strip()
    if not sep:
        label, target = raw.strip(), raw.strip()
    if not label or not target:
        raise BoardError(f"Link {raw!r} must look like 'label | path_or_url'")
    if not is_url(target):
        target = repo_path(target, "link")
    return {"label": label, "path_or_url": target}


def parse_sections(body: str) -> dict[str, str]:
    headings = [(m.group(1).strip(), m.start(), m.end()) for m in re.finditer(r"^##[ \t]+(.+?)[ \t]*$", body, re.M)]
    names = [name for name, _, _ in headings]
    if names != list(SECTIONS):
        raise BoardError(f"Body sections must be exactly {', '.join('## ' + s for s in SECTIONS)} in order; found {names}")
    if body[:headings[0][1]].strip():
        raise BoardError("Text before '## Question' is not allowed")
    sections = {}
    for index, (name, _, end) in enumerate(headings):
        stop = headings[index + 1][1] if index + 1 < len(headings) else len(body)
        sections[SECTION_KEYS[name]] = body[end:stop].strip()
    return sections


def validate(slug: str, meta: dict, body: str) -> tuple[dict, dict]:
    if not SLUG.match(slug or ""):
        raise BoardError("Slug must be lowercase letters, digits and hyphens")
    unknown = sorted(set(meta) - set(FIELDS))
    if unknown:
        raise BoardError(f"Unknown front matter fields: {', '.join(unknown)}")
    title = meta.get("title")
    if not isinstance(title, str) or not title.strip() or "\n" in title or len(title) > 200:
        raise BoardError("title must be a non-empty single line (at most 200 characters)")
    status = meta.get("status", "todo")
    if status not in STATUSES:
        raise BoardError(f"status must be one of {', '.join(STATUSES)}")
    try:
        order = int(str(meta.get("order", 100)).strip())
    except ValueError as exc:
        raise BoardError("order must be an integer") from exc
    due = meta.get("due") or None
    if due is not None:
        try:
            due = dt.date.fromisoformat(str(due)).isoformat()
        except ValueError as exc:
            raise BoardError("due must be YYYY-MM-DD") from exc
    normalized = {"title": title.strip(), "status": status, "order": order, "due": due}
    for field in ("threads", "links", "runs"):
        value = meta.get(field, [])
        if isinstance(value, dict) and field == "links":
            value = [value]
        if not isinstance(value, list):
            raise BoardError(f"{field} must be a list")
        normalized[field] = value
    for thread in normalized["threads"]:
        if not isinstance(thread, str) or not THREAD.match(thread):
            raise BoardError(f"Thread id {thread!r} must be lowercase letters, digits and hyphens")
    links = []
    for link in normalized["links"]:
        if isinstance(link, dict):
            link = f"{link.get('label', '')} | {link.get('path_or_url', '')}"
        if not isinstance(link, str) or FORBIDDEN.search(link) or len(link) > 400:
            raise BoardError(f"Invalid link {link!r}")
        links.append(parse_link(link))
    normalized["links"] = links
    normalized["runs"] = [repo_path(str(r), "run") for r in normalized["runs"] if str(r).strip()]
    artifact = meta.get("artifact") or None
    if artifact is not None:
        artifact = repo_path(str(artifact), "artifact")
        if not artifact.endswith(".json"):
            raise BoardError("artifact must be a .json file")
    normalized["artifact"] = artifact
    if not isinstance(body, str) or len(body) > MAX_BODY:
        raise BoardError(f"body must be text of at most {MAX_BODY} characters")
    return normalized, parse_sections(body.replace("\r\n", "\n"))


def _quote(value: str) -> str:
    if re.search(r"[:#\[\]{}\"',&*!|>%@`]", value) or value.strip() != value or value.lower() in {"true", "false", ""}:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def serialize(meta: dict, sections: dict) -> str:
    lines = ["---", f"title: {_quote(meta['title'])}", f"status: {meta['status']}", f"order: {meta['order']}"]
    if meta.get("due"):
        lines.append(f"due: {meta['due']}")
    lines.append(f"threads: [{', '.join(meta['threads'])}]")
    if meta["links"]:
        lines.append("links:")
        lines += [f"  - {_quote(link['label'] + ' | ' + link['path_or_url'])}" for link in meta["links"]]
    else:
        lines.append("links: []")
    lines.append(f"runs: [{', '.join(meta['runs'])}]")
    if meta.get("artifact"):
        lines.append(f"artifact: {meta['artifact']}")
    lines.append("---")
    for name in SECTIONS:
        lines += [f"## {name}", sections[SECTION_KEYS[name]] or "-", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


# --- storage ----------------------------------------------------------------------

def card_path(slug: str) -> Path:
    if not SLUG.match(slug or ""):
        raise HTTPException(400, "Invalid board slug")
    base = Path(BOARD_DIR).resolve()
    path = (base / f"{slug}.md").resolve()
    if path.parent != base:
        raise HTTPException(400, "Invalid board slug")
    return path


def resolve_repo_file(relative: str) -> Path:
    try:
        clean = repo_path(relative, "path")
    except BoardError as exc:
        raise HTTPException(400, str(exc)) from exc
    root = Path(REPO_ROOT).resolve()
    path = (root / clean).resolve()
    if not path.is_relative_to(root) or not path.is_relative_to(root / "docs"):
        raise HTTPException(403, "Only files under docs/ can be opened from the board")
    return path


def load(path: Path) -> dict:
    meta, body = split_text(path.read_text(encoding="utf-8"))
    normalized, sections = validate(path.stem, meta, body)
    artifact_exists = bool(normalized["artifact"]) and (Path(REPO_ROOT) / normalized["artifact"]).is_file()
    return {"slug": path.stem, **normalized, "sections": sections, "body": body.strip() + "\n",
            "artifact_exists": artifact_exists}


def load_all() -> tuple[list[dict], list[dict]]:
    cards, errors = [], []
    base = Path(BOARD_DIR)
    for path in sorted(base.glob("*.md")) if base.is_dir() else []:
        if path.name.lower() == "readme.md":
            continue
        try:
            cards.append(load(path))
        except (DiaryError, BoardError, OSError, UnicodeDecodeError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
    cards.sort(key=lambda c: (c["order"], c["slug"]))
    return cards, errors


def write_card(slug: str, meta: dict, sections: dict) -> None:
    atomic_write(card_path(slug), serialize(meta, sections))


# --- routes (static paths before /board/{slug}) ------------------------------------

@router.get("/board")
def list_cards() -> dict:
    cards, errors = load_all()
    return {"cards": cards, "errors": errors, "statuses": list(STATUSES)}


@router.get("/board/file")
def board_file(path: str = Query(..., min_length=1, max_length=400)):
    """Read-only view of a docs/ file linked from a card (markdown, tex, json, pdf)."""
    target = resolve_repo_file(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    if target.suffix.lower() == ".pdf":
        return FileResponse(target, media_type="application/pdf")
    if target.suffix.lower() not in DOC_SUFFIXES:
        raise HTTPException(415, "This file type is not shown here")
    return Response(target.read_text(encoding="utf-8", errors="replace"), media_type="text/plain; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


@router.get("/board/{slug}")
def get_card(slug: str) -> dict:
    path = card_path(slug)
    if not path.is_file():
        raise HTTPException(404, "Board card not found")
    try:
        return load(path)
    except (DiaryError, BoardError) as exc:
        raise HTTPException(422, f"Board card is invalid: {exc}") from exc


@router.get("/board/{slug}/artifact")
def card_artifact(slug: str):
    card = get_card(slug)
    if not card["artifact"]:
        raise HTTPException(404, "This card has no artifact")
    target = resolve_repo_file(card["artifact"])
    if not target.is_file():
        raise HTTPException(404, f"Artifact {card['artifact']} does not exist yet")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(422, f"Artifact is not valid JSON: {exc}") from exc


@router.put("/board/{slug}")
def put_card(slug: str, payload: dict = Body(...)) -> dict:
    """Body: {"text": full markdown file} or {"front_matter": {...}, "body": "## Question ..."}."""
    path = card_path(slug)
    try:
        if isinstance(payload.get("text"), str):
            meta, body = split_text(payload["text"])
        else:
            meta, body = payload.get("front_matter"), payload.get("body")
            if not isinstance(meta, dict):
                raise BoardError("front_matter must be an object")
        normalized, sections = validate(slug, meta, body)
    except (DiaryError, BoardError) as exc:
        raise HTTPException(422, str(exc)) from exc
    with _write_lock:
        created = not path.exists()
        write_card(slug, normalized, sections)
    return {"created": created, "card": load(path)}


@router.patch("/board/{slug}")
def patch_card(slug: str, payload: dict = Body(...)) -> dict:
    """Quick edits from the board: {"status": ..., "order": ...}."""
    path = card_path(slug)
    unknown = sorted(set(payload) - {"status", "order"})
    if unknown or not payload:
        raise HTTPException(422, "Only status and order can be patched")
    with _write_lock:
        if not path.is_file():
            raise HTTPException(404, "Board card not found")
        try:
            card = load(path)
            meta = {k: card[k] for k in ("title", "status", "order", "due", "threads", "links", "runs", "artifact")}
            meta.update(payload)
            normalized, sections = validate(slug, meta, card["body"])
        except (DiaryError, BoardError) as exc:
            raise HTTPException(422, str(exc)) from exc
        write_card(slug, normalized, sections)
    return load(path)


