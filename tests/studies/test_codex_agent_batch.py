import json
import tempfile
import unittest
from pathlib import Path

from studies.codex_agent.batch import RunSpec, build_specs, read_run_outcome


class CodexBatchTests(unittest.TestCase):
    def test_build_specs_creates_opaque_cross_product_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            specs = build_specs(
                models=["model-a", "model-b"],
                efforts=["low", "medium"],
                conditions=["baseline-plus"],
                repeats=2,
                output_root=Path(tmpdir),
            )

            self.assertEqual(len(specs), 8)
            self.assertEqual(specs[0].output_dir.name, "run-0001")
            self.assertEqual(specs[-1].output_dir.name, "run-0008")
            self.assertNotIn(specs[0].model, str(specs[0].output_dir))

    def test_read_run_outcome_merges_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir, "run-0001")
            output_dir.mkdir()
            Path(output_dir, "result.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "solved": True,
                        "action_count": 12,
                    }
                ),
                encoding="utf-8",
            )
            spec = RunSpec(1, "model-a", "low", "baseline-plus", 1, output_dir)

            outcome = read_run_outcome(spec, 0)

            self.assertTrue(outcome["solved"])
            self.assertEqual(outcome["action_count"], 12)
            self.assertEqual(outcome["model"], "model-a")


if __name__ == "__main__":
    unittest.main()
