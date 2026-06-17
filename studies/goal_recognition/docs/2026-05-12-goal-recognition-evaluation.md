# Goal Recognition Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build side-quest tooling that asks LLMs to infer ARC-AGI-3 game goals from either one frame or ten random-action frames, then lets the user manually verify predictions and graph the results.

**Architecture:** Keep the experiment outside `client/` under `side_quests/`. Reuse the existing `ArcadeEnv`, `FrameData`, `LlmClient`, and terminal play helpers rather than adding a new ARC client. The two setup runners write the same `predictions.jsonl` shape so the review and report tools can stay simple.

**Tech Stack:** Python standard library, `argparse`, `json/jsonl`, existing `arc_agi`, current `client.arc` types/env plus `client.engine.llm_client`, optional `matplotlib` fallback-free SVG generation for the first graph.

---

## File Structure

- Create `side_quests/__init__.py`: marks the side experiment package.
- Create `side_quests/one_frame_goal_recognition/__init__.py`: package marker.
- Create `side_quests/one_frame_goal_recognition/prompt.py`: builds the one-frame LLM prompt.
- Create `side_quests/one_frame_goal_recognition/run.py`: CLI runner for reset -> one frame -> LLM prediction -> artifacts.
- Create `side_quests/ten_frame_goal_recognition/__init__.py`: package marker.
- Create `side_quests/ten_frame_goal_recognition/prompt.py`: builds the trajectory LLM prompt.
- Create `side_quests/ten_frame_goal_recognition/run.py`: CLI runner for reset -> random legal actions -> LLM prediction -> artifacts.
- Create `side_quests/goal_recognition_review/__init__.py`: package marker.
- Create `side_quests/goal_recognition_review/review.py`: CLI for manual verification while playing.
- Create `side_quests/goal_recognition_review/report.py`: CLI for CSV plus SVG graph from reviewed predictions.
- Create `tests/side_quests/test_one_frame_goal_recognition.py`: focused prompt/artifact tests for setup 1.
- Create `tests/side_quests/test_ten_frame_goal_recognition.py`: focused random trajectory/prompt tests for setup 2.
- Create `tests/side_quests/test_goal_recognition_review.py`: focused review/report data tests.

The two setup workers must not edit each other's directories or tests. The review/report task starts only after both runner artifacts follow the shared row format.

---

### Task 1: Package Scaffold

**Files:**
- Create: `side_quests/__init__.py`
- Create: `tests/side_quests/__init__.py`

- [ ] **Step 1: Create package markers**

Create `side_quests/__init__.py`:

```python
"""Side experiments that reuse the ARC client without changing the main agent."""
```

Create `tests/side_quests/__init__.py`:

```python
"""Tests for side quest experiment tooling."""
```

- [ ] **Step 2: Verify imports can resolve**

Run:

```bash
python -c "import side_quests; print(side_quests.__doc__)"
```

Expected: prints `Side experiments that reuse the ARC client without changing the main agent.`

- [ ] **Step 3: Commit scaffold**

```bash
git add side_quests/__init__.py tests/side_quests/__init__.py
git commit -m "chore: scaffold side quest package"
```

---

### Task 2: One-Frame Goal Recognition Runner

**Worker ownership:** Worker 1 only.

**Files:**
- Create: `side_quests/one_frame_goal_recognition/__init__.py`
- Create: `side_quests/one_frame_goal_recognition/prompt.py`
- Create: `side_quests/one_frame_goal_recognition/run.py`
- Create: `tests/side_quests/test_one_frame_goal_recognition.py`

- [ ] **Step 1: Write prompt tests**

Create `tests/side_quests/test_one_frame_goal_recognition.py`:

