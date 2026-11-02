"""Rebuild the AVO-era diary figures (July to late September 2026) from the run files.

Run from anywhere:
    uv run --no-project --with matplotlib python -I docs/research/diary-figures-20261029/avo-era/make_figures.py

Read-only on every run folder; writes only the PNGs and data.json next to this script.
Paths below are relative to the repository root.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

# Folders that never hold usage records but can be huge.
PRUNE = {"frames", "model_requests", "workspace_blobs", "observations", "__pycache__", ".sandboxes",
         "drafts", "workspace", "initial_frames", "codex_workspace", "note_history", "solver", "evaluation"}


# --------------------------------------------------------------------------- token readers

def _ts(value):
    if not value:
        return None
    try:
        t = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _walk(base: Path):
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in PRUNE]
        for f in fns:
            yield Path(dp) / f


def _codex_events(path: Path, threads: dict):
    """Codex app-server `thread/tokenUsage/updated`: cumulative totals per thread."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "tokenUsage" not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            p = d.get("payload") or {}
            usage = (p.get("tokenUsage") or {}).get("total")
            tid = p.get("threadId")
            if not usage or not tid:
                continue
            threads.setdefault(tid, []).append((_ts(d.get("recorded_at")), _norm_codex(usage)))


def _norm_codex(u):
    return {"total": u.get("totalTokens", 0), "input": u.get("inputTokens", 0),
            "cached": u.get("cachedInputTokens", 0), "output": u.get("outputTokens", 0)}


def _codex_session(path: Path, threads: dict):
    """Direct-player `codex_session.jsonl`: one line per turn with cumulative `turn.usage.total`."""
    tid = "session:" + _rel(path.parent)
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            usage = ((d.get("turn") or {}).get("usage") or {}).get("total")
            if usage:
                threads.setdefault(tid, []).append((_ts(d.get("timestamp")), _norm_codex(usage)))


def _opencode(path: Path, threads: dict):
    """OpenCode `message.updated` events: per-message usage; keep the last value of each message."""
    msgs = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"tokens"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            p = d.get("payload") or {}
            info = (p.get("properties") or p).get("info") if isinstance(p, dict) else None
            if not isinstance(info, dict) or "tokens" not in info:
                continue
            t = info["tokens"]
            cache = t.get("cache") or {}
            total = t.get("total") or (t.get("input", 0) + t.get("output", 0) + t.get("reasoning", 0)
                                       + cache.get("read", 0) + cache.get("write", 0))
            msgs[(info.get("sessionID"), info.get("id"))] = (_ts(d.get("recorded_at")), {
                "total": total, "input": t.get("input", 0) + cache.get("read", 0) + cache.get("write", 0),
                "cached": cache.get("read", 0), "output": t.get("output", 0) + t.get("reasoning", 0)})
    # Turn per-message usage into a cumulative series per session.
    by_session = {}
    for (sid, _mid), (t, u) in msgs.items():
        by_session.setdefault(sid, []).append((t or 0, u))
    for sid, rows in by_session.items():
        rows.sort(key=lambda r: r[0])
        acc = {"total": 0, "input": 0, "cached": 0, "output": 0}
        series = []
        for t, u in rows:
            acc = {k: acc[k] + u[k] for k in acc}
            series.append((t, dict(acc)))
        threads["opencode:" + str(sid)] = series


def token_threads(base: Path) -> dict:
    """All usage series under `base`, keyed by thread id (copies of a thread collapse to one key)."""
    threads: dict = {}
    for f in _walk(base):
        if f.name in ("app_server_events.jsonl", "agent_events.jsonl"):
            _codex_events(f, threads)
        elif f.name == "codex_session.jsonl":
            _codex_session(f, threads)
        elif f.name == "opencode_events.jsonl":
            _opencode(f, threads)
        elif f.name == "provider_usage.json":
            u = json.loads(f.read_text(encoding="utf-8"))
            threads["provider:" + _rel(f.parent)] = [(None, {
                "total": u.get("total_tokens", 0), "input": u.get("prompt_tokens", 0), "cached": 0,
                "output": u.get("completion_tokens", 0)})]
    return threads


def thread_final(series):
    return max(series, key=lambda r: r[1]["total"])[1]


def totals(threads: dict) -> dict | None:
    if not threads:
        return None
    acc = {"total": 0, "input": 0, "cached": 0, "output": 0}
    for s in threads.values():
        u = thread_final(s)
        for k in acc:
            acc[k] += u[k]
    acc["threads"] = len(threads)
    acc["thread_totals"] = {tid: thread_final(s)["total"] for tid, s in threads.items()}
    return acc


def tokens_until(threads: dict, t: float) -> int:
    """Cumulative total tokens across threads recorded at or before time t."""
    out = 0
    for s in threads.values():
        best = 0
        for ts, u in s:
            if ts is not None and ts <= t + 1:
                best = max(best, u["total"])
        out += best
    return out


# --------------------------------------------------------------------------- AVO campaigns

def _evaluations(c: Path):
    for name in ("evolution_summary.json", "lineage.json", "population.json"):
        f = c / name
        if f.exists():
            s = json.loads(f.read_text(encoding="utf-8"))
            evs = (s.get("population") or s).get("evaluations") or []
            if evs:
                return evs
    return []


def _levels(e):
    sc = e.get("score") or {}
    lv = sc.get("solver_levels_completed", sc.get("levels_completed"))
    wl = ((sc.get("environment_task") or {}).get("score") or {}).get("win_levels") or sc.get("win_levels")
    return (lv if lv is not None else e.get("fitness")), wl


