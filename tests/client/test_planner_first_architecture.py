import tempfile
import unittest
from pathlib import Path

from client.engine.memory import EngineMemory
from client.engine.perception import EngineState, Perception
from client.engine.planner import Planner
from client.engine.rulebook import Rulebook
from client.arc.types import (
    ActionInput,
    FrameData,
    GameAction,
    GameState,
    RenderedFrame,
)


def _frame(
    grid: list[list[int]],
    *,
    image_url: str = "",
    available_actions: list[GameAction] | None = None,
) -> FrameData:
    return FrameData(
        frame=[grid],
        state=GameState.PLAYING,
        levels_completed=0,
        game_id="planner-first-world",
        win_levels=1,
        guid="planner-first-world",
        full_reset=False,
        available_actions=available_actions or [GameAction.ACTION4],
        action_input=ActionInput(action=GameAction.ACTION4),
        legend={},
        rendered_frame=RenderedFrame("image/png", image_url) if image_url else None,
    )


class FakeLlm:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
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
        return self.payload


class PlannerFirstArchitectureTests(unittest.TestCase):
    def test_perception_preserves_optional_image_without_changing_logical_equality(
        self,
    ) -> None:
        perception = Perception()

        first = perception.perceive(_frame([[2, 0]], image_url="data:image/png;base64,a"))
        second = perception.perceive(
            _frame([[2, 0]], image_url="data:image/png;base64,b")
        )

        self.assertEqual(first.image.data_url, "data:image/png;base64,a")
        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))

    def test_memory_timeline_is_canonical_and_transitions_are_derived(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            before = perception.perceive(_frame([[2, 0]]))
            after = perception.perceive(_frame([[0, 2]]))

            memory.append_initial_state(before)
            transition = memory.append_action_result(GameAction.ACTION4, after)

            self.assertEqual([item.kind for item in memory.timeline], ["state", "action", "state"])
            self.assertEqual(memory.current_state(), after)
            self.assertEqual(transition.id, "T000001")
            self.assertEqual(memory.recent_transitions(1), [transition])
            self.assertEqual(memory.transition_by_id("T000001"), transition)

    def test_planner_starts_from_memory_and_attaches_memory_images_to_probe(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            before = perception.perceive(
                _frame([[2, 0]], image_url="data:image/png;base64,before")
            )
            after = perception.perceive(
                _frame([[0, 2]], image_url="data:image/png;base64,after")
            )
            memory.append_initial_state(before)
            memory.append_action_result(GameAction.ACTION4, after)
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeLlm({"subgoal": "compare the latest move", "plan": ["ACTION4"]})
            planner = Planner(memory=memory, rulebook=rulebook, llm_client=llm)

            decision = planner.choose_action()

            self.assertEqual(decision.action, GameAction.ACTION4)
            self.assertEqual(decision.reason, "explore_subgoal")
            self.assertTrue(decision.exploratory)
            self.assertEqual(
                llm.calls[0]["image_data_urls"],
                ["data:image/png;base64,before", "data:image/png;base64,after"],
            )
            self.assertEqual(llm.calls[0]["purpose"], "subgoal/action")
            self.assertIn("Last memory transition", llm.calls[0]["prompt"])

    def test_planner_keeps_game_goal_when_llm_sets_subgoal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            memory.append_initial_state(perception.perceive(_frame([[2, 0]])))
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeLlm({"subgoal": "move next to the box", "plan": ["ACTION4"]})
            planner = Planner(memory=memory, rulebook=rulebook, llm_client=llm)

            decision = planner.choose_action()

            self.assertEqual(decision.action, GameAction.ACTION4)
            self.assertEqual(planner.game_goal.kind, "game_goal")
            self.assertEqual(planner.active_plan.goal.kind, "subgoal")

    def test_planner_rejects_missing_available_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            state = EngineState(
                grid=((2, 0),),
                state=GameState.PLAYING,
                levels_completed=0,
                win_levels=1,
                game_id="planner-first-world",
                available_actions=(),
            )
            memory.append_initial_state(state)
            planner = Planner(memory=memory, rulebook=Rulebook(Path(tmpdir)))

            with self.assertRaisesRegex(ValueError, "No available actions"):
                planner.choose_action(current=state)


if __name__ == "__main__":
    unittest.main()
