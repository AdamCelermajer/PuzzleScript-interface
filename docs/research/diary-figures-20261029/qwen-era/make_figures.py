"""Diary figures for the Qwen 3.8 period (30 Sep - 21 Oct 2026).

Run from the repo root:
    uv run --no-project --with matplotlib python -I docs/research/diary-figures-20261029/qwen-era/make_figures.py

Reads run outputs (read-only) and writes, next to this script, data.json and fig1..fig6 PNGs.
Token counts:
- OpenCode: every `step_finish` part in raw/*.jsonl (input = fresh, cache.read = cached, output + reasoning = generated).
- Codex: the last cumulative `tokenUsage.total` per thread in app_server_events.jsonl (AVO) or the last
  `turn.usage.total` in codex_session.jsonl (Baseline+). Codex `inputTokens` already includes cached tokens.
"processed" = fresh + cached input tokens summed over every request; "generated" = output incl. reasoning.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
WB = "output/workbench"


def rp(rel: str) -> Path:
    return ROOT / rel


def read_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------------------------
SKIP_PARTS = ("workspace", "seed")


def _skipped(path: Path, base: Path) -> bool:
    return any(any(s in part for s in SKIP_PARTS) for part in path.relative_to(base).parts[:-1])


def zero() -> dict:
    return {"fresh": 0, "cached": 0, "generated": 0, "reasoning": 0, "requests": 0}


def add(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in zero()}


def opencode_tokens(path: Path) -> dict:
    t = zero()
    for e in read_jsonl(path):
        if e.get("type") != "step_finish":
            continue
        k = (e.get("part") or {}).get("tokens") or {}
        t["fresh"] += k.get("input", 0) or 0
        t["cached"] += ((k.get("cache") or {}).get("read", 0) or 0)
        t["generated"] += (k.get("output", 0) or 0) + (k.get("reasoning", 0) or 0)
        t["reasoning"] += k.get("reasoning", 0) or 0
        t["requests"] += 1
    return t


def _codex_total(u: dict) -> dict:
    cached = u.get("cachedInputTokens", 0) or 0
    return {"fresh": (u.get("inputTokens", 0) or 0) - cached, "cached": cached,
            "generated": u.get("outputTokens", 0) or 0, "reasoning": u.get("reasoningOutputTokens", 0) or 0,
            "requests": 0}


def codex_app_tokens(path: Path) -> dict:
    last: dict[str, dict] = {}
    for e in read_jsonl(path):
        if e.get("method") != "thread/tokenUsage/updated":
            continue
        p = e.get("payload") or {}
        last[p.get("threadId") or "?"] = (p.get("tokenUsage") or {}).get("total") or {}
    t = zero()
    for u in last.values():
        t = add(t, _codex_total(u))
    return t


def codex_session_tokens(path: Path) -> dict:
    """Cumulative totals; a drop in the running total starts a new segment."""
    t, seg, prev = zero(), None, -1
    for e in read_jsonl(path):
        u = ((e.get("turn") or {}).get("usage") or {}).get("total")
        if not u:
            continue
        if seg is not None and (u.get("totalTokens") or 0) < prev:
            t = add(t, _codex_total(seg))
        seg, prev = u, u.get("totalTokens") or 0
    if seg is not None:
        t = add(t, _codex_total(seg))
    return t


def tokens_in(rel: str) -> dict:
    """All tokens recorded under one run folder (players, coaches, optimizers)."""
    base = rp(rel)
    t = zero()
    if not base.exists():
        return t
    for f in base.rglob("*.jsonl"):
        if _skipped(f, base):
            continue
        if f.parent.name == "raw":
            t = add(t, opencode_tokens(f))
        elif f.name == "app_server_events.jsonl":
            t = add(t, codex_app_tokens(f))
        elif f.name == "codex_session.jsonl":
            t = add(t, codex_session_tokens(f))
    return t


def processed(t: dict) -> int:
    return t["fresh"] + t["cached"]


# ---------------------------------------------------------------------------------------------
# Game progress
# ---------------------------------------------------------------------------------------------
def level_ups(rel: str) -> tuple[int, list[int]]:
    """(actions, [action index at which each level was completed]) from transitions.jsonl."""
    rows = list(read_jsonl(rp(rel) / "transitions.jsonl"))
    ups = [r["action_index"] for r in rows
           if r["after"]["levels_completed"] > r["before"]["levels_completed"]]
    return len(rows), ups


def avo_research_levels(rel: str) -> tuple[int, list[int]]:
    """AVO research session: transitions counted in evidence.jsonl, level-ups from task_evaluated."""
    n, ups, best = 0, [], 0
    for e in read_jsonl(rp(rel) / "evidence.jsonl"):
        if e.get("type") == "transition":
            n += 1
        elif e.get("type") == "task_evaluated":
            lv = e["payload"]["score"]["levels_completed"]
            while lv > best:
                best += 1
                ups.append(n)
    return n, ups


# ---------------------------------------------------------------------------------------------
# 1. Quantization (21 Oct)
# ---------------------------------------------------------------------------------------------
QUANT = [  # arm, run folder, grading folder, host list price USD/M (fresh, output, cached) or None
    ("16-bit", "DeepInfra", f"{WB}/20261021T130008-thu-quant-bf16-deepinfra-77cb4e7e",
     "output/thursday/quant/bf16-deepinfra-77cb4e7e", (0.15, 1.875, 0.037)),
    ("8-bit", "Chutes", f"{WB}/20261021T130008-thu-quant-fp8-chutes-03610dbf",
     "output/thursday/quant/fp8-chutes-03610dbf", (0.039, 1.25, 0.004)),
    ("4-bit", "ModelRun", f"{WB}/20261021T130008-thu-quant-fp4-modelrun-6bdb73f4",
     "output/thursday/quant/fp4-modelrun-6bdb73f4", None),
]
# ModelRun's list price is not stored in the repo; the Thursday page (docs/research/thursday-20261022.html)
# reports $1.51 per game at the host's list price.
QUANT_4BIT_COST_FROM_PAGE = 1.51
NANOGPT_27B = (0.15, 0.7, 0.04)  # studies/thursday/metrics.py PRICES


def price(t: dict, p: tuple) -> float:
    fresh, out, cached = p
    return (t["fresh"] * fresh + t["cached"] * cached + t["generated"] * out) / 1e6


def quant_data() -> list[dict]:
    arms = []
    for arm, host, folder, gfolder, host_price in QUANT:
        grading = read_json(rp(gfolder) / "grading.json")
        runs = []
        for run in ("run-0001", "run-0002", "run-0003"):
            g = grading[run]
            c, p, w = g["rules_correct"], g["rules_partial"], g["rules_wrong"]
            actions, ups = level_ups(f"{folder}/{run}")
            t = tokens_in(f"{folder}/{run}")
            # bf16 run-0001: the 172nd action completed level 3 and ended the game before transitions.jsonl
            # recorded it (grading.json notes); the grading's level count is used when it is higher.
            levels = max(len(ups), int(g.get("levels_completed") or 0))
            runs.append({"run": f"{folder}/{run}", "actions": actions, "levels": levels,
                         "levels_in_transitions": len(ups), "level_at": ups,
                         "rules_correct": c, "rules_partial": p, "rules_wrong": w,
                         "rules_not_found": 7 - c - p - w, "degenerate_text": bool(g.get("degenerate_text")),
                         "tokens": t, "processed": processed(t),
                         "cost_host_usd": round(price(t, host_price), 3) if host_price else None,
                         "cost_nanogpt_usd": round(price(t, NANOGPT_27B), 3)})
        n = len(runs)
        cost_host = (round(sum(r["cost_host_usd"] for r in runs) / n, 3) if host_price
                     else QUANT_4BIT_COST_FROM_PAGE)
        arms.append({"arm": arm, "host": host, "runs": runs,
                     "rules": {k: sum(r[f"rules_{k}"] for r in runs) for k in ("correct", "partial", "wrong", "not_found")},
                     "mean_processed": sum(r["processed"] for r in runs) / n,
                     "mean_generated": sum(r["tokens"]["generated"] for r in runs) / n,
                     "mean_actions": sum(r["actions"] for r in runs) / n,
                     "cost_host_per_game": cost_host,
                     "cost_host_source": "computed from tokens x host list price" if host_price
                     else "Thursday page (ModelRun price not in repo)",
                     "cost_nanogpt_per_game": round(sum(r["cost_nanogpt_usd"] for r in runs) / n, 3),
                     "degenerate_runs": sum(r["degenerate_text"] for r in runs)})
    return arms


# ---------------------------------------------------------------------------------------------
# 2. Qwen family on Modality (8-15 Oct)
# ---------------------------------------------------------------------------------------------
FAMILY_BASELINE = [  # label, model, provider, run, date
    ("27B", "27B", "OpenRouter · Alibaba", f"{WB}/20261008T112945-f705fa9a/run-0001", "2026-10-08"),
    ("Flash", "Flash", "OpenRouter · Alibaba", f"{WB}/20261013T150241-d07d5558/run-0001", "2026-10-13"),
    ("Max", "Max", "OpenRouter · Alibaba", f"{WB}/20261013T150245-989f6c8b/run-0001", "2026-10-13"),
    ("27B", "27B", "NanoGPT", f"{WB}/20261015T012502-nano-modality-baseline-plus-fixed-714e64/run-0001", "2026-10-15"),
    ("Flash", "Flash", "NanoGPT", f"{WB}/20261015T012502-nano-modality-baseline-plus-fixed-714e64/run-0002", "2026-10-15"),
]
FAMILY_AVO = [
    ("27B", "OpenRouter · Alibaba", f"{WB}/20261013T165330-avo-27b-modality/run-0001/campaign", "2026-10-13"),
    ("Flash", "OpenRouter · Alibaba", f"{WB}/20261013T173422-avo-flash-modality-recovery/run-0001/campaign", "2026-10-13"),
    ("Max", "OpenRouter · Alibaba", f"{WB}/20261013T152559-avo-max-92c30e52/run-0001/campaign", "2026-10-13"),
    ("27B", "NanoGPT", f"{WB}/20261015T011847-nano-modality-avo-27b-thinking-e8ea89/run-0001/campaign", "2026-10-15"),
]


def avo_solver(rel: str) -> dict:
    s = read_json(rp(rel) / "x_0001" / "summary.json")
    score = s.get("score") or {}
    return {"solver_levels": score.get("solver_levels_completed"),
            "solver_actions": score.get("solver_environment_actions"),
            "research_levels": (score.get("research_score") or {}).get("levels_completed"),
            "research_actions": score.get("research_environment_actions")}


def family_data() -> dict:
    base = []
    for label, model, provider, run, date in FAMILY_BASELINE:
        actions, ups = level_ups(run)
        t = tokens_in(run)
        base.append({"model": model, "provider": provider, "run": run, "date": date, "actions": actions,
                     "levels": len(ups), "level_at": ups, "tokens": t, "processed": processed(t)})
    avo = []
    for model, provider, run, date in FAMILY_AVO:
        t = tokens_in(run)
        avo.append({"model": model, "provider": provider, "run": run, "date": date, **avo_solver(run),
                    "tokens": t, "processed": processed(t)})
    return {"baseline_plus": base, "avo": avo}


# ---------------------------------------------------------------------------------------------
# 3-4. Self-hosted 27B, 3 frameworks x 3 games (21 Oct)
# ---------------------------------------------------------------------------------------------
H2 = f"{WB}/20261021T144508-vast-fp8-harness2-153a4dc2"
B4 = f"{WB}/20261021T162323-vast-fp8-baseline-v4-6767db38"
AVO2 = f"{WB}/20261021T160936-vast-fp8-avo-v2-b994ed09"
GAMES = [("modality", "Modality", "run-0001", 4), ("icecrates", "IceCrates", "run-0002", 6),
         ("knightoban", "Knightoban", "run-0003", 6)]
SHORTEST = {  # per level; docs/research/premise-review-20261021.md, studies/thursday/rules/
    "modality": [6, 33, 66, 158],
    "icecrates": [4, 5, 12, 29, 8, 32],
    "knightoban": [20, 10, 33, 41, 32, 28],
}
OPENROUTER_27B = (0.04, 1.35, 0.018)  # output/thursday/cost/or_cost_raw.py, listing of 21 Oct


def vast_data() -> dict:
    games = {}
    for key, name, run, win in GAMES:
        g = {"name": name, "win_levels": win, "shortest": SHORTEST[key], "frameworks": {}, "rollouts": {}}
        # Harness² base1 = agent-driven player with an empty harness
        for label in ("base1", "inv1", "dom1"):
            rel = f"{H2}/{run}/rollouts/{label}"
            if not rp(rel).exists():
                continue
            actions, ups = level_ups(rel)
            t = tokens_in(rel)
            g["rollouts"][label] = {"run": rel, "actions": actions, "levels": len(ups), "level_at": ups,
                                    "tokens": t, "processed": processed(t)}
        coach = tokens_in(f"{H2}/{run}/improver")
        g["coach_tokens"] = coach
        g["coach_processed"] = processed(coach)
        g["frameworks"]["harness2_base1"] = g["rollouts"]["base1"]
        actions, ups = level_ups(f"{B4}/{run}")
        t = tokens_in(f"{B4}/{run}")
        g["frameworks"]["baseline_v4"] = {"run": f"{B4}/{run}", "actions": actions, "levels": len(ups),
                                          "level_at": ups, "tokens": t, "processed": processed(t)}
        actions, ups = avo_research_levels(f"{AVO2}/{run}/campaign/x_0001/research")
        t = tokens_in(f"{AVO2}/{run}")
        g["frameworks"]["avo_v2_research"] = {"run": f"{AVO2}/{run}", "actions": actions, "levels": len(ups),
                                              "level_at": ups, "tokens": t, "processed": processed(t),
                                              "solver_scored": False}
        for fw in g["frameworks"].values():
            fw["cost_openrouter_usd"] = round(price(fw["tokens"], OPENROUTER_27B), 2)
        games[key] = g
    return games


# ---------------------------------------------------------------------------------------------
# 5. Tool-call probe (21 Oct)
# ---------------------------------------------------------------------------------------------
PROBE_ROWS = [  # display label, condition prefix in probes.jsonl
    ("27B · Chat · plain tool", ["chat · short", "chat · long"]),
    ("27B · Responses · plain tool", ["responses · short", "responses · long"]),
    ("27B · Responses · flat tool", ["responses-flat · short", "responses-flat · long"]),
    ("Flash · Responses · plain tool", ["responses · short · qwen/qwen3.8-flash", "responses · long · qwen/qwen3.8-flash"]),
    ("27B · Responses · namespaced tool", ["responses-namespace · short", "responses-namespace · long"]),
    ("Flash · Responses · namespaced tool", ["responses-namespace · short · qwen/qwen3.8-flash",
                                             "responses-namespace · long · qwen/qwen3.8-flash"]),
    ("Codex's 15 Oct request · Responses", ["replay · responses (as Codex sent it)"]),
    ("same conversation · Chat", ["replay · chat (same conversation)"]),
]


def probe_data() -> dict:
    rows = list(read_jsonl(rp("output/thursday/q1/probes.jsonl")))
    out, tok, cost = [], 0, 0.0
    for label, conds in PROBE_ROWS:
        sel = [r for r in rows if r["condition"] in conds]
        c = collections.Counter(r["outcome"] for r in sel)
        t = sum((r.get("usage") or {}).get("total_tokens", 0) or 0 for r in sel)
        out.append({"label": label, "conditions": conds, "n": len(sel), "outcomes": dict(c), "tokens": t})
    for r in rows:
        u = r.get("usage") or {}
        tok += u.get("total_tokens", 0) or 0
        cost += u.get("cost", 0) or 0
    return {"rows": out, "probes": len(rows), "total_tokens": tok, "total_cost_usd": round(cost, 3)}


# ---------------------------------------------------------------------------------------------
# 6. The period: 27B on Modality over time, and tokens per run
# ---------------------------------------------------------------------------------------------
PERIOD_27B_MODALITY = [  # label, date, driver (turn | agent), provider, harness, run folder
    ("30 Sep · Codex · OpenRouter", "2026-09-30", "turn", "OpenRouter", "codex", f"{WB}/20260930T224156-3572b5fe/run-0001"),
    ("8 Oct · Codex · Alibaba", "2026-10-08", "turn", "OpenRouter", "codex", f"{WB}/20261008T112945-f705fa9a/run-0001"),
    ("15 Oct · Codex · NanoGPT", "2026-10-15", "turn", "NanoGPT", "codex",
     f"{WB}/20261015T012502-nano-modality-baseline-plus-fixed-714e64/run-0001"),
    ("20 Oct · OpenCode turn-by-turn · NanoGPT", "2026-10-20", "turn", "NanoGPT", "opencode",
     f"{WB}/20261020T123325-modality-harness2-27b-thinking-image-245dcdb8/run-0001/rollouts/base1"),
    ("20 Oct · OpenCode agent-driven · NanoGPT", "2026-10-20", "agent", "NanoGPT", "opencode",
     f"{WB}/20261020T142237-modality-harness2-27b-agent-d099cb74/run-0001/rollouts/base1"),
    ("21 Oct · OpenCode turn-based v4 · self-hosted", "2026-10-21", "turn", "vast", "opencode", f"{B4}/run-0001"),
    ("21 Oct · OpenCode agent-driven · self-hosted", "2026-10-21", "agent", "vast", "opencode", f"{H2}/run-0001/rollouts/base1"),
]
for _arm, _host, _folder, _g, _p in QUANT:
    for _i in (1, 2, 3):
        PERIOD_27B_MODALITY.append((f"21 Oct · quant {_arm} · NanoGPT pinned", "2026-10-21", "agent", "NanoGPT",
                                    "opencode", f"{_folder}/run-000{_i}"))

INDEX_FIRST, INDEX_LAST = "2026-09-30", "2026-10-21"


def provider_of(model: str) -> str:
    m = (model or "").split("/")[0]
    return {"openrouter": "OpenRouter", "nanogpt": "NanoGPT", "vast": "vast"}.get(m, m or "?")


def model_of(model: str) -> str:
    m = (model or "").lower()
    for k, v in (("27b", "27B"), ("flash", "Flash"), ("max", "Max")):
        if k in m:
            return v
    return m.split("/")[-1] or "?"


def _run_meta(run: Path) -> dict:
    for name in ("run_spec.json", "run_config.json", "campaign/evolution_config.json", "campaign/run_spec.json"):
        d = read_json(run / name)
        if not d.get("model") and isinstance(d.get("player"), dict):  # AVO evolution_config.json
            d = {**d["player"], "framework": "avo", "game_id": (d.get("profile_settings") or {}).get("game_id", "")}
        if d.get("model"):
            fw = d.get("framework") or ("avo" if (run / "campaign").is_dir() else "baseline")
            return {"model": d["model"], "framework": fw, "harness": d.get("harness") or d.get("agent_backend")
                    or ("codex" if "codex" in run.as_posix() or not d.get("harness") else ""),
                    "game": d.get("game_id") or ""}
    return {}


def period_runs() -> list[dict]:
    """Every run folder started 30 Sep - 21 Oct with a Qwen 3.8 model and recorded tokens.

    Sources: output/workbench/<YYYYMMDDT...-job>/run-NNNN and the 8 Oct output/codex_agent/qwen* runs
    (smoke folders are left out). Harness is Codex for every run before 15 Oct whose spec names none.
    """
    candidates = []
    for job in sorted(rp(WB).iterdir()):
        m = re.match(r"(\d{4})(\d{2})(\d{2})T", job.name)
        if not (job.is_dir() and m):
            continue
        date = "-".join(m.groups())
        if INDEX_FIRST <= date <= INDEX_LAST:
            candidates += [(date, r) for r in sorted(job.glob("run-*")) if r.is_dir()]
    for r in sorted(rp("output/codex_agent").glob("qwen*-2026100*")):
        if r.is_dir():
            candidates.append(("2026-10-08", r))
    rows = []
    for date, run in candidates:
        meta = _run_meta(run)
        model = str(meta.get("model", ""))
        if "qwen" not in model and not model.startswith("vast/"):
            continue
        rel = run.relative_to(ROOT).as_posix()
        t = tokens_in(rel)
        if processed(t) == 0:
            continue
        fw = {"avo": "AVO", "harness2": "Harness²"}.get(str(meta["framework"]), "Baseline")
        harness = "opencode" if t["requests"] else "codex"  # only OpenCode records per-request counts
        rows.append({"id": rel, "date": date, "provider": provider_of(model), "model": model_of(model),
                     "harness": harness, "framework": fw,
                     "game": str(meta.get("game")).replace("ps_", "").replace("-v1", ""),
                     "tokens": t, "processed": processed(t)})
    return rows


def period_data() -> dict:
    lines = []
    for label, date, driver, provider, harness, run in PERIOD_27B_MODALITY:
        actions, ups = level_ups(run)
        t = tokens_in(run)
        lines.append({"label": label, "date": date, "driver": driver, "provider": provider, "harness": harness,
                      "run": run, "actions": actions, "levels": len(ups), "level_at": ups,
                      "tokens": t, "processed": processed(t)})
    return {"modality_27b": lines, "runs": period_runs()}


# =============================================================================================
# Plotting (16:9 slides, 13.33 x 7.5 in at 150 dpi)
# =============================================================================================
BG, INK, MUTED, GRID = "#fbf8f2", "#2b2722", "#6f675c", "#e4ddd0"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
LIGHT_BLUE, GRAY, DARK_GRAY = "#86b6ef", "#d3ccbf", "#8a8276"
W, H, DPI = 13.33, 7.5, 150


def _style():
    import matplotlib as mpl
    mpl.use("Agg")
    mpl.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "font.family": "DejaVu Sans", "font.size": 14, "text.color": INK,
        "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "axes.labelsize": 14,
        "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 13, "ytick.labelsize": 13,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": False, "grid.color": GRID, "grid.linewidth": 1.0, "grid.linestyle": "-",
        "lines.linewidth": 2.0, "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
        "legend.frameon": False, "legend.fontsize": 13,
    })


def _figure(title: str, subtitle: str, source: str):
    import textwrap
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(W, H), dpi=DPI)
    fig.text(0.035, 0.955, title, fontsize=22, fontweight="bold", color=INK, va="top")
    fig.text(0.035, 0.885, "\n".join(textwrap.wrap(subtitle, 118)), fontsize=14, color=MUTED, va="top",
             linespacing=1.3)
    fig.text(0.035, 0.018, "\n".join(textwrap.wrap(source, 175)), fontsize=10, color=MUTED, va="bottom",
             linespacing=1.3)
    return fig


def _keys(fig, x: float, y: float, items: list[tuple[str, str]], kind: str = "box", gap: float = 0.025,
          size: float = 13):
    """A row of colour keys with ink labels, in figure coordinates."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    r = fig.canvas.get_renderer()
    for label, color in items:
        if kind == "line":
            fig.add_artist(Line2D([x, x + 0.022], [y, y], color=color, lw=3, transform=fig.transFigure))
            x += 0.028
        elif kind == "dot":
            fig.add_artist(Line2D([x + 0.006], [y], marker="o", ms=10, color=color, lw=0, transform=fig.transFigure))
            x += 0.016
        else:
            fig.add_artist(Rectangle((x, y - 0.011), 0.013, 0.022, color=color, transform=fig.transFigure))
            x += 0.018
        t = fig.text(x, y, label, fontsize=size, color=INK, va="center")
        x += t.get_window_extent(r).width / fig.bbox.width + gap


