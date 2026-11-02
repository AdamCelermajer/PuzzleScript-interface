"""Levels completed against actions used: one panel per arm, one step line per run, and the
optimum as a dashed staircase.

    python -m studies.thursday.curves RUN_OR_JOB [...] [--label 'GLOB=ARM' ...] [--out FILE.png]
"""
from __future__ import annotations

import argparse
import math
from itertools import accumulate
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from studies.thursday.metrics import OUT, arm_of, find_runs, parse_labels, read_json  # noqa: E402
from studies.thursday.modality import load_transitions, optimum_moves  # noqa: E402

# Categorical slots in fixed order (dataviz reference palette); arms take them in sorted order.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def staircase(level_at: list[int], end: int) -> tuple[list[int], list[int]]:
    xs, ys = [0], [0]
    for k, at in enumerate(level_at, 1):
        xs += [at, at]
        ys += [k - 1, k]
    xs.append(max(end, xs[-1]))
    ys.append(len(level_at))
    return xs, ys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--label", action="append", default=[], help="GLOB=ARM, repeatable")
    parser.add_argument("--out", type=Path, default=OUT / "curves.png")
    args = parser.parse_args(argv)
    labels = parse_labels(args.label)
    runs: dict[str, list[tuple[str, list[int], int]]] = {}
    for run in find_runs(args.paths):
        run = run.resolve()
        transitions = load_transitions(run)
        level_at = [t["action_index"] for t in transitions
                    if t["after"]["levels_completed"] > t["before"]["levels_completed"]]
        runs.setdefault(arm_of(run, read_json(run / "run_config.json"), labels), []).append(
            (run.name, level_at, len(transitions)))
    arms = sorted(runs)
    optimum = list(accumulate(optimum_moves()))
    x_max = max(300, max(end for group in runs.values() for _, _, end in group))
    cols = min(3, len(arms))
    rows = math.ceil(len(arms) / cols)
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK})
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.0 * rows), sharex=True, sharey=True,
                             squeeze=False, facecolor=SURFACE)
    for i, arm in enumerate(arms):
        ax = axes[i // cols][i % cols]
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        xs, ys = staircase(optimum, x_max)
        ax.plot(xs, ys, color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)), zorder=4)  # on top: optimal runs hide it otherwise
        colour = SERIES[i % len(SERIES)]
        for name, level_at, end in sorted(runs[arm]):
            xs, ys = staircase(level_at, end)
            ax.plot(xs, ys, color=colour, linewidth=2, alpha=0.85, solid_capstyle="round")
            ax.plot([end], [len(level_at)], marker="o", markersize=5, color=colour,
                    markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.set_title(f"{arm}  (n={len(runs[arm])})", loc="left", fontsize=10, color=INK)
        ax.set_xlim(0, x_max)
        ax.set_ylim(-0.1, len(optimum) + 0.2)
        ax.set_yticks(range(len(optimum) + 1))
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        if i % cols == 0:
            ax.set_ylabel("levels completed")
        if i // cols == rows - 1:
            ax.set_xlabel("actions used")
    axes[0][0].text(optimum[-1] - 4, len(optimum) - 0.3, "optimum", color=MUTED, fontsize=8, ha="right")
    for j in range(len(arms), rows * cols):
        axes[j // cols][j % cols].set_visible(False)
    fig.suptitle("Modality: levels completed vs actions (dot = where the run ended; dashed = optimum)",
                 x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150, facecolor=SURFACE)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
