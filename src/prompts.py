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
 
 
# =============================================================================
# 1. LEGEND INFERENCE
# =============================================================================
 
def get_infer_legend_prompt(history_log: str, current_legend_text: str, game_name: str = "Unknown") -> tuple[str, str]:
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
        "Output ONLY a JSON object: {\"<integer_id>\": \"<role name>\", ...}\n"
    )
    prompt = (
        f"{current_legend_text}\n\n"
        f"OBSERVATION HISTORY:\n{history_log}\n\n"
        "For each integer id that appears on the board, infer its role from how it behaves across these states. "
        "Output only the JSON object."
    )
    return sys, prompt
 
 
# =============================================================================
# 2. RULE DEDUCTION (called every N steps on a short recent window)
# =============================================================================
 
def get_deduce_rules_prompt(events: str, known_rules_text: str, focus_prompt: str, game_name: str = "Unknown") -> tuple[str, str]:
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
        "Output ONLY valid JSON: {\"legend\": {\"symbol\": \"role\"}, \"rules\": {\"Category Name\": [\"rule 1\", \"rule 2\"]}, \"final_goal\": \"goal description\"}\n"
        "If no new rules can be confidently inferred, output: {\"legend\": {}, \"rules\": {}, \"final_goal\": \"\"}"
    )
    prompt = (
        f"{known_rules_text}\n\n"
        f"RECENT EVENTS (action → resulting board state):\n{events}\n\n"
        f"{focus_prompt}"
        "Identify any new rules not already in KNOWN RULES. "
        "Follow the rule format exactly. Output only the JSON."
    )
    return sys, prompt
 
 
# =============================================================================
# 3. RULE COMPRESSION (new — collapses direction-specific rules into general ones)
# =============================================================================
 
def get_compress_rules_prompt(known_rules_text: str) -> tuple[str, str]:
    sys = (
        "You are a rule abstraction specialist for 2D grid world physics. "
        "You receive rules deduced one observation at a time. Find rules that express the same mechanic across "
        "different directions (W/A/S/D) and collapse them into one direction-agnostic rule. "
        "Only merge rules where the behaviour is genuinely identical across all directions. "
        "Remove semantic duplicates.\n\n"
        f"{RULE_FORMAT}\n\n"
        "Output ONLY valid JSON: {\"compressed_rules\": {\"Category Name\": [\"rule 1\", \"rule 2\", ...]}}"
    )
    prompt = (
        f"RULES TO COMPRESS:\n{known_rules_text}\n\n"
        "Compress this rule set while preserving behaviour. Output only the JSON."
    )
    return sys, prompt
 
 
# =============================================================================
# 4. RULE REFINEMENT (final consolidation pass — called at end of learning)
# =============================================================================
 
def get_refine_rules_prompt(known_rules_text: str, history_log: str, game_name: str = "Unknown") -> tuple[str, str]:
    sys = (
        "You are a quality auditor for world physics rules. "
        f"The environment is named '{game_name}'. Use this title for thematic context when naming symbols. "
        "You are given a candidate rule set and a transition history. "
        "Your job is to produce the cleanest, most accurate, most minimal rule set possible.\n\n"
        f"{RULE_FORMAT}\n\n"
        "AUDIT STEPS (apply in order):\n"
        "1. VERIFY: For each rule, find at least one event in the history that supports it. "
        "If no supporting event exists, mark it as unverified.\n"
        "2. REMOVE UNVERIFIED: Drop all unverified rules. Do not keep rules you cannot trace to an observation.\n"
        "3. REMOVE CONTRADICTIONS: If two rules have the same condition but different effects, "
        "keep the one supported by more observations and drop the other.\n"
        "4. DIRECTION CHECK: Verify W=up, A=left, S=down, D=right in every rule. Fix any mismatches.\n"
        "5. COMPRESS: Merge direction-specific rules into direction-agnostic forms where the behaviour "
        "is genuinely identical across directions (see compression step 1 from the rule format).\n"
        "6. INFER LEGEND: Based on observed behaviour, assign a role name to each symbol.\n"
        "7. FINAL GOAL: State the final goal of the environment based on the history.\n\n"
        "DO NOT add rules that are not evidenced by the history.\n\n"
        "Output ONLY valid JSON: {\"final_rules\": {\"Category Name\": [\"rule 1\", \"rule 2\"]}, \"legend\": {\"symbol\": \"role\", ...}, \"final_goal\": \"goal description\"}"
    )
    prompt = (
        f"CANDIDATE RULES:\n{known_rules_text}\n\n"
        f"TRANSITION HISTORY (ground truth):\n{history_log}\n\n"
        "Audit and clean the rules. Output only the JSON."
    )
    return sys, prompt
 
 