def _grid(ax, axis="x"):
    ax.grid(True, axis=axis, color=GRID, lw=1)
    ax.set_axisbelow(True)


def _rows_axis(ax):
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)


def _m(v: float) -> str:
    return f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.0f}k"


def _save(fig, name: str):
    import matplotlib.pyplot as plt
    fig.savefig(OUT / name, dpi=DPI)
    plt.close(fig)


def _steps(level_at: list[int], actions: int):
    xs, ys = [0], [0]
    for k, a in enumerate(level_at, start=1):
        xs += [a, a]
        ys += [k - 1, k]
    xs.append(actions)
    ys.append(len(level_at))
    return xs, ys


def _per_level(level_at: list[int]) -> list[int]:
    return [b - a for a, b in zip([0] + level_at[:-1], level_at)]


# --- Figure 1: quantization ------------------------------------------------------------------
def fig_quant(q: list[dict]):
    from matplotlib.ticker import MaxNLocator
    fig = _figure("16-bit learned the most rules; 4-bit used 4× the tokens",
                  "Qwen 3.8 27B on Modality, agent-driven in OpenCode, each arm pinned to one host through NanoGPT; "
                  "3 games per arm, all stopped by hand at about 35 minutes (21 Oct)",
                  "Rules: 7 Modality rules graded rule by rule against the game source "
                  "(output/thursday/quant/*/grading.json). Tokens: OpenCode step_finish in raw/ (processed = fresh + "
                  "cached input over all requests; generated incl. reasoning). Cost: tokens × the host's OpenRouter "
                  "list price (21 Oct); ModelRun's price is not in the repo, so 4-bit shows the Thursday page's $1.51.")
    qq = q[::-1]
    y = list(range(len(qq)))
    axa = fig.add_axes([0.255, 0.25, 0.215, 0.43])
    rest = [fig.add_axes([x, 0.25, 0.115, 0.43]) for x in (0.525, 0.685, 0.845)]
    cats = [("correct", BLUE, "white"), ("partial", LIGHT_BLUE, INK), ("wrong", ORANGE, "white"),
            ("not_found", GRAY, INK)]
    for i, a in enumerate(qq):
        left = 0
        for key, color, txt in cats:
            v = a["rules"][key]
            if v:
                axa.barh(i, v - 0.12, left=left, height=0.5, color=color)
                if v >= 2:
                    axa.text(left + (v - 0.12) / 2, i, str(v), ha="center", va="center", color=txt, fontsize=13,
                             fontweight="bold")
            left += v
    axa.set_xlim(0, 21)
    axa.set_xticks([0, 7, 14, 21])
    axa.set_title("Rules at the stop\n(3 games × 7 rules)", pad=10)
    axa.set_yticks(y)
    axa.set_yticklabels([f"{a['arm']} · {a['host']}\nlevels {'·'.join(str(r['levels']) for r in a['runs'])} "
                         f"in {min(r['actions'] for r in a['runs'])}–{max(r['actions'] for r in a['runs'])} moves"
                         for a in qq], fontsize=13, color=INK)
    _rows_axis(axa)
    _grid(axa)
    specs = [("Tokens processed\nper game", lambda a: a["mean_processed"] / 1e6,
              lambda a: [r["processed"] / 1e6 for r in a["runs"]], lambda v: f"{v:.1f}M"),
             ("Tokens generated\nper game", lambda a: a["mean_generated"] / 1e3,
              lambda a: [r["tokens"]["generated"] / 1e3 for r in a["runs"]], lambda v: f"{v:.0f}k"),
             ("Cost per game\n(host list price)", lambda a: a["cost_host_per_game"],
              lambda a: [r["cost_host_usd"] for r in a["runs"] if r["cost_host_usd"] is not None],
              lambda v: f"${v:.2f}")]
    for ax, (title, mean, dots, fmt) in zip(rest, specs):
        vals = [mean(a) for a in qq]
        ax.barh(y, vals, height=0.5, color=BLUE)
        top = max(vals + [d for a in qq for d in dots(a)])
        for i, a in enumerate(qq):
            ds = dots(a)
            ax.plot(ds, [i] * len(ds), "o", ms=7, color=INK, mec=BG, mew=1.5, zorder=3)
            ax.text(max([vals[i]] + ds) + top * 0.09, i, fmt(vals[i]), va="center", fontsize=13.5,
                    fontweight="bold", color=INK)
        ax.set_xlim(0, top * 1.75)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_title(title, pad=10, fontsize=13.5)
        ax.xaxis.set_major_locator(MaxNLocator(2))
        _grid(ax)
    rest[0].set_xlabel("millions")
    rest[1].set_xlabel("thousands")
    rest[2].set_xlabel("USD")
    _keys(fig, 0.255, 0.785, [("correct", BLUE), ("partial", LIGHT_BLUE), ("wrong", ORANGE), ("not found", GRAY)],
          gap=0.014)
    fig.text(0.685, 0.785, "bar = mean of 3 games, dot = one game", fontsize=13, color=MUTED, va="center")
    deg = {a["arm"]: a["degenerate_runs"] for a in q}
    fig.text(0.035, 0.165, f"Reasoning collapsed into one repeated word (\"story\" \"story\" …) in {deg['4-bit']} of 3 "
             f"4-bit games, {deg['8-bit']} of 3 at 8-bit, {deg['16-bit']} of 3 at 16-bit.\nOne game reached level 3 "
             "(16-bit, at its 172nd move).", fontsize=13, color=INK, va="top", linespacing=1.35)
    _save(fig, "fig1_quantization.png")


