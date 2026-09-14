import base64
import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from client.arc.types import ActionInput, FrameData, GameAction, GameState, RenderedFrame
from studies.codex_agent.runner import CodexAgentRunner


def _frame(
    grid: list[list[int]],
    *,
    state: GameState = GameState.PLAYING,
    levels_completed: int = 0,
    action: GameAction = GameAction.RESET,
    image: bool = False,
) -> FrameData:
    rendered = None
    if image:
        rendered = RenderedFrame(
            mime_type="image/png",
            data_url="data:image/png;base64," + base64.b64encode(b"png").decode(),
        )
    return FrameData(
        frame=[grid],
        state=state,
        levels_completed=levels_completed,
        game_id="codex-test-world",
        win_levels=1,
        guid="codex-test-world",
        full_reset=(action == GameAction.RESET),
        available_actions=[
            GameAction.ACTION1,
            GameAction.ACTION2,
            GameAction.ACTION3,
            GameAction.ACTION4,
        ],
        action_input=ActionInput(action=action),
        rendered_frame=rendered,
    )


@dataclass
class FakeEnv:
    reset_frame: FrameData
    step_frames: list[FrameData]
    step_actions: list[GameAction] = field(default_factory=list)

    def reset(self) -> FrameData:
        return self.reset_frame

    def step(self, action: GameAction) -> FrameData:
        self.step_actions.append(action)
        return self.step_frames[len(self.step_actions) - 1]


class FakeSession:
    def __init__(self, responses: list[dict[str, str]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def next_action(self, prompt: str, image_path=None) -> dict[str, str]:
        self.calls.append({"prompt": prompt, "image_path": image_path})
        return self.responses.pop(0)


class CodexAgentTests(unittest.TestCase):
    def test_grid_encoding_instructions_are_only_given_for_hex_projection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            frame = _frame([[0, 0], [1, 2]])
            runner = CodexAgentRunner(FakeEnv(frame, []), FakeSession([]), tmpdir, max_steps=1)
            self.assertNotIn("2x2", runner._turn_prompt(frame, "", initial=True))
            frame.projection = {"mode": "visible-cell-v1"}
            prompt = runner._turn_prompt(frame, "", initial=True)
            self.assertIn("identical rendered textures", prompt)
            self.assertIn("Hidden object differences are not encoded", prompt)
            self.assertNotIn("4096", prompt)
            frame.projection = {"mode": "visible-cell-hex-v2"}
            self.assertIn("4096*a+256*b+16*c+d", runner._turn_prompt(frame, "", initial=True))
            frame.projection = {"mode": "object-cell-v1"}
            prompt = runner._turn_prompt(frame, "", initial=True)
            self.assertIn("one cell per visible game tile", prompt)
            self.assertNotIn("4096", prompt)

    def test_one_persistent_session_receives_each_frame_and_solves(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0, 0]], image=True),
                step_frames=[
                    _frame([[0, 2, 0]], action=GameAction.ACTION4, image=True),
                    _frame(
                        [[0, 0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                        image=True,
                    ),
                ],
            )
            session = FakeSession(
                [
                    {"action": "ACTION4", "note": "move right"},
                    {"action": "ACTION4", "note": "continue right"},
                ]
            )

            result = CodexAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=5,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(
                result.actions,
                [GameAction.ACTION4, GameAction.ACTION4],
            )
            self.assertEqual(len(session.calls), 2)
            self.assertIn("Solve this unknown puzzle game", session.calls[0]["prompt"])
            self.assertNotIn("Solve this unknown puzzle game", session.calls[1]["prompt"])
            for call in session.calls:
                self.assertNotIn("codex-test-world", call["prompt"])
                self.assertNotIn("game_id=", call["prompt"])
                self.assertNotIn("ACTION1=Up", call["prompt"])
            self.assertIn("Previous action ACTION4", session.calls[1]["prompt"])
            self.assertTrue(Path(session.calls[0]["image_path"]).exists())
            self.assertTrue(Path(session.calls[1]["image_path"]).exists())

            transcript = [
                json.loads(line)
                for line in result.transcript_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(transcript), 2)
            self.assertEqual(transcript[0]["response"]["action"], "ACTION4")
            self.assertTrue(transcript[0]["result"]["changed"])
            transitions = [
                json.loads(line)
                for line in result.transitions_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(len(transitions), 2)
            self.assertEqual(transitions[-1]["after"]["state"], "WIN")
            self.assertEqual(transitions[-1]["after"]["grid"], [[0, 0, 2]])
            self.assertEqual(
                transitions[0]["changed_cells"],
                [
                    {"row": 0, "col": 0, "before": 2, "after": 0},
                    {"row": 0, "col": 1, "before": 0, "after": 2},
                ],
            )

    def test_finish_is_rejected_until_environment_reports_win(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0]]),
                step_frames=[
                    _frame(
                        [[0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                    )
                ],
            )
            session = FakeSession(
                [
                    {"action": "FINISH", "note": "done"},
                    {"action": "ACTION4", "note": "move"},
                ]
            )

            result = CodexAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=2,
                max_decisions=2,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(env.step_actions, [GameAction.ACTION4])
            self.assertIn("FINISH was rejected", session.calls[1]["prompt"])


class ContinuationTests(unittest.TestCase):
    def test_restore_does_not_consume_additional_budget(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            parent = root / "parent"
            parent.mkdir()
            before = {"grid": [[2, 0, 0]], "state": "PLAYING", "levels_completed": 0, "win_levels": 1}
            after = {**before, "grid": [[0, 2, 0]]}
            (parent / "result.json").write_text(json.dumps({"solved": False, "reason": "step_budget_exhausted", "action_count": 1}))
            (parent / "transitions.jsonl").write_text(json.dumps({"action_index": 1, "action": "ACTION4", "before": before, "after": after}) + "\n")
            env = FakeEnv(_frame(before["grid"]), [
                _frame(after["grid"]), _frame([[0, 0, 2]], state=GameState.WIN, levels_completed=1)
            ])
            session = FakeSession([{"action": "ACTION4", "note": ""}])
            result = CodexAgentRunner(env, session, root / "child", max_steps=1, continuation_from=parent).run()
            self.assertTrue(result.solved)
            self.assertEqual(len(result.actions), 1)
            self.assertEqual(len(env.step_actions), 2)
            self.assertIn("new-session continuation after 1 prior game actions", session.calls[0]["prompt"])
            restoration = json.loads((root / "child/restoration.json").read_text())
            self.assertTrue(restoration["all_transitions_verified"])
            self.assertFalse(restoration["same_codex_conversation"])

    def test_mismatched_replay_is_rejected(self):
        from studies.codex_agent.continuation import restore_game
        env = FakeEnv(_frame([[2, 0]]), [_frame([[2, 0]])])
        history = [{"action_index": 1, "action": "ACTION4", "before": {"grid": [[2, 0]]},
                    "after": {"grid": [[0, 2]], "state": "PLAYING", "levels_completed": 0, "win_levels": 1}}]
        with self.assertRaisesRegex(ValueError, "Restoration mismatch"):
            restore_game(env, env.reset(), history)

    def test_only_note_files_are_carried_over(self):
        from studies.codex_agent.continuation import seed_notes
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "parent/workspace"
            source.mkdir(parents=True)
            (source / "strategy.md").write_text("learned plan")
            (source / "tool_calls.jsonl").write_text("private log")
            seed_notes(root / "parent", root / "child")
            self.assertEqual((root / "child/strategy.md").read_text(), "learned plan")
            self.assertFalse((root / "child/tool_calls.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
