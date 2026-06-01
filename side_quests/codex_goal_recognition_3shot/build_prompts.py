from __future__ import annotations

import argparse
import json
from pathlib import Path

from side_quests.codex_goal_recognition_3shot.progress import Progress
from side_quests.codex_goal_recognition_3shot.prompts import build_prompt_variants
from side_quests.codex_goal_recognition_3shot.schema import make_run_paths, write_json


DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts"
ROOT = Path(__file__).resolve().parents[2]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 2: build cache-friendly prompt payloads from prepared evidence."
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args(argv)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ready_evidence(run_dir: Path) -> list[dict]:
    evidence_items = []
    for path in sorted((run_dir / "evidence").glob("*/*.json")):
        payload = read_json(path)
        if payload.get("status") == "ready":
            payload["_path"] = path
            evidence_items.append(payload)
    return evidence_items


def image_path_for(run_dir: Path, game_id: str, evidence: dict) -> Path | None:
    image_path = evidence.get("image_path")
    if image_path:
        return Path(image_path)
    source_path = run_dir / "sources" / game_id / "source.json"
    if not source_path.exists():
        return None
    source = read_json(source_path)
    return Path(source["screenshot_path"]) if source.get("screenshot_path") else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = args.run_dir.resolve()
    paths = make_run_paths(run_dir.parent, run_dir.name)
    paths.prompts.mkdir(parents=True, exist_ok=True)
    evidence_items = load_ready_evidence(run_dir)
    progress = Progress(len(evidence_items), "stage 2")

    for evidence in evidence_items:
        game_id = evidence["game_id"]
        evidence_mode = evidence["evidence_mode"]
        observations = evidence.get("observations") or []
        prompts = build_prompt_variants(
            game_id=game_id,
            trajectory=observations,
            available_actions=evidence.get("available_actions") or [],
            evidence_mode=evidence_mode,
            first_image_path=image_path_for(run_dir, game_id, evidence),
        )
        for prompt in prompts.values():
            input_mode = prompt["input_mode"]
            prompt_id = prompt["prompt_id"]
            prompt_path = paths.prompts / game_id / evidence_mode / input_mode / f"{prompt_id}.json"
            write_json(
                prompt_path,
                {
                    "run_id": evidence["run_id"],
                    "game_id": game_id,
                    "evidence_path": str(Path(evidence["_path"]).relative_to(run_dir)),
                    **prompt,
                },
            )
        progress.step(f"{game_id} {evidence_mode}")

    print(f"prompts: {paths.prompts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
