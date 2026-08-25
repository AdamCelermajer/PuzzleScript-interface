import unittest

from avo.core.framework import Action, Observation, Transition
from avo.core.profile import resolve_profile_manifest
from avo.environments.puzzlescript.profile import PuzzleScriptProfile


class PuzzleScriptProfileTests(unittest.TestCase):
    def test_bundled_profile_is_resolvable(self) -> None:
        manifest = resolve_profile_manifest("puzzlescript")
        self.assertEqual(manifest.name, "profile.toml")
        self.assertEqual(manifest.parent.name, "puzzlescript")

    def test_fitness_is_success_then_action_cost(self) -> None:
        profile = PuzzleScriptProfile(environment=None)  # type: ignore[arg-type]
        before = Observation(payload={}, status="PLAYING")
        won = Observation(
            payload={},
            status="WIN",
            progress={"levels_completed": 2, "win_levels": 2},
        )
        transition = Transition(1, before, Action("A1"), won)
        result = profile.evaluate((transition,), won)

        self.assertTrue(result.terminal)
        self.assertTrue(result.success)
        self.assertEqual(result.score["success"], 1)
        self.assertEqual(result.score["levels_completed"], 2)
        self.assertEqual(result.score["environment_actions"], 1)

    def test_stopping_while_playing_is_not_success(self) -> None:
        profile = PuzzleScriptProfile(environment=None)  # type: ignore[arg-type]
        playing = Observation(
            payload={},
            status="PLAYING",
            progress={"levels_completed": 1, "win_levels": 2},
        )
        result = profile.evaluate((), playing)

        self.assertFalse(result.terminal)
        self.assertFalse(result.success)
        self.assertEqual(result.score["success"], 0)


if __name__ == "__main__":
    unittest.main()