# --- Figure 2: Qwen family on Modality -------------------------------------------------------
MODEL_COLOR = {"27B": BLUE, "Flash": ORANGE, "Max": AQUA}


def fig_family(f: dict):
    fig = _figure("On Modality only Max solved 4/4 (AVO), on the fewest tokens",
                  "Qwen 3.8 27B, Flash and Max in the Codex harness, one run per row (8–15 Oct). Baseline+ plays turn "
                  "by turn, one action per request; AVO runs a research session, then scores the solver it wrote",
                  "Levels: transitions.jsonl (Baseline+) and x_0001/summary.json solver score (AVO; 1500 = the "
                  "solver's full action budget). Tokens: Codex cumulative usage per thread (codex_session.jsonl, "
                  "app_server_events.jsonl); processed = input incl. cached; generated incl. reasoning; AVO counts "
                  "research and optimizer sessions.")
    groups = [("Baseline+ · OpenRouter (Alibaba), 100 actions", [r for r in f["baseline_plus"]
                                                                 if r["provider"].startswith("OpenRouter")]),
              ("Baseline+ · NanoGPT, 1000-step budget, stopped by hand", [r for r in f["baseline_plus"]
                                                                          if r["provider"] == "NanoGPT"]),
              ("AVO · OpenRouter (Alibaba), final solver", [r for r in f["avo"] if r["provider"].startswith("OpenRouter")]),
              ("AVO · NanoGPT, final solver", [r for r in f["avo"] if r["provider"] == "NanoGPT"])]
    layout, headers, yy = [], [], 0.0
    for name, members in groups:
        headers.append((yy, name))
        yy += 0.8
        for r in members:
            if "solver_levels" in r:
                lv = r["solver_levels"] or 0
                txt = (f"solver {lv}/4 in {r['solver_actions']} actions" if r["solver_actions"]
                       else "solver exited with an error, 0/4")
            else:
                lv, txt = r["levels"], f"{r['levels']}/4 in {r['actions']} actions"
            layout.append((yy, r["model"], lv, txt, r["processed"], r["tokens"]["generated"]))
            yy += 1
        yy += 0.3
    axl = fig.add_axes([0.20, 0.13, 0.30, 0.60])
    axr = fig.add_axes([0.60, 0.13, 0.27, 0.60])
    for y, model, lv, txt, proc, gen in layout:
        c = MODEL_COLOR[model]
        axl.barh(y, max(lv, 0.03), height=0.55, color=c)
        axl.text(max(lv, 0) + 0.1, y, txt, va="center", fontsize=12.5, color=INK)
        axr.barh(y, proc / 1e6, height=0.55, color=c)
        axr.text(proc / 1e6 + 1.0, y, f"{proc / 1e6:.1f}M  ({_m(gen)} generated)", va="center", fontsize=12.5,
                 color=INK)
    for ax in (axl, axr):
        ax.set_ylim(yy - 0.1, -0.6)
        ax.set_yticks([y for y, *_ in layout])
        _rows_axis(ax)
        _grid(ax)
    for y, name in headers:
        axl.annotate(name, xy=(0, y), xycoords=("axes fraction", "data"), xytext=(-125, 0),
                     textcoords="offset points", fontsize=13, fontweight="bold", color=INK, va="center",
                     annotation_clip=False, bbox=dict(boxstyle="square,pad=0.15", fc=BG, ec="none"))
    axl.set_yticklabels([m for _, m, *_ in layout], fontsize=13.5, color=INK)
    axr.set_yticklabels([])
    axl.set_xlim(0, 7.4)
    axl.set_xticks([0, 1, 2, 3, 4])
    axl.set_title("Modality levels completed (of 4)", pad=10)
    axr.set_xlim(0, 75)
    axr.set_xticks([0, 20, 40])
    axr.set_title("Tokens processed per run (millions)", pad=10)
    _keys(fig, 0.20, 0.79, [("27B", BLUE), ("Flash", ORANGE), ("Max", AQUA)], gap=0.025)
    _save(fig, "fig2_qwen_family_modality.png")


