"""Candidate statements of Modality's rules in a run's reasoning and messages, with the number of
game actions taken at that moment, for labelling (correct / wrong / guess) by hand or by a model.

Seven rules:
    action_map    ACTION1-4 = up/down/left/right
    undo          ACTION7 = undo
    white_dark    a step between white and dark is blocked
    grey_bridge   grey (checkered) connects white and dark
    push          walking into the box pushes it
    floor_push    a push needs a matching floor (white/grey vs dark)
    goal          a level is won by putting the box on the blue square

Matching is deliberately loose: it finds candidates, it does not decide whether a statement is
right. The first-mention summary is therefore an upper bound on when a rule was first stated.

    python -m studies.thursday.rules_timeline RUN_OR_JOB [...] [--out DIR]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import re
from datetime import datetime, timedelta
from pathlib import Path

from studies.thursday.metrics import OUT, find_runs, read_jsonl
from studies.thursday.modality import load_transitions

OBJ = r"(?:crate|box|block|door|frame|boulder)"
ACTOR = r"(?:robot|person|player|character|agent|avatar)"
TARGET = r"(?:target|goal|blue(?: square| tile| cell)?|tile 0|tile 9|code 0|code 9)"
WHITE, DARK = r"(?:white|light)", r"(?:dark|black)"
GREY = r"(?:grey|gray|checker(?:ed|board)?)"
NO = r"(?:blocked|can'?t|cannot|can not|not allowed|impassable|never|no direct|not possible|fails?)"
G = r"[^.\n]"  # within one sentence

RULES = {
    "action_map": rf"ACTION1\b{G}{{0,25}}\bup\b|ACTION2\b{G}{{0,25}}\bdown\b|ACTION3\b{G}{{0,25}}\bleft\b"
                  rf"|ACTION4\b{G}{{0,25}}\bright\b",
    "undo": rf"ACTION7\b{G}{{0,60}}\bundo|\bundo{G}{{0,60}}ACTION7",
    "white_dark": rf"{WHITE}{G}{{0,60}}{DARK}{G}{{0,80}}{NO}|{DARK}{G}{{0,60}}{WHITE}{G}{{0,80}}{NO}"
                  rf"|{NO}{G}{{0,60}}(?:{WHITE}{G}{{0,30}}{DARK}|{DARK}{G}{{0,30}}{WHITE})",
    "grey_bridge": rf"{GREY}{G}{{0,100}}(?:bridge|connect|both|either|transition|switch|gateway|link|between)"
                   rf"|(?:bridge|connect|gateway){G}{{0,60}}{GREY}",
    "push": rf"push(?:es|ed|ing)?{G}{{0,60}}{OBJ}|{OBJ}{G}{{0,60}}push|sokoban",
    "floor_push": rf"push{G}{{0,120}}(?:same|match|compatib|correspond){G}{{0,60}}(?:floor|base|colou?r|tile|zone|type)"
                  rf"|(?:same|match|compatib|correspond){G}{{0,60}}(?:floor|base|colou?r|tile|zone|type){G}{{0,120}}push"
                  rf"|{DARK}{G}{{0,40}}{ACTOR}{G}{{0,60}}push|only{G}{{0,60}}{DARK}{G}{{0,60}}push",
    "goal": rf"{OBJ}{G}{{0,60}}(?:on|onto|to|into|reach|cover){G}{{0,30}}{TARGET}"
            rf"|(?:win|complete|solve|clear){G}{{0,80}}{OBJ}{G}{{0,60}}{TARGET}",
}
PATTERNS = {rule: re.compile(pattern, re.IGNORECASE) for rule, pattern in RULES.items()}
SNIPPET = 400


def utc(stamp: str) -> datetime:
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return moment.replace(tzinfo=None) - (moment.utcoffset() or timedelta())


def action_clock(transitions: list[dict], events: list[dict]):
    """f(event) -> (actions taken so far, levels completed so far).

    transitions.jsonl stamps are naive container time; agent events are UTC. If the first game
    action and the first `game.py do` command are hours apart, the whole-hour difference is
    taken as a timezone shift.
    """
    times = [datetime.fromisoformat(t["timestamp"]) for t in transitions]
    first_do = next((utc(e["t"]) for e in events if e.get("type") == "command" and "game.py do" in str(e.get("text"))), None)
    shift = timedelta(hours=round((times[0] - first_do).total_seconds() / 3600)) if times and first_do else timedelta()
    times = [t - shift for t in times]
    levels = [t["after"]["levels_completed"] for t in transitions]

    def at(event: dict) -> tuple[int, int]:
        n = bisect.bisect_right(times, utc(event["t"]))
        return n, levels[n - 1] if n else 0
    return at


def sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start), text.rfind("!", 0, start)) + 1
    stops = [i for i in (text.find(".", end), text.find("\n", end)) if i >= 0]
    right = min(stops) + 1 if stops else len(text)
    left, right = max(left, start - SNIPPET // 2), min(right, end + SNIPPET // 2)
    return " ".join(text[left:right].split())


def candidates(run: Path) -> list[dict]:
    transitions, events = load_transitions(run), read_jsonl(run / "agent_events.jsonl")
    at = action_clock(transitions, events)
    rows, seen = [], set()
    for index, event in enumerate(events):
        if event.get("type") not in ("reasoning", "message") or not event.get("t"):
            continue
        text = event.get("text") or ""
        actions, levels = at(event)
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                snippet = sentence(text, match.start(), match.end())
                if (rule, snippet) in seen:
                    continue
                seen.add((rule, snippet))
                rows.append({"run": run.name, "rule": rule, "actions": actions, "levels_done": levels,
                             "event": index, "type": event["type"], "turn": event.get("turn", ""),
                             "t": event["t"], "snippet": snippet, "label": ""})
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=OUT / "rules")
    args = parser.parse_args(argv)
    runs = [run.resolve() for run in find_runs(args.paths)]
    rows = [row for run in runs for row in candidates(run)]
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "candidates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["run", "rule", "actions", "levels_done", "event", "type",
                                                    "turn", "t", "snippet", "label"])
        writer.writeheader()
        writer.writerows(rows)
    names = [run.name for run in runs]
    lines = ["First candidate statement of each rule: game actions taken at that moment (number of candidates).",
             "", "| rule | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for rule in RULES:
        cells = []
        for name in names:
            found = [r for r in rows if r["run"] == name and r["rule"] == rule]
            cells.append(f"{min(r['actions'] for r in found)} ({len(found)})" if found else "–")
        lines.append(f"| {rule} | " + " | ".join(cells) + " |")
    level_lines = []
    for run in runs:
        ups = [t["action_index"] for t in load_transitions(run)
               if t["after"]["levels_completed"] > t["before"]["levels_completed"]]
        level_lines.append(f"- {run.name}: levels completed at actions {', '.join(map(str, ups)) or 'none'}")
    text = "\n".join(lines + ["", *level_lines]) + "\n"
    (args.out / "first_mentions.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {args.out / 'candidates.csv'} ({len(rows)} candidates) and {args.out / 'first_mentions.md'}")


if __name__ == "__main__":
    main()
