from __future__ import annotations

import json
import tempfile
from pathlib import Path

from avo.monitor_evolution import evolution_snapshot


def test_evolution_snapshot_reports_live_research_and_budgets() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        current = root / "x_0001"
        research = current / "research"
        sandbox = root / ".sandboxes" / "avo-player-x_0001-test"
        research.mkdir(parents=True)
        sandbox.mkdir(parents=True)
        (sandbox / "solver.py").write_text("pass\n", encoding="utf-8")
        (root / "evolution_config.json").write_text(
            json.dumps(
                {
                    "max_evaluations": 10,
                    "player": {"max_environment_steps": 300},
                    "fresh_solver_max_environment_steps": 1500,
                }
            ),
            encoding="utf-8",
        )
        (root / "lineage.json").write_text(
            json.dumps(
                {
                    "candidates": [{"candidate_id": "x_0001"}],
                    "evaluations": [],
                }
            ),
            encoding="utf-8",
        )
        events = [
            {"type": "episode_started"},
            {
                "type": "transition",
                "payload": {"after": {"progress": {"levels_completed": 2}}},
            },
        ]
        (research / "evidence.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n",
            encoding="utf-8",
        )

        snapshot = evolution_snapshot(root)

        assert snapshot["current"] == "x_0001"
        assert snapshot["phase"] == "research"
        assert snapshot["hypotheses_evaluated"] == 0
        assert snapshot["max_hypotheses"] == 10
        assert snapshot["research"]["actions"] == 1
        assert snapshot["research"]["budget"] == 300
        assert snapshot["research"]["levels"] == 2
        assert snapshot["solver"]["draft_present"] is True
        assert snapshot["fresh_evaluation"]["budget"] == 1500