# --- Figure 3: self-hosted 27B, 3 frameworks x 3 games ---------------------------------------
FW = [("harness2_base1", "Agent-driven player (Harness² base1)", BLUE),
      ("baseline_v4", "Turn-based Baseline v4", ORANGE),
      ("avo_v2_research", "AVO v2 research session", AQUA)]


def fig_vast(v: dict):
    from matplotlib.lines import Line2D
    fig = _figure("Self-hosted 27B: agent-driven play solved IceCrates and Knightoban 6/6",
                  "Qwen3.8-27B-FP8 on vast.ai (vLLM), OpenCode, max thinking, 1000-move budget, one run per cell; "
                  "all stopped at 18:14 on 21 Oct. Under each title: levels, moves, tokens processed (generated)",
                  "Levels: transitions.jsonl (player, Baseline) and the research session's evidence.jsonl (AVO; no AVO "
                  "solver attempt was scored before the stop). Tokens: OpenCode step_finish in raw/; base1 = player "
                  "rollout only, AVO = research + optimizer. Shortest = BFS over the game's rules "
                  "(docs/research/premise-review-20261021.md).")
    for i, key in enumerate(["modality", "icecrates", "knightoban"]):
        g = v[key]
        x0 = 0.065 + i * 0.32
        ax = fig.add_axes([x0, 0.15, 0.255, 0.43])
        xmax = max(fw["actions"] for fw in g["frameworks"].values())
        fig.text(x0, 0.73, g["name"], fontsize=16, fontweight="bold", color=INK, va="center")
        for j, (fkey, _, color) in enumerate(FW):
            fw = g["frameworks"][fkey]
            xs, ys = _steps(fw["level_at"], fw["actions"])
            ax.plot(xs, ys, color=color, lw=2.4, zorder=3 + (fkey == "harness2_base1"))
            ax.plot([xs[-1]], [ys[-1]], "o", ms=9, color=color, mec=BG, mew=2, zorder=5)
            yy = 0.69 - j * 0.033
            fig.add_artist(Line2D([x0 + 0.006], [yy], marker="o", ms=8, color=color, lw=0, transform=fig.transFigure))
            fig.text(x0 + 0.017, yy, f"{fw['levels']}/{g['win_levels']} in {fw['actions']} · "
                     f"{_m(fw['processed'])} ({_m(fw['tokens']['generated'])})", fontsize=12.5, color=INK, va="center")
        short = sum(g["shortest"])
        ax.axvline(short, color=MUTED, lw=1, zorder=1)
        ax.text(short + xmax * 0.015, g["win_levels"] + 0.3, f"shortest {short}", ha="left", va="center",
                fontsize=11.5, color=MUTED)
        ax.set_xlim(0, xmax * 1.04)
        ax.set_ylim(-0.15, g["win_levels"] + 0.6)
        ax.set_yticks(range(g["win_levels"] + 1))
        ax.set_xlabel("game actions")
        _grid(ax, "y")
        if i == 0:
            ax.set_ylabel("levels completed")
    _keys(fig, 0.065, 0.785, [(n, c) for _, n, c in FW], kind="line", gap=0.03)
    _save(fig, "fig3_vast_frameworks_games.png")


