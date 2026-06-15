RULE_FORMAT = """
Executable rule JSON shape:
  {
    "summary": "ACTION4 moves the player one cell right into empty space.",
    "action": "ACTION4",
    "anchor": 2,
    "conditions": [
      {"dx": 0, "dy": 0, "value": 2},
      {"dx": 1, "dy": 0, "value": 0}
    ],
    "effects": [
      {"dx": 0, "dy": 0, "value": 0},
      {"dx": 1, "dy": 0, "value": 2}
    ],
    "evidence_ids": ["T000001"]
  }

Offsets are relative to the anchor cell. Use only integer cell values from the boards.
""".strip()


def get_deduce_rules_prompt(
    events: str, known_rules_text: str, focus_prompt: str, game_name: str = "Unknown"
) -> tuple[str, str]:
    system = (
        "You are a physics engine reverse-engineer. "
        f"You are observing a grid environment named '{game_name}'. "
        "You observe action/state transitions and propose executable mechanical rules.\n\n"
        f"{RULE_FORMAT}\n\n"
        "Only propose rules directly supported by the event log. "
        "Do not guess, do not duplicate known rules, and do not over-generalize from one direction. "
        "Every rule must include a concise natural-language summary and cite the "
        "transition ids that support it.\n\n"
        'Output only JSON: {"rules": [<rule objects>]}\n'
        'If no rule is supported, output: {"rules": []}'
    )
    prompt = (
        f"{known_rules_text}\n\n"
        f"Recent events:\n{events}\n\n"
        f"{focus_prompt}"
        "Identify new rule hypotheses. Output only JSON."
    )
    return system, prompt


def get_explore_subgoal_prompt(
    current_board: str,
    available_actions: str,
    recent_events: str,
    known_rules_text: str,
    game_name: str = "Unknown",
    rendered_image_note: str = "",
) -> tuple[str, str]:
    system = (
        "You guide an agent learning a grid puzzle by experiment. "
        f"The game is '{game_name}'. "
        "Verified rules could not produce a plan, so choose a small useful subgoal "
        "and one next action to learn more or move toward solving. "
        "Use only the available actions. "
        "Do not predict the next board or dump a full state. "
        'Output only JSON: {"subgoal": "one short sentence", "plan": ["ACTION1"]}'
    )
    image_section = (
        f"Rendered image: {rendered_image_note}\n\n" if rendered_image_note else ""
    )
    prompt = (
        f"Current board:\n{current_board}\n\n"
        f"Available actions: {available_actions}\n\n"
        f"Known rule hypotheses:\n{known_rules_text or '- none'}\n\n"
        f"Recent evidence:\n{recent_events or '- none'}\n\n"
        f"{image_section}"
        "Choose the next subgoal and one-action plan. Output only JSON."
    )
    return system, prompt
