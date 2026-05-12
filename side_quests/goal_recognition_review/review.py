from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from client.play_arc_client import QUIT_COMMAND, key_to_action, read_key, update_dashboard
from client.terminal_dashboard import TerminalDashboard


LABELS = {
    "c": "correct",
    "w": "wrong",
    "p": "partial",
    "s": "skipped",
}


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
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


def print_prediction(row: dict) -> None:
    prediction = row.get("prediction") or {}
    print("")
    print(f"Game: {row.get('game_id')}")
    print(f"Setup: {row.get('setup')}")
    print(f"Goal: {prediction.get('goal_guess', '')}")
    print(f"Win condition: {prediction.get('win_condition_guess', '')}")
    print(f"Confidence: {prediction.get('confidence', '')}")
    uncertainties = prediction.get("uncertainties") or []
    if uncertainties:
        print("Uncertainties:")
        for item in uncertainties:
            print(f"- {item}")
    print("")


def play_for_review(row: dict, backend_url: str, api_key: str) -> None:
    game_id = row["game_id"]
    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=backend_url,
        arc_api_key=api_key,
    )
    dashboard = TerminalDashboard(
        game_id=game_id,
        mode="VERIFY",
        controls="W/A/S/D move | R reset | Z undo | Q return to verdict",
        display_profile="arc" if "three.arcprize.org" in backend_url else "puzzlescript",
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


def ask_verdict() -> tuple[str, str]:
    while True:
        command = input(
            "Verdict [c correct / w wrong / p partial / s skip / n note]: "
        ).strip().lower()
        if command == "n":
            note = input("Note: ").strip()
            return "partial", note
        if command in LABELS:
            note = input("Note, optional: ").strip()
            return LABELS[command], note
        print("Use c, w, p, s, or n.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manually verify goal-recognition predictions."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--backend-url", default="https://three.arcprize.org")
    parser.add_argument("--api-key", default=os.getenv("ARC_API_KEY", ""))
    parser.add_argument("--out", type=Path)
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
        input("Press Enter to play this game, then Q in the game view to return here.")
        play_for_review(row, args.backend_url, args.api_key)
        label, note = ask_verdict()
        reviewed.append(apply_verification(row, label, note))
        write_rows(out, reviewed + rows[len(reviewed) :])

    write_rows(out, reviewed)
    print(f"reviewed predictions: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
