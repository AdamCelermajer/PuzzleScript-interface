"""What the AVO player and its solver see of an observation.

A move's PuzzleScript observation holds every board the engine produced: the board before
the move, then one board per engine step (several while something slides). The player sees
only the current board, the last one, as a plain grid like Harness²'s ``game.py``;
``history --move N`` prints every board of one move. ``solver.py`` reads the same
current-board observation as JSON. The evidence store and the laboratory history keep every
board unchanged.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

MAX_CHANGED_CELLS = 40  # as Harness²'s game.py lists them
HISTORY_PAGE = 20


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def _is_grid(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(row, list) for row in value)


def boards(observation: Any) -> list[list[list[Any]]] | None:
    """Every board of an observation ({"payload": {"frame": [grid, ...]}}); None for other payloads."""
    payload = observation.get("payload") if isinstance(observation, Mapping) else None
    frames = payload.get("frame") if isinstance(payload, Mapping) else None
    if isinstance(frames, list) and frames and all(_is_grid(frame) for frame in frames):
        return frames
    return None


def current_only(observation: Any) -> Any:
    """The observation with only its current board and no pixel table: what solver.py reads."""
    if not isinstance(observation, Mapping):
        return observation
    result = dict(observation)
    grids = boards(observation)
    if grids is not None:
        result["payload"] = {**observation["payload"], "frame": [grids[-1]]}
    metadata = observation.get("metadata")
    if isinstance(metadata, Mapping) and isinstance(metadata.get("projection"), Mapping):
        projection = {key: value for key, value in metadata["projection"].items() if key != "patterns"}
        result["metadata"] = {**metadata, "projection": projection}
    return result


def grid_text(grid: list[list[Any]]) -> str:
    return "\n".join(" ".join(str(cell) for cell in row) for row in grid)


def _levels(observation: Mapping[str, Any]) -> tuple[Any, Any] | None:
    progress = observation.get("progress")
    if isinstance(progress, Mapping) and "levels_completed" in progress:
        return progress.get("levels_completed"), progress.get("win_levels")
    return None


def _state(observation: Mapping[str, Any]) -> str:
    levels = _levels(observation)
    if levels is not None:
        return f"state={observation.get('status')} levels={levels[0]}/{levels[1]}"
    progress = observation.get("progress")
    return f"state={observation.get('status')}" + (f" progress={_compact(progress)}" if progress is not None else "")


def _image(observation: Mapping[str, Any]) -> str:
    rendered = (observation.get("metadata") or {}).get("rendered_frame") or {}
    return str(rendered.get("path") or "") if isinstance(rendered, Mapping) else ""


def _changed_cells(before: list[list[Any]], after: list[list[Any]]) -> list[str] | None:
    """Cells that differ between two boards, or None when the board changed size."""
    if len(before) != len(after) or any(len(old) != len(new) for old, new in zip(before, after)):
        return None
    return [f"({row},{column}) {old}->{new}" for row, (old_row, new_row) in enumerate(zip(before, after))
            for column, (old, new) in enumerate(zip(old_row, new_row)) if old != new]


def observation_text(observation: Mapping[str, Any]) -> str:
    """The current state: state, levels, available actions, the current board and its image."""
    actions = ", ".join(observation.get("available_actions") or []) or "unknown"
    lines = [_state(observation), f"available_actions={actions}"]
    grids = boards(observation)
    if grids is None:
        lines.append("payload: " + _compact(observation.get("payload")))
    else:
        mode = ((observation.get("metadata") or {}).get("projection") or {}).get("mode")
        lines += [f"board ({mode}):" if mode else "board:", grid_text(grids[-1])]
    if _image(observation):
        lines.append(f"image: {_image(observation)}")
    return "\n".join(lines)


def _footer(result: Mapping[str, Any]) -> list[str]:
    lines = []
    task = result.get("task")
    if isinstance(task, Mapping):
        lines.append(f"task: fitness={task.get('fitness')} terminal={task.get('terminal')} "
                     f"success={task.get('success')}")
    budgets = result.get("budgets")
    if isinstance(budgets, Mapping):
        lines.append("budgets: " + ", ".join(f"{key}={round(value) if isinstance(value, float) else value}"
                                             for key, value in budgets.items()))
    for event in result.get("supervisor_events") or []:
        lines.append(f"supervisor {event.get('severity')}: {event.get('message')} {_compact(event.get('evidence'))}")
    supervisor = result.get("supervisor")
    if isinstance(supervisor, Mapping) and supervisor.get("attention_required"):
        lines.append("supervisor: environment actions are paused until you run "
                     'python avo_tool.py acknowledge_supervisor "revised approach"')
    if result.get("evaluations"):
        lines.append("prediction evaluations: " + _compact(result["evaluations"]))
    return lines


def probe_text(result: Mapping[str, Any]) -> str:
    """One move, as game.py reports it: what changed, then the current board only."""
    transition = result["transition"]
    before, after, move = transition["before"], transition["after"], transition["sequence"]
    head = f"{transition['action']['id']} (move {move}, episode {transition['episode']}): "
    grids, previous = boards(after), boards(before)
    levels_before, levels_after = _levels(before), _levels(after)
    if levels_before and levels_after and (levels_after[0] or 0) > (levels_before[0] or 0):
        head += f"LEVEL COMPLETED ({levels_after[0]}/{levels_after[1]}). The board below is the next level."
    elif grids is not None and previous is not None:
        changed = _changed_cells(previous[-1], grids[-1])
        if changed is None:
            head += "the board changed size"
        elif not changed:
            head += "nothing changed"
        else:
            more = f" and {len(changed) - MAX_CHANGED_CELLS} more" if len(changed) > MAX_CHANGED_CELLS else ""
            head += "changed " + ", ".join(changed[:MAX_CHANGED_CELLS]) + more
    else:
        head += "nothing changed" if before.get("payload") == after.get("payload") else "the payload changed"
    lines = [head]
    if grids is not None:
        lines.append(f"engine steps this move: {len(grids) - 1}; every board of it: "
                     f"python avo_tool.py history --move {move}")
    return "\n".join([*lines, observation_text(after), *_footer(result)])


def move_summary(transition: Mapping[str, Any]) -> dict[str, Any]:
    """One line's worth of a recorded move, without its observations."""
    before, after = transition["before"], transition["after"]
    grids, previous = boards(after), boards(before)
    changed = _changed_cells(previous[-1], grids[-1]) if grids is not None and previous is not None else None
    return {
        "move": transition["sequence"], "episode": transition["episode"], "action": transition["action"]["id"],
        "state": after.get("status"), "levels_before": _levels(before), "levels_after": _levels(after),
        "engine_steps": len(grids) - 1 if grids is not None else None,
        "changed_cells": len(changed) if changed is not None else None,
        "changed": before.get("payload") != after.get("payload"),
    }