```python
import json
from pathlib import Path

from side_quests.one_frame_goal_recognition.prompt import build_prompt
from side_quests.one_frame_goal_recognition.run import (
    completed_game_ids,
    normalize_prediction,
    write_jsonl,
)


def test_one_frame_prompt_contains_grid_and_no_semantic_metadata() -> None:
    system, prompt = build_prompt(
        game_id="ls20",
        grid=[[0, 1], [2, 0]],
        available_actions=["ACTION1", "ACTION2"],
    )

    assert "goal recognition" in system.lower()
    assert "ls20" not in prompt
    assert "[0, 1]" in prompt
    assert "ACTION1" in prompt
    assert "game source" not in prompt.lower()


def test_normalize_prediction_preserves_expected_fields() -> None:
    prediction = normalize_prediction(
        {
            "goal_guess": "Reach the target.",
            "win_condition_guess": "Player overlaps target.",
            "key_objects": [{"value": 2, "role_guess": "player"}],
            "confidence": "0.7",
            "uncertainties": ["one frame only"],
            "extra": "ignored",
        }
    )

    assert prediction == {
        "goal_guess": "Reach the target.",
        "win_condition_guess": "Player overlaps target.",
        "key_objects": [{"value": 2, "role_guess": "player"}],
        "confidence": 0.7,
        "uncertainties": ["one frame only"],
    }


def test_completed_game_ids_reads_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    write_jsonl(path, {"game_id": "a", "prediction": {}})
    write_jsonl(path, {"game_id": "b", "prediction": {}})

    assert completed_game_ids(path) == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/side_quests/test_one_frame_goal_recognition.py -q
```

Expected: import failure because `side_quests.one_frame_goal_recognition` does not exist yet.

- [ ] **Step 3: Create one-frame prompt builder**

Create `side_quests/one_frame_goal_recognition/__init__.py`:

```python
"""One-frame ARC goal-recognition experiment."""
```

Create `side_quests/one_frame_goal_recognition/prompt.py`:

```python
from __future__ import annotations

from client.engine.utils import format_grid


def build_prompt(
    game_id: str,
    grid: list[list[int]],
    available_actions: list[str],
) -> tuple[str, str]:
    system = (
        "You are evaluating goal recognition in ARC-AGI-3 games. "
        "Infer the likely game goal only from the provided numeric frame."
    )
    prompt = (
        "You see one observation frame from an unknown ARC-AGI-3 game.\n"
        "Do not assume hidden source code, title semantics, README text, or known solutions.\n"
        "Numeric grid values are visual object/color ids, not labels.\n\n"
        f"Available actions: {', '.join(available_actions) or 'none'}\n"
        f"Frame:\n{format_grid(grid)}\n\n"
        "Return JSON only with this shape:\n"
        "{\n"
        '  "goal_guess": "short plain-English goal",\n'
        '  "win_condition_guess": "observable condition that would mean success",\n'
        '  "key_objects": [{"value": 2, "role_guess": "player"}],\n'
        '  "confidence": 0.0,\n'
        '  "uncertainties": ["what cannot be known from one frame"]\n'
        "}"
    )
    return system, prompt
```

- [ ] **Step 4: Create one-frame runner**

Create `side_quests/one_frame_goal_recognition/run.py`:

```python
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arc_agi import Arcade, OperationMode

from client.arc.arcade_env import ArcadeEnv
from client.engine.llm_client import Config, LlmClient
from client.engine.utils import last_grid
from side_quests.one_frame_goal_recognition.prompt import build_prompt


SETUP = "one_frame"
DEFAULT_BACKEND_URL = "https://three.arcprize.org"
DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts"


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-one-frame")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data) + "\n")


def completed_game_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        game_id = str(row.get("game_id", "")).strip()
        if game_id:
            completed.add(game_id)
    return completed


def normalize_prediction(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal_guess": str(data.get("goal_guess", "")).strip(),
        "win_condition_guess": str(data.get("win_condition_guess", "")).strip(),
        "key_objects": data.get("key_objects") if isinstance(data.get("key_objects"), list) else [],
        "confidence": float(data.get("confidence", 0.0) or 0.0),
        "uncertainties": data.get("uncertainties") if isinstance(data.get("uncertainties"), list) else [],
    }


def discover_games(backend_url: str, api_key: str) -> list[str]:
    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=backend_url,
        arc_api_key=api_key,
    )
    games = arcade.get_environments()
    return [str(getattr(game, "id", getattr(game, "game_id", game))) for game in games]


def selected_games(args: argparse.Namespace) -> list[str]:
    if args.game_id:
        return [args.game_id]
    if args.games != "all":
        return [item.strip() for item in args.games.split(",") if item.strip()]
    games = discover_games(args.backend_url, args.api_key)
    return games[: args.limit] if args.limit else games


def make_llm(args: argparse.Namespace) -> LlmClient:
    cfg = Config(
        game="goal_recognition",
        mode="goal_recognition",
        server_url=args.backend_url,
    )
    return LlmClient(cfg)


def run_game(game_id: str, args: argparse.Namespace, llm: LlmClient, frames_dir: Path) -> dict[str, Any]:
    env = ArcadeEnv(game_id=game_id, backend_url=args.backend_url, api_key=args.api_key)
    frame_data = env.reset()
    grid = last_grid(frame_data.frame)
    available_actions = [action.name for action in frame_data.available_actions]
    system, prompt = build_prompt(game_id, grid, available_actions)
    raw_response = llm.call_json(system, prompt, purpose=SETUP)
    prediction = normalize_prediction(raw_response)

    write_json(
        frames_dir / f"{game_id}.json",
        {
            "game_id": game_id,
            "setup": SETUP,
            "frames": [grid],
            "available_actions": available_actions,
            "guid": frame_data.guid,
        },
    )

    return {
        "game_id": game_id,
        "setup": SETUP,
        "frames_seen": 1,
        "actions_taken": [],
        "available_actions": available_actions,
        "state": frame_data.state.name,
        "levels_completed": frame_data.levels_completed,
        "win_levels": frame_data.win_levels,
        "prediction": prediction,
        "manual_verification": None,
        "raw_response": raw_response,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one-frame goal recognition.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default=os.getenv("ARC_API_KEY", ""))
    parser.add_argument("--games", default="all")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = utc_run_id()
    run_dir = args.out / run_id
    frames_dir = run_dir / "frames"
    predictions_path = run_dir / "predictions.jsonl"
    errors_path = run_dir / "errors.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    llm = make_llm(args)
    games = selected_games(args)
    done = completed_game_ids(predictions_path) if args.resume else set()
    write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "setup": SETUP,
            "backend_url": args.backend_url,
            "purpose": SETUP,
            "limit": args.limit,
            "games": games,
        },
    )

    for game_id in games:
        if game_id in done:
            continue
        try:
            row = run_game(game_id, args, llm, frames_dir)
            write_jsonl(predictions_path, row)
            print(f"saved {game_id}")
        except Exception as exc:
            write_jsonl(errors_path, {"game_id": game_id, "error": str(exc)})
            print(f"error {game_id}: {exc}", file=sys.stderr)

    print(f"predictions: {predictions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
python -m pytest tests/side_quests/test_one_frame_goal_recognition.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Run import smoke check**

Run:

```bash
python -m side_quests.one_frame_goal_recognition.run --help
```

Expected: argparse help prints without importing errors.

- [ ] **Step 7: Commit setup 1**

```bash
git add side_quests/one_frame_goal_recognition tests/side_quests/test_one_frame_goal_recognition.py
git commit -m "feat: add one-frame goal recognition runner"
```

---

### Task 3: Ten-Frame Random Goal Recognition Runner

**Worker ownership:** Worker 2 only.

**Files:**
- Create: `side_quests/ten_frame_goal_recognition/__init__.py`
- Create: `side_quests/ten_frame_goal_recognition/prompt.py`
- Create: `side_quests/ten_frame_goal_recognition/run.py`
- Create: `tests/side_quests/test_ten_frame_goal_recognition.py`

- [ ] **Step 1: Write trajectory tests**

Create `tests/side_quests/test_ten_frame_goal_recognition.py`:

```python
import random

from client.arc.types import ActionInput, FrameData, GameAction, GameState
from side_quests.ten_frame_goal_recognition.prompt import build_prompt
from side_quests.ten_frame_goal_recognition.run import choose_random_action, normalize_prediction


def frame_with_actions(actions: list[GameAction]) -> FrameData:
    return FrameData(
        frame=[[[0, 1], [2, 0]]],
        state=GameState.PLAYING,
        levels_completed=0,
        game_id="dummy",
        win_levels=1,
        guid="guid",
        full_reset=False,
        available_actions=actions,
        action_input=ActionInput(action=GameAction.RESET),
    )


def test_choose_random_action_excludes_reset_and_undo_when_other_actions_exist() -> None:
    action = choose_random_action(
        frame_with_actions([GameAction.RESET, GameAction.ACTION1, GameAction.ACTION7]),
        random.Random(1),
    )

    assert action == GameAction.ACTION1