# --- Figure 4: same-game coaching ------------------------------------------------------------
def fig_coaching(v: dict):
    from matplotlib.lines import Line2D
    fig = _figure("Coaching on the same game brought moves down to the shortest",
                  "Harness² on the self-hosted 27B (21 Oct). base1 = first attempt with an empty harness; inv1 and "
                  "dom1 replay the game with the harness a 27B coach (INV, DOM) wrote from base1's record",
                  "Moves per level from transitions.jsonl. Tokens processed (fresh + cached input) from OpenCode "
                  "step_finish: the player rollout's own, coach sessions (improver/) listed separately. IceCrates "
                  "dom1 was cut at the 18:14 stop. Shortest = BFS (studies/thursday/rules/). Modality's coaches "
                  "produced no harness before the stop.")
    series = [("base1", "base1, no harness", DARK_GRAY), ("inv1", "inv1, INV coach", BLUE),
              ("dom1", "dom1, DOM coach", ORANGE)]
    for i, key in enumerate(["icecrates", "knightoban"]):
        g = v[key]
        x0 = 0.075 + i * 0.475
        ax = fig.add_axes([x0, 0.15, 0.40, 0.42])
        lv = list(range(1, g["win_levels"] + 1))
        ax.plot(lv, g["shortest"], color=INK, lw=1.2, marker="o", ms=4, zorder=2)
        for label, _, color in series:
            pl = _per_level(g["rollouts"][label]["level_at"])
            ax.plot(lv[:len(pl)], pl, color=color, lw=2.4, marker="o", ms=9, mec=BG, mew=2, zorder=3)
        ax.set_xticks(lv)
        ax.set_xlabel("level")
        ax.set_ylim(0, None)
        _grid(ax, "y")
        if i == 0:
            ax.set_ylabel("moves in the level")
        fig.text(x0, 0.775, g["name"], fontsize=16, fontweight="bold", color=INK, va="center")
        rows = [(INK, "line", f"shortest: {sum(g['shortest'])} moves")]
        for label, name, color in series:
            ro = g["rollouts"][label]
            rows.append((color, "dot", f"{name}: {ro['levels']}/{g['win_levels']} in {ro['actions']} moves · "
                                       f"{ro['processed'] / 1e6:.2f}M tok"))
        rows.append((None, "", f"coach sessions: {g['coach_processed'] / 1e6:.1f}M tok"))
        for j, (color, kind, text) in enumerate(rows):
            yy = 0.735 - j * 0.033
            if kind == "line":
                fig.add_artist(Line2D([x0, x0 + 0.014], [yy, yy], color=INK, lw=1.2, transform=fig.transFigure))
            elif kind == "dot":
                fig.add_artist(Line2D([x0 + 0.007], [yy], marker="o", ms=8, color=color, lw=0,
                                      transform=fig.transFigure))
            fig.text(x0 + 0.02, yy, text, fontsize=12.5, color=INK if color else MUTED, va="center")
    _save(fig, "fig4_same_game_coaching.png")