def campaign(rel: str, label: str = "", group: str = "") -> dict:
    c = ROOT / rel
    cfg = json.loads((c / "evolution_config.json").read_text(encoding="utf-8"))
    threads = token_threads(c)
    evs = sorted(_evaluations(c), key=lambda e: e.get("recorded_at") or "")
    start = None
    for s in threads.values():
        for ts, _ in s:
            if ts is not None and (start is None or ts < start):
                start = ts
    rows, best = [], 0.0
    for i, e in enumerate(evs, 1):
        lv, wl = _levels(e)
        t = _ts(e.get("recorded_at"))
        best = max(best, float(lv or 0))
        rows.append({"n": i, "candidate": e.get("candidate_id"), "levels": lv, "win_levels": wl, "best": best,
                     "recorded_at": e.get("recorded_at"),
                     "hours": round((t - start) / 3600, 3) if (t and start) else None,
                     "cum_tokens": tokens_until(threads, t) if (t and threads) else None})
    wl = next((r["win_levels"] for r in reversed(rows) if r["win_levels"]), None)
    player = cfg.get("player") or {}
    return {"id": rel, "label": label, "group": group, "game": (cfg.get("profile_settings") or {}).get("game_id"),
            "inner": f"{player.get('model')} {player.get('effort') or ''}".strip(),
            "outer": f"{cfg.get('optimizer_model')} {cfg.get('optimizer_effort') or ''}".strip(),
            "world_model_mode": cfg.get("world_model_mode"), "fitness_owner": cfg.get("fitness_owner"),
            "max_evaluations": cfg.get("max_evaluations"), "evaluations": rows, "win_levels": wl,
            "best_levels": best if rows else None, "solved": bool(rows and wl and best >= wl),
            "tokens": totals(threads)}


MIDAS = [  # (path, label)
    ("avo/output/evolution/midas-live-v01-20260825", "Aug 25 Sol/Sol, in-run levels"),
    ("avo/output/evolution/midas-solver-v03-20260827", "Aug 27 v03"),
    ("avo/output/evolution/midas-solver-v04-20260827", "Aug 27 v04"),
    ("avo/output/evolution/midas-solver-clean-v08-20260827", "Aug 27 clean v08"),
    ("avo/output/evolution/midas-luna-medium-sol-high-20260828T144003", "Aug 28 Luna/Sol"),
    ("avo/output/evolution/midas-luna-medium-sol-high-20260828T200612", "Aug 28 Luna/Sol (2)"),
    ("avo/output/evolution/midas-outer-evidence-luna-medium-sol-high-20260828T210529", "Aug 28 Luna/Sol, outer evidence"),
    ("avo/output/evolution/midas-outer-sol-high-inner-sol-high-x20-budget300-20260831T013257", "Aug 31 Sol/Sol, 300 research"),
    ("avo/output/evolution/midas-outer-sol-high-fast-inner-sol-high-fast-x20-research500-eval1500-20260831T031836", "Aug 31 Sol/Sol fast, 500 research"),
    ("avo/output/evolution/midas-outer-sol-high-inner-sol-high-x20-discovery-research500-eval1500-20260831T042951", "Aug 31 Sol/Sol discovery, 500 research"),
]
MIDAS_NO_EVAL = [  # campaigns that recorded no evaluation (tokens only)
    "avo/output/evolution/midas-solver-v01-20260827", "avo/output/evolution/midas-solver-v02-20260827",
    "avo/output/evolution/midas-solver-clean-v05-20260827", "avo/output/evolution/midas-solver-clean-v06-20260827",
    "avo/output/evolution/midas-solver-clean-v07-20260827", "avo/output/evolution/midas-model-first-v01-20260828",
    "avo/output/evolution/midas-model-first-luna-high-20260828", "avo/output/evolution/midas-model-first-luna-high-v01-20260828",
    "avo/output/evolution/midas-model-first-luna-high-v02-20260828", "avo/output/evolution/midas-model-first-luna-high-v03-20260828",
    "avo/output/evolution/midas-spark-high-sol-high-20260828",
]