def test_ten_frame_prompt_contains_actions_and_frames() -> None:
    system, prompt = build_prompt(
        game_id="ls20",
        trajectory=[
            {"action": "RESET", "grid": [[0, 1], [2, 0]]},
            {"action": "ACTION1", "grid": [[0, 1], [0, 2]]},
        ],
        available_actions=["ACTION1", "ACTION2"],
    )

    assert "goal recognition" in system.lower()
    assert "ls20" not in prompt
    assert "ACTION1" in prompt
    assert "[0, 1]" in prompt
    assert "trajectory" in prompt.lower()


def test_normalize_prediction_matches_shared_schema() -> None:
    prediction = normalize_prediction({"goal_guess": "Collect all dots.", "confidence": 1})

    assert prediction["goal_guess"] == "Collect all dots."
    assert prediction["win_condition_guess"] == ""
    assert prediction["key_objects"] == []
    assert prediction["confidence"] == 1.0
    assert prediction["uncertainties"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/side_quests/test_ten_frame_goal_recognition.py -q
```

Expected: import failure because `side_quests.ten_frame_goal_recognition` does not exist yet.

- [ ] **Step 3: Create ten-frame prompt builder**

Create `side_quests/ten_frame_goal_recognition/__init__.py`:

```python
"""Ten-random-frame ARC goal-recognition experiment."""
```

Create `side_quests/ten_frame_goal_recognition/prompt.py`:

```python
from __future__ import annotations

from client.engine.utils import format_grid


def build_prompt(
    game_id: str,
    trajectory: list[dict],
    available_actions: list[str],
) -> tuple[str, str]:
    system = (
        "You are evaluating goal recognition in ARC-AGI-3 games. "
        "Infer the likely game goal only from the provided random-action trajectory."
    )
    blocks = []
    for index, item in enumerate(trajectory):
        blocks.append(
            f"Observation {index}\n"
            f"Action before observation: {item['action']}\n"
            f"Frame:\n{format_grid(item['grid'])}"
        )
    prompt = (
        "You see a short random-action trajectory from an unknown ARC-AGI-3 game.\n"
        "Actions were random legal actions, not a solution attempt.\n"
        "Do not assume hidden source code, title semantics, README text, or known solutions.\n"
        "Numeric grid values are visual object/color ids, not labels.\n\n"
        f"Available actions after final observation: {', '.join(available_actions) or 'none'}\n\n"
        "Trajectory:\n"
        + "\n\n".join(blocks)
        + "\n\nReturn JSON only with this shape:\n"
        "{\n"
        '  "goal_guess": "short plain-English goal",\n'
        '  "win_condition_guess": "observable condition that would mean success",\n'
        '  "key_objects": [{"value": 2, "role_guess": "player"}],\n'
        '  "confidence": 0.0,\n'
        '  "uncertainties": ["what cannot be known from this random trajectory"]\n'
        "}"
    )
    return system, prompt
```

- [ ] **Step 4: Create ten-frame runner**

Create `side_quests/ten_frame_goal_recognition/run.py`:

```python
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arc_agi import Arcade, OperationMode

from client.arc.arcade_env import ArcadeEnv
from client.engine.llm_client import Config, LlmClient
from client.arc.types import FrameData, GameAction, GameState
from client.engine.utils import last_grid
from side_quests.ten_frame_goal_recognition.prompt import build_prompt


SETUP = "ten_frame_random"
DEFAULT_BACKEND_URL = "https://three.arcprize.org"
DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts"


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-ten-frame")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data) + "\n")


def completed_game_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        game_id = str(row.get("game_id", "")).strip()
        if game_id:
            completed.add(game_id)
    return completed


def normalize_prediction(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal_guess": str(data.get("goal_guess", "")).strip(),
        "win_condition_guess": str(data.get("win_condition_guess", "")).strip(),
        "key_objects": data.get("key_objects") if isinstance(data.get("key_objects"), list) else [],
        "confidence": float(data.get("confidence", 0.0) or 0.0),
        "uncertainties": data.get("uncertainties") if isinstance(data.get("uncertainties"), list) else [],
    }


def choose_random_action(frame_data: FrameData, rng: random.Random) -> GameAction | None:
    actions = [
        action
        for action in frame_data.available_actions
        if action not in {GameAction.RESET, GameAction.ACTION7}
    ]
    if not actions:
        actions = list(frame_data.available_actions)
    if not actions:
        return None
    return rng.choice(actions)


def discover_games(backend_url: str, api_key: str) -> list[str]:
    arcade = Arcade(
        operation_mode=OperationMode.ONLINE,
        arc_base_url=backend_url,
        arc_api_key=api_key,
    )
    games = arcade.get_environments()
    return [str(getattr(game, "id", getattr(game, "game_id", game))) for game in games]


def selected_games(args: argparse.Namespace) -> list[str]:
    if args.game_id:
        return [args.game_id]
    if args.games != "all":
        return [item.strip() for item in args.games.split(",") if item.strip()]
    games = discover_games(args.backend_url, args.api_key)
    return games[: args.limit] if args.limit else games


def make_llm(args: argparse.Namespace) -> LlmClient:
    cfg = Config(
        game="goal_recognition",
        mode="goal_recognition",
        server_url=args.backend_url,
    )
    return LlmClient(cfg)


def collect_trajectory(env: ArcadeEnv, steps: int, rng: random.Random) -> tuple[list[dict[str, Any]], list[str], FrameData]:
    frame_data = env.reset()
    trajectory = [{"action": "RESET", "grid": last_grid(frame_data.frame)}]
    actions_taken: list[str] = []

    for _ in range(steps):
        if frame_data.state in {GameState.WIN, GameState.GAME_OVER}:
            break
        action = choose_random_action(frame_data, rng)
        if action is None:
            break
        actions_taken.append(action.name)
        frame_data = env.step(action)
        trajectory.append({"action": action.name, "grid": last_grid(frame_data.frame)})

    return trajectory, actions_taken, frame_data


def run_game(game_id: str, args: argparse.Namespace, llm: LlmClient, frames_dir: Path) -> dict[str, Any]:
    rng = random.Random(args.seed + sum(ord(char) for char in game_id))
    env = ArcadeEnv(game_id=game_id, backend_url=args.backend_url, api_key=args.api_key)
    trajectory, actions_taken, frame_data = collect_trajectory(env, args.steps, rng)
    available_actions = [action.name for action in frame_data.available_actions]
    system, prompt = build_prompt(game_id, trajectory, available_actions)
    raw_response = llm.call_json(system, prompt, purpose=SETUP)
    prediction = normalize_prediction(raw_response)

    write_json(
        frames_dir / f"{game_id}.json",
        {
            "game_id": game_id,
            "setup": SETUP,
            "trajectory": trajectory,
            "actions_taken": actions_taken,
            "available_actions": available_actions,
            "guid": frame_data.guid,
        },
    )

    return {
        "game_id": game_id,
        "setup": SETUP,
        "frames_seen": len(trajectory),
        "actions_taken": actions_taken,
        "available_actions": available_actions,
        "state": frame_data.state.name,
        "levels_completed": frame_data.levels_completed,
        "win_levels": frame_data.win_levels,
        "prediction": prediction,
        "manual_verification": None,
        "raw_response": raw_response,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ten-random-frame goal recognition.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--api-key", default=os.getenv("ARC_API_KEY", ""))
    parser.add_argument("--games", default="all")
    parser.add_argument("--game-id")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = utc_run_id()
    run_dir = args.out / run_id
    frames_dir = run_dir / "frames"
    predictions_path = run_dir / "predictions.jsonl"
    errors_path = run_dir / "errors.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    llm = make_llm(args)
    games = selected_games(args)
    done = completed_game_ids(predictions_path) if args.resume else set()
    write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "setup": SETUP,
            "backend_url": args.backend_url,
            "purpose": SETUP,
            "limit": args.limit,
            "steps": args.steps,
            "seed": args.seed,
            "games": games,
        },
    )

    for game_id in games:
        if game_id in done:
            continue
        try:
            row = run_game(game_id, args, llm, frames_dir)
            write_jsonl(predictions_path, row)
            print(f"saved {game_id}")
        except Exception as exc:
            write_jsonl(errors_path, {"game_id": game_id, "error": str(exc)})
            print(f"error {game_id}: {exc}", file=sys.stderr)

    print(f"predictions: {predictions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
python -m pytest tests/side_quests/test_ten_frame_goal_recognition.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Run import smoke check**

Run:

```bash
python -m side_quests.ten_frame_goal_recognition.run --help
```

Expected: argparse help prints without importing errors.

- [ ] **Step 7: Commit setup 2**

```bash
git add side_quests/ten_frame_goal_recognition tests/side_quests/test_ten_frame_goal_recognition.py
git commit -m "feat: add ten-frame goal recognition runner"
```

---

### Task 4: Manual Review Tool

**Files:**
- Create: `side_quests/goal_recognition_review/__init__.py`
- Create: `side_quests/goal_recognition_review/review.py`
- Create: `tests/side_quests/test_goal_recognition_review.py`

- [ ] **Step 1: Write review data tests**

Create `tests/side_quests/test_goal_recognition_review.py` with the review tests first:

```python
import json
from pathlib import Path

from studies.goal_recognition.review.review import apply_verification, load_rows, write_rows


def test_apply_verification_sets_label_and_note() -> None:
    row = {"game_id": "ls20", "manual_verification": None}

    updated = apply_verification(row, label="correct", note="goal matched")

    assert updated["manual_verification"] == {
        "label": "correct",
        "note": "goal matched",
    }


def test_load_and_write_rows_round_trip_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    rows = [
        {"game_id": "a", "manual_verification": None},
        {"game_id": "b", "manual_verification": {"label": "wrong", "note": ""}},
    ]

    write_rows(path, rows)

    assert load_rows(path) == rows
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/side_quests/test_goal_recognition_review.py -q
```

Expected: import failure because `studies.goal_recognition.review` does not exist yet.

- [ ] **Step 3: Create review tool**

Create `side_quests/goal_recognition_review/__init__.py`:

```python
"""Manual review and reporting for goal-recognition experiments."""
```

Create `side_quests/goal_recognition_review/review.py`:

```python
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
        command = input("Verdict [c correct / w wrong / p partial / s skip / n note]: ").strip().lower()
        if command == "n":
            note = input("Note: ").strip()
            return "partial", note
        if command in LABELS:
            note = input("Note, optional: ").strip()
            return LABELS[command], note
        print("Use c, w, p, s, or n.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manually verify goal-recognition predictions.")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--backend-url", default="https://three.arcprize.org")
    parser.add_argument("--api-key", default=os.getenv("ARC_API_KEY", ""))
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = load_rows(args.predictions)
    out = args.out or args.predictions.with_name(args.predictions.stem + ".reviewed.jsonl")

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
        write_rows(out, reviewed + rows[len(reviewed):])

    write_rows(out, reviewed)
    print(f"reviewed predictions: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused review tests**

Run:

```bash
python -m pytest tests/side_quests/test_goal_recognition_review.py -q
```

Expected: review tests pass.

- [ ] **Step 5: Run review help smoke check**

Run:

```bash
python -m studies.goal_recognition.review.review --help
```

Expected: argparse help prints without importing errors.

---

### Task 5: Report Tool

**Files:**
- Modify: `side_quests/goal_recognition_review/report.py`
- Modify: `tests/side_quests/test_goal_recognition_review.py`

- [ ] **Step 1: Add report tests**

Append these tests to `tests/side_quests/test_goal_recognition_review.py`:

```python
from studies.goal_recognition.review.report import count_labels, svg_bar_chart


def test_count_labels_groups_by_setup_and_label() -> None:
    rows = [
        {"setup": "one_frame", "manual_verification": {"label": "correct"}},
        {"setup": "one_frame", "manual_verification": {"label": "wrong"}},
        {"setup": "ten_frame_random", "manual_verification": {"label": "partial"}},
    ]

    counts = count_labels(rows)

    assert counts["one_frame"]["correct"] == 1
    assert counts["one_frame"]["wrong"] == 1
    assert counts["ten_frame_random"]["partial"] == 1


def test_svg_bar_chart_contains_setup_labels() -> None:
    svg = svg_bar_chart(
        {
            "one_frame": {"correct": 2, "partial": 1, "wrong": 1, "skipped": 0},
            "ten_frame_random": {"correct": 3, "partial": 0, "wrong": 1, "skipped": 1},
        }
    )

    assert "<svg" in svg
    assert "one_frame" in svg
    assert "ten_frame_random" in svg
```

- [ ] **Step 2: Run tests to verify report imports fail**

Run:

```bash
python -m pytest tests/side_quests/test_goal_recognition_review.py -q
```

Expected: import failure for `studies.goal_recognition.review.report`.

- [ ] **Step 3: Create report tool**

Create `side_quests/goal_recognition_review/report.py`:

```python
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


LABELS = ["correct", "partial", "wrong", "skipped"]
COLORS = {
    "correct": "#2f9e44",
    "partial": "#f59f00",
    "wrong": "#e03131",
    "skipped": "#868e96",
}


def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def count_labels(rows: list[dict]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {label: 0 for label in LABELS})
    for row in rows:
        setup = str(row.get("setup") or "unknown")
        verification = row.get("manual_verification") or {}
        label = str(verification.get("label") or "skipped")
        if label not in LABELS:
            label = "skipped"
        counts[setup][label] += 1
    return dict(counts)


def write_csv(path: Path, counts: dict[str, dict[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["setup", *LABELS, "verified_total"])
        for setup, labels in sorted(counts.items()):
            verified_total = labels["correct"] + labels["partial"] + labels["wrong"]
            writer.writerow([setup, *[labels[label] for label in LABELS], verified_total])


def svg_bar_chart(counts: dict[str, dict[str, int]]) -> str:
    setups = sorted(counts)
    width = 760
    height = 120 + 70 * max(1, len(setups))
    left = 160
    bar_width = 420
    row_height = 55
    max_total = max((sum(counts[setup].values()) for setup in setups), default=1)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="20" y="32" font-family="Arial" font-size="20" font-weight="700">Goal Recognition Verification</text>',
    ]
    for row_index, setup in enumerate(setups):
        y = 70 + row_index * row_height
        x = left
        labels = counts[setup]
        total = sum(labels.values()) or 1
        lines.append(f'<text x="20" y="{y + 18}" font-family="Arial" font-size="14">{setup}</text>')
        for label in LABELS:
            value = labels[label]
            segment = int((value / max_total) * bar_width)
            if value:
                lines.append(f'<rect x="{x}" y="{y}" width="{segment}" height="24" fill="{COLORS[label]}"/>')
                lines.append(f'<text x="{x + 4}" y="{y + 17}" font-family="Arial" font-size="12" fill="white">{value}</text>')
            x += segment
        lines.append(f'<text x="{left + bar_width + 20}" y="{y + 18}" font-family="Arial" font-size="13">total {total}</text>')
    legend_x = 20
    legend_y = height - 30
    for label in LABELS:
        lines.append(f'<rect x="{legend_x}" y="{legend_y - 12}" width="12" height="12" fill="{COLORS[label]}"/>')
        lines.append(f'<text x="{legend_x + 18}" y="{legend_y - 2}" font-family="Arial" font-size="12">{label}</text>')
        legend_x += 100
    lines.append("</svg>")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report goal-recognition verification results.")
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=Path("side_quests/goal_recognition_review/report"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = load_rows(args.runs)
    counts = count_labels(rows)
    csv_path = args.out.with_suffix(".csv")
    svg_path = args.out.with_suffix(".svg")
    write_csv(csv_path, counts)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg_bar_chart(counts), encoding="utf-8")
    print(f"csv: {csv_path}")
    print(f"svg: {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run report/review tests**

Run:

```bash
python -m pytest tests/side_quests/test_goal_recognition_review.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run report help smoke check**

Run:

```bash
python -m studies.goal_recognition.review.report --help
```

Expected: argparse help prints without importing errors.

- [ ] **Step 6: Commit review/report**

```bash
git add side_quests/goal_recognition_review tests/side_quests/test_goal_recognition_review.py
git commit -m "feat: add goal recognition review and report tools"
```

---

### Task 6: Final Integration Check

**Files:**
- Inspect only unless a previous task missed a path.

- [ ] **Step 1: Run focused side quest tests**

Run:

```bash
python -m pytest tests/side_quests -q
```

Expected: all side quest tests pass.

- [ ] **Step 2: Run CLI help checks**

Run:

```bash
python -m side_quests.one_frame_goal_recognition.run --help
python -m side_quests.ten_frame_goal_recognition.run --help
python -m studies.goal_recognition.review.review --help
python -m studies.goal_recognition.review.report --help
```

Expected: each command prints argparse help and exits with status 0.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short --branch
```

Expected: branch is clean except for intentional uncommitted changes if the user explicitly requested no commit.

- [ ] **Step 4: Record any runtime limitation**

If `ARC_API_KEY` or `OPENROUTER_API_KEY` is missing, do not claim a live ARC/LLM run passed. State exactly which smoke checks passed and which live checks were skipped.
