"""Research diary: dated markdown entries under docs/diary/, linked to runs, exportable.

Entry format (docs/architecture/revamp-contract.md section 6): `YYYY-MM-DD-<slug>.md`
with a flat front matter block and exactly the body sections Did, Found, Decided, Next.
The front matter parser is deliberately minimal (flat scalars, booleans and string
lists) so no YAML dependency is needed and nothing in an entry can execute.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Response

from workbench.catalog import read_json, snapshot

ROOT = Path(__file__).resolve().parents[1]
# Both roots are module attributes so tests (and other checkouts) can point elsewhere.
DIARY_DIR = Path(os.environ.get("WORKBENCH_DIARY_DIR") or ROOT / "docs" / "diary")
RUN_ROOT = ROOT

SECTIONS = ("Did", "Found", "Decided", "Next")
FIELDS = ("date", "title", "threads", "runs", "commits", "docs", "reconstructed")
LIST_FIELDS = ("threads", "runs", "commits", "docs")
MEETING_THREAD = "meetings"
SLUG = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9][a-z0-9-]{0,79}$")
THREAD = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
LIST_ITEM_FORBIDDEN = re.compile(r"[,\[\]\"'#\r\n]")
MAX_BODY = 20_000
RUN_CACHE_SECONDS = 60

router = APIRouter(prefix="/api/workbench")
_run_cache: dict = {}
_run_lock = threading.Lock()
_write_lock = threading.Lock()


class DiaryError(ValueError):
    pass


# --- parsing -----------------------------------------------------------------

def _scalar(raw: str):
    value = raw.strip()
    if value.startswith('"'):
        end = _closing_quote(value)
        return value[1:end].replace('\\"', '"').replace("\\\\", "\\")
    if value.startswith("'"):
        end = value.find("'", 1)
        if end < 0:
            raise DiaryError(f"Unterminated quote: {raw!r}")
        return value[1:end]
    value = re.sub(r"\s+#.*$", "", value).strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def _closing_quote(value: str) -> int:
    index = 1
    while index < len(value):
        if value[index] == "\\":
            index += 2
            continue
        if value[index] == '"':
            return index
        index += 1
    raise DiaryError(f"Unterminated quote: {value!r}")


def _inline_list(raw: str) -> list[str]:
    value = re.sub(r"\]\s+#.*$", "]", raw.strip())
    if not value.endswith("]"):
        raise DiaryError(f"Unterminated list: {raw!r}")
    inner = value[1:-1].strip()
    return [str(_scalar(item)) for item in inner.split(",") if item.strip()] if inner else []


def parse_front_matter(block: str) -> dict:
    meta: dict = {}
    key = None
    for number, line in enumerate(block.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s*(.*)$", line) or re.match(r"^-\s+(.*)$", line)
        if item:
            if key is None or not isinstance(meta.get(key), list):
                raise DiaryError(f"Front matter line {number}: list item without a list key")
            meta[key].append(str(_scalar(item.group(1))))
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$", line)
        if not match:
            raise DiaryError(f"Front matter line {number}: expected 'key: value'")
        key, raw = match.group(1), match.group(2).strip()
        if raw.startswith("["):
            meta[key] = _inline_list(raw)
        elif raw == "" or raw.startswith("#"):
            meta[key] = []
        else:
            meta[key] = _scalar(raw)
    return meta


def split_text(text: str) -> tuple[dict, str]:
    text = text.replace("\r\n", "\n").lstrip("﻿")
    if not text.startswith("---\n"):
        raise DiaryError("Entry must start with a '---' front matter block")
    end = text.find("\n---", 3)
    if end < 0 or text[end + 4:end + 5] not in {"", "\n"}:
        raise DiaryError("Front matter block is not closed with '---'")
    return parse_front_matter(text[4:end]), text[end + 5:]


def parse_sections(body: str) -> dict[str, str]:
    headings = [(m.group(1).strip(), m.start(), m.end()) for m in re.finditer(r"^##[ \t]+(.+?)[ \t]*$", body, re.M)]
    names = [name for name, _, _ in headings]
    if names != list(SECTIONS):
        raise DiaryError(f"Body sections must be exactly {', '.join('## ' + s for s in SECTIONS)} in order; found {names}")
    if body[:headings[0][1]].strip():
        raise DiaryError("Text before '## Did' is not allowed")
    sections = {}
    for index, (name, _, end) in enumerate(headings):
        stop = headings[index + 1][1] if index + 1 < len(headings) else len(body)
        sections[name.lower()] = body[end:stop].strip()
    return sections


def bullets(section: str) -> list[str]:
    """Top-level bullets of a section; indented continuation lines are joined."""
    items: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^[-*]\s+(.*)$", line)
        if match:
            items.append(match.group(1).strip())
        elif items and line.strip() and line.startswith((" ", "\t")):
            items[-1] += " " + line.strip()
        elif line.strip() and not items:
            items.append(line.strip())
    return [item for item in items if item not in {"—", "-", "–", ""}]


# --- validation and serialization -------------------------------------------

def _valid_date(value, field: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise DiaryError(f"{field} must be YYYY-MM-DD") from exc


def validate(slug: str, meta: dict, body: str) -> tuple[dict, dict, list[str]]:
    """Return (normalized meta, sections, warnings) or raise DiaryError."""
    match = SLUG.match(slug or "")
    if not match:
        raise DiaryError("Slug must look like YYYY-MM-DD-short-name (lowercase letters, digits, hyphens)")
    _valid_date(match.group(1), "Slug date")
    unknown = sorted(set(meta) - set(FIELDS))
    if unknown:
        raise DiaryError(f"Unknown front matter fields: {', '.join(unknown)}")
    date = _valid_date(meta.get("date"), "date")
    if date.isoformat() != match.group(1):
        raise DiaryError("Front matter date must equal the slug date")
    title = meta.get("title")
    if not isinstance(title, str) or not title.strip() or "\n" in title or len(title) > 200:
        raise DiaryError("title must be a non-empty single line (at most 200 characters)")
    normalized = {"date": date.isoformat(), "title": title.strip()}
    for field in LIST_FIELDS:
        value = meta.get(field, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise DiaryError(f"{field} must be a list of strings")
        value = [v.strip() for v in value if v.strip()]
        for item in value:
            if LIST_ITEM_FORBIDDEN.search(item) or len(item) > 300:
                raise DiaryError(f"{field} item {item!r} contains a forbidden character")
        normalized[field] = value
    if not normalized["threads"]:
        raise DiaryError("threads must name at least one thread")
    for thread in normalized["threads"]:
        if not THREAD.match(thread):
            raise DiaryError(f"Thread id {thread!r} must be lowercase letters, digits and hyphens")
    for commit in normalized["commits"]:
        if not COMMIT.match(commit):
            raise DiaryError(f"Commit {commit!r} must be a hexadecimal SHA")
    for item in normalized["docs"] + normalized["runs"]:
        parts = item.replace("\\", "/").split("/")
        if item.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", item) or ".." in parts:
            raise DiaryError(f"Path {item!r} must be repo-relative")
    reconstructed = meta.get("reconstructed", False)
    if not isinstance(reconstructed, bool):
        raise DiaryError("reconstructed must be true or false")
    normalized["reconstructed"] = reconstructed
    if not isinstance(body, str) or len(body) > MAX_BODY:
        raise DiaryError(f"body must be text of at most {MAX_BODY} characters")
    sections = parse_sections(body.replace("\r\n", "\n"))
    warnings = []
    known = {t["id"] for t in thread_registry()}
    for thread in normalized["threads"]:
        if known and thread not in known:
            warnings.append(f"Thread {thread!r} is not in the docs/diary/README.md registry")
    return normalized, sections, warnings


def _yaml_scalar(value: str) -> str:
    if re.search(r"[:#\[\]{}\"',&*!|>%@`]", value) or value.strip() != value or value.lower() in {"true", "false", ""}:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def serialize(meta: dict, sections: dict) -> str:
    lines = ["---", f"date: {meta['date']}", f"title: {_yaml_scalar(meta['title'])}"]
    lines += [f"{field}: [{', '.join(meta[field])}]" for field in LIST_FIELDS]
    lines += [f"reconstructed: {'true' if meta['reconstructed'] else 'false'}", "---"]
    for name in SECTIONS:
        lines += [f"## {name}", sections[name.lower()] or "- —", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


# --- storage -----------------------------------------------------------------

def entry_path(slug: str) -> Path:
    if not SLUG.match(slug or ""):
        raise HTTPException(400, "Invalid diary slug")
    base = DIARY_DIR.resolve()
    path = (base / f"{slug}.md").resolve()
    if path.parent != base:
        raise HTTPException(400, "Invalid diary slug")
    return path


def load(path: Path) -> dict:
    meta, body = split_text(path.read_text(encoding="utf-8"))
    normalized, sections, warnings = validate(path.stem, meta, body)
    return {"slug": path.stem, **normalized, "sections": sections, "body": body.strip() + "\n", "warnings": warnings}


def load_all() -> tuple[list[dict], list[dict]]:
    entries, errors = [], []
    if not DIARY_DIR.is_dir():
        return entries, errors
    for path in sorted(DIARY_DIR.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        try:
            entries.append(load(path))
        except (OSError, UnicodeDecodeError, DiaryError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
    entries.sort(key=lambda e: (e["date"], e["slug"]))
    return entries, errors


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".diary-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def thread_registry() -> list[dict]:
    """Rows of the '## Threads' table in docs/diary/README.md: | `id` | description | status |."""
    try:
        text = (DIARY_DIR / "README.md").read_text(encoding="utf-8")
    except OSError:
        return []
    section = re.search(r"^## Threads\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    rows = []
    for line in (section.group(1) if section else "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and line.strip().startswith("|"):
            thread = cells[0].strip("`").strip()
            if THREAD.match(thread):
                rows.append({"id": thread, "description": cells[1], "status": cells[2].strip("`* ")})
    return rows


# --- runs --------------------------------------------------------------------

def _run_date(row: dict, root: Path) -> str | None:
    run_dir = root / row.get("id", "")
    spec = read_json(run_dir / "run_spec.json")
    for value in (spec.get("created_at"), (row.get("config") or {}).get("created_at"),
                  (row.get("config") or {}).get("started_at")):
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            return value[:10]
    found = None
    for part in str(row.get("id", "")).split("/"):
        match = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?:T\d{4,6}Z?)?(?!\d)", part)
        if match:
            try:
                found = dt.date(*map(int, match.groups())).isoformat()
            except ValueError:
                pass
    if found:
        return found
    for name in ("run_config.json", "evolution_config.json"):
        try:
            return dt.date.fromtimestamp((run_dir / name).stat().st_mtime).isoformat()
        except OSError:
            continue
    return None


def _run_summary(row: dict, root: Path) -> dict:
    spec = read_json(root / row.get("id", "") / "run_spec.json")
    kind = row.get("kind")
    status = row.get("status") or "unknown"
    outcome = "stopped" if status == "cancelled" else status
    if kind == "avo":
        if row.get("solved"):
            outcome += ", solved"
        elif row.get("best_fitness") is not None:
            outcome += f", best fitness {row['best_fitness']:g}"
        if row.get("evaluated"):
            outcome += f", {row['evaluated']} evaluation(s)"
    elif row.get("solved"):
        outcome += ", task goal reached"
    if kind != "avo" and row.get("levels") is not None:
        total = row.get("recorded_win_levels")
        outcome += f", {row['levels']}/{total} levels" if total else f", {row['levels']} level(s)"
        if row.get("actions") is not None:
            outcome += f" in {row['actions']} actions"
    return {"id": row.get("id"), "date": row.get("_date"), "variant": row.get("variant") or kind,
            "harness": spec.get("harness") or row.get("agent_backend") or row.get("harness"),
            "model": spec.get("model") or row.get("model"), "game": spec.get("game_id") or row.get("game_id"),
            "status": status, "solved": bool(row.get("solved")), "outcome": outcome}


def run_index() -> list[dict]:
    """Catalog rows with a start date, cached briefly; no Docker probe is needed here."""
    root = Path(RUN_ROOT)
    with _run_lock:
        cached = _run_cache.get(str(root))
        if cached and time.monotonic() - cached[0] < RUN_CACHE_SECONDS:
            return cached[1]
        try:
            rows = snapshot(root, {})["runs"]
        except Exception:  # The diary stays usable when a run archive is unreadable.
            rows = []
        summaries = []
        for row in rows:
            row = {**row, "_date": _run_date(row, root)}
            summaries.append(_run_summary(row, root))
        summaries.sort(key=lambda r: (r["date"] or "", r["id"] or ""))
        _run_cache[str(root)] = (time.monotonic(), summaries)
        return summaries


def linked_runs(entry: dict, index: list[dict]) -> list[dict]:
    runs, seen = [], set()
    for ref in entry["runs"]:
        ref_id = ref.replace("\\", "/").rstrip("/")
        if ref_id.endswith("*"):  # trailing wildcard: every run whose id starts with the prefix
            matches = [r for r in index if str(r["id"]).startswith(ref_id[:-1])]
        else:
            matches = [r for r in index if r["id"] == ref_id or str(r["id"]).startswith(ref_id + "/")]
        if not matches:
            runs.append({"id": ref_id, "linked": "explicit", "found": False})
        for run in matches:
            if run["id"] not in seen:
                seen.add(run["id"])
                runs.append({**run, "linked": "explicit", "found": True})
    for run in index:
        if run["date"] == entry["date"] and run["id"] not in seen:
            seen.add(run["id"])
            runs.append({**run, "linked": "date", "found": True})
    return runs


# --- selection and export -----------------------------------------------------

def _date_param(value: str | None, name: str) -> str | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(400, f"{name} must be YYYY-MM-DD") from exc


def select(entries: list[dict], thread: str | None, start: str | None, end: str | None) -> list[dict]:
    wanted = {t.strip() for t in (thread or "").split(",") if t.strip()}
    return [e for e in entries
            if (not wanted or wanted & set(e["threads"]))
            and (not start or e["date"] >= start) and (not end or e["date"] <= end)]


def public(entry: dict, index: list[dict], body: bool = False) -> dict:
    keys = ("slug", "date", "title", "threads", "reconstructed", "commits", "docs", "sections", "warnings")
    value = {k: entry[k] for k in keys}
    value["explicit_runs"] = entry["runs"]
    value["runs"] = linked_runs(entry, index)
    if body:
        value["body"] = entry["body"]
    return value


def default_export_start(entries: list[dict], end: str) -> str:
    """Day after the last entry tagged `meetings` before `end`; otherwise two weeks back."""
    meetings = [e["date"] for e in entries if MEETING_THREAD in e["threads"] and e["date"] < end]
    if meetings:
        return (dt.date.fromisoformat(max(meetings)) + dt.timedelta(days=1)).isoformat()
    return (dt.date.fromisoformat(end) - dt.timedelta(days=14)).isoformat()


def export_markdown(entries: list[dict], start: str, end: str, thread: str | None, index: list[dict]) -> str:
    registry = {t["id"]: t for t in thread_registry()}
    lines = [f"# Research progress, {start} to {end}", "",
             f"Adam Celermajer, M.Sc (Bar-Ilan University). Prepared {dt.date.today().isoformat()} from the research diary."
             + (f" Thread filter: {thread}." if thread else ""), ""]
    if not entries:
        return "\n".join(lines + ["No diary entries in this period.", ""])
    reconstructed = sum(e["reconstructed"] for e in entries)
    lines += [f"{len(entries)} diary {'entry' if len(entries) == 1 else 'entries'}" + (f" ({reconstructed} reconstructed from git history and documents)" if reconstructed else "") + ".", ""]

    lines += ["## Progress by thread", ""]
    order = list(dict.fromkeys(t for e in entries for t in e["threads"]))
    for thread_id in order:
        info = registry.get(thread_id, {})
        heading = f"### {thread_id}" + (f" ({info['status']})" if info.get("status") else "")
        lines += [heading, ""] + ([f"_{info['description']}_", ""] if info.get("description") else [])
        # An entry's Did bullets appear once, under its primary (first) thread.
        for entry in (e for e in entries if thread_id in e["threads"]):
            if entry["threads"][0] == thread_id:
                did = [b.rstrip(".") for b in bullets(entry["sections"]["did"])]
                lines.append(f"- **{entry['date']} {entry['title']}**" + (": " + "; ".join(did) + "." if did else ""))
            else:
                lines.append(f"- {entry['date']} {entry['title']} (see {entry['threads'][0]})")
        lines.append("")

    for title, key in (("Key findings", "found"), ("Decisions", "decided")):
        items = [(e["date"], b) for e in entries for b in bullets(e["sections"][key])]
        lines += [f"## {title}", ""] + ([f"- ({d}) {b}" for d, b in items] or ["- None recorded."]) + [""]

    # Only the latest entry of each thread carries current next steps; older ones are stale.
    latest = {}
    for entry in entries:
        for thread_id in entry["threads"]:
            latest[thread_id] = entry["slug"]
    nexts = []
    for entry in entries:
        if entry["slug"] in latest.values():
            nexts += [b for b in bullets(entry["sections"]["next"]) if b not in nexts]
    lines += ["## Next steps", ""] + ([f"- {b}" for b in nexts] or ["- None recorded."]) + [""]

    runs = {}
    for entry in entries:
        for run in linked_runs(entry, index):
            if run.get("found"):
                runs.setdefault(run["id"], run)
    lines += ["## Linked runs", ""]
    if runs:
        rows = sorted(runs.values(), key=lambda r: (r.get("date") or "", r["id"]))
        lines += ["| Date | Run | Framework | Harness | Model | Game | Outcome |", "|---|---|---|---|---|---|---|"]
        for run in rows[:40]:
            cells = [run.get("date") or "", f"`{run['id']}`", run.get("variant") or "", run.get("harness") or "",
                     run.get("model") or "", run.get("game") or "", run.get("outcome") or ""]
            lines.append("| " + " | ".join(str(c).replace("|", "/") for c in cells) + " |")
        if len(rows) > 40:
            lines.append(f"\n{len(rows) - 40} more runs are listed in the workbench run catalog.")
    else:
        lines.append("No runs recorded in this period.")
    lines.append("")

    commits = list(dict.fromkeys(c for e in entries for c in e["commits"]))
    docs = list(dict.fromkeys(d for e in entries for d in e["docs"]))
    if commits or docs:
        lines += ["## Sources", ""]
        if commits:
            lines.append("- Commits: " + ", ".join(f"`{c}`" for c in commits))
        if docs:
            lines.append("- Documents: " + ", ".join(f"`{d}`" for d in docs))
        lines.append("")
    return "\n".join(lines)


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])_([^_]+)_(?!\w)", r"<em>\1</em>", text)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)


def markdown_to_html(text: str) -> str:
    """Enough markdown for the export: headings, bullets, tables and paragraphs."""
    out, in_list, table = [], False, []

    def flush_table():
        if not table:
            return
        out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in table[0]) + "</tr></thead><tbody>")
        out.extend("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>" for row in table[2:])
        out.append("</tbody></table>")
        table.clear()

    for line in text.splitlines():
        if line.startswith("|"):
            table.append([c.strip() for c in line.strip().strip("|").split("|")])
            continue
        flush_table()
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if in_list and not bullet:
            out.append("</ul>")
            in_list = False
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif bullet:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(bullet.group(1))}</li>")
        elif line.strip():
            out.append(f"<p>{_inline(line.strip())}</p>")
    flush_table()
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


PRINT_CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
html { font-family: "Charter", "Georgia", "Times New Roman", serif; font-size: 10.5pt; color: #111; }
body { max-width: 178mm; margin: 12mm auto; line-height: 1.38; }
h1 { font-size: 17pt; margin: 0 0 4pt; }
h2 { font-size: 12.5pt; margin: 14pt 0 4pt; border-bottom: 0.6pt solid #888; padding-bottom: 2pt; }
h3 { font-size: 11pt; margin: 10pt 0 2pt; }
h2, h3 { break-after: avoid; page-break-after: avoid; }
p { margin: 3pt 0; }
ul { margin: 2pt 0 6pt 0; padding-left: 15pt; }
li { margin: 1.5pt 0; break-inside: avoid; }
code { font-family: "Consolas", "Menlo", monospace; font-size: 8.8pt; overflow-wrap: anywhere; }
table { border-collapse: collapse; width: 100%; font-size: 8.4pt; margin: 4pt 0; }
th, td { border: 0.5pt solid #aaa; padding: 2pt 3pt; text-align: left; vertical-align: top; }
th { background: #eee; }
tr { break-inside: avoid; page-break-inside: avoid; }
a { color: inherit; }
@media print { body { margin: 0; max-width: none; } }
"""


