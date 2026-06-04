from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from client.play_arc_client import QUIT_COMMAND, key_to_action, read_key, update_dashboard
from client.terminal_dashboard import TerminalDashboard
from client.engine.utils import format_grid
from studies.goal_recognition.keys import default_arc_api_key


STUDY_DIR = Path(__file__).resolve().parents[1]
ARC_BACKEND_URL = "https://three.arcprize.org"
PUZZLESCRIPT_BACKEND_URL = "http://127.0.0.1:8000"
PUZZLESCRIPT_SETUPS = {"openrouter_goal_recognition_matrix"}

LABELS = {
    "c": "correct",
    "w": "wrong",
    "p": "partial",
    "s": "skipped",
}


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def apply_verification(row: dict, label: str, note: str = "") -> dict:
    updated = dict(row)
    updated["manual_verification"] = {"label": label, "note": note}
    return updated


def frame_path_name(game_id: str) -> str:
    return game_id.replace("/", "_").replace("\\", "_") + ".json"


def default_evidence_roots(setup: str) -> list[Path]:
    return [STUDY_DIR / "experiment" / "artifacts"]


def find_evidence_file(row: dict, roots: list[Path]) -> Path | None:
    game_id = str(row.get("game_id", "")).strip()
    if not game_id:
        return None

    file_name = frame_path_name(game_id)
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob(file_name):
            if path.parent.name == "frames":
                candidates.append(path)

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_review_evidence(row: dict, roots: list[Path] | None = None) -> dict | None:
    embedded = row.get("review_evidence")
    if isinstance(embedded, dict):
        return embedded

    search_roots = roots or default_evidence_roots(str(row.get("setup", "")))
    evidence_file = find_evidence_file(row, search_roots)
    if evidence_file is None:
        return None

    data = json.loads(evidence_file.read_text(encoding="utf-8-sig"))
    evidence = {
        "available_actions": data.get("available_actions") or [],
        "source": str(evidence_file),
    }
    if "trajectory" in data:
        evidence["trajectory"] = data["trajectory"]
    if "frames" in data:
        evidence["frames"] = data["frames"]
    return evidence


def review_evidence_grid(evidence: dict) -> tuple[str, list[list[int]] | None]:
    frames = evidence.get("frames")
    if isinstance(frames, list) and frames:
        return "Observation frame", frames[-1]

    trajectory = evidence.get("trajectory")
    if isinstance(trajectory, list) and trajectory:
        index = len(trajectory) - 1
        item = trajectory[index]
        if isinstance(item, dict):
            action = item.get("action", "unknown")
            return f"Latest observation {index} after {action}", item.get("grid")

    return "Observation frame", None


def format_review_grid(grid: list[list[int]]) -> str:
    values = [value for row in grid for value in row]
    cell_width = max((len(str(value)) for value in values), default=1)
    lines = []
    for row in grid:
        lines.append(" ".join(str(value).rjust(cell_width) for value in row))
    return "\n".join(lines)


def format_compact_review_grid(grid: list[list[int]]) -> str:
    return format_grid(grid)


def print_evidence(row: dict, evidence: dict | None, show_trajectory: bool) -> None:
    actions = row.get("available_actions") or []
    if evidence:
        actions = evidence.get("available_actions") or actions
    print(f"Available actions: {', '.join(actions) or 'none'}")
    print(f"Frames seen by LLM: {row.get('frames_seen', '')}")
    if row.get("actions_taken"):
        print(f"Actions taken: {', '.join(row.get('actions_taken') or [])}")

    if not evidence:
        print("Saved numeric frame evidence was not found for this row.")
        print("")
        return

    if isinstance(evidence.get("trajectory"), list):
        print("Compact trajectory shown to LLM:")
        for index, item in enumerate(evidence["trajectory"]):
            action = item.get("action", "unknown")
            print(f"\nObservation {index} after {action}")
            print(format_compact_review_grid(item.get("grid") or []))
        label, grid = review_evidence_grid(evidence)
        print(f"\nNumeric reference - {label}:")
        print(format_review_grid(grid or []))
        print("")
        return

    label, grid = review_evidence_grid(evidence)
    print(f"Compact {label.lower()} shown to LLM:")
    print(format_compact_review_grid(grid or []))
    print(f"\nNumeric reference - {label}:")
    print(format_review_grid(grid or []))
    print("")


def print_prediction(row: dict) -> None:
    prediction = row.get("prediction") or {}
    print("")
    print(f"Game: {row.get('game_id')}")
    print(f"Setup: {row.get('setup')}")
    print(f"Goal: {prediction.get('goal_guess', '')}")
    if prediction.get("win_condition_guess"):
        print(f"Win condition: {prediction.get('win_condition_guess', '')}")
    if prediction.get("confidence") not in {None, ""}:
        print(f"Confidence: {prediction.get('confidence', '')}")
    uncertainties = prediction.get("uncertainties") or []
    if uncertainties:
        print("Uncertainties:")
        for item in uncertainties:
            print(f"- {item}")
    print("")


