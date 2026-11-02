"""Rule-learning curves: share of true rules the world model states, against actions, tool calls and tokens."""
import json, os, glob
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

here = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(f"{here}/versions.json", encoding="utf-8"))
rules = json.load(open(f"{here}/rules.json", encoding="utf-8"))
grades = {}
for d in glob.glob(f"{here}/tasks/*"):
    ids = json.load(open(f"{d}/ids.json", encoding="utf-8"))
    g = json.load(open(f"{d}/grades.json", encoding="utf-8"))
    for k, vid in ids.items():
        grades[vid] = g[k]
VAL = {"correct": 1.0, "partial": 0.5, "absent": 0.0, "wrong": 0.0}

def score(gr, game, kind=None):
    rs = [r for r in rules[game] if kind is None or r["kind"] == kind]
    return 100 * sum(VAL[gr[r["id"]]] for r in rs) / len(rs)

INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
COLOR = {"agent": "#2a78d6", "controller": "#eb6834"}
GAMES = [("ps_modality-v1", "Modality"), ("ps_icecrates-v1", "IceCrates"), ("ps_knightoban-v1", "Knightoban")]
XS = [("actions", "game actions"), ("tool_calls", "tool calls"), ("gen_tokens", "generated tokens (output + reasoning)")]

def label(name, r):
    if r["driver"] == "agent":
        return "agent-driven"
    return "controller " + name.split("-vast-fp8-")[1].split("-")[0].replace("baseline", "b")

def curves(kind=None):
    out = {}
    for name, r in data.items():
        pts = [(v, score(grades[f"{name}#{i}"], r["game"], kind)) for i, v in enumerate(r["versions"])
               if f"{name}#{i}" in grades]
        out[name] = pts
    return out

def figure(kind, path, title):
    cs = curves(kind)
    fig, axes = plt.subplots(3, 3, figsize=(15, 10.5), facecolor=SURF)
    for row, (game, gname) in enumerate(GAMES):
        for col, (xk, xl) in enumerate(XS):
            ax = axes[row][col]; ax.set_facecolor(SURF)
            for name, r in data.items():
                if r["game"] != game or not cs[name] or not (r["driver"] == "agent" or "baseline-v4" in name):
                    continue
                c = COLOR[r["driver"]]
                xs = [0] + [v[xk] for v, _ in cs[name]] + [r["totals"][xk]]
                ys = [0] + [s for _, s in cs[name]] + [cs[name][-1][1]]
                ax.step(xs, ys, where="post", color=c, lw=2, alpha=0.95 if r["driver"] == "agent" else 0.75)
                for lu in r["levelups"]:  # level completed: a dot on the curve
                    y = ([0] + [s for v, s in cs[name] if v[xk] <= lu[xk]])[-1]
                    ax.plot(lu[xk], y, "o", ms=6, color=c, mec=SURF, mew=1.5, zorder=3)
                ax.annotate(f"{r['totals']['levels']} levels", (xs[-1], ys[-1]), xytext=(4, 0),
                            textcoords="offset points", fontsize=7.5, color=INK2, va="center")
            ax.set_ylim(-3, 103); ax.set_yticks([0, 25, 50, 75, 100])
            ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
            for s in ("top", "right"): ax.spines[s].set_visible(False)
            for s in ("left", "bottom"): ax.spines[s].set_color(AXIS)
            ax.tick_params(colors=MUTED, labelsize=8)
            if xk == "gen_tokens":
                ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
            ax.set_xlim(0, max(r["totals"][xk] for r in data.values() if r["game"] == game) * 1.12)
            if row == 2: ax.set_xlabel(xl, color=INK2, fontsize=9)
            if col == 0: ax.set_ylabel(f"{gname}\nrules known (%)", color=INK, fontsize=10)
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], color=COLOR["agent"], lw=2), Line2D([], [], color=COLOR["controller"], lw=2),
                Line2D([], [], ls="", marker="o", color=MUTED)],
               ["agent-driven (Harness² base, game.py)", "controller-driven (baseline, one action per turn)", "level completed"],
               loc="upper right", ncol=3, frameon=False, fontsize=9, labelcolor=INK2)
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, color=INK)
    fig.text(0.01, 0.932, "Qwen 3.8 27B FP8, OpenCode, 1000-action budget, 21 Oct runs (one run per line).\nEach world_model.md version "
             "graded against the true rules from the game's script.txt: correct = 1, partial = 0.5. Controller tool calls include one act.py per action.", fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=130, facecolor=SURF); plt.close(fig)

figure(None, f"{here}/rule-learning-all.png", "Rules the world model gets right, as play goes on")
figure("hidden", f"{here}/rule-learning-hidden.png", "Hidden rules only")
figure("visible", f"{here}/rule-learning-visible.png", "Visible rules only")
print("ok")
