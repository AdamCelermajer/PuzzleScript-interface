import unittest

from client.arc.types import GameAction
from client.engine.goal_manager import GoalManager
from client.engine.perception import EngineState


def _state(grid: list[list[int]]) -> EngineState:
    return EngineState(
        grid=tuple(tuple(row) for row in grid),
        state="playing",
        levels_completed=0,
        win_levels=1,
        game_id="goal-manager-world",
        available_actions=(GameAction.ACTION1, GameAction.ACTION4),
    )


class FakeLlm:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def call_json(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> dict:
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "image_data_urls": list(image_data_urls or []),
                "purpose": purpose,
            }
        )
        if not self.payloads:
            raise AssertionError("Unexpected LLM call")
        return self.payloads.pop(0)


class GoalManagerTests(unittest.TestCase):
    def test_game_goal_and_subgoal_are_separate(self) -> None:
        manager = GoalManager()

        game_goal = manager.ensure_goal(None)
        subgoal = manager.set_subgoal("move next to the box")

        self.assertEqual(game_goal.description, "complete the level")
        self.assertEqual(game_goal.kind, "game_goal")
        self.assertEqual(subgoal.description, "move next to the box")
        self.assertEqual(subgoal.kind, "subgoal")
        self.assertIs(manager.game_goal, game_goal)
        self.assertIs(manager.subgoal, subgoal)

    def test_asks_llm_for_subgoal_then_action_plan(self) -> None:
        llm = FakeLlm(
            [
                {"subgoal": "move next to the box"},
                {"plan": ["ACTION4"]},
            ]
        )
        manager = GoalManager()

        goal = manager.ask_for_subgoal(
            llm_client=llm,
            current=_state([[2, 0]]),
            actions=[GameAction.ACTION1, GameAction.ACTION4],
            recent_events="Action: ACTION1",
            known_rules_text="- none",
            image_data_urls=["data:image/png;base64,before"],
        )
        plan = manager.ask_for_action_plan(
            llm_client=llm,
            current=_state([[2, 0]]),
            actions=[GameAction.ACTION1, GameAction.ACTION4],
            subgoal=goal,
            recent_events="Action: ACTION1",
            known_rules_text="- none",
            image_data_urls=["data:image/png;base64,before"],
        )

        self.assertEqual(goal.description, "move next to the box")
        self.assertEqual(goal.kind, "subgoal")
        self.assertEqual(plan, [GameAction.ACTION4])
        self.assertEqual(llm.calls[0]["purpose"], "subgoal")
        self.assertEqual(llm.calls[1]["purpose"], "action plan")
        self.assertIn("Choose the next subgoal", llm.calls[0]["prompt"])
        self.assertNotIn('"plan"', llm.calls[0]["system"])
        self.assertIn("Current subgoal: move next to the box", llm.calls[1]["prompt"])
        self.assertIn("Rendered image context is attached.", llm.calls[0]["prompt"])
        self.assertIn("Rendered image context is attached.", llm.calls[1]["prompt"])


if __name__ == "__main__":
    unittest.main()