# Final campaign folder of each game in each multi-game batch (later folders resume earlier ones).
MULTI = [
    # Sep 8: Astra low outer, Luna high inner (r7 repairs; continuation r3 for the three unsolved games)
    ("output/avo-six-live-20260908-r7/repairs/modality-04/campaign", "Modality", "Sep 8 Astra/Luna"),
    ("output/avo-six-live-20260908-r7/repairs/purple-04/campaign", "Purple", "Sep 8 Astra/Luna"),
    ("output/avo-six-live-20260908-r7/repairs/magnetic-04/campaign", "Magnetic", "Sep 8 Astra/Luna"),
    ("output/avo-three-continue-x10-20260908-r3/knightoban-04/campaign", "Knightoban", "Sep 8 Astra/Luna"),
    ("output/avo-three-continue-x10-20260908-r3/atlas-04/campaign", "Atlas Shrank", "Sep 8 Astra/Luna"),
    ("output/avo-three-continue-x10-20260908-r3/enqueue-04/campaign", "Enqueue", "Sep 8 Astra/Luna"),
    # Sep 10: OpenCode muse-spark
    ("output/opencode-modality-muse-20260910-02/campaign", "Modality", "Sep 10 OpenCode muse-spark"),
    # Sep 14: Astra medium outer, Luna medium inner, two world-model modes
    ("output/workbench/20260914T142420-astra-luna-six-pairs/run-0001/campaign", "Feeling like filling", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T142420-astra-luna-six-pairs/run-0002/campaign", "Feeling like filling", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T142420-astra-luna-six-pairs/run-0003/campaign", "Mowing", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T142420-astra-luna-six-pairs/run-0004/campaign", "Mowing", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T142420-astra-luna-six-pairs/run-0009/campaign", "Fatigued square maze", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T142420-astra-luna-six-pairs/run-0010/campaign", "Fatigued square maze", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T142104Z-storage-recovery/run-0005/campaign", "2D whale world", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T142104Z-storage-recovery/run-0006/campaign", "2D whale world", "Sep 14 Astra/Luna"),
    ("output/workbench/20260914T213636Z-usage-recovery/run-0001/campaign", "Compressed", "Sep 14 Astra/Luna xhigh"),
    ("output/workbench/20260914T213636Z-usage-recovery/run-0002/campaign", "Compressed", "Sep 14 Astra/Luna xhigh"),
    ("output/workbench/20260914T213636Z-usage-recovery/run-0003/campaign", "Using pushers", "Sep 14 Astra/Luna xhigh"),
    ("output/workbench/20260914T213636Z-usage-recovery/run-0004/campaign", "Using pushers", "Sep 14 Astra/Luna xhigh"),
    # Sep 22: GPT-6 Astra in both roles
    ("output/workbench/20260922T104342-96361f28/run-0001/campaign", "IceCrates", "Sep 22 Astra/Astra"),
    ("output/workbench/20260922T104342-96361f28/run-0002/campaign", "IceCrates", "Sep 22 Astra/Astra"),
    ("output/workbench/20260922T104342-96361f28/run-0003/campaign", "Portal Ban", "Sep 22 Astra/Astra"),
    ("output/workbench/20260922T104342-96361f28/run-0004/campaign", "Portal Ban", "Sep 22 Astra/Astra"),
    ("output/workbench/20260922T104342-04b2a088/run-0001/campaign", "Enqueue", "Sep 22 Astra/Astra"),
    ("output/workbench/20260922T104342-04b2a088/run-0002/campaign", "Enqueue", "Sep 22 Astra/Astra"),
    ("output/workbench/20260922T104342-04b2a088/run-0003/campaign", "Atlas Shrank", "Sep 22 Astra/Astra"),
    ("output/workbench/20260922T104342-04b2a088/run-0004/campaign", "Atlas Shrank", "Sep 22 Astra/Astra"),
    # Sep 23-24: DeepSeek V4.1 Flash (both roles, OpenRouter through Codex) and GPT-6 Luna/Sol on Enqueue
    ("output/workbench/20260923T145406-40bfa276/run-0001/campaign", "Modality", "Sep 23 DeepSeek Flash"),
    ("output/workbench/20260923T145406-40bfa276/run-0003/campaign", "IceCrates", "Sep 23 DeepSeek Flash"),
    ("output/workbench/20260923T160431-1fbf9810/run-0001/campaign", "Knightoban", "Sep 23 DeepSeek Flash"),
    ("output/workbench/20260924T084030-resume-cb21528d/run-0001/campaign", "Enqueue", "Sep 23 DeepSeek Flash"),
    ("output/workbench/20260924T012255-d419258c/run-0001/campaign", "Enqueue", "Sep 24 GPT-6 Luna/Sol"),
]

# Campaign folders that are aborted attempts or earlier segments (tokens only, for the overview).
MULTI_OTHER_GLOBS = [
    "output/avo-six-live-20260908/run-*/campaign", "output/avo-six-live-20260908-r[2-7]/run-*/campaign",
    "output/avo-six-live-20260908-r7/repairs/*-0[23]/campaign",
    "output/avo-three-continue-x10-20260908/*/campaign", "output/avo-three-continue-x10-20260908-r2/*/campaign",
    "output/workbench/20260914T142420-astra-luna-six-pairs/run-00*/campaign",
    "output/workbench/20260914T142104Z-storage-recovery/run-00*/campaign",
    "output/workbench/20260914T212836-8fa9be08/run-00*/campaign",
    "output/workbench/20260923T145406-40bfa276/run-0002/campaign",
    "output/workbench/20260924T010548-df1831ea/run-0001/campaign",
    "output/deepseek-max-trace-probe-20260923*/campaign",
    "output/codex-openrouter-side-test-20260914/*/campaign",
]


# --------------------------------------------------------------------------- direct player

DIRECT = [  # (path, label)
    ("output/codex_agent/luna-high-baseline-vs-plus-20260904-151524/baseline", "Luna high · baseline"),
    ("output/codex_agent/luna-high-baseline-vs-plus-20260904-151524/baseline-plus", "Luna high · baseline+"),
    ("output/codex_agent/gpt55-medium-baseline-plus-notes-fixed-20260904-161913", "GPT-5.5 medium · baseline+, notes fixed"),
    ("output/codex_agent/baseline-vs-plus-20260904-135358/baseline", "GPT-5.5 medium · baseline"),
    ("output/codex_agent/run-20260904-234208", "GPT-5.5 medium · baseline+"),
    ("studies/codex_agent/output/20260904-final-gpt55-medium-baseline-sokoban-basic", "GPT-5.5 medium · baseline, 200 steps"),
    ("studies/codex_agent/output/20260904-final-gpt55-medium-baseline-plus-plus-sokoban-basic", "GPT-5.5 medium · baseline++, 200 steps"),
    ("output/codex_agent/gpt55-xhigh-baseline-plus-20260905-audit", "GPT-5.5 xhigh · baseline+"),
    ("output/codex_agent/luna-medium-baseline-150-20260905-v4", "Luna medium · baseline"),
    ("output/codex_agent/luna-medium-baseline-plus-150-20260905-v4", "Luna medium · baseline+"),
    ("output/codex_agent/modality-55-high-baseline-plus-1000-20260907T181409-r3", "GPT-5.5 high · baseline+"),
]
DIRECT_ABORTED_GLOBS = [
    "output/codex_agent/luna-medium-baseline*-150-20260905-audit", "output/codex_agent/luna-medium-baseline*-150-20260905-v[23]",
    "output/codex_agent/gpt55-xhigh-baseline-plus-continuation50-20260905", "output/codex_agent/run-20260904-233705",
    "output/codex_agent/modality-55-high-baseline-plus-1000-20260907T181409", "output/codex_agent/modality-55-high-baseline-plus-1000-20260907T181409-r2",
    "output/codex_agent/baseline-vs-plus-20260904-135358/baseline-plus",
]


def _run_date(rel: str) -> str | None:
    import re
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", rel)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _level_ups(d: Path) -> list[int]:
    """Action number at which each level was completed (from transitions, else the transcript)."""
    ups, prev = [], 0
    if (d / "transitions.jsonl").exists():
        for line in (d / "transitions.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            lv = (r.get("after") or {}).get("levels_completed") or 0
            if lv > prev:
                ups.append(r.get("action_index"))
                prev = lv
        return ups
    if (d / "transcript.jsonl").exists():
        n = 0
        for line in (d / "transcript.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line).get("result") or {}
            if r.get("action"):
                n += 1
            lv = r.get("levels_completed") or 0
            if lv > prev:
                ups.append(n)
                prev = lv
    return ups


def direct_run(rel: str, label: str = "") -> dict:
    d = ROOT / rel
    cfg = json.loads((d / "run_config.json").read_text(encoding="utf-8"))
    res = json.loads((d / "result.json").read_text(encoding="utf-8")) if (d / "result.json").exists() else None
    err = json.loads((d / "error.json").read_text(encoding="utf-8")) if (d / "error.json").exists() else None
    levels = wl = actions = None
    solved = False
    if res:
        levels, wl, actions, solved = res.get("levels_completed"), res.get("win_levels"), res.get("action_count"), bool(res.get("solved"))
        # Before c6a701a (Sep 14) the runtime did not count the final level on WIN; a WIN state is the whole game.
        if res.get("final_state") == "WIN" and wl:
            levels = wl
    elif (d / "transitions.jsonl").exists():  # no result file: read the last recorded transition
        lines = (d / "transitions.jsonl").read_text(encoding="utf-8").splitlines()
        if lines:
            last = json.loads(lines[-1])
            after = last.get("after") or {}
            levels, wl, actions = after.get("levels_completed"), after.get("win_levels"), len(lines)
    ups = _level_ups(d)
    if levels and wl and levels == wl and len(ups) < wl and actions:
        ups.append(actions)  # the winning action of the final level
    return {"id": rel, "label": label, "model": cfg.get("model"), "effort": cfg.get("reasoning_effort"),
            "date": _run_date(rel), "level_up_at_action": ups, "final_state": (res or {}).get("final_state"),
            "condition": cfg.get("condition"), "game": cfg.get("game_id"), "max_steps": cfg.get("max_steps"),
            "levels": levels, "win_levels": wl, "actions": actions, "task_goal_reached": solved,
            "has_result": res is not None, "error": (err or {}).get("message"),
            "tokens": totals(token_threads(d))}


# --------------------------------------------------------------------------- other single runs

SINGLE = [  # first AVO single-agent runs (Aug 23-25)
    "avo/output/20260823T185546", "avo/output/20260823T190032", "avo/output/20260823T191110",
    "avo/output/20260823T195926", "avo/output/20260823T200521", "avo/output/20260823T200837",
    "avo/output/20260823T201145", "avo/output/20260823T201214",
    "avo/output/sokoban-basic-full-20260824", "avo/output/sokoban-basic-full-v04-20260824",
    "avo/output/midas-full-v01-20260825", "avo/output/midas-full-v02-20260825", "avo/output/midas-full-v03-20260825",
    "avo/output/midas-visible-v04-20260825", "avo/output/midas-visible-patterns-v05-20260825",
    "avo/output/midas-checkpoints-v06-20260825",
]


def single_run(rel: str) -> dict:
    d = ROOT / rel
    cfg = json.loads((d / "run_config.json").read_text(encoding="utf-8")) if (d / "run_config.json").exists() else {}
    fs = json.loads((d / "final_summary.json").read_text(encoding="utf-8")) if (d / "final_summary.json").exists() else {}
    model = cfg.get("model") or (cfg.get("agent") or {}).get("model") or cfg.get("provider_model")
    pu = d / "provider_usage.json"
    if pu.exists():
        model = json.loads(pu.read_text(encoding="utf-8")).get("model") or model
    score = (fs.get("score") or (fs.get("evaluation") or {}).get("score") or {})
    levels = score.get("levels_completed", fs.get("levels_completed"))
    if fs.get("success") and score.get("win_levels"):
        levels = score["win_levels"]  # final level not counted on WIN before c6a701a
    return {"id": rel, "model": model, "game": cfg.get("game_id") or (cfg.get("profile_settings") or {}).get("game_id"),
            "levels": levels,
            "win_levels": score.get("win_levels", fs.get("win_levels")),
            "success": fs.get("success"), "environment_steps": fs.get("environment_steps"),
            "tokens": totals(token_threads(d))}


# --------------------------------------------------------------------------- extraction

def extract() -> dict:
    data = {"generated_from": "run folders under avo/output, output/ and studies/codex_agent/output",
            "token_definition": "total = input tokens (including cache hits) + output tokens (including reasoning), "
                                "summed over every model session (outer optimizer + inner research agents) found in the run folder",
            "midas": [campaign(p, label) for p, label in MIDAS],
            "midas_no_evaluation": [campaign(p) for p in MIDAS_NO_EVAL],
            "multi": [campaign(p, game, group) for p, game, group in MULTI],
            "direct": [direct_run(p, label) for p, label in DIRECT],
            "single": [single_run(p) for p in SINGLE]}
    used = {c["id"] for c in data["multi"]}
    other = []
    for pat in MULTI_OTHER_GLOBS:
        for p in sorted(glob.glob(str(ROOT / pat))):
            rel = Path(p).relative_to(ROOT).as_posix()
            if rel not in used and (Path(p) / "evolution_config.json").exists():
                used.add(rel)
                other.append(campaign(rel, group="aborted or resumed segment"))
    data["multi_other"] = other
    da = []
    for pat in DIRECT_ABORTED_GLOBS:
        for p in sorted(glob.glob(str(ROOT / pat))):
            da.append(direct_run(Path(p).relative_to(ROOT).as_posix()))
    data["direct_aborted"] = da
    return data


# --------------------------------------------------------------------------- plotting

CREAM, INK, MUTED, FAINT = "#fbf8f2", "#2b2722", "#6f6a62", "#a39d92"
GRID, AXIS, TRACK = "#e9e3d7", "#cfc7b8", "#efe9dd"
BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#b9b2a6"
W, H, DPI = 13.333, 7.5, 150


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 13, "text.color": INK,
        "axes.labelcolor": MUTED, "axes.labelsize": 14, "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelsize": 13, "ytick.labelsize": 13, "axes.edgecolor": AXIS, "axes.linewidth": 1,
        "savefig.facecolor": CREAM, "figure.facecolor": CREAM, "axes.facecolor": CREAM,
        "legend.frameon": False, "legend.fontsize": 13, "lines.solid_capstyle": "round",
    })
    return plt


def _fig(plt, title, subtitle, size=23):
    fig = plt.figure(figsize=(W, H), dpi=DPI)
    fig.text(0.045, 0.935, title, size=size, weight="bold", color=INK, va="baseline")
    fig.text(0.045, 0.893, subtitle, size=14, color=MUTED, va="baseline")
    return fig


def _style(ax, grid="y"):
    ax.set_facecolor(CREAM)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0, pad=6)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.9)
        ax.set_axisbelow(True)


