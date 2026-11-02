"""Goal-recognition accuracy from graded.json: humans vs models, one frame vs three random actions."""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

here = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(f"{here}/graded.json", encoding="utf-8"))["rows"]
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, BLUE_SOFT = "#2a78d6", "#a9c9f0"

def rate(rs, ok):
    return 100 * sum(r["verdict"] in ok for r in rs) / len(rs)

def pick(source, condition):
    return [r for r in rows if r["source"] == source and (condition is None or r["condition"] == condition)]

IMG, TXT = "one_frame, text_plus_first_image", "one_frame, text_only"
answerers = [("Humans (38 people)", pick("human", None)), ("GPT-5.5", pick("gpt-5.5", IMG)), ("Kimi K2.6", pick("kimi-k2.6", IMG)),
             ("Claude Opus 4.8", pick("claude-opus-4.8", IMG)), ("DeepSeek V4 Pro (no image)", pick("deepseek-v4-pro", TXT))]
fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.6), facecolor=SURF, gridspec_kw={"width_ratios": [1.2, 1]})
for ax in (a, b):
    ax.set_facecolor(SURF); ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9); ax.set_xlim(0, 100)
ys = range(len(answerers))[::-1]
for y, (name, rs) in zip(ys, answerers):
    c, cp = rate(rs, ("correct",)), rate(rs, ("correct", "partial"))
    a.barh(y, cp, color=BLUE_SOFT, height=0.6); a.barh(y, c, color=BLUE, height=0.6)
    a.text(c - 1.5, y, f"{c:.0f}%", va="center", ha="right", color="#ffffff", fontsize=9)
    a.text(cp + 1.5, y, f"{cp:.0f}%", va="center", color=INK2, fontsize=9)
a.set_yticks(list(ys), [n for n, _ in answerers], color=INK, fontsize=10)
a.set_xlabel("answers (%)", color=INK2, fontsize=9)
a.set_title("From the first frame: correct (dark) and correct or partial (light)", loc="left", fontsize=10.5, color=INK)
models = [("GPT-5.5", "gpt-5.5"), ("Kimi K2.6", "kimi-k2.6"), ("Claude Opus 4.8", "claude-opus-4.8")]
for y, (name, m) in zip(range(len(models))[::-1], models):
    one, three = rate(pick(m, IMG), ("correct",)), rate(pick(m, "three_random_actions, text_plus_first_image"), ("correct",))
    b.plot([three, one], [y, y], color=AXIS, lw=2, zorder=1)
    b.plot(one, y, "o", ms=9, color=BLUE, mec=SURF, mew=2, zorder=2); b.plot(three, y, "o", ms=9, color="#eb6834", mec=SURF, mew=2, zorder=2)
    b.text(one + 2, y + 0.18, f"{one:.0f}%", color=INK2, fontsize=9); b.text(three - 2, y + 0.18, f"{three:.0f}%", color=INK2, fontsize=9, ha="right")
b.set_yticks(range(len(models))[::-1], [n for n, _ in models], color=INK, fontsize=10); b.set_ylim(-0.6, len(models) - 0.4)
b.set_xlabel("correct answers (%)", color=INK2, fontsize=9)
b.set_title("Three random actions first make every model worse", loc="left", fontsize=10.5, color=INK)
b.plot([], [], "o", color=BLUE, label="first frame"); b.plot([], [], "o", color="#eb6834", label="after 3 random actions")
b.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="lower right")
fig.suptitle("Naming a game's goal: 50 PuzzleScript games, answers graded against each game's script", x=0.01, ha="left", fontsize=12.5, color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(f"{here}/goal-recognition.png", dpi=130, facecolor=SURF)