# --- Figure 5: tool-call probe ---------------------------------------------------------------
def fig_probe(p: dict):
    plain = [r for r in p["rows"] if "plain" in r["label"] or "flat" in r["label"]]
    ns = [r for r in p["rows"] if "namespaced" in r["label"]]
    ok_plain = sum(r["outcomes"].get("tool call", 0) for r in plain)
    ok_ns = sum(r["outcomes"].get("tool call", 0) for r in ns)
    fig = _figure(f"NanoGPT drops namespaced tools: plain {ok_plain}/{sum(r['n'] for r in plain)}, "
                  f"namespaced {ok_ns}/{sum(r['n'] for r in ns)}",
                  "Direct calls to NanoGPT with no CLI (21 Oct): one write_note tool declared four ways, plus Codex's "
                  "real 15 Oct request replayed as sent and on the Chat endpoint",
                  f"output/thursday/q1/probes.jsonl: {p['probes']} calls, {p['total_tokens'] / 1e3:.0f}k tokens, "
                  f"${p['total_cost_usd']:.2f} (studies/thursday/probe_tool_calls.py). Codex declares MCP tools inside "
                  "a namespace on the Responses endpoint; OpenCode sends plain tools on Chat. Right: proper calls and "
                  "tokens used per condition.")
    outs = [("tool call", "proper tool call", BLUE), ("text leak", "call written as text", ORANGE),
            ("no call", "no call", GRAY), ("error", "malformed-call error", DARK_GRAY)]
    rows = p["rows"][::-1]
    ax = fig.add_axes([0.30, 0.13, 0.44, 0.60])
    for i, r in enumerate(rows):
        left = 0
        for key, _, color in outs:
            n = r["outcomes"].get(key, 0)
            if n:
                frac = n / r["n"]
                ax.barh(i, frac - 0.005, left=left, height=0.55, color=color)
                if frac >= 0.2:
                    ax.text(left + frac / 2, i, str(n), ha="center", va="center", fontsize=12.5, fontweight="bold",
                            color="white" if color in (BLUE, ORANGE, DARK_GRAY) else INK)
                left += frac
        ok = r["outcomes"].get("tool call", 0)
        ax.text(1.03, i, f"{ok}/{r['n']} proper · {r['tokens'] / 1e3:.0f}k tok", va="center", fontsize=13,
                color=INK, fontweight="bold" if ok == 0 else "normal")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["label"] for r in rows], fontsize=13.5, color=INK)
    _rows_axis(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticklabels(["0%", "50%", "100%"])
    _grid(ax)
    _keys(fig, 0.30, 0.785, [(lab, c) for _, lab, c in outs], gap=0.02)
    _save(fig, "fig5_toolcall_probe.png")


# --- Figure 6: the period --------------------------------------------------------------------
def fig_period(pd: dict, quant: list[dict]):
    from matplotlib.lines import Line2D
    fig = _figure("Agent-driven play cost ~¼ the tokens per move of turn-by-turn play",
                  "Left: Qwen 3.8 27B on Modality, 30 Sep – 21 Oct, turn by turn (one action per request) or driving "
                  "the game itself. Right: tokens processed by every Qwen 3.8 run of the period with recorded usage",
                  "Levels: transitions.jsonl (16-bit game 1 reached level 3 at move 172, per its grading). Tokens: "
                  "OpenCode step_finish or Codex cumulative usage; processed = fresh + cached input over all requests. "
                  "Right: output/workbench runs + 8 Oct output/codex_agent runs; 30 Sep AVO campaigns recorded no usage.")
    lines = {l["label"]: l for l in pd["modality_27b"]}
    rows = []  # label, driver, levels text, best level, processed, actions
    for lab, short in [("30 Sep · Codex · OpenRouter", "30 Sep · Codex · OpenRouter"),
                       ("8 Oct · Codex · Alibaba", "8 Oct · Codex · OpenRouter (Alibaba)"),
                       ("15 Oct · Codex · NanoGPT", "15 Oct · Codex · NanoGPT"),
                       ("20 Oct · OpenCode turn-by-turn · NanoGPT", "20 Oct · OpenCode turn-by-turn · NanoGPT"),
                       ("20 Oct · OpenCode agent-driven · NanoGPT", "20 Oct · OpenCode agent · NanoGPT")]:
        l = lines[lab]
        rows.append((short, l["driver"], f"{l['levels']}/4 in {l['actions']}", l["levels"], l["processed"],
                     l["actions"]))
    for a in quant:
        n_act = sum(r["actions"] for r in a["runs"])
        rows.append((f"21 Oct · OpenCode agent · {a['arm']} host ×3", "agent",
                     f"{'·'.join(str(r['levels']) for r in a['runs'])} in "
                     f"{min(r['actions'] for r in a['runs'])}–{max(r['actions'] for r in a['runs'])}",
                     max(r["levels"] for r in a["runs"]), sum(r["processed"] for r in a["runs"]), n_act))
    for lab, short in [("21 Oct · OpenCode turn-based v4 · self-hosted", "21 Oct · OpenCode turn-based v4 · self-hosted"),
                       ("21 Oct · OpenCode agent-driven · self-hosted", "21 Oct · OpenCode agent · self-hosted")]:
        l = lines[lab]
        rows.append((short, l["driver"], f"{l['levels']}/4 in {l['actions']}", l["levels"], l["processed"],
                     l["actions"]))
    axa = fig.add_axes([0.345, 0.16, 0.10, 0.55])
    axb = fig.add_axes([0.495, 0.16, 0.11, 0.55])
    for i, (lab, driver, txt, best, proc, acts) in enumerate(rows):
        c = BLUE if driver == "agent" else ORANGE
        axa.barh(i, max(best, 0.04), height=0.58, color=c)
        axa.text(max(best, 0) + 0.2, i, txt, va="center", fontsize=11, color=INK)
        per = proc / max(acts, 1) / 1e3
        axb.barh(i, per, height=0.58, color=c)
        axb.text(per + 5, i, f"{per:.0f}k ({_m(proc)})", va="center", fontsize=11, color=INK)
    for ax in (axa, axb):
        ax.set_ylim(len(rows) - 0.4, -0.6)
        ax.set_yticks(range(len(rows)))
        _rows_axis(ax)
        _grid(ax)
    axa.set_yticklabels([r[0] for r in rows], fontsize=11.5, color=INK)
    axb.set_yticklabels([])
    axa.set_xlim(0, 9.5)
    axa.set_xticks([0, 4])
    axa.set_title("Levels\n(of 4)", pad=10)
    axb.set_xlim(0, 240)
    axb.set_xticks([0, 100])
    axb.set_title("Tokens per move\n(run total)", pad=10)
    _keys(fig, 0.035, 0.785, [("turn by turn", ORANGE), ("agent-driven", BLUE)], gap=0.02)
    # right: every run of the period, by date
    bx = fig.add_axes([0.70, 0.16, 0.27, 0.55])
    dates = sorted({r["date"] for r in pd["runs"]})
    shapes = {"OpenRouter": "o", "NanoGPT": "s", "vast": "^"}
    seen = collections.Counter()
    for r in pd["runs"]:
        x = dates.index(r["date"])
        seen[r["date"]] += 1
        jitter = ((seen[r["date"]] * 0.618) % 1.0 - 0.5) * 0.7
        filled = r["harness"] == "opencode"
        bx.plot(x + jitter, r["processed"] / 1e6, shapes.get(r["provider"], "o"), ms=8,
                mfc=DARK_GRAY if filled else BG, mec=DARK_GRAY, mew=1.6, alpha=0.9, zorder=3)
    bx.set_yscale("log")
    bx.set_ylim(0.03, 3000)
    bx.set_yticks([0.1, 1, 10, 100])
    bx.set_yticklabels(["0.1M", "1M", "10M", "100M"])
    bx.minorticks_off()
    bx.set_xticks(range(len(dates)))
    import datetime as dt
    bx.set_xticklabels([str(dt.date.fromisoformat(d).day) for d in dates], fontsize=12)
    bx.set_xlim(-0.6, len(dates) - 0.4)
    bx.set_title(f"Tokens processed per run\n({len(pd['runs'])} runs, all games)", pad=10)
    bx.set_xlabel("day (30 Sep – 21 Oct; days with runs only)", fontsize=11.5)
    _grid(bx, "y")
    handles = [Line2D([], [], marker=m, lw=0, ms=8, mfc=DARK_GRAY, mec=DARK_GRAY, label=n)
               for n, m in (("OpenRouter", "o"), ("NanoGPT", "s"), ("self-hosted", "^"))]
    handles += [Line2D([], [], marker="o", lw=0, ms=8, mfc=BG, mec=DARK_GRAY, mew=1.6, label="Codex (hollow)"),
                Line2D([], [], marker="o", lw=0, ms=8, mfc=DARK_GRAY, mec=DARK_GRAY, label="OpenCode (filled)")]
    bx.legend(handles=handles, loc="upper left", ncol=1, fontsize=11, handletextpad=0.2, borderaxespad=0.3,
              labelspacing=0.3)
    _save(fig, "fig6_period_27b_modality_tokens.png")


def draw_all(data: dict):
    _style()
    fig_quant(data["quant"])
    fig_family(data["family"])
    fig_vast(data["vast"])
    fig_coaching(data["vast"])
    fig_probe(data["probe"])
    fig_period(data["period"], data["quant"])

if __name__ == "__main__":
    import sys
    data = {"quant": quant_data(), "family": family_data(), "vast": vast_data(), "probe": probe_data(),
            "period": period_data()}
    (OUT / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    if "--data-only" not in sys.argv:
        draw_all(data)