def _foot(fig, text):
    fig.text(0.045, 0.022, text, size=11, color=FAINT, va="baseline")


def M(n):
    return f"{n / 1e6:.1f}M" if n < 1e9 else f"{n / 1e9:.2f}B"


def _curve(c):
    """Step curve of best-so-far levels against cumulative tokens, starting at the origin."""
    xs, ys = [0.0], [0.0]
    for r in c["evaluations"]:
        if r["cum_tokens"] is None:
            continue
        xs.append(r["cum_tokens"] / 1e6)
        ys.append(r["best"])
    return xs, ys


def _draw_curve(ax, c, color, lw=2.2, alpha=1.0, z=3, extend=True, markers=True):
    xs, ys = _curve(c)
    ax.plot(xs, ys, drawstyle="steps-post", color=color, lw=lw, alpha=alpha, zorder=z, solid_joinstyle="round")
    if markers and len(xs) > 1:
        ax.scatter(xs[1:], ys[1:], s=34, color=color, alpha=alpha, zorder=z + 1, edgecolors=CREAM, linewidths=1.5)
    if extend and c["tokens"] and c["tokens"]["total"] / 1e6 > xs[-1] * 1.01:
        end = c["tokens"]["total"] / 1e6  # tokens spent after the last recorded evaluation
        ax.plot([xs[-1], end], [ys[-1], ys[-1]], color=color, lw=1.2, alpha=0.55 * alpha, zorder=z)
        ax.scatter([end], [ys[-1]], s=30, facecolors=CREAM, edgecolors=color, linewidths=1.5, alpha=alpha, zorder=z + 1)
    return xs[-1], ys[-1]