def _summary_line(move: Mapping[str, Any]) -> str:
    parts = []
    cells, steps = move.get("changed_cells"), move.get("engine_steps")
    if cells:
        parts.append(f"{cells} cell{'s' if cells != 1 else ''} changed")
    elif cells == 0 or (steps is None and not move.get("changed")):
        parts.append("nothing changed")
    else:
        parts.append("board changed size" if steps is not None else "changed")
    if steps is not None:
        parts.append(f"{steps} engine step{'s' if steps != 1 else ''}")
    levels_before, levels_after = move.get("levels_before"), move.get("levels_after")
    if levels_after:
        levels = f"{levels_after[0]}/{levels_after[1]}"
        if levels_before and list(levels_before) != list(levels_after):
            levels = f"{levels_before[0]}/{levels_before[1]}->{levels}"
        parts.append(f"levels {levels}")
    parts.append(f"state {move.get('state')}")
    return f"move {move['move']} episode {move['episode']} {move['action']}: " + ", ".join(parts)


def move_boards_text(transition: Mapping[str, Any]) -> str:
    """Every board of one recorded move, in order, as plain grids."""
    before, after = transition["before"], transition["after"]
    lines = [f"move {transition['sequence']} (episode {transition['episode']}): {transition['action']['id']}",
             f"before: {_state(before)}", f"after: {_state(after)}"]
    grids = boards(after)
    if grids is None:
        lines += ["payload before: " + _compact(before.get("payload")),
                  "payload after: " + _compact(after.get("payload"))]
    else:
        for index, grid in enumerate(grids):
            if index == 0 and len(grids) > 1:
                label = "the board before the move"
            else:
                label = f"engine step {index}" + (", the final board" if index == len(grids) - 1 else "")
            lines += [f"board {index + 1}/{len(grids)}, {label}:", grid_text(grid)]
    if _image(after):
        lines.append(f"image of the final board: {_image(after)}")
    return "\n".join(lines)


def history_text(result: Mapping[str, Any]) -> str:
    if "move" in result:
        return move_boards_text(result["move"])
    moves, count = result.get("moves") or [], result.get("count", 0)
    if not moves:
        return f"No moves in this range; {count} recorded."
    lines = [f"moves {moves[0]['move']}-{moves[-1]['move']} of {count}; older: --offset N --limit N; "
             "every board of one move: python avo_tool.py history --move N"]
    return "\n".join([*lines, *(_summary_line(move) for move in moves)])


def render(method: str, result: Any) -> str | None:
    """Plain text for the commands that show the game; None keeps the JSON reply."""
    if not isinstance(result, Mapping):
        return None
    if method == "probe" and isinstance(result.get("transition"), Mapping):
        return probe_text(result)
    if method == "history":
        return history_text(result)
    if method in {"observe", "reset", "restore"} and isinstance(result.get("observation"), Mapping):
        head = []
        if method == "reset":
            head.append(f"Episode {result.get('episode')} started from a fresh reset.")
        elif method == "restore":
            head.append(f"Restored {result.get('checkpoint_id')}; episode {result.get('episode')} started.")
        return "\n".join([*head, observation_text(result["observation"]), *_footer(result)])
    return None
