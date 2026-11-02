import json
import tempfile
import unittest
from pathlib import Path

from client.arc.types import GameAction, GameState
from client.engine.memory import EngineMemory
from client.engine.perception import EngineState
from client.engine.plan_history import PlanHistory, backfill_plan_history


def state(column: int) -> EngineState:
    grid = [0, 0, 0, 0]
    grid[column] = 2
    return EngineState(
        grid=(tuple(grid),),
        state=GameState.PLAYING,
        levels_completed=0,
        win_levels=1,
        game_id="plan-history-test",
    )


class PlanHistoryTests(unittest.TestCase):
    def test_raw_log_backfill_maps_multi_step_plan_to_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            memory.append_initial_state(state(0))
            memory.append_action_result(
                GameAction.ACTION4,
                state(1),
                decision_source="explore_subgoal",
            )
            memory.append_action_result(
                GameAction.ACTION4,
                state(2),
                decision_source="active_plan",
            )
            (base / "llm_attempt.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "purpose": "subgoal",
                                "parsed_response": {
                                    "subgoal": "move right twice"
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "purpose": "action plan",
                                "parsed_response": {
                                    "plan": ["ACTION4", "ACTION4"]
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            history = backfill_plan_history(
                base / "plan.json",
                base / "llm_attempt.jsonl",
                memory,
            )
            steps = history.replay_steps(memory)

            self.assertEqual(history.changes[0].transition_id, "T000001")
            self.assertEqual(steps["S000002"]["step_index"], 1)
            self.assertEqual(steps["S000003"]["step_index"], 2)

    def test_replay_does_not_continue_plan_across_other_decision_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            memory = EngineMemory(base / "timeline.jsonl")
            memory.append_initial_state(state(0))
            memory.append_action_result(
                GameAction.ACTION4,
                state(1),
                decision_source="explore_subgoal",
            )
            memory.append_action_result(
                GameAction.ACTION4,
                state(2),
                decision_source="rule_plan",
            )
            memory.append_action_result(
                GameAction.ACTION4,
                state(3),
                decision_source="active_plan",
            )
            history = PlanHistory(base / "plan.json", create=True)
            history.record_change(
                "T000001",
                "move right three times",
                ["ACTION4", "ACTION4", "ACTION4"],
            )

            steps = history.replay_steps(memory)

            self.assertIn("S000002", steps)
            self.assertNotIn("S000003", steps)
            self.assertNotIn("S000004", steps)


if __name__ == "__main__":
    unittest.main()
