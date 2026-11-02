"""Run token totals: one convention across every recorded usage format, each session counted once."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from workbench import run_tokens as tokens


def lines(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def usage_event(harness, turn, usage, session="s1"):
    return {"schema": "agent-event-v1", "t": f"2026-10-21T00:00:0{turn}Z", "session": session, "role": "player",
            "turn": turn, "type": "usage", "usage": usage, "harness": harness}


def step(part_id, input, output, reasoning, read):
    return {"id": part_id, "type": "step-finish",
            "tokens": {"input": input, "output": output, "reasoning": reasoning, "cache": {"read": read, "write": 0}}}


def thread_usage(thread, input, output, reasoning, cached):
    return {"method": "thread/tokenUsage/updated", "payload": {"threadId": thread, "tokenUsage": {
        "last": {"inputTokens": 1, "outputTokens": 1},
        "total": {"inputTokens": input, "outputTokens": output, "reasoningOutputTokens": reasoning,
                  "cachedInputTokens": cached, "totalTokens": input + output}}}}


class RunTokensTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.run = Path(self.temp.name) / "run"
        tokens._cache.clear()
        tokens._index_cache.clear()

    def tearDown(self):
        tokens._cache.clear()
        tokens._index_cache.clear()
        self.temp.cleanup()

    def test_nothing_recorded_is_none(self):
        lines(self.run / "transitions.jsonl", [{"action_index": 1}])
        self.assertIsNone(tokens.run_tokens(self.run))
        self.assertIsNone(tokens.run_tokens(self.run / "missing"))

    def test_harness_usage_events_skip_turn_end_and_turns_jsonl(self):
        usage = {"input": 100, "output": 20, "reasoning": 0, "cached": 60, "cost_usd": 0.1}
        lines(self.run / "agent_events.jsonl", [
            usage_event("claude-code", 1, usage),
            {**usage_event("claude-code", 1, usage), "type": "turn_end"},
            usage_event("claude-code", 2, usage)])
        lines(self.run / "turns.jsonl", [{"turn": 1, "usage": usage}, {"turn": 2, "usage": usage}])
        self.assertEqual(tokens.run_tokens(self.run),
                         {"input": 200, "output": 40, "reasoning": 0, "cached": 120, "total": 240})

    def test_opencode_counts_raw_steps_with_cache_and_reasoning_added_back(self):
        # The usage event sums turn 1's steps; turn 2 was stopped before its usage event was written.
        lines(self.run / "agent_events.jsonl",
              [usage_event("opencode", 1, {"input": 15, "output": 3, "reasoning": 7, "cached": 80})])
        lines(self.run / "raw/turn-1.jsonl", [
            {"type": "step_finish", "part": step("p1", 10, 2, 4, 50)},
            {"type": "step_finish", "part": step("p2", 5, 1, 3, 30)}])
        lines(self.run / "raw/turn-2.jsonl", [{"type": "step_finish", "part": step("p3", 1, 1, 1, 10)}])
        self.assertEqual(tokens.run_tokens(self.run),
                         {"input": 106, "output": 12, "reasoning": 8, "cached": 90, "total": 118})

    def test_harness2_rollouts_and_coach_sessions_add_up(self):
        usage = {"input": 10, "output": 1, "reasoning": 0, "cached": 0}
        lines(self.run / "rollouts/base1/agent_events.jsonl", [usage_event("bare", 1, usage, "a")])
        lines(self.run / "improver/sessions/harness2-prop-x/agent_events.jsonl", [usage_event("bare", 1, usage, "b")])
        lines(self.run / "levels/L1/rounds/R1/rollouts/dom1/agent_events.jsonl", [usage_event("bare", 1, usage, "c")])
        # Agent scratch copies are not sessions of this run.
        lines(self.run / "rollouts/base1/workspace/agent_events.jsonl", [usage_event("bare", 1, usage, "d")])
        self.assertEqual(tokens.run_tokens(self.run)["total"], 33)

    def test_codex_app_server_keeps_the_last_running_total_per_thread(self):
        optimizer = [thread_usage("t1", 100, 10, 5, 80), thread_usage("t1", 300, 30, 15, 250)]
        lines(self.run / "optimizer_analysis/agent_events.jsonl", optimizer)
        lines(self.run / "optimizer_analysis/app_server_events.jsonl", optimizer)  # full copy of the same thread
        lines(self.run / "evaluations/x_0001/run_001/analysis/app_server_events.jsonl", [thread_usage("t2", 50, 5, 1, 40)])
        self.assertEqual(tokens.run_tokens(self.run),
                         {"input": 350, "output": 35, "reasoning": 16, "cached": 290, "total": 385})

    def test_codex_session_running_total_restarts_with_a_new_thread(self):
        def turn(input, output):
            return {"turn_kind": "game_action", "turn": {"id": f"turn-{input}", "usage": {
                "last": {"inputTokens": 1, "outputTokens": 1},
                "total": {"inputTokens": input, "outputTokens": output, "reasoningOutputTokens": 1,
                          "cachedInputTokens": input // 2}}}}
        lines(self.run / "codex_session.jsonl", [turn(100, 10), turn(250, 20), turn(40, 4)])
        self.assertEqual(tokens.run_tokens(self.run),
                         {"input": 290, "output": 24, "reasoning": 2, "cached": 145, "total": 314})

    def test_opencode_server_parts_are_deduplicated_by_id(self):
        part = step("p1", 20, 5, 2, 100)
        event = {"method": "message.part.updated", "native": {"properties": {"part": part}}, "payload": {"part": part}}
        lines(self.run / "optimizer_analysis/agent_events.jsonl", [event, event])
        self.assertEqual(tokens.run_tokens(self.run),
                         {"input": 120, "output": 7, "reasoning": 2, "cached": 100, "total": 127})

    def test_openrouter_model_session_replies(self):
        usage = {"prompt_tokens": 500, "completion_tokens": 90, "total_tokens": 590,
                 "prompt_tokens_details": {"cached_tokens": 100}, "completion_tokens_details": {"reasoning_tokens": 60}}
        lines(self.run / "model_session.jsonl", [{"turn": 1, "usage": usage}, {"turn": 2, "usage": usage}])
        self.assertEqual(tokens.run_tokens(self.run),
                         {"input": 1000, "output": 180, "reasoning": 120, "cached": 200, "total": 1180})

    def test_continued_run_counts_only_what_it_added_to_its_copied_source(self):
        source, continued, later = (Path(self.temp.name) / name for name in ("source", "continued", "later"))
        usage = {"input": 10, "output": 1, "reasoning": 0, "cached": 0}
        copied_events = [usage_event("bare", 1, usage, "a"), usage_event("bare", 2, usage, "a")]
        copied_thread = [thread_usage("t1", 100, 10, 5, 80)]
        for run, events, thread in (
                (source, copied_events, copied_thread),
                # The continuation copied the source folder, resumed thread t1 and started session b.
                (continued, copied_events + [usage_event("bare", 1, usage, "b")],
                 copied_thread + [thread_usage("t1", 160, 16, 8, 120)]),
                (later, copied_events + [usage_event("bare", 1, usage, "b")],
                 copied_thread + [thread_usage("t1", 160, 16, 8, 120), thread_usage("t1", 200, 20, 9, 150)])):
            lines(run / "rollouts/base1/agent_events.jsonl", events)
            lines(run / "optimizer_analysis/agent_events.jsonl", thread)
        for age, run in enumerate((later, continued, source)):
            for path in run.rglob("*.jsonl"):
                os.utime(path, (1_800_000_000 - 100 * age, 1_800_000_000 - 100 * age))
        runs = [source, continued, later, Path(self.temp.name) / "queued-without-files"]
        self.assertEqual(tokens.run_tokens(source, runs),
                         {"input": 120, "output": 12, "reasoning": 5, "cached": 80, "total": 132})
        self.assertEqual(tokens.run_tokens(continued, runs),
                         {"input": 70, "output": 7, "reasoning": 3, "cached": 40, "total": 77})
        self.assertEqual(tokens.run_tokens(later, runs),
                         {"input": 40, "output": 4, "reasoning": 1, "cached": 30, "total": 44})
        # On its own a run counts everything in its folder.
        self.assertEqual(tokens.run_tokens(later)["total"], 253)

    def test_cached_until_a_source_file_changes(self):
        path = self.run / "agent_events.jsonl"
        usage = {"input": 10, "output": 1, "reasoning": 0, "cached": 0}
        lines(path, [usage_event("bare", 1, usage)])
        self.assertEqual(tokens.run_tokens(self.run)["total"], 11)
        lines(path, [usage_event("bare", 1, usage), usage_event("bare", 2, usage)])
        os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 10))
        self.assertEqual(tokens.run_tokens(self.run)["total"], 22)


if __name__ == "__main__":
    unittest.main()
