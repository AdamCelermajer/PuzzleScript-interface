# =============================================================================
# RULE FORMAT SPECIFICATION
# Used as a shared reference across all prompts that produce or consume rules.
# =============================================================================
#
# Rules must follow one of these two templates:
#
#   INTERACTION:
#   IF action is '<X>' AND <subject> is at <position> relative to <object>
#   THEN <effect>
#
#   BLOCKING:
#   IF action is '<X>' AND <subject> cannot move because <object> is at <position>
#   THEN <subject> does not move
#
# Directions: W=up, A=left, S=down, D=right
# Positions:  "above", "below", "to the left of", "to the right of"
# Effects:    "<A> moves <direction>", "<A> becomes <B>", "<A> and <B> both move <direction>"
#
# =============================================================================

RULE_FORMAT = """
RULE FORMAT — every rule must follow this exact template:
  IF action is '<WASD>' AND <cell description> THEN <effect>
 
Effect vocabulary (use only these forms):
  - '<X> moves <direction>'
  - '<X> and <Y> both move <direction>'
  - '<X> becomes <Y>'
  - '<X> does not move'
 
Directions: W=up, A=left, S=down, D=right
Positions:  'above P', 'below P', 'to the left of P', 'to the right of P'
""".strip()


def get_infer_legend_prompt(
    history_log: str, current_legend_text: str, game_name: str = "Unknown"
) -> tuple[str, str]:
    sys = (
        "You are a symbol analyst for 2D grid worlds. "
        f"The environment you are analyzing is named '{game_name}'. Use this context sparingly to guide symbol naming. "
        "Your task is to identify what each integer (0-15) represents strictly by observing its mechanical behavior — "
        "what moves, what blocks, what gets pushed, what acts as a goal, etc.\n\n"
        "Rules:\n"
        "- Be highly conservative. Base roles purely on verified mechanical behavior (e.g., 'movable block', 'solid obstacle').\n"
        "- DO NOT hallucinate or infer symbols that never appear in the board state.\n"
        "- Support logical and literal descriptions rather than imaginative guesses.\n"
        "- Retain or update existing legend mappings if provided, and add any newly discovered symbols.\n"
        'Output ONLY a JSON object: {"<integer_id>": "<role name>", ...}\n'
    )
    prompt = (
        f"{current_legend_text}\n\n"
        f"OBSERVATION HISTORY:\n{history_log}\n\n"
        "For each integer id that appears on the board, infer its role from how it behaves across these states. "
        "Output only the JSON object."
    )
    return sys, prompt


def get_deduce_rules_prompt(
    events: str, known_rules_text: str, focus_prompt: str, game_name: str = "Unknown"
) -> tuple[str, str]:
    sys = (
        "You are a physics engine reverse-engineer. "
        f"You are observing a grid environment named '{game_name}'. "
        "You observe sequences of actions and board states (integer grids) and deduce the underlying rules.\n\n"
        f"{RULE_FORMAT}\n\n"
        "CONSTRAINTS — a rule is only valid if ALL of these hold:\n"
        "1. EVIDENCED: The rule is directly supported by at least one action-outcome pair in the event log. No guessing.\n"
        "2. CAUSAL: The rule describes a cause (action + board state) and its direct effect. "
        "Do not describe side-effects or correlations.\n"
        "3. DIRECTION-CONSISTENT: The direction in IF must match the movement direction in THEN.\n"
        "4. NOT DUPLICATE: Do not emit a rule already in KNOWN RULES, even if worded differently.\n"
        "5. NOT CONTRADICTING: Do not emit a rule whose THEN conflicts with a KNOWN RULE under the same condition.\n"
        "6. NOT OVER-GENERALISED: If you only saw one direction, write only that direction's rule.\n"
        "7. CHAIN RULE: If an action causes two objects to move together (e.g. player pushes crate), "
        "the IF condition MUST include the state of the cell that the furthest object would enter, not just "
        "the cell between player and object.\n\n"
        "8. UPDATE LEGEND: If you learn a new symbol's role, output it. If no new legend info is learned, output an empty object {}.\n"
        "9. CLASSIFY RULES: Group the inferred rules into categories you invent (e.g. 'Movement', 'Collision').\n"
        "10. INFER FINAL GOAL: Based on the events, infer what the overall goal of the environment is (e.g., 'Move all crates to the target'). If unknown, leave empty.\n\n"
        'Output ONLY valid JSON: {"legend": {"symbol": "role"}, "rules": {"Category Name": ["rule 1", "rule 2"]}, "final_goal": "goal description"}\n'
        'If no new rules can be confidently inferred, output: {"legend": {}, "rules": {}, "final_goal": ""}'
    )
    prompt = (
        f"{known_rules_text}\n\n"
        f"RECENT EVENTS (action → resulting board state):\n{events}\n\n"
        f"{focus_prompt}"
        "Identify any new rules not already in KNOWN RULES. "
        "Follow the rule format exactly. Output only the JSON."
    )
    return sys, prompt


def get_compress_rules_prompt(known_rules_text: str) -> tuple[str, str]:
    sys = (
        "You are a rule abstraction specialist for 2D grid world physics. "
        "You receive rules deduced one observation at a time. Find rules that express the same mechanic across "
        "different directions (W/A/S/D) and collapse them into one direction-agnostic rule. "
        "Only merge rules where the behaviour is genuinely identical across all directions. "
        "Remove semantic duplicates.\n\n"
        f"{RULE_FORMAT}\n\n"
        'Output ONLY valid JSON: {"compressed_rules": {"Category Name": ["rule 1", "rule 2", ...]}}'
    )
    prompt = (
        f"KNOWN RULES:\n{known_rules_text}\n\n"
        "Compress direction-specific duplicates into general rules where justified. Output only JSON."
    )
    return sys, prompt
