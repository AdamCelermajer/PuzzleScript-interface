import tempfile
import unittest
from pathlib import Path

from client.engine.memory import EngineMemory
from client.engine.perception import EngineState, Perception
from client.engine.planner import Planner
from client.engine.rule_schema import CellCondition, CellEffect, GeneralizedRule
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
            llm = FakeLlm(
                [
                    {"subgoal": "compare the latest move"},
                    {"plan": ["ACTION4"]},
                ]
            )
            planner = Planner(memory=memory, rulebook=rulebook, llm_client=llm)

            decision = planner.choose_action()

            self.assertEqual(decision.action, GameAction.ACTION4)
            self.assertEqual(decision.reason, "explore_subgoal")
            self.assertTrue(decision.exploratory)
            self.assertEqual(
                llm.calls[0]["image_data_urls"],
                ["data:image/png;base64,before", "data:image/png;base64,after"],
            )
            self.assertEqual(
                llm.calls[1]["image_data_urls"],
                ["data:image/png;base64,before", "data:image/png;base64,after"],
            )
            self.assertEqual(llm.calls[0]["purpose"], "subgoal")
            self.assertEqual(llm.calls[1]["purpose"], "action plan")
            self.assertIn("Last memory transition", llm.calls[0]["prompt"])

    def test_planner_keeps_game_goal_when_llm_sets_subgoal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            memory.append_initial_state(perception.perceive(_frame([[2, 0]])))
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeLlm(
                [
                    {"subgoal": "move next to the box"},
                    {"plan": ["ACTION4"]},
                ]
            )
            planner = Planner(memory=memory, rulebook=rulebook, llm_client=llm)

            decision = planner.choose_action()

            self.assertEqual(decision.action, GameAction.ACTION4)
            self.assertEqual(planner.game_goal.kind, "game_goal")
            self.assertEqual(planner.active_plan.goal.kind, "subgoal")

    def test_llm_plan_continues_from_second_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            state = perception.perceive(
                _frame(
                    [[2, 0]],
                    available_actions=[GameAction.ACTION1, GameAction.ACTION4],
                )
            )
            memory.append_initial_state(state)
            rulebook = Rulebook(Path(tmpdir))
            llm = FakeLlm(
                [
                    {"subgoal": "try a two-step probe"},
                    {"plan": ["ACTION4", "ACTION1"]},
                ]
            )
            planner = Planner(memory=memory, rulebook=rulebook, llm_client=llm)

            first = planner.choose_action(current=state)
            second = planner.choose_action(current=state)

            self.assertEqual(first.action, GameAction.ACTION4)
            self.assertEqual(first.plan, [GameAction.ACTION4, GameAction.ACTION1])
            self.assertTrue(first.exploratory)
            self.assertEqual(second.action, GameAction.ACTION1)
            self.assertEqual(second.reason, "active_plan")
            self.assertTrue(second.exploratory)
            self.assertEqual(len(llm.calls), 2)

    def test_rule_plan_continues_from_second_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            perception = Perception()
            start = perception.perceive(
                _frame(
                    [[2, 0], [0, 0]],
                    available_actions=[GameAction.ACTION2, GameAction.ACTION4],
                )
            )
            middle = perception.perceive(
                _frame(
                    [[0, 2], [0, 0]],
                    available_actions=[GameAction.ACTION2, GameAction.ACTION4],
                )
            )
            memory = EngineMemory(Path(tmpdir) / "timeline.jsonl")
            memory.append_initial_state(start)
            rulebook = Rulebook(Path(tmpdir))
            rulebook.add_generalized_rule(
                GeneralizedRule(
                    id="G000001",
                    action="ACTION4",
                    anchor=2,
                    conditions=(
                        CellCondition(dx=0, dy=0, value=2),
                        CellCondition(dx=1, dy=0, value=0),
                    ),
                    effects=(
                        CellEffect(dx=0, dy=0, value=0),
                        CellEffect(dx=1, dy=0, value=2),
                    ),
                    evidence_ids=("T000001",),
                    summary="ACTION4 moves right into empty space.",
                )
            )
            rulebook.add_generalized_rule(
                GeneralizedRule(
                    id="G000002",
                    action="ACTION2",
                    anchor=2,
                    conditions=(
                        CellCondition(dx=0, dy=0, value=2),
                        CellCondition(dx=-1, dy=0, value=0),
                        CellCondition(dx=0, dy=1, value=0),
                    ),
                    effects=(
                        CellEffect(dx=0, dy=0, value=0),
                        CellEffect(dx=0, dy=1, value=2),
                    ),
                    evidence_ids=("T000002",),
                    summary="ACTION2 moves down into empty space and wins.",
                    result_state=GameState.WIN.value,
                    levels_completed=1,
                )
            )
            planner = Planner(memory=memory, rulebook=rulebook)

            first = planner.choose_action(current=start)
            second = planner.choose_action(current=middle)

            self.assertEqual(first.action, GameAction.ACTION4)
            self.assertEqual(first.reason, "rule_plan")
            self.assertEqual(first.plan, [GameAction.ACTION4, GameAction.ACTION2])
            self.assertEqual(second.action, GameAction.ACTION2)
            self.assertEqual(second.reason, "active_plan")
            self.assertFalse(second.exploratory)

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