# =============================================================================
# 5. SUBGOAL PLANNING (drives exploration toward unseen interactions)
# =============================================================================
 
def get_plan_subgoal_prompt(
    board: str,
    recent: str,
    known_rules: list,
    inferred_legend: dict | None = None,
) -> tuple[str, str]:

    known_rules_text = (
        "KNOWN RULES SO FAR:\n" + "\n".join(f"- {r}" for r in known_rules)
        if known_rules else "KNOWN RULES SO FAR: none yet"
    )
    legend_text = ""
    if inferred_legend:
        legend_text = (
            f"SYMBOL ROLES DEDUCED SO FAR: {inferred_legend}\n"
            "Use this to target the right objects in your subgoal.\n\n"
        )
 
    sys = (
        "You are a systematic experiment designer for a 2D grid world. "
        "Your goal is to identify gaps in the current rule set and design one targeted action sequence "
        "that will produce a new, unseen interaction or will advance to the final goal of the world.\n\n"
        "Think like a scientist: what interaction have you NOT yet observed? "
        "What single subgoal would most likely reveal a new rule or advance to the final goal?"
    )
    prompt = (
        f"CURRENT BOARD:\n{board}\n\n"
        f"{legend_text}"
        f"{known_rules_text}\n\n"
        f"RECENT ACTIONS:\n{recent}\n\n"
        "Identify the most important interaction that is NOT yet covered by the known rules. "
        "State a single, concrete subgoal in one sentence. "
        "Be specific about which object to interact with and in which direction."
    )
    return sys, prompt
 
 
# =============================================================================
# 6. LEARNING ACT (picks next move toward subgoal)
# =============================================================================
 
def get_learning_act_prompt(subgoal: str, board: str, known_rules_text: str, hist: str) -> tuple[str, str]:
    sys = (
        "You are an agent in a 2D grid world. "
        "You must select the single best next action to make progress toward your subgoal.\n\n"
        "Actions: ACTION1 (up), ACTION2 (down), ACTION3 (left), ACTION4 (right), ACTION5 (action/space), RESET (reset board)\n\n"
        "Output ONLY the exact action name (e.g. ACTION1). No explanation, no reasoning, no punctuation."
    )
    prompt = (
        f"SUBGOAL: {subgoal}\n\n"
        f"BOARD OVER TIME:\n{board}\n\n"
        f"{known_rules_text}\n\n"
        f"RECENT HISTORY:\n{hist}\n\n"
        "Select the action that best moves you toward the subgoal. "
        "Do NOT repeat an action that left the board unchanged. "
        "If you are stuck, or any action do not help, you can use RESET to reset the board."
        "Output one action name only: ACTION1, ACTION2, ACTION3, ACTION4, ACTION5, or RESET."
    )
    return sys, prompt
 
 
# =============================================================================
# 7. SOLVING ACT (used in solving mode — requires rules to be passed in)
# =============================================================================
 
def get_solving_act_prompt(board: str, legend: dict, known_rules: list, show_legend: bool) -> tuple[str, str]:
    rules_text = (
        "WORLD RULES:\n" + "\n".join(f"- {r}" for r in known_rules)
        if known_rules else ""
    )
    legend_text = f"LEGEND: {legend}\n" if show_legend and legend else ""
 
    sys = (
        "You are a puzzle solver in a 2D grid world. "
        "Use the world rules to reason about what will happen before you act. "
        "Output ONLY the exact action name. No explanation."
    )
    prompt = (
        f"{legend_text}"
        f"{rules_text}\n\n"
        f"BOARD OVER TIME:\n{board}\n\n"
        "Choose your next action: ACTION1 (up), ACTION2 (down), ACTION3 (left), ACTION4 (right), ACTION5, RESET\n"
        "Output action name only."
    )
    return sys, prompt
 
