"""What the baseline player is told, word for word the same whoever drives the game.

Both drivers share the system prompt, the observation text, the first message and the final
report; only one line differs: how a move is sent (``act`` once per turn for the controller,
``do`` as often as it likes for the agent). A harness that takes tools (``native_tools``) gets them as
real tools that run the same scripts; any other harness runs the scripts through its shell.
"""
from __future__ import annotations

from game.grid import last_grid
from frameworks import levels, world_model

SYSTEM_PROMPT = (
    "You are playing an unknown puzzle game. Complete as many levels as you can within your action budget.\n\n"
    "Each observation gives the game status, the available actions and the grid (one number per tile type). "
    "The current picture is frame.png in your working folder. Actions are opaque: learn what they do by "
    "trying them. Every action costs one from your budget.\n\n"
    "Your folder persists for the whole run: keep notes and scripts there as you find useful. Learn about "
    "the game only by playing it: do not search this machine or the network for its files.\n\n"
)
PLAY = {
    ("controller", True): "Each turn you get one observation. Submit one action with the act tool.",
    ("controller", False): "Each turn you get one observation. Submit one action with: python act.py ACTION",
    ("agent", True): "Play with the do tool.",
    ("agent", False): "Play with: python game.py do ACTION",
}
ACTION_ARGUMENT = "one of the available actions"
TOOLS = {
    "controller": [
        {"name": "act", "description": "Submit your action for this turn. This ends your turn; the next "
                                       "observation comes in the next turn.",
         "argument": "action", "argument_description": ACTION_ARGUMENT, "command": ["python", "act.py"]},
    ],
    "agent": [
        {"name": "do", "description": "Take one action now. Returns the new observation. Costs one action.",
         "argument": "action", "argument_description": ACTION_ARGUMENT, "command": ["python", "game.py", "do"]},
    ],
}
# Only the legacy encodings need explaining beyond the system prompt's "one number per tile type".
ENCODINGS = {
    "object-cell-v1": "Grid encoding: one cell per visible game tile; values are anonymous object-combination IDs.",
    "visible-cell-hex-v2": ("Grid encoding: each visible tile is a 2x2 block [[a,b],[c,d]]. Its opaque pattern ID "
                            "is 4096*a+256*b+16*c+d. Group these blocks to recover the tile board; the PNG shows "
                            "the same visible board."),
}
REPORT_PROMPT = ("The game has ended ({reason}; levels completed {levels}/{total}); do not take another action. "
                 + world_model.final_prompt() + " Then reply 'done'.")


def system_prompt(driver: str, tools: bool) -> str:
    return SYSTEM_PROMPT + PLAY[driver, tools]


def game_tools(driver: str, session) -> list[dict]:
    """The driver's tools for a harness that takes them; none otherwise (the prompt then names the scripts)."""
    return TOOLS[driver] if getattr(session, "native_tools", False) else []


def available(frame) -> list[str]:
    """The game's actions plus RESET, which every game accepts."""
    names = [action.name for action in getattr(frame, "available_actions", None) or [] if action.name != "RESET"]
    return names + ["RESET"]


def observation(frame, actions_used: int, max_steps: int, last: str = "") -> str:
    grid = last_grid(frame.frame)
    lines = [f"Last action: {last}"] if last else []
    lines += [f"state={getattr(frame.state, 'value', frame.state)} levels={frame.levels_completed}/{frame.win_levels} "
              f"actions_used={actions_used}/{max_steps}",
              f"available_actions={', '.join(available(frame))}"]
    encoding = ENCODINGS.get((getattr(frame, "projection", None) or {}).get("mode"))
    if encoding:
        lines.append(encoding)
    lines += ["grid:", "\n".join(" ".join(str(cell) for cell in row) for row in grid)]
    return "\n".join(lines)


def last_action(name: str, levels_before: int, frame) -> str:
    """The observation's "Last action" line: the action, and whether it completed a level. What changed
    on the grid is left for the player to see."""
    if frame.levels_completed > levels_before:
        return f"{name}: LEVEL COMPLETED ({frame.levels_completed}/{frame.win_levels}). The grid below is the next level."
    return name


def first_message(max_steps: int, start_level: int, frame) -> str:
    return (f"Play the game now. You have {max_steps} actions.{levels.start_note(start_level, frame.win_levels)}"
            f"\n\n{observation(frame, 0, max_steps)}")