def export_html(markdown: str, title: str) -> str:
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title><style>{PRINT_CSS}</style></head>\n<body>\n"
            f"{markdown_to_html(markdown)}\n</body></html>\n")


# --- routes (static paths before /diary/{slug}) ------------------------------

@router.get("/diary")
def list_entries(thread: str | None = None, from_: str | None = Query(None, alias="from"),
                 to: str | None = None) -> dict:
    start, end = _date_param(from_, "from"), _date_param(to, "to")
    entries, errors = load_all()
    index = run_index()
    return {"entries": [public(e, index) for e in select(entries, thread, start, end)], "errors": errors}


@router.get("/diary/threads")
def list_threads() -> dict:
    entries, _ = load_all()
    registry = thread_registry()
    used = {t for e in entries for t in e["threads"]}
    rows = registry + [{"id": t, "description": "", "status": "unregistered"}
                       for t in sorted(used - {r["id"] for r in registry})]
    for row in rows:
        dates = [e["date"] for e in entries if row["id"] in e["threads"]]
        row.update(entries=len(dates), first=min(dates, default=None), last=max(dates, default=None))
    return {"threads": rows}


@router.get("/diary/export")
def export(from_: str | None = Query(None, alias="from"), to: str | None = None,
           thread: str | None = None, format: str = "md") -> Response:
    if format not in {"md", "html"}:
        raise HTTPException(400, "format must be md or html")
    entries, _ = load_all()
    end = _date_param(to, "to") or dt.date.today().isoformat()
    start = _date_param(from_, "from") or default_export_start(entries, end)
    if start > end:
        raise HTTPException(400, "from must not be after to")
    chosen = select(entries, thread, start, end)
    document = export_markdown(chosen, start, end, thread, run_index())
    name = f"research-progress-{start}-to-{end}"
    if format == "html":
        return Response(export_html(document, name), media_type="text/html; charset=utf-8")
    return Response(document, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'inline; filename="{name}.md"'})


