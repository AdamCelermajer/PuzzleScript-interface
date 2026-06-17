from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from client.engine.memory import EngineMemory, TransitionRecord
from client.engine.rule_schema import GeneralizedRule
from client.engine.rulebook import Rulebook


def build_report(base_path: str | Path, recent: int = 5) -> str:
    base = Path(base_path)
    memory = EngineMemory(base / "timeline.jsonl")
    rulebook = Rulebook(base)
    transitions = memory.all()

    lines = [
        f"Rules debug: {base}",
        f"Rules: {len(rulebook.generalized_rules)}",
        f"Transitions: {len(transitions)}",
        "",
        "Rules",
        "-----",
    ]
    if rulebook.generalized_rules:
        for rule in rulebook.generalized_rules:
            lines.extend(_format_rule(rule, transitions))
    else:
        lines.append("- none")

    lines.extend(["", f"Recent transitions (last {recent})", "--------------------"])
    recent_transitions = transitions[-max(0, recent) :]
    if recent_transitions:
        for transition in recent_transitions:
            lines.extend(_format_transition(transition))
    else:
        lines.append("- none")
    return "\n".join(lines)


def _format_rule(
    rule: GeneralizedRule, transitions: list[TransitionRecord]
) -> list[str]:
    supports = ", ".join(rule.evidence_ids) or "none"
    contradictions = ", ".join(rule.contradictions) or "none"
    lines = [
        f"- {rule.id} {rule.action} anchor={rule.anchor}",
        f"  natural_language: {rule.summary or 'not recorded'}",
        f"  IF {_conditions_text(rule)}",
        f"  THEN {_effects_text(rule)}",
        f"  supports: {supports}",
        f"  contradictions: {contradictions}",
        (
            "  stats: "
            f"hits={rule.prediction_hits} "
            f"failures={rule.prediction_failures} "
            f"revisions={rule.revision_count}"
        ),
    ]
    evidence = [item for item in transitions if item.id in rule.evidence_ids]
    for transition in evidence:
        lines.append(f"  evidence {transition.id}: {transition.action.name}")
    return lines


def _format_transition(transition: TransitionRecord) -> list[str]:
    return [
        f"- {transition.id}: {transition.action.name}",
        "  Before:",
        *_indent_rows(transition.before.rows(), "    "),
        "  After:",
        *_indent_rows(transition.after.rows(), "    "),
    ]


def _conditions_text(rule: GeneralizedRule) -> str:
    if not rule.conditions:
        return "true"
    return ", ".join(
        f"cell({condition.dx},{condition.dy})={condition.value}"
        for condition in rule.conditions
    )


def _effects_text(rule: GeneralizedRule) -> str:
    if not rule.effects:
        return "no change"
    effects = [
        f"set({effect.dx},{effect.dy})={effect.value}" for effect in rule.effects
    ]
    if rule.result_state is not None:
        effects.append(f"result_state={rule.result_state}")
    if rule.levels_completed is not None:
        effects.append(f"levels_completed={rule.levels_completed}")
    return ", ".join(effects)


def _indent_rows(rows: list[str], prefix: str) -> list[str]:
    return [f"{prefix}{row}" for row in rows]


def main() -> None:
    parser = ArgumentParser(description="Inspect learned rules and timeline evidence")
    parser.add_argument("--rules-dir", type=Path, default=Path("client/rules"))
    parser.add_argument("--game-id", type=str, default="ps_sokoban_basic-v1")
    parser.add_argument("--recent", type=int, default=5)
    args = parser.parse_args()

    print(build_report(args.rules_dir / args.game_id, recent=args.recent))


if __name__ == "__main__":
    main()