def play_for_review(row: dict, backend_url: str, api_key: str) -> None:
    game_id = row["game_id"]
    display_profile = "color" if row.get("setup") in PUZZLESCRIPT_SETUPS else "review_numeric"
    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=backend_url,
        arc_api_key=api_key,
    )
    dashboard = TerminalDashboard(
        game_id=game_id,
        mode="VERIFY",
        controls="W/A/S/D move | R reset | Z undo | Q return to verdict",
        display_profile=display_profile,
    )
    try:
        env = arcade.make(game_id, renderer=dashboard.render)
        if env is None:
            print(f"Failed to create game environment for {game_id}", file=sys.stderr)
            return
        obs = env.reset()
        update_dashboard(dashboard, obs)
        while True:
            key = read_key()
            command = key_to_action(key)
            if command is None:
                continue
            if command == QUIT_COMMAND:
                return
            if command == GameAction.RESET:
                obs = env.reset()
            else:
                obs = env.step(command)
            update_dashboard(dashboard, obs)
    finally:
        dashboard.close()


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def launch_play_gui(row: dict, backend_url: str, api_key: str) -> bool:
    if os.name != "nt":
        return False

    game_id = str(row["game_id"])
    cwd = Path.cwd()
    command = (
        f"Set-Location -LiteralPath {powershell_quote(str(cwd))}; "
        "python -m client.play_arc_gui "
        f"--game-id {powershell_quote(game_id)} "
        f"--backend-url {powershell_quote(backend_url)}"
    )
    env = os.environ.copy()
    if api_key:
        env["ARC_API_KEY"] = api_key
    subprocess.Popen(
        ["powershell", "-NoExit", "-Command", command],
        cwd=str(cwd),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return True


def backend_url_for_row(row: dict, requested_backend_url: str) -> str:
    if (
        row.get("setup") in PUZZLESCRIPT_SETUPS
        and requested_backend_url == ARC_BACKEND_URL
    ):
        return str(row.get("backend_url") or PUZZLESCRIPT_BACKEND_URL)
    return requested_backend_url


def api_key_for_row(row: dict, requested_api_key: str) -> str:
    if (
        row.get("setup") in PUZZLESCRIPT_SETUPS
        and requested_api_key == default_arc_api_key()
    ):
        return "local-dev"
    return requested_api_key


def ask_verdict() -> tuple[str, str]:
    note = ""
    while True:
        command = input(
            "Verdict [c correct / w wrong / p partial / s skip / n note]: "
        ).strip().lower()
        if command == "n":
            note = input("Note: ").strip()
            continue
        if command in LABELS:
            if not note:
                note = input("Note, optional: ").strip()
            return LABELS[command], note
        print("Use c, w, p, s, or n.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manually verify goal-recognition predictions."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--backend-url", default=ARC_BACKEND_URL)
    parser.add_argument("--api-key", default=default_arc_api_key())
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--play",
        action="store_true",
        help="Launch the mouse GUI player before recording each verdict.",
    )
    parser.add_argument(
        "--show-trajectory",
        action="store_true",
        help="Show every saved ten-frame observation instead of only the first one.",
    )
    parser.add_argument(
        "--evidence-root",
        action="append",
        type=Path,
        help="Additional artifact root to search for saved frame evidence.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = load_rows(args.predictions)
    out = args.out or args.predictions.with_name(
        args.predictions.stem + ".reviewed.jsonl"
    )

    reviewed = []
    for row in rows:
        if row.get("manual_verification"):
            reviewed.append(row)
            continue
        print_prediction(row)
        evidence_roots = default_evidence_roots(str(row.get("setup", "")))
        if args.evidence_root:
            evidence_roots.extend(args.evidence_root)
        if args.show_trajectory or not args.play:
            print_evidence(
                row,
                load_review_evidence(row, evidence_roots),
                show_trajectory=args.show_trajectory,
            )
        if args.play:
            backend_url = backend_url_for_row(row, args.backend_url)
            api_key = api_key_for_row(row, args.api_key)
            if launch_play_gui(row, backend_url, api_key):
                input("Play GUI opened. Inspect it, then press Enter here.")
            else:
                input("Press Enter to play this game, then Q to return here.")
                play_for_review(row, backend_url, api_key)
        else:
            input("Inspect the evidence above, then press Enter to record verdict.")
        label, note = ask_verdict()
        reviewed.append(apply_verification(row, label, note))
        write_rows(out, reviewed + rows[len(reviewed) :])

    write_rows(out, reviewed)
    print(f"reviewed predictions: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