# Figure 1 ------------------------------------------------------------------

def fig_midas(plt, data, out):
    by = {c["id"].split("/")[-1]: c for c in data["midas"]}
    live = by["midas-live-v01-20260825"]
    best = by["midas-outer-evidence-luna-medium-sol-high-20260828T210529"]
    fresh_other = [by[k] for k in by if k.startswith("midas-luna-medium") or k.startswith("midas-outer-sol")]
    inrun_one = [by[k] for k in ("midas-solver-v03-20260827", "midas-solver-v04-20260827", "midas-solver-clean-v08-20260827")]
    singles = [r for r in data["single"] if r["game"] == "ps_midas-v1" and r["tokens"] and r["levels"] is not None]

    fig = _fig(plt, "Midas: playing in-run reached 8 of 15 levels; fresh solvers peaked at 6",
               "Best levels so far against cumulative tokens, AVO on ps_midas-v1, Aug 25–31 (outer optimizer + inner agents)")
    ax = fig.add_axes([0.075, 0.12, 0.66, 0.71])
    _style(ax)
    for c in fresh_other:
        _draw_curve(ax, c, BLUE, lw=1.6, alpha=0.38, z=2)
    _draw_curve(ax, best, BLUE, lw=2.6, z=5)
    _draw_curve(ax, live, ORANGE, lw=2.6, z=5)
    for c in inrun_one:
        r = c["evaluations"][-1]
        ax.scatter([r["cum_tokens"] / 1e6], [r["best"]], s=60, color=ORANGE, zorder=6, edgecolors=CREAM, linewidths=1.5)
    for r in singles:
        ax.scatter([r["tokens"]["total"] / 1e6], [r["levels"]], s=60, marker="D", color=ORANGE, alpha=0.6, zorder=4,
                   edgecolors=CREAM, linewidths=1.5)
    ax.set_xlim(0, 92)
    ax.set_ylim(0, 15.6)
    ax.set_yticks([0, 3, 6, 9, 12, 15])
    ax.axhline(15, color=AXIS, lw=1, zorder=1)
    ax.text(1, 15.15, "all 15 levels", size=12, color=MUTED)
    ax.set_xlabel("cumulative tokens (millions)")
    ax.set_ylabel("best levels completed")

    bt, bl = best["evaluations"][-1]["cum_tokens"] / 1e6, best["best_levels"]
    ax.text(bt, bl + 0.45, f"Luna inner + Sol outer, {len(best['evaluations'])} fresh-solver\n"
                           f"evaluations: {bl:g}/15 at {M(best['evaluations'][-1]['cum_tokens'])} tokens",
            ha="right", va="bottom", size=13, color=INK)
    lt, ll = live["evaluations"][-1]["cum_tokens"] / 1e6, live["best_levels"]
    ax.text(lt + 1.2, ll + 0.2, f"Sol/Sol, {len(live['evaluations'])} whole-run evaluations: {ll:g}/15 at "
                          f"{M(live['evaluations'][-1]['cum_tokens'])}\n(the agent plays; no reusable solver)",
            ha="left", va="bottom", size=13, color=INK)
    v04 = by["midas-solver-v04-20260827"]["evaluations"][-1]
    ax.text(v04["cum_tokens"] / 1e6, 8.45, f"Aug 27 v04: 8/15 at {M(v04['cum_tokens'])}", ha="center", va="bottom",
            size=12.5, color=INK)
    lo = min(r["tokens"]["total"] for r in singles) / 1e6
    ax.text(19.5, 4.3, f"at 4/15, {lo:.0f}–24M: single-agent runs (diamonds)\nand two 1-evaluation campaigns",
            size=12, color=MUTED, va="bottom")
    ax.text(21.5, 1.75, "light blue: other fresh-solver campaigns, 2–4/15 at 14–40M", size=12, color=MUTED, va="center")

    from matplotlib.lines import Line2D
    h = [Line2D([], [], color=BLUE, lw=2.6, marker="o", ms=6, mec=CREAM),
         Line2D([], [], color=ORANGE, lw=2.6, marker="o", ms=6, mec=CREAM)]
    fig.legend(h, ["learned solver replayed from a\nfresh reset (Aug 28–31)", "agent plays the game itself\n(Aug 25–27)"],
               loc="upper left", bbox_to_anchor=(0.75, 0.83), handlelength=2.2, labelspacing=1.1)
    side = fig.add_axes([0.758, 0.12, 0.21, 0.5]); side.axis("off")
    nf = sum(c["tokens"]["total"] for c in data["midas"] + data["midas_no_evaluation"] if c["tokens"]) + \
        sum(r["tokens"]["total"] for r in data["single"] if r["tokens"] and r["game"] == "ps_midas-v1")
    side.text(0, 1, f"{M(nf)} tokens across all Midas\nruns logged Aug 25–31.\n\n"
                    "Hollow end dots: tokens spent\nafter the last evaluation.\n\n"
                    "Levels before Aug 28 come from the\nagent's own play; from Aug 28 the\n"
                    "score is the learned solver alone.", size=12.5, color=MUTED, va="top", linespacing=1.35)
    _foot(fig, "Source: avo/output/evolution/midas-*, avo/output/midas-*-20260825. Tokens = input incl. cache hits + output.")
    fig.savefig(out / "fig1_midas_levels_vs_tokens.png")
    plt.close(fig)


