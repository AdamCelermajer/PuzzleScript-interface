from __future__ import annotations

import json
import sys
import textwrap
from argparse import ArgumentParser
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.arc.arcade_env import ArcadeEnv
from avo.core.framework import Action, AvoLaboratory
from avo.environments.puzzlescript.adapter import PuzzleScriptEnvironment
from avo.legacy.agentic import AgentDecision, AgenticVariationRunner, SearchBudget


class DemoResearchAgent:
    """A deterministic stand-in that exercises the same contract as the future LLM."""

    def __init__(self, action: str) -> None:
        self.action = action

    @staticmethod
    def _write_package(root: Path, manifest: dict, source: str) -> None:
        package = root / manifest["candidate_id"]
        package.mkdir(parents=True, exist_ok=True)
        package.joinpath("manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        package.joinpath("predict.py").write_text(
            textwrap.dedent(source).strip() + "\n",
            encoding="utf-8",
        )

    def decide(self, context) -> AgentDecision:
        common = {
            "schema_version": 1,
            "complexity": 0.05,
            "command": ["$PYTHON", "predict.py"],
        }
        self._write_package(
            context.workspace,
            {
                **common,
                "candidate_id": "x_static",
                "parent_id": None,
                "claim": "The selected action leaves the observation unchanged.",
            },
            """
            import json, sys
            request = json.load(sys.stdin)
            json.dump({
                "protocol": "avo-theory-prediction-v1",
                "expected": request["current"],
                "confidence": 0.55,
                "rationale": "minimal null model"
            }, sys.stdout)
            """,
        )
        self._write_package(
            context.workspace,
            {
                **common,
                "candidate_id": "x_terminal",
                "parent_id": "x_static",
                "claim": "The selected action leaves the frame unchanged and reaches WIN.",
            },
            """
            import json, sys
            request = json.load(sys.stdin)
            expected = request["current"]
            expected["status"] = "WIN"
            json.dump({
                "protocol": "avo-theory-prediction-v1",
                "expected": expected,
                "confidence": 0.25,
                "rationale": "competing terminal hypothesis"
            }, sys.stdout)
            """,
        )
        return AgentDecision(
            action=Action(self.action),
            rationale="Execute one discriminating environment probe.",
        )


def main() -> None:
    parser = ArgumentParser(description="Run one auditable agentic cycle against PuzzleScript")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--game-id", default="ps_sokoban_basic-v1")
    parser.add_argument("--action", default="ACTION1")
    parser.add_argument("--output-dir", default="avo/output/legacy-lab-demo")
    args = parser.parse_args()

    output = Path(args.output_dir)
    laboratory = AvoLaboratory(
        environment=PuzzleScriptEnvironment(
            ArcadeEnv(game_id=args.game_id, backend_url=args.backend_url)
        ),
        candidates=[],
        evidence_dir=output,
    )
    result = AgenticVariationRunner(
        laboratory=laboratory,
        agent=DemoResearchAgent(args.action),
        candidate_workspace=output / "candidates",
        budget=SearchBudget(max_decisions=1, max_environment_steps=1),
    ).run()
    cycle = result.cycles[0]

    summary = {
        "control": "agent created candidates and selected the probe",
        "candidates_created": result.candidates_created,
        "executed_action": cycle.transition.action.id,
        "initial_fingerprint": cycle.transition.before.fingerprint,
        "actual_fingerprint": cycle.transition.after.fingerprint,
        "evaluations": [
            {
                "candidate": evaluation.candidate_id,
                "exact": evaluation.exact,
                "prospective_accuracy": evaluation.prospective_accuracy,
                "status_accuracy": evaluation.status_accuracy,
            }
            for evaluation in cycle.evaluations
        ],
        "stop_reason": result.stop_reason,
        "evidence_path": str(laboratory.store.path.resolve()),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
