"""Merge the existing game surveys into ``benchmark/games.json`` (contract section 5).

Sources (all optional except the game directories):
- ``benchmark/vetting/catalog-audit.json``      title/author/structure/protocol exclusions
- ``output/game-selection-20/selection.json``   newest tier judgments (preferred)
- ``output/game-selection-20/level-inventory.json`` playable level counts for those games
- ``benchmark/vetting/selection-v0.json``       older tiers and mechanic summaries
- ``benchmark/games/index.json``                 reference (BFS replay) collection
- ``experiement/bfs_solver/*results*.json``      BFS solve status and depth
- ``puzzlescript_interface/api/catalog.py``      whether the ARC service lists the game

Rebuilding is idempotent: ``tags``, ``tags_status``, ``summary`` (when set), ``notes``
and manually set tiers survive. Agent solve rates are never stored here.

    uv run python -m scripts.build_game_metadata [--check]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAMES_JSON = Path("benchmark/games.json")
GAME_ID_RE = re.compile(r"^ps_[a-z0-9_]+-v\d+$")
MANY_LEVELS = 12        # many-levels property threshold (playable maps)
LARGE_MAP_AREA = 300    # large-maps property threshold (cells in the largest map)

TAG_VOCABULARY = {
    "mechanics": {
        "push": "The player moves objects by walking into them (including chains of pushed objects).",
        "pull": "The player drags, lifts or carries objects instead of only pushing them.",
        "slide": "The player or objects keep moving until blocked (ice, sliding moves).",
        "gravity": "Unsupported objects or the player fall each turn; side-view or platform play.",
        "teleport": "Portals or teleporters move things between distant cells.",
        "merge": "Two objects combine into a different object (fusing, adding up values).",
        "spawn": "Moves create new objects or copies (duplication, emitters, splitting).",
        "transform": "Objects change type or state when pushed, touched or triggered.",
        "multi-avatar": "More than one controllable character, moved together or by switching control.",
        "remote-movement": "Player input moves other objects at a distance (shared moves, arrows, magnets, mirrored movers).",
        "switch-door": "Pressure plates, switches or levers open, close or toggle gates and walls.",
        "key-lock": "Collected keys or tokens unlock doors or barriers.",
        "collect": "Items are picked up by walking onto them (coins, pickups, food).",
        "fill-pit": "Objects pushed into holes, pits or water fill them and make them walkable.",
        "trail": "Movement leaves a persistent trail, path or body behind (snake, path drawing).",
        "rotation": "Objects rotate, or facing direction changes what a move or action does (not cosmetic left/right sprites).",
        "spread": "Something propagates cell by cell (fire, shadow, virus, liquid, beams of state).",
        "destruction": "Objects are removed or destroyed (explosions, cutters, crushing, pits that consume).",
        "hazard": "Cells or objects that kill the player or force a restart.",
        "npc": "Autonomous enemies or creatures that move by their own rules each turn.",
        "beam": "Line-of-sight effects: lasers, light, shots or rays that travel across the board.",
        "match-clear": "Groups of matching objects are cleared when aligned or adjacent.",
        "crate-on-target": "Win by covering every target with a crate-like object (Sokoban goal).",
        "reach-exit": "Win by moving the player (or players) onto an exit or goal cell.",
    },
    "properties": {
        "hidden-state": "Rule-relevant state is not visible in the rendered frame (aliased sprites, counters, phases).",
        "irreversible": "Moves can create dead ends; progress often needs undo or restart.",
        "multi-goal": "Several win conditions must hold together, or objects must be sorted to different goals.",
        "text-instructions": "In-game message screens explain or hint at the mechanics.",
        "counting": "Solutions depend on counting, numbers or arithmetic.",
        "limited-resources": "A finite move budget, stamina, ammunition or consumable objects constrains play.",
        "cascades": "One input triggers multi-step chain reactions resolved before the next input.",
        "randomness": "Random rules make transitions non-deterministic (derived from the source audit).",
        "realtime": "The game advances on a timer without input (derived from the source audit).",
        "action-button": "The action key (ACTION5) has a game-specific effect (derived from the source audit).",
        "many-levels": f"At least {MANY_LEVELS} playable levels (derived from the level count).",
        "large-maps": f"The largest map has at least {LARGE_MAP_AREA} cells (derived from the source audit).",
    },
}
DERIVED_PROPERTIES = ("randomness", "realtime", "action-button", "many-levels", "large-maps")


def read_json(path: Path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return fallback


def write_json_atomic(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    handle, temp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def default_title(game_id: str) -> str:
    return re.sub(r"^ps_|-v\d+$", "", game_id).replace("_", " ").title()


def arc_catalog_ids(games_dir: Path) -> set[str]:
    sys.path.insert(0, str(ROOT))
    from puzzlescript_interface.api.catalog import build_catalog
    return {entry.game_id for entry in build_catalog(games_dir)}


def bfs_results(root: Path) -> dict[str, dict]:
    """Best BFS record per game: a solved level beats an unsolved one; the 60 s
    semantic sweep (newest, complete) is preferred among equals."""
    base = root / "experiement/bfs_solver"
    best: dict[str, tuple[tuple, dict]] = {}
    files = sorted(base.glob("*.json")) if base.is_dir() else []
    for path in files:
        if not re.search(r"(?:^results|_results).*\.json$", path.name):
            continue
        data = read_json(path, {}) or {}
        for row in data.get("results") or []:
            game_id = row.get("gameId")
            if not isinstance(game_id, str):
                continue
            solved = row.get("solved") is True
            record = {"solved": solved, "depth": row.get("solutionDepth") if solved else None,
                      "level": row.get("levelIndex"), "status": row.get("status"),
                      "source": f"experiement/bfs_solver/{path.name}"}
            rank = (solved, path.name.startswith("semantic_all"), -(row.get("levelIndex") or 0))
            if game_id not in best or rank > best[game_id][0]:
                best[game_id] = (rank, record)
    return {game_id: record for game_id, (_, record) in best.items()}


def derived_properties(entry: dict, audit: dict) -> list[str]:
    reasons = set(audit.get("exclusion_reasons") or [])
    features = audit.get("features") or {}
    flags = {
        "randomness": "random_rules" in reasons,
        "realtime": "realtime" in reasons,
        "action-button": bool(features.get("action_button")),
        "many-levels": (entry.get("levels") or 0) >= MANY_LEVELS,
        "large-maps": (audit.get("max_area") or 0) >= LARGE_MAP_AREA,
    }
    return [name for name in DERIVED_PROPERTIES if flags[name]]


def apply_derived_properties(entry: dict, derived: list[str]) -> None:
    """Derived properties are facts from the source audit, so they replace any
    drafted guess; reviewed tag sets are left untouched."""
    if entry.get("tags_status") == "reviewed":
        return
    tags = entry.setdefault("tags", {"mechanics": [], "properties": []})
    kept = [p for p in tags.get("properties", []) if p not in DERIVED_PROPERTIES]
    tags["properties"] = kept + derived


def build(root: Path, existing: dict | None = None, arc_ids: set[str] | None = None) -> dict:
    games_dir = root / "puzzlescript_interface/games"
    audit_rows = {row["game_id"]: row for row in
                  (read_json(root / "benchmark/vetting/catalog-audit.json", {}) or {}).get("games", [])}
    current = {row["id"]: row for row in
               (read_json(root / "output/game-selection-20/selection.json", {}) or {}).get("games", [])}
    inventory = {row["id"]: len(row.get("maps") or []) for row in
                 read_json(root / "output/game-selection-20/level-inventory.json", []) or []}
    older = {row["game_id"]: row for row in
             (read_json(root / "benchmark/vetting/selection-v0.json", {}) or {}).get("selection", [])}
    reference = {row["game_id"] for row in
                 (read_json(root / "benchmark/games/index.json", {}) or {}).get("games", [])}
    bfs = bfs_results(root)
    if arc_ids is None:
        arc_ids = arc_catalog_ids(games_dir)
    previous = (existing or {}).get("games", {})

    ids = {p.name for p in games_dir.iterdir() if p.is_dir() and GAME_ID_RE.match(p.name)} if games_dir.is_dir() else set()
    ids |= set(audit_rows)
    games = {}
    for game_id in sorted(ids):
        audit = audit_rows.get(game_id, {})
        old = previous.get(game_id, {})
        has_script = (games_dir / game_id / "script.txt").is_file()
        reasons = list(audit.get("exclusion_reasons") or [])
        if not has_script:
            reasons.append("no_script")
        if audit.get("runtime_smoke_passed") is False:
            reasons.append("runtime_failure")
        if has_script and game_id not in arc_ids:
            reasons.append("not_in_arc_catalog")
        collections = [name for name, members in
                       (("selection-20", current), ("selection-v0", older), ("reference", reference))
                       if game_id in members]
        if game_id in current:
            tier, tier_source = str(current[game_id].get("difficulty", "")).lower() or None, "selection-20"
        elif game_id in older:
            tier, tier_source = older[game_id].get("tier") or None, "selection-v0"
        else:
            tier, tier_source = None, None
        if old.get("tier_source") == "manual":
            tier, tier_source = old.get("tier"), "manual"
        levels = inventory.get(game_id, audit.get("map_levels"))
        v0_summary = (older.get(game_id) or {}).get("mechanic_summary") or ""
        summary = old.get("summary") or v0_summary
        entry = {
            "title": (current.get(game_id) or {}).get("name") or audit.get("title") or default_title(game_id),
            "author": audit.get("author") or "",
            "homepage": audit.get("homepage") or "",
            "status": "excluded" if reasons else "playable",
            "exclusion_reasons": reasons,
            "arc_catalog": game_id in arc_ids,
            "collections": collections,
            "tier": tier,
            "tier_source": tier_source,
            "levels": levels,
            "structure": {"objects": audit.get("object_count"), "rule_groups": audit.get("parsed_rule_groups"),
                          "max_area": audit.get("max_area")},
            "bfs": bfs.get(game_id),
            "tags": old.get("tags") or {"mechanics": [], "properties": []},
            "tags_status": old.get("tags_status") or "none",
            "summary": summary,
            "summary_source": old.get("summary_source") or ("selection-v0" if summary and summary == v0_summary else None),
            "notes": old.get("notes") or "",
        }
        for key in ("tags_model", "tags_drafted_at"):
            if key in old:
                entry[key] = old[key]
        if has_script:
            apply_derived_properties(entry, derived_properties(entry, audit))
        games[game_id] = entry
    return {"schema": "games-v1",
            "tag_vocabulary": {kind: list(terms) for kind, terms in TAG_VOCABULARY.items()},
            "tag_definitions": {term: text for terms in TAG_VOCABULARY.values() for term, text in terms.items()},
            "games": games}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="exit 1 if games.json would change")
    args = parser.parse_args(argv)
    path = args.root / GAMES_JSON
    existing = read_json(path)
    result = build(args.root, existing)
    if args.check:
        return 0 if existing == result else 1
    write_json_atomic(path, result)
    games = result["games"].values()
    print(f"{path}: {len(result['games'])} games, "
          f"{sum(g['status'] == 'playable' for g in games)} playable, "
          f"{sum(g['tier'] is not None for g in games)} tiered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
