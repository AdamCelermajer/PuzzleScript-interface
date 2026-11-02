import base64
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from game.types import ActionInput, FrameData, GameAction, GameState, RenderedFrame
from frameworks.avo.core.framework import (
    Action,
    AvoLaboratory,
    Comparison,
    DeterministicSupervisor,
    Observation,
    Prediction,
)
from frameworks.avo.environments.puzzlescript.adapter import PuzzleScriptEnvironment


class TinyEnvironment:
    def __init__(self) -> None:
        self.value = 0

    def observation(self) -> Observation:
        return Observation(payload={"value": self.value}, available_actions=("ADD", "WAIT"))

    def reset(self) -> Observation:
        self.value = 0
        return self.observation()

    def step(self, action: Action) -> Observation:
        if action.id == "ADD":
            self.value += 1
        return self.observation()

    def compare(self, expected: Observation, actual: Observation) -> Comparison:
        exact = expected.payload == actual.payload
        return Comparison(exact, float(exact), 1, 1)


@dataclass
class AddTheory:
    candidate_id: str = "x_add"
    parent_id: str | None = None
    claim: str = "ADD increments the value"
    complexity: float = 0.1

    def predict(self, history, current, action) -> Prediction:
        value = current.payload["value"] + (1 if action.id == "ADD" else 0)
        return Prediction(Observation(payload={"value": value}, available_actions=current.available_actions))


@dataclass
class StaticTheory:
    candidate_id: str = "x_static"
    parent_id: str | None = None
    claim: str = "Nothing changes"
    complexity: float = 0.02

    def predict(self, history, current, action) -> Prediction:
        return Prediction(current)


class AvoFrameworkTests(unittest.TestCase):
    def test_freezes_predictions_before_transition_and_scores_them(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            lab = AvoLaboratory(TinyEnvironment(), [AddTheory(), StaticTheory()], output)
            lab.reset()
            result = lab.step(Action("ADD"))

            self.assertEqual(result.transition.after.payload, {"value": 1})
            self.assertTrue(result.evaluations[0].exact)
            self.assertFalse(result.evaluations[1].exact)
            records = [json.loads(line) for line in lab.store.path.read_text(encoding="utf-8").splitlines()]
            types = [record["type"] for record in records]
            self.assertLess(types.index("prediction_frozen"), types.index("transition"))
            self.assertIn("prediction_evaluated", types)

    def test_experiment_choice_prefers_candidate_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            lab = AvoLaboratory(TinyEnvironment(), [AddTheory(), StaticTheory()], output)
            lab.reset()
            choice = lab.choose_experiment([Action("WAIT"), Action("ADD")])
            self.assertEqual(choice.action.id, "ADD")
            self.assertGreater(choice.disagreement, 0)

    def test_supervisor_redirects_repeated_no_change(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            lab = AvoLaboratory(
                TinyEnvironment(),
                [StaticTheory()],
                output,
                supervisor=DeterministicSupervisor(no_change_limit=2),
            )
            lab.reset()
            lab.step(Action("WAIT"))
            result = lab.step(Action("WAIT"))
            self.assertEqual(result.supervisor_events[0].code, "repeated_no_change")

    def test_puzzlescript_adapter_preserves_contract_without_a_legend(self) -> None:
        frame = FrameData(
            frame=[[[1, 2], [0, 3]]],
            state=GameState.PLAYING,
            levels_completed=0,
            game_id="secret-game-id",
            win_levels=1,
            guid="secret-guid",
            full_reset=True,
            available_actions=[GameAction.ACTION1, GameAction.ACTION5],
            action_input=ActionInput(GameAction.RESET),
            legend={1: "wall"},
        )
        observation = PuzzleScriptEnvironment.from_frame(frame)
        self.assertEqual(observation.payload, {"frame": frame.frame})
        self.assertEqual(observation.available_actions, ("ACTION1", "ACTION5"))
        self.assertNotIn("legend", observation.metadata)
        self.assertNotIn("game_id", observation.metadata)

    def test_puzzlescript_final_png_is_saved_and_referenced_without_base64_logs(self) -> None:
        png = b"\x89PNG\r\n\x1a\nfinal-frame"
        frame = FrameData(
            frame=[[[1]]],
            state=GameState.PLAYING,
            levels_completed=0,
            game_id="secret-game-id",
            win_levels=1,
            guid="secret-guid",
            full_reset=True,
            available_actions=[GameAction.ACTION1],
            action_input=ActionInput(GameAction.RESET),
            rendered_frame=RenderedFrame(
                mime_type="image/png",
                data_url="data:image/png;base64,"
                + base64.b64encode(png).decode("ascii"),
                width=45,
                height=45,
            ),
        )

        class RenderedEnvironment:
            def reset(self) -> FrameData:
                return frame

            def step(self, action: GameAction, data=None) -> FrameData:
                return frame

        with tempfile.TemporaryDirectory() as output:
            environment = PuzzleScriptEnvironment(RenderedEnvironment())
            lab = AvoLaboratory(environment, [], output)
            observation = lab.reset()
            rendered = observation.metadata["rendered_frame"]
            saved = Path(rendered["path"])
            transition = lab.step(Action("ACTION1")).transition

            self.assertEqual(saved.read_bytes(), png)
            self.assertEqual(rendered["artifact_path"], "frames/observation_000001.png")
            self.assertEqual(rendered["width"], 45)
            self.assertEqual(rendered["height"], 45)
            self.assertEqual(
                transition.after.metadata["rendered_frame"]["artifact_path"],
                "frames/observation_000002.png",
            )
            self.assertEqual(lab.history[0], transition)
            evidence = lab.store.path.read_text(encoding="utf-8")
            self.assertIn(str(saved).replace("\\", "\\\\"), evidence)
            self.assertNotIn("data:image/png;base64", evidence)


if __name__ == "__main__":
    unittest.main()