@router.get("/diary/{slug}")
def get_entry(slug: str) -> dict:
    path = entry_path(slug)
    if not path.is_file():
        raise HTTPException(404, "Diary entry not found")
    try:
        entry = load(path)
    except DiaryError as exc:
        raise HTTPException(422, f"Diary entry is invalid: {exc}") from exc
    return public(entry, run_index(), body=True)


@router.put("/diary/{slug}")
def put_entry(slug: str, payload: dict = Body(...)) -> dict:
    """Body: {"text": full file} or {"front_matter": {...}, "body": "## Did ..."}."""
    path = entry_path(slug)
    try:
        if isinstance(payload.get("text"), str):
            meta, body = split_text(payload["text"])
        else:
            meta, body = payload.get("front_matter"), payload.get("body")
            if not isinstance(meta, dict):
                raise DiaryError("front_matter must be an object")
            meta = {**meta, "date": str(meta.get("date", ""))}
        normalized, sections, warnings = validate(slug, meta, body)
    except DiaryError as exc:
        raise HTTPException(422, str(exc)) from exc
    with _write_lock:
        created = not path.exists()
        atomic_write(path, serialize(normalized, sections))
    entry = load(path)
    return {"created": created, "entry": public(entry, run_index(), body=True), "warnings": warnings}
