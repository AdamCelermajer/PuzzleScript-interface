import json
import os
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from client.arc.types import ActionInput, FrameData, GameAction, GameState, RenderedFrame
from studies.react_agent import run as react_run
from studies.react_agent.run import _print_event
from studies.react_agent.runner import ReactAgentRunner


def _frame(
    grid: list[list[int]],
    *,
    state: GameState = GameState.PLAYING,
    levels_completed: int = 0,
    action: GameAction = GameAction.RESET,
    rendered_frame: RenderedFrame | None = None,
) -> FrameData:
    return FrameData(
        frame=[grid],
        state=state,
        levels_completed=levels_completed,
        game_id="react-test-world",
        win_levels=1,
        guid="react-test-world",
        full_reset=(action == GameAction.RESET),
        available_actions=[GameAction.ACTION1, GameAction.ACTION4],
        action_input=ActionInput(action=action),
        legend={},
        rendered_frame=rendered_frame,
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
        index = min(len(self.step_actions) - 1, len(self.step_frames) - 1)
        return self.step_frames[index]


@dataclass
class SequenceEnv:
    step_actions: list[GameAction] = field(default_factory=list)

    def reset(self) -> FrameData:
        self.step_actions.clear()
        return _frame([[2, 0, 0]])

    def step(self, action: GameAction) -> FrameData:
        self.step_actions.append(action)
        if self.step_actions == [GameAction.ACTION4, GameAction.ACTION4]:
            return _frame(
                [[0, 0, 2]],
                state=GameState.WIN,
                levels_completed=1,
                action=action,
            )
        if self.step_actions == [GameAction.ACTION4]:
            return _frame([[0, 2, 0]], action=action)
        return _frame([[2, 0, 0]], action=action)


class FakeLlm:
    def __init__(self, responses: list[dict | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def call_json(self, system: str, prompt: str, purpose: str = "") -> dict:
        self.calls.append({"system": system, "prompt": prompt, "purpose": purpose})
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeTextLlm:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def call_text(
        self,
        system: str,
        prompt: str,
        image_data_urls: list[str] | None = None,
        purpose: str = "",
    ) -> str:
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "purpose": purpose,
                "image_data_urls": image_data_urls or [],
            }
        )
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        return self.responses.pop(0)


class ReactAgentTests(unittest.TestCase):
    def test_headless_event_print_replaces_non_ascii(self) -> None:
        _print_event("unicode quote \uff08")

    def test_cli_uses_kimi_model_by_default(self) -> None:
        captured: dict[str, object] = {}

        class FakeEnv:
            def __init__(self, **kwargs) -> None:
                captured["env_kwargs"] = kwargs

        class FakeLlm:
            def __init__(self, cfg, **kwargs) -> None:
                captured["model"] = cfg.model

        class FakeRunner:
            def __init__(self, **kwargs) -> None:
                captured["runner_kwargs"] = kwargs
                self.output_dir = kwargs["output_dir"]

            def run(self):
                return SimpleNamespace(
                    solved=False,
                    actions=[],
                    output_dir=self.output_dir,
                    transcript_path=Path(self.output_dir) / "transcript.jsonl",
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(
                    os.environ,
                    {"REACT_AGENT_KIMI_API_KEY": "test-key"},
                    clear=True,
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "run.py",
                        "--backend-url",
                        "http://localhost:8000",
                        "--game-id",
                        "ps_sokoban_basic-v1",
                        "--max-steps",
                        "7",
                        "--output-dir",
                        tmpdir,
                        "--no-window",
                    ],
                ),
                patch.object(react_run, "ArcadeEnv", FakeEnv),
                patch.object(react_run, "ReactLlmClient", FakeLlm),
                patch.object(react_run, "ReactAgentRunner", FakeRunner),
            ):
                react_run.main()

        self.assertEqual(captured["model"], "kimi-k2.6")

    def test_react_agent_can_create_tools_act_and_write_transcript(self) -> None:
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
            llm = FakeLlm(
                [
                    {
                        "thought": "remember the initial board",
                        "tool": "write_file",
                        "args": {"path": "notes/rules.txt", "content": "start: 2 0"},
                    },
                    {
                        "thought": "try a helper",
                        "tool": "run_python",
                        "args": {"code": "print('helper-ok')"},
                    },
                    {
                        "thought": "move right",
                        "tool": "take_action",
                        "args": {"action": "ACTION4"},
                    },
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=3,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(result.actions, [GameAction.ACTION4])
            self.assertEqual(env.step_actions, [GameAction.ACTION4])
            self.assertEqual((Path(tmpdir) / "notes" / "rules.txt").read_text(), "start: 2 0")
            self.assertEqual([call["purpose"] for call in llm.calls], ["react agent"] * 3)

            transcript = [
                json.loads(line)
                for line in result.transcript_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(transcript), 3)
            self.assertEqual(transcript[1]["tool_result"]["content"]["stdout"], "helper-ok\n")
            self.assertEqual(transcript[2]["tool_result"]["content"]["action"], "ACTION4")
            self.assertTrue(transcript[2]["tool_result"]["content"]["changed"])
            self.assertEqual(
                transcript[2]["tool_result"]["content"]["diff"],
                [
                    {"row": 0, "col": 0, "before": 2, "after": 0},
                    {"row": 0, "col": 1, "before": 0, "after": 2},
                ],
            )
            observations = json.loads(
                (Path(tmpdir) / "observations.json").read_text(encoding="utf-8")
            )
            self.assertEqual(observations["actions"], ["ACTION4"])
            self.assertIn("tool_history", observations)
            history = json.loads((Path(tmpdir) / "history.json").read_text())
            tool_history = json.loads((Path(tmpdir) / "tool_history.json").read_text())
            self.assertIsInstance(history, list)
            self.assertIsInstance(tool_history, list)
            self.assertEqual(history[-1]["action"], "ACTION4")

    def test_workspace_file_tools_reject_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [])
            llm = FakeLlm(
                [
                    {
                        "thought": "try escaping",
                        "tool": "write_file",
                        "args": {"path": "../escape.txt", "content": "nope"},
                    },
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=Path(tmpdir) / "run",
                max_steps=1,
                max_tool_calls=2,
            ).run()

            self.assertFalse((Path(tmpdir) / "escape.txt").exists())
            transcript = result.transcript_path.read_text(encoding="utf-8")
            self.assertIn("path escapes workspace", transcript)
            self.assertIn("finish rejected because ARC state is not solved", transcript)

    def test_unknown_action_does_not_step_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [_frame([[0, 2]])])
            llm = FakeLlm(
                [
                    {
                        "thought": "invalid action",
                        "tool": "take_action",
                        "args": {"action": "ACTION99"},
                    },
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
            ).run()

            self.assertEqual(env.step_actions, [])

    def test_known_no_op_action_from_same_grid_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                _frame([[2, 0]]),
                [
                    _frame([[2, 0]], action=GameAction.ACTION4),
                    _frame([[0, 2]], action=GameAction.ACTION4),
                ],
            )
            llm = FakeLlm(
                [
                    {
                        "thought": "blocked move",
                        "tool": "take_action",
                        "args": {"action": "ACTION4"},
                    },
                    {
                        "thought": "repeat blocked move",
                        "tool": "take_action",
                        "args": {"action": "ACTION4"},
                    },
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=3,
                max_tool_calls=3,
            ).run()

            self.assertEqual(result.actions, [GameAction.ACTION4])
            self.assertEqual(env.step_actions, [GameAction.ACTION4])
            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                transcript[1]["tool_result"]["content"]["error"],
                "known no-op action from same grid rejected",
            )

    def test_invalid_llm_json_is_logged_and_retried(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [])
            events: list[str] = []
            llm = FakeLlm(
                [
                    ValueError("LLM returned invalid JSON"),
                    {"thought": "stop cleanly", "tool": "finish", "args": {}},
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
                event_sink=events.append,
            ).run()

            self.assertFalse(result.solved)
            self.assertEqual(len(llm.calls), 2)
            self.assertTrue(any("LLM call error 1/3" in event for event in events))
            transcript = [
                json.loads(line)
                for line in result.transcript_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(transcript[0]["response"]["tool"], "llm_error")
            self.assertFalse(transcript[0]["tool_result"]["ok"])

    def test_text_llm_responses_are_parsed_without_provider_json_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [])
            llm = FakeTextLlm(
                [
                    "```json\n"
                    '{"thought":"inspect first","tool":"inspect_state","args":{}}\n'
                    "```",
                    "I will stop now.\n"
                    '{"thought":"done","tool":"finish","args":{"message":"ok"}}',
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
            ).run()

            self.assertFalse(result.solved)
            self.assertEqual([call["purpose"] for call in llm.calls], ["react agent"] * 2)
            transcript = [
                json.loads(line)
                for line in result.transcript_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(transcript[0]["response"]["tool"], "inspect_state")
            self.assertEqual(transcript[1]["response"]["tool"], "finish")

    def test_tool_results_are_visible_to_next_llm_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [])
            llm = FakeLlm(
                [
                    {"thought": "look once", "tool": "inspect_state", "args": {}},
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
            ).run()

            second_prompt = llm.calls[1]["prompt"]
            self.assertIn("Recent tool calls and results", second_prompt)
            self.assertIn("inspect_state", second_prompt)
            self.assertIn("ACTION1=Up", second_prompt)
            self.assertIn("probe before spending many real", second_prompt)
            self.assertIn("Main action budget used", second_prompt)
            self.assertIn("remaining", second_prompt)
            self.assertIn("Avoid ACTION7", llm.calls[0]["system"])
            self.assertIn("authoritative feedback", llm.calls[0]["system"])
            self.assertIn('"note": "...", "tool"', llm.calls[0]["system"])
            self.assertIn("Do not include chain-of-thought", llm.calls[0]["system"])
            self.assertNotIn('"thought": "...", "tool"', llm.calls[0]["system"])

    def test_repeated_non_action_tools_are_blocked_after_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [])
            llm = FakeLlm(
                [
                    {"thought": "look once", "tool": "inspect_state", "args": {}},
                    {"thought": "look again", "tool": "inspect_state", "args": {}},
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
                max_non_action_tools=1,
            ).run()

            self.assertEqual(result.actions, [])
            transcript = [
                json.loads(line)
                for line in result.transcript_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(transcript[1]["response"]["tool"], "take_action_required")
            self.assertIn(
                "Non-action tool budget is exhausted",
                transcript[1]["tool_result"]["content"]["message"],
            )

    def test_action_sequence_is_allowed_after_non_action_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                _frame([[2, 0]]),
                [_frame([[0, 2]], action=GameAction.ACTION4)],
            )
            llm = FakeLlm(
                [
                    {"thought": "look", "tool": "inspect_state", "args": {}},
                    {
                        "thought": "act with a sequence",
                        "tool": "take_action_sequence",
                        "args": {"actions": ["ACTION4"]},
                    },
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
                max_non_action_tools=1,
            ).run()

            self.assertEqual(result.actions, [GameAction.ACTION4])
            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(transcript[1]["response"]["tool"], "take_action_sequence")
            self.assertIn("note", transcript[0]["response"])
            self.assertNotIn("thought", transcript[0]["response"])
            self.assertLessEqual(len(transcript[0]["response"]["note"].split()), 12)

    def test_action_events_report_action_names_and_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            events: list[str] = []
            env = FakeEnv(
                _frame([[2, 0]]),
                [_frame([[0, 2]], action=GameAction.ACTION4)],
            )
            llm = FakeLlm(
                [
                    {
                        "note": "move right",
                        "tool": "take_action",
                        "args": {"action": "ACTION4"},
                    }
                ]
            )

            ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=1,
                event_sink=events.append,
            ).run()

            result_events = [event for event in events if event.startswith("Tool result")]
            self.assertTrue(any("ACTION4 Right" in event for event in result_events))
            self.assertTrue(any("changed=True" in event for event in result_events))
            self.assertTrue(any(event.startswith("Note: move right") for event in events))

    def test_finish_is_rejected_until_arc_reports_solved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                _frame([[2, 0]]),
                [
                    _frame(
                        [[0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                    )
                ],
            )
            llm = FakeLlm(
                [
                    {"note": "claim done", "tool": "finish", "args": {}},
                    {
                        "note": "now act",
                        "tool": "take_action",
                        "args": {"action": "ACTION4"},
                    },
                    {"note": "confirmed done", "tool": "finish", "args": {}},
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=2,
                max_tool_calls=3,
            ).run()

            self.assertTrue(result.solved)
            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(transcript[0]["response"]["tool"], "finish")
            self.assertFalse(transcript[0]["tool_result"]["ok"])
            self.assertEqual(
                transcript[0]["tool_result"]["content"]["error"],
                "finish rejected because ARC state is not solved",
            )

    def test_repeated_sequence_from_same_grid_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                _frame([[2, 0]]),
                [
                    _frame([[2, 0]], action=GameAction.ACTION4),
                    _frame([[0, 2]], action=GameAction.ACTION4),
                ],
            )
            llm = FakeLlm(
                [
                    {
                        "thought": "try sequence",
                        "tool": "take_action_sequence",
                        "args": {"actions": ["ACTION4"]},
                    },
                    {
                        "thought": "repeat same sequence",
                        "tool": "take_action_sequence",
                        "args": {"actions": ["ACTION4"]},
                    },
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=5,
                max_tool_calls=3,
            ).run()

            self.assertEqual(result.actions, [GameAction.ACTION4])
            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                transcript[1]["tool_result"]["content"]["error"],
                "repeated sequence from same grid rejected",
            )

    def test_json_string_tool_args_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [])
            llm = FakeLlm(
                [
                    {
                        "thought": "helper args encoded as a string",
                        "tool": "run_python",
                        "args": '{"code": "print(123)"}',
                    },
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
            ).run()

            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(transcript[0]["response"]["args"], {"code": "print(123)"})
            self.assertEqual(transcript[0]["tool_result"]["content"]["stdout"], "123\n")

    def test_rendered_frame_is_forwarded_to_text_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            image_url = "data:image/png;base64,abc123"
            env = FakeEnv(
                _frame(
                    [[2, 0]],
                    rendered_frame=RenderedFrame("image/png", image_url),
                ),
                [],
            )
            llm = FakeTextLlm(
                ['{"thought":"look visually","tool":"finish","args":{}}']
            )

            ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=1,
            ).run()

            self.assertEqual(llm.calls[0]["image_data_urls"], [image_url])
            self.assertIn("rendered screenshot", llm.calls[0]["system"])

    def test_action_sequence_executes_multiple_steps_with_diffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                _frame([[2, 0, 0]]),
                [
                    _frame([[0, 2, 0]], action=GameAction.ACTION4),
                    _frame(
                        [[0, 0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                    ),
                ],
            )
            llm = FakeLlm(
                [
                    {
                        "thought": "take a path",
                        "tool": "take_action_sequence",
                        "args": {"actions": ["ACTION4", "ACTION4", "ACTION4"]},
                    }
                ]
            )

            result = ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=5,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(result.actions, [GameAction.ACTION4, GameAction.ACTION4])
            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            content = transcript[0]["tool_result"]["content"]
            self.assertEqual(content["actions_executed"], 2)
            self.assertTrue(content["solved"])
            self.assertEqual(content["transitions"][0]["action"], "ACTION4")
            self.assertTrue(content["transitions"][0]["changed"])

    def test_probe_action_tree_finds_winning_sequence_without_main_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            llm = FakeLlm(
                [
                    {
                        "thought": "probe fresh episodes",
                        "tool": "probe_action_tree",
                        "args": {"actions": ["ACTION4"], "max_depth": 2},
                    },
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            result = ReactAgentRunner(
                env=SequenceEnv(),
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=3,
                max_tool_calls=2,
                max_probe_actions=4,
                probe_env_factory=SequenceEnv,
            ).run()

            self.assertEqual(result.actions, [])
            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            content = transcript[0]["tool_result"]["content"]
            self.assertTrue(content["solved"])
            self.assertEqual(content["actions"], ["ACTION4", "ACTION4"])
            self.assertLessEqual(content["probe_actions_used"], 4)

    def test_probe_action_tree_respects_probe_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            llm = FakeLlm(
                [
                    {
                        "thought": "probe too little",
                        "tool": "probe_action_tree",
                        "args": {"actions": ["ACTION4"], "max_depth": 3},
                    }
                ]
            )

            ReactAgentRunner(
                env=SequenceEnv(),
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=3,
                max_tool_calls=1,
                max_probe_actions=1,
                probe_env_factory=SequenceEnv,
            ).run()

            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            content = transcript[0]["tool_result"]["content"]
            self.assertFalse(content["solved"])
            self.assertEqual(content["probe_actions_used"], 1)

    def test_run_python_can_read_automatic_observations_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(_frame([[2, 0]]), [])
            llm = FakeLlm(
                [
                    {
                        "thought": "read observations",
                        "tool": "run_python",
                        "args": {
                            "code": (
                                "import json; "
                                "print(json.load(open('observations.json'))['history'][0]['action'])"
                            )
                        },
                    },
                    {"thought": "stop", "tool": "finish", "args": {}},
                ]
            )

            ReactAgentRunner(
                env=env,
                llm_client=llm,
                output_dir=tmpdir,
                max_steps=1,
                max_tool_calls=2,
            ).run()

            transcript = [
                json.loads(line)
                for line in (Path(tmpdir) / "transcript.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(transcript[0]["tool_result"]["content"]["stdout"], "RESET\n")


if __name__ == "__main__":
    unittest.main()