# Figure 2 ------------------------------------------------------------------

def fig_games(plt, data, out):
    multi = data["multi"]
    games = ["Modality", "Purple", "Magnetic", "Knightoban", "Atlas Shrank", "Enqueue", "IceCrates"]
    style = {"Sep 8 Astra/Luna": (BLUE, "Astra low / Luna high, Sep 8"),
             "Sep 10 OpenCode muse-spark": (AQUA, "OpenCode muse-spark, Sep 10"),
             "Sep 23 DeepSeek Flash": (ORANGE, "DeepSeek V4.1 Flash, Sep 23–24")}
    nolog = {"Sep 22 Astra/Astra": "Astra/Astra", "Sep 24 GPT-6 Luna/Sol": "GPT-6 Luna/Sol"}
    fig = _fig(plt, "DeepSeek Flash matched GPT's best level on every game both played",
               "Best fresh-solver levels against cumulative tokens (millions), one AVO campaign per line, Sep 8–24", size=23)
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], color=c, lw=2.6, marker="o", ms=6, mec=CREAM) for c, _ in style.values()],
               [n for _, n in style.values()], loc="upper left", bbox_to_anchor=(0.04, 0.875), ncol=3,
               handlelength=2.0, columnspacing=2.2, fontsize=13)
    gs = fig.add_gridspec(2, 4, left=0.045, right=0.985, top=0.765, bottom=0.215, wspace=0.26, hspace=1.05)
    for i, g in enumerate(games):
        ax = fig.add_subplot(gs[i // 4, i % 4])
        _style(ax)
        cs = [c for c in multi if c["label"] == g]
        wl = next(c["win_levels"] for c in cs if c["win_levels"])
        lines, xmax = [], 1
        for c in cs:
            if c["group"] in style and c["tokens"]:
                col, _ = style[c["group"]]
                x, y = _draw_curve(ax, c, col, lw=2.2)
                xmax = max(xmax, c["tokens"]["total"] / 1e6)
                lines.append((col, f"{y:g}/{wl} at {M(c['evaluations'][-1]['cum_tokens'])}, {len(c['evaluations'])} eval."))
        gray = []
        for grp, name in nolog.items():
            done = [c for c in cs if c["group"] == grp]
            if done:
                gray.append(f"{name} {max(c['best_levels'] for c in done):g}/{wl}")
        if gray:
            lines.append((GRAY, ", ".join(gray) + " (no token log)"))
        ax.set_xlim(0, xmax * 1.08)
        ax.set_ylim(0, wl * 1.04)
        ax.set_yticks([0, wl])
        ax.set_title(f"{g} ({wl} levels)", loc="left", size=14.5, color=INK, weight="bold", pad=8)
        for k, (col, txt) in enumerate(lines):
            off = -34 - 16 * k
            ax.annotate("●", (0, 0), xycoords="axes fraction", xytext=(0, off), textcoords="offset points",
                        size=11, color=col, va="center", annotation_clip=False)
            ax.annotate(txt, (0, 0), xycoords="axes fraction", xytext=(13, off), textcoords="offset points",
                        size=11.5, color=INK, va="center", annotation_clip=False)
    key = fig.add_subplot(gs[1, 3]); key.axis("off")
    key.text(-0.02, 1.12, "Label: best levels at the tokens of\nthe last evaluation, evaluations run.\n"
                         "Hollow dot: campaign total, including\ntokens spent after the last evaluation.\n\n"
                         "Grey: campaigns whose traces kept\nno token usage (compact tracing).\n"
                         "Portal Ban (not drawn): Astra/Astra\n5/5, no token log.",
             size=11.5, color=MUTED, va="top", transform=key.transAxes, linespacing=1.35)
    _foot(fig, "Source: output/avo-six-live-20260908-r7/repairs, output/avo-three-continue-x10-20260908-r3, "
               "output/opencode-modality-muse-20260910-02, output/workbench/2026092*.")
    fig.savefig(out / "fig2_games_levels_vs_tokens.png")
    plt.close(fig)


# Figure 3 ------------------------------------------------------------------

SEP14_FIRST_SEGMENT = {  # resumed campaigns: their first segment kept a token log, the resumed part did not
    "output/workbench/20260914T142104Z-storage-recovery/run-0005/campaign": "output/workbench/20260914T142420-astra-luna-six-pairs/run-0005/campaign",
    "output/workbench/20260914T142104Z-storage-recovery/run-0006/campaign": "output/workbench/20260914T142420-astra-luna-six-pairs/run-0006/campaign",
}
SEP14_MEDIUM_FAIL = {"Compressed": ["output/workbench/20260914T142104Z-storage-recovery/run-0007/campaign",
                                    "output/workbench/20260914T142104Z-storage-recovery/run-0008/campaign"],
                     "Using pushers": ["output/workbench/20260914T142104Z-storage-recovery/run-0011/campaign",
                                       "output/workbench/20260914T142104Z-storage-recovery/run-0012/campaign"]}


def fig_sep14(plt, data, out):
    rows = [("Feeling like filling", "Sep 14 Astra/Luna", "medium"), ("Mowing", "Sep 14 Astra/Luna", "medium"),
            ("Fatigued square maze", "Sep 14 Astra/Luna", "medium"), ("2D whale world", "Sep 14 Astra/Luna", "medium"),
            ("Compressed", "Sep 14 Astra/Luna xhigh", "xhigh"), ("Using pushers", "Sep 14 Astra/Luna xhigh", "xhigh")]
    seg = {c["id"]: c for c in data["multi_other"]}
    modes = [("final-only", BLUE, "world model written once, at the end"),
             ("between-hypotheses", ORANGE, "rewritten between hypotheses")]
    fig = _fig(plt, "Astra/Luna solved all six new games in some mode; neither mode was faster",
               "Evaluations until the fresh solver first won (10 allowed), Astra outer + Luna inner, Sep 14, two world-model modes",
               size=22)
    ax = fig.add_axes([0.2, 0.235, 0.47, 0.59])
    _style(ax, grid="x")
    ax.spines["left"].set_visible(False)
    y, ticks, labels = 0, [], []
    bh = 0.34
    for game, grp, eff in rows:
        cs = {c["world_model_mode"]: c for c in data["multi"] if c["label"] == game and c["group"] == grp}
        ticks.append(y + bh / 2 + 0.03)
        labels.append(f"{game}\n(Luna xhigh rerun)" if eff == "xhigh" else game)
        for k, (mode, col, _) in enumerate(modes):
            c = cs[mode]
            evs, wl = c["evaluations"], c["win_levels"]
            solved_at = next((r["n"] for r in evs if r["best"] >= wl), None)
            n = solved_at or len(evs)
            yy = y + k * (bh + 0.06)
            ax.barh(yy, n, height=bh, color=col, alpha=1.0 if solved_at else 0.35, zorder=3)
            if c["tokens"]:
                tok_txt = f"{M(c['tokens']['total'])} tokens"
            elif c["id"] in SEP14_FIRST_SEGMENT and seg[SEP14_FIRST_SEGMENT[c["id"]]]["tokens"]:
                tok_txt = f"≥{M(seg[SEP14_FIRST_SEGMENT[c['id']]]['tokens']['total'])} tokens*"
            else:
                tok_txt = "no token log"
            res = f"won at evaluation {n}" if solved_at else f"not won, {c['best_levels']:g}/{wl} after {n}"
            ax.text(n + 0.15, yy, f"{res} · {tok_txt}", va="center", size=12, color=INK, zorder=4)
        y += 2 * bh + 0.55
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels, size=13, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 10.2)
    ax.set_xticks(range(0, 11, 2))
    ax.set_xlabel("evaluations used")
    from matplotlib.patches import Patch
    fig.legend([Patch(color=c) for _, c, _ in modes], [f"{m}: {d}" for m, _, d in modes],
               loc="upper left", bbox_to_anchor=(0.195, 0.875), ncol=2, handlelength=1.2, columnspacing=2.0, fontsize=12.5)
    mf = []
    for g, ids in SEP14_MEDIUM_FAIL.items():
        mf.append(f"{g} {' and '.join(str(int(seg[i]['best_levels'])) + '/4' for i in ids)}")
    fig.text(0.045, 0.058, "Light bar: not won within the budget. Compressed and Using pushers first ran with Luna medium and stayed unsolved\n"
                           f"after 10 evaluations per mode ({'; '.join(mf)}).\n* First segment only: the storage and usage-limit recoveries "
                           "ran with compact tracing and kept no token usage.", size=12, color=MUTED, va="baseline", linespacing=1.4)
    _foot(fig, "Source: output/workbench/20260914T142420-astra-luna-six-pairs, 20260914T142104Z-storage-recovery, "
               "20260914T212836-8fa9be08, 20260914T213636Z-usage-recovery.")
    fig.savefig(out / "fig3_sep14_world_model_modes.png")
    plt.close(fig)


# Figure 4 ------------------------------------------------------------------

def _day(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def fig_direct(plt, data, out):
    runs = data["direct"]
    fig = _fig(plt, "Direct player: 3 of 10 Sokoban runs won; GPT-5.5 cleared 3 of 4 Modality levels",
               "Codex player, one action per turn, Sep 4–7. Bar = actions used, track = step budget, ticks = level completed",
               size=20.5)
    ax = fig.add_axes([0.3, 0.145, 0.43, 0.675])
    _style(ax, grid="x")
    ax.spines["left"].set_visible(False)
    ys, labels, y = [], [], 0
    for r in runs:
        if r["game"] == "ps_modality-v1":
            y += 0.8
        ys.append(y)
        cap = min(r["max_steps"], 300)
        ax.barh(y, cap, height=0.56, color=TRACK, zorder=1)
        col = BLUE if r["levels"] == r["win_levels"] else (ORANGE if r["levels"] else GRAY)
        ax.barh(y, r["actions"], height=0.56, color=col, zorder=3)
        for a in r["level_up_at_action"]:
            ax.plot([a, a], [y - 0.36, y + 0.36], color=INK, lw=1.8, zorder=4)
        tok = M(r["tokens"]["total"]) + " tokens" if r["tokens"] else "tokens not logged"
        budget = f" of {r['max_steps']:,}" if r["max_steps"] > 300 else ""
        ax.text(max(cap, r["actions"]) + 4, y, f"{r['levels']}/{r['win_levels']} · {r['actions']}{budget} actions · {tok}",
                va="center", size=12, color=INK)
        labels.append(f"{_day(r['date'])} · {r['label']}")
        y += 1
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, size=12.5, color=INK)
    ax.set_ylim(ys[-1] + 0.6, -1.2)
    ax.set_xlim(0, 300)
    ax.set_xlabel("environment actions")
    for yy, txt in ((-0.95, "Sokoban basic, 2 levels"), (ys[-1] - 0.75, "Modality, 4 levels")):
        ax.text(0, yy, txt, size=12.5, color=MUTED, weight="bold", va="center")
    from matplotlib.patches import Patch
    fig.legend([Patch(color=BLUE), Patch(color=ORANGE), Patch(color=GRAY)], ["won the game", "some levels", "no level"],
               loc="upper left", bbox_to_anchor=(0.295, 0.875), ncol=3, handlelength=1.2, fontsize=12.5)
    n_err = sum(1 for r in data["direct_aborted"] if r["error"])
    _foot(fig, f"Left out: {n_err} attempts aborted by the isolation guard or SDK start-up, "
               f"{len(data['direct_aborted']) - n_err} stopped without a result. "
               "WIN counts as 2/2: before c6a701a the runtime did not count the final level.")
    fig.savefig(out / "fig4_direct_player.png")
    plt.close(fig)


# Figure 5 ------------------------------------------------------------------

def _dedup_entities(data):
    """Every run once, each model session counted once even when resumed campaigns copied it."""
    seen, ents = set(), []

    def add(rec, group, outcome):
        t = rec.get("tokens")
        if not t:
            return
        new = {k: v for k, v in t["thread_totals"].items() if k not in seen}
        seen.update(new)
        tot = sum(new.values())
        if tot <= 0:
            return
        share = tot / t["total"] if t["total"] else 0
        ents.append({"id": rec["id"], "group": group, "outcome": outcome, "tokens": tot,
                     "cached": round(t["cached"] * share), "output": round(t["output"] * share)})

    def out_campaign(c):
        if not c["evaluations"]:
            return "none"
        return "solved" if c["solved"] else ("partial" if (c["best_levels"] or 0) > 0 else "none")

    groups = {"Sep 8 Astra/Luna": "luna", "Sep 14 Astra/Luna": "luna", "Sep 10 OpenCode muse-spark": "opencode",
              "Sep 23 DeepSeek Flash": "deepseek"}
    for c in data["multi"]:
        if c["group"] in groups:
            add(c, groups[c["group"]], out_campaign(c))
    for c in data["midas"]:
        add(c, "midas", out_campaign(c))
    for r in data["direct"]:
        add(r, "direct", "solved" if r["levels"] == r["win_levels"] else ("partial" if r["levels"] else "none"))
    for r in data["single"]:
        add(r, "opus" if "opus" in str(r["model"]) else "sol_single",
            "solved" if r["success"] else ("partial" if r["levels"] else "none"))
    for c in data["midas_no_evaluation"]:
        add(c, "midas", "none")
    for c in data["multi_other"]:
        add(c, "deepseek" if "deepseek" in c["inner"] else "luna", out_campaign(c))
    for r in data["direct_aborted"]:
        add(r, "direct", "none")
    return ents


GROUPS = [("opus", "AVO single agent · Opus 5 fast\n(OpenRouter) · Aug 23"),
          ("sol_single", "AVO single agent · GPT-5.6 Sol\nMidas · Aug 25"),
          ("midas", "AVO evolution · Sol or Luna inner,\nSol outer · Midas · Aug 25–31"),
          ("luna", "AVO evolution · Luna inner,\nAstra outer · Sep 8–14"),
          ("opencode", "AVO evolution · OpenCode\nmuse-spark · Sep 10"),
          ("deepseek", "AVO evolution · DeepSeek V4.1\nFlash (OpenRouter) · Sep 14–24"),
          ("direct", "Direct player · GPT-5.5 or\nLuna · Sep 4–7")]


def fig_overview(plt, data, out):
    import random
    ents = _dedup_entities(data)
    total = sum(e["tokens"] for e in ents)
    cached = sum(e["cached"] for e in ents)
    data["overview"] = {"runs": len(ents), "total_tokens": total, "cached_tokens": cached,
                        "output_tokens": sum(e["output"] for e in ents),
                        "by_group": {g: {"runs": sum(1 for e in ents if e["group"] == g),
                                         "tokens": sum(e["tokens"] for e in ents if e["group"] == g),
                                         "solved": sum(1 for e in ents if e["group"] == g and e["outcome"] == "solved")}
                                     for g, _ in GROUPS},
                        "entities": ents}
    fig = _fig(plt, f"July–September: {M(total)} tokens logged across {len(ents)} runs, {cached / total:.0%} of them cache hits",
               "Total tokens per run or campaign (log scale), each model session counted once; colour = best outcome", size=22)
    ax = fig.add_axes([0.25, 0.14, 0.55, 0.69])
    _style(ax, grid="x")
    ax.spines["left"].set_visible(False)
    ax.set_xscale("log")
    cols = {"solved": BLUE, "partial": ORANGE, "none": GRAY}
    rnd = random.Random(7)
    for gi, (g, _label) in enumerate(GROUPS):
        es = [e for e in ents if e["group"] == g]
        for e in sorted(es, key=lambda e: e["outcome"] != "none"):
            ax.scatter([e["tokens"]], [gi + (rnd.random() - 0.5) * 0.42], s=70, color=cols[e["outcome"]], zorder=3,
                       edgecolors=CREAM, linewidths=1.5)
        gt = sum(e["tokens"] for e in es)
        ns = sum(1 for e in es if e["outcome"] == "solved")
        ax.text(1.02, gi, f"{M(gt)} · {len(es)} run" + ("s" if len(es) != 1 else "") + (f" · {ns} won" if ns else ""), transform=ax.get_yaxis_transform(),
                va="center", size=12.5, color=INK)
    ax.set_yticks(range(len(GROUPS)))
    ax.set_yticklabels([l for _, l in GROUPS], size=12, color=INK, linespacing=1.15)
    ax.set_ylim(len(GROUPS) - 0.5, -0.75)
    ax.set_xlim(3e3, 4e8)
    ax.set_xticks([1e4, 1e5, 1e6, 1e7, 1e8])
    ax.set_xticklabels(["10K", "100K", "1M", "10M", "100M"])
    ax.minorticks_off()
    ax.set_xlabel("total tokens (input incl. cache hits + output)")
    ax.text(1.02, -0.7, "group total", transform=ax.get_yaxis_transform(), size=12, color=MUTED, weight="bold")
    from matplotlib.lines import Line2D
    h = [Line2D([], [], ls="", marker="o", ms=9, color=c, mec=CREAM) for c in cols.values()]
    fig.legend(h, ["won the game", "some levels", "no level or no evaluation"], loc="upper left",
               bbox_to_anchor=(0.245, 0.875), ncol=3, handletextpad=0.3, columnspacing=1.6, fontsize=12.5)
    _foot(fig, "No token usage recorded (left out): Jul 16 smoke runs, Aug 23 Sol runs, Aug 24 Sokoban, Sep 4 runs before 23:00, "
               "Sep 14 recoveries, Sep 22 Astra, Sep 24 GPT-6 Luna.")
    fig.savefig(out / "fig5_tokens_overview.png")
    plt.close(fig)


def main(data, out: Path):
    plt = _mpl()
    fig_midas(plt, data, out)
    fig_games(plt, data, out)
    fig_sep14(plt, data, out)
    fig_direct(plt, data, out)
    fig_overview(plt, data, out)


if __name__ == "__main__":
    import sys
    data_path = HERE / "data.json"
    if "--plot-only" in sys.argv and data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
    else:
        data = extract()
    if "--extract-only" not in sys.argv:
        main(data, HERE)
    data_path.write_text(json.dumps(data, indent=1), encoding="utf-8")


