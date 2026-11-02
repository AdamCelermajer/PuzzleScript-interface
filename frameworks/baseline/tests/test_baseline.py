import base64
import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from game.types import ActionInput, FrameData, GameAction, GameState, RenderedFrame
from frameworks import world_model
from frameworks.baseline.runner import CodexAgentRunner
from frameworks.baseline import prompt as baseline_prompt
from frameworks.baseline.session import CliGameSession, GameSessionConfig, game_instructions


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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class CodexAgentTests(unittest.TestCase):
    def test_unusable_reply_gets_corrected_without_advancing_the_game(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            frame = _frame([[2, 0]], image=True)
            env = FakeEnv(frame, [_frame([[0, 2]], state=GameState.WIN, levels_completed=1)])
            session = FakeSession([ValueError("No action in reply"), {"action": "ACTION4", "note": "move"}])
            result = CodexAgentRunner(env, session, tmpdir, max_steps=1).run()
            self.assertTrue(result.solved)
            self.assertEqual(env.step_actions, [GameAction.ACTION4])
            self.assertEqual(result.decisions, 2)
            self.assertIn("The game has not advanced", session.calls[1]["prompt"])
            self.assertEqual(Path(session.calls[0]["image_path"]).read_bytes(), Path(session.calls[1]["image_path"]).read_bytes())

    def test_reset_is_an_available_action_that_costs_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [_frame([[0, 2]], state=GameState.WIN, levels_completed=1)])
            session = FakeSession([{"action": "RESET"}, {"action": "ACTION4"}])
            result = CodexAgentRunner(env, session, tmpdir, max_steps=5).run()
            self.assertIn("available_actions=ACTION1, ACTION2, ACTION3, ACTION4, RESET", session.calls[0]["prompt"])
            self.assertTrue(session.calls[1]["prompt"].startswith("Last action: RESET: nothing changed"))
            self.assertEqual(result.actions, [GameAction.RESET, GameAction.ACTION4])
            self.assertEqual(env.step_actions, [GameAction.ACTION4])  # RESET went to env.reset()

    def test_grid_encoding_instructions_are_only_given_for_hex_projection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            frame = _frame([[0, 0], [1, 2]])
            runner = CodexAgentRunner(FakeEnv(frame, []), FakeSession([]), tmpdir, max_steps=1)
            self.assertNotIn("2x2", runner._turn_prompt(frame, "", "", initial=True))
            frame.projection = {"mode": "visible-cell-v1"}  # the default: the system prompt explains it
            prompt = runner._turn_prompt(frame, "", "", initial=True)
            self.assertNotIn("Grid encoding", prompt)
            self.assertNotIn("Hidden object differences", prompt)
            frame.projection = {"mode": "visible-cell-hex-v2"}
            self.assertIn("4096*a+256*b+16*c+d", runner._turn_prompt(frame, "", "", initial=True))
            frame.projection = {"mode": "object-cell-v1"}
            prompt = runner._turn_prompt(frame, "", "", initial=True)
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
            self.assertTrue(session.calls[0]["prompt"].startswith("Play the game now. You have 5 actions."))
            self.assertNotIn("Play the game now", session.calls[1]["prompt"])
            for call in session.calls:
                self.assertNotIn("codex-test-world", call["prompt"])
                self.assertNotIn("game_id=", call["prompt"])
                self.assertNotIn("ACTION1=Up", call["prompt"])
            self.assertTrue(session.calls[1]["prompt"].startswith("Last action: ACTION4: changed (0,0) 2->0"))
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

    def test_player_keeps_notes_world_model_which_is_copied_and_reported(self) -> None:
        class ModelKeepingSession(FakeSession):
            def __init__(self, responses, workspace: Path) -> None:
                super().__init__(responses)
                self.world_model_path = workspace / "notes" / "world_model.md"
                self.world_model_path.parent.mkdir(parents=True)

            def next_action(self, prompt: str, image_path=None) -> dict[str, str]:
                self.world_model_path.write_text(f"belief {len(self.calls) + 1}", encoding="utf-8")
                return super().next_action(prompt, image_path)

            def final_world_model(self, **game_end) -> Path:
                self.game_end = game_end
                self.world_model_path.write_text("final report", encoding="utf-8")
                return self.world_model_path

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(world_model, "EVERY", 1):
            root = Path(tmpdir)
            env = FakeEnv(
                reset_frame=_frame([[2, 0, 0]]),
                step_frames=[
                    _frame([[0, 2, 0]], action=GameAction.ACTION4),
                    _frame([[0, 0, 2]], state=GameState.WIN, levels_completed=1, action=GameAction.ACTION4),
                ],
            )
            session = ModelKeepingSession([{"action": "ACTION4", "note": ""}] * 2, root / "ws")
            result = CodexAgentRunner(env=env, session=session, output_dir=root / "out", max_steps=5).run()

            copies = root / "out" / "world_model_snapshots"
            self.assertEqual(sorted(p.name for p in copies.iterdir()),
                             ["a0001.md", "a0002.md", "final.md", "level-1-a0002.md"])
            # Copied after the turn that follows each snapshot point; nobody asks for it during play.
            self.assertFalse(any("World model" in call["prompt"] for call in session.calls))
            self.assertEqual(session.game_end, {"reason": "task_goal_reached", "levels": 1, "total": 1})
            self.assertEqual((copies / "a0001.md").read_text(encoding="utf-8"), "belief 2")
            # No turn followed the winning action: the final report is that update.
            self.assertEqual((copies / "level-1-a0002.md").read_text(encoding="utf-8"), "final report")
            self.assertEqual(result.world_model_path, root / "out" / "world_model.md")
            self.assertEqual(result.world_model_path.read_text(encoding="utf-8"), "final report")
            self.assertEqual((copies / "final.md").read_text(encoding="utf-8"), "final report")

    def test_turn_based_prompt_is_the_agentic_one_but_for_the_line_on_moves(self) -> None:
        self.assertEqual(game_instructions(True), baseline_prompt.SYSTEM_PROMPT
                         + "Each turn you get one observation. Submit one action with: python act.py ACTION")
        self.assertTrue(game_instructions(True, tools=True).endswith("Submit one action with the act tool."))
        shared = baseline_prompt.SYSTEM_PROMPT
        self.assertEqual(baseline_prompt.system_prompt("agent", True), shared + "Play with the look and do tools.")

    def test_memento_opens_a_fresh_session_every_turn_and_says_so(self) -> None:
        self.assertTrue(game_instructions(True, memento=True).startswith(game_instructions(True)))
        self.assertIn("you will remember nothing from earlier turns", game_instructions(True, memento=True))

        class Harness:
            session_id, turn_number, seen = "", 0, []

            def turn(self, prompt, images=(), timeout=None):
                self.seen.append(self.session_id)
                self.turn_number += 1
                self.session_id = f"s{self.turn_number}"
                return type("R", (), {"text": "ACTION1", "error": "", "session_id": self.session_id,
                                      "usage": {}, "events": [], "timed_out": False})()

        for memento, expected in ((True, ["", ""]), (False, ["", "s1"])):
            with tempfile.TemporaryDirectory() as tmpdir:
                game = CliGameSession(GameSessionConfig(workspace_enabled=True, memento=memento), tmpdir)
                game.session = Harness()
                game.session.seen = []
                game._turn("one", [], "game_action")
                game._turn("two", [], "game_action")
                self.assertEqual(game.session.seen, expected)

    def test_notes_are_kept_after_every_turn_outside_the_mirror(self) -> None:
        class Harness:
            session_id, turn_number = "", 0

            def turn(self, prompt, images=(), timeout=None):
                self.turn_number += 1
                (work / "notes" / "strategy.md").write_text(f"version {self.turn_number}", encoding="utf-8")
                return type("R", (), {"text": "ACTION1", "error": "", "session_id": "s", "usage": {},
                                      "events": [], "timed_out": False})()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            work, out = root / "work", root / "out"
            game = CliGameSession(GameSessionConfig(workspace_enabled=True), work, out, mirror_directory=out / "workspace")
            (work / "notes").mkdir(parents=True)
            game.session = Harness()
            game._turn("one", [], "game_action")
            game._turn("two", [], "game_action")
            self.assertEqual((out / "workspace" / "notes" / "strategy.md").read_text(encoding="utf-8"), "version 2")
            self.assertEqual([(out / "notes_history" / f"turn-000{n}" / "strategy.md").read_text(encoding="utf-8")
                              for n in (1, 2)], ["version 1", "version 2"])

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
    def test_failed_run_restores_progress_without_rewriting_the_parent(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            parent = root / "parent"
            parent.mkdir()
            before = {"grid": [[2, 0, 0]], "state": "PLAYING", "levels_completed": 0, "win_levels": 1}
            after = {**before, "grid": [[0, 2, 0]]}
            (parent / "error.json").write_text(json.dumps({"type": "ValueError", "message": "Codex returned invalid action JSON: explanation"}))
            (parent / "run_config.json").write_text(json.dumps({"max_steps": 2}))
            (parent / "transitions.jsonl").write_text(json.dumps({"action_index": 1, "action": "ACTION4", "before": before, "after": after}) + "\n")
            env = FakeEnv(_frame(before["grid"]), [_frame(after["grid"]), _frame([[0, 0, 2]], state=GameState.WIN, levels_completed=1)])
            result = CodexAgentRunner(env, FakeSession([{"action": "ACTION4", "note": ""}]), root / "child", max_steps=1, continuation_from=parent).run()
            self.assertTrue(result.solved)
            self.assertEqual(len(result.actions), 1)
            self.assertEqual(len(env.step_actions), 2)
            self.assertFalse((parent / "result.json").exists())
            self.assertTrue((parent / "error.json").exists())

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
        from frameworks.baseline.continuation import restore_game
        env = FakeEnv(_frame([[2, 0]]), [_frame([[2, 0]])])
        history = [{"action_index": 1, "action": "ACTION4", "before": {"grid": [[2, 0]]},
                    "after": {"grid": [[0, 2]], "state": "PLAYING", "levels_completed": 0, "win_levels": 1}}]
        with self.assertRaisesRegex(ValueError, "Restoration mismatch"):
            restore_game(env, env.reset(), history)

    def test_only_note_files_are_carried_over(self):
        from frameworks.baseline.continuation import seed_notes
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "parent/workspace"
            source.mkdir(parents=True)
            (source / "strategy.md").write_text("learned plan")
            (source / "tool_calls.jsonl").write_text("private log")
            seed_notes(root / "parent", root / "child")
            # Notes persist only under notes/ (older runs kept them at the root).
            self.assertEqual((root / "child/notes/strategy.md").read_text(), "learned plan")
            self.assertFalse((root / "child/tool_calls.jsonl").exists())
            self.assertFalse((root / "child/notes/tool_calls.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
