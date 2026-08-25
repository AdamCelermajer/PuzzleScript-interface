import tempfile
import threading
import time
import unittest
import shutil
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from client.runtime.runner import RunResult
from client.arc.types import GameAction, GameState
from client.engine.memory import EngineMemory
from client.engine.perception import EngineImage, EngineState
from client.engine.prompts import PromptStore, default_prompt_dir
from workbench.app import create_app
from workbench.paper_library import PaperLibrary
from workbench.run_manager import RunManager


class EmptyCollection:
    def all(self):
        return []


class EmptyFailures:
    def recent(self, limit=50):
        return []


class EmptyMemory:
    def recent_transitions(self, limit):
        return []


def fake_engine():
    return SimpleNamespace(
        natural_rule_library=EmptyCollection(),
        logical_rulebook=SimpleNamespace(generalized_rules=[]),
        failure_log=EmptyFailures(),
        memory=EmptyMemory(),
        goal_manager=SimpleNamespace(game_goal=None, subgoal=None),
        action_selector=SimpleNamespace(active_plan=None, last_decision=None),
    )


class FakeEnv:
    def __init__(self, renderer=None, **_kwargs):
        self.renderer = renderer


class ImmediateLoop:
    def __init__(self, env, engine, event_sink=None, **_kwargs):
        self.event_sink = event_sink

    def run(self, max_steps, game_id):
        self.event_sink("fake run complete")
        return RunResult("completed", "step_budget_exhausted", 1, game_id)


class BlockingLoop:
    release = threading.Event()

    def __init__(self, env, engine, event_sink=None, stop_event=None, **_kwargs):
        self.stop_event = stop_event

    def run(self, max_steps, game_id):
        while not self.stop_event.is_set() and not self.release.wait(0.01):
            pass
        status = "cancelled" if self.stop_event.is_set() else "completed"
        return RunResult(status, "stop_requested", 0, game_id)


class ProviderFailureLoop:
    def __init__(self, *_args, **_kwargs):
        pass

    def run(self, max_steps, game_id):
        raise ValueError(
            "LLM provider error: Error code: 403; "
            "manage key at https://provider.invalid/keys/secret-key-id"
        )


class FakePaperAssistant:
    def __init__(self, answer="The claim survives only as an experimental treatment."):
        self.answer = answer
        self.calls = []

    def ask(self, **kwargs):
        self.calls.append(kwargs)
        return self.answer


class FakeCodexSession:
    configs = []

    def __init__(self, config, working_directory):
        self.config = config
        self.working_directory = Path(working_directory)
        self.__class__.configs.append(config)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeCodexRunner:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.calls.append(kwargs)

    def run(self):
        frame = SimpleNamespace(
            frame=[[[2, 0]]],
            state=GameState.PLAYING,
            levels_completed=0,
            win_levels=1,
            action_input=SimpleNamespace(action=GameAction.RESET),
            rendered_frame=None,
        )
        self.kwargs["env"].renderer(1, frame)
        self.kwargs["decision_sink"](
            {"action": "ACTION4", "note": "move right", "decision": 1}
        )
        self.kwargs["transition_sink"](
            {
                "id": "T000001",
                "action": "ACTION4",
                "before": {"grid": [[2, 0]]},
                "after": {"grid": [[0, 2]]},
            }
        )
        self.kwargs["event_sink"]("Decision 1: ACTION4 | move right")
        return SimpleNamespace(status="completed", reason="step_budget_exhausted")


def manager(
    tmpdir,
    loop_factory=ImmediateLoop,
    prompt_store=None,
    codex_session_factory=FakeCodexSession,
    codex_runner_factory=FakeCodexRunner,
):
    return RunManager(
        rules_dir=tmpdir,
        env_factory=FakeEnv,
        llm_factory=lambda *args, **kwargs: object(),
        engine_factory=lambda *args, **kwargs: fake_engine(),
        loop_factory=loop_factory,
        codex_session_factory=codex_session_factory,
        codex_runner_factory=codex_runner_factory,
        codex_runs_dir=Path(tmpdir) / "codex-output",
        prompt_store=prompt_store,
    )


def wait_finished(run, timeout=2):
    deadline = time.time() + timeout
    while run.status in {"starting", "running", "stopping"} and time.time() < deadline:
        time.sleep(0.01)


class WorkbenchApiTests(unittest.TestCase):
    def test_paper_investigation_uses_grounded_assistant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assistant = FakePaperAssistant()
            client = TestClient(create_app(manager(tmpdir), paper_assistant=assistant))
            response = client.post(
                "/api/workbench/paper-investigation/ask",
                json={
                    "paper": "vista",
                    "question": "Does this invalidate executable rules?",
                    "selected_passage": "Free-form language is sufficient.",
                    "history": [
                        {"role": "assistant", "content": "We should separate necessity from usefulness."}
                    ],
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["answer"], assistant.answer)
            self.assertEqual(assistant.calls[0]["paper"], "vista")
            self.assertEqual(
                assistant.calls[0]["selected_passage"],
                "Free-form language is sufficient.",
            )

    def test_paper_investigation_rejects_invalid_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(
                create_app(manager(tmpdir), paper_assistant=FakePaperAssistant())
            )
            response = client.post(
                "/api/workbench/paper-investigation/ask",
                json={"paper": "unknown", "question": "Explain this."},
            )

            self.assertEqual(response.status_code, 404)

    @staticmethod
    def sample_pdf(title="A saved research paper"):
        stream = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.add_metadata({"/Title": title, "/Author": "Ada Researcher"})
        writer.write(stream)
        return stream.getvalue()

    def test_paper_library_upload_status_annotations_and_questions_are_folder_backed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assistant = FakePaperAssistant("Linked evidence changes the claim.")
            library = PaperLibrary(Path(tmpdir) / "papers")
            client = TestClient(create_app(
                manager(tmpdir), paper_assistant=assistant, paper_library=library
            ))

            uploaded = client.post(
                "/api/workbench/paper-investigation/papers/upload",
                params={"filename": "experiment.pdf"},
                content=self.sample_pdf(),
                headers={"Content-Type": "application/pdf"},
            )
            self.assertEqual(uploaded.status_code, 201)
            paper = uploaded.json()["paper"]
            paper_id = paper["id"]
            paper_dir = Path(tmpdir) / "papers" / paper_id
            self.assertEqual(paper["title"], "A saved research paper")
            self.assertTrue((paper_dir / "paper.pdf").is_file())
            self.assertTrue((paper_dir / "text.txt").is_file())
            self.assertTrue((paper_dir / "annotations.json").is_file())
            self.assertTrue((paper_dir / "questions.json").is_file())

            status = client.patch(
                f"/api/workbench/paper-investigation/papers/{paper_id}",
                json={"status": "finished", "last_page": 1},
            )
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["paper"]["status"], "finished")
            self.assertTrue(status.json()["paper"]["completed_at"])

            added = client.post(
                f"/api/workbench/paper-investigation/papers/{paper_id}/annotations",
                json={
                    "id": "underline-1",
                    "quote": "The decisive passage.",
                    "page": 1,
                    "comment": "This changes the baseline.",
                },
            )
            self.assertEqual(added.status_code, 201)
            updated = client.patch(
                f"/api/workbench/paper-investigation/papers/{paper_id}/annotations/underline-1",
                json={"comment": "Compare against the same model."},
            )
            self.assertEqual(
                updated.json()["annotation"]["comment"],
                "Compare against the same model.",
            )

            asked = client.post(
                "/api/workbench/paper-investigation/ask",
                json={
                    "paper_ids": [paper_id],
                    "annotation_ids": ["underline-1"],
                    "question": "What does this change?",
                },
            )
            self.assertEqual(asked.status_code, 200)
            self.assertIn("The decisive passage", assistant.calls[0]["source_context"])
            saved = client.get(
                f"/api/workbench/paper-investigation/papers/{paper_id}"
            ).json()
            self.assertEqual(saved["paper"]["annotation_count"], 1)
            self.assertEqual(saved["paper"]["question_count"], 1)
            self.assertEqual(saved["questions"][0]["annotation_ids"], ["underline-1"])
            self.assertEqual(
                client.get(
                    f"/api/workbench/paper-investigation/papers/{paper_id}/pdf"
                ).status_code,
                200,
            )

    def test_paper_library_accepts_arxiv_links_and_keeps_stable_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            library = PaperLibrary(Path(tmpdir) / "papers")
            client = TestClient(create_app(manager(tmpdir), paper_library=library))
            with patch.object(library, "_download_pdf", return_value=self.sample_pdf("Linked paper")):
                response = client.post(
                    "/api/workbench/paper-investigation/papers/import",
                    json={"url": "https://arxiv.org/abs/2603.99999"},
                )

            self.assertEqual(response.status_code, 201)
            paper = response.json()["paper"]
            self.assertEqual(paper["id"], "arxiv-2603-99999")
            self.assertEqual(paper["source_type"], "arxiv")
            self.assertTrue((Path(tmpdir) / "papers" / paper["id"] / "paper.pdf").is_file())

    def test_paper_question_can_link_multiple_selected_papers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assistant = FakePaperAssistant("The comparison needs a matched ablation.")
            library = PaperLibrary(Path(tmpdir) / "papers")
            client = TestClient(create_app(
                manager(tmpdir), paper_assistant=assistant, paper_library=library
            ))

            response = client.post(
                "/api/workbench/paper-investigation/ask",
                json={
                    "paper_ids": ["avo", "vista"],
                    "question": "Where do these papers actually collide?",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["paper_ids"], ["avo", "vista"])
            self.assertEqual(assistant.calls[0]["paper"], "avo, vista")
            self.assertEqual(len(library.questions("avo")), 1)
            self.assertEqual(len(library.questions("vista")), 1)
            self.assertEqual(
                library.questions("avo")[0]["id"],
                library.questions("vista")[0]["id"],
            )

    def test_current_run_endpoint_allows_reload_to_reattach_and_stop(self):
        BlockingLoop.release.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            run_manager = manager(tmpdir, BlockingLoop)
            first_page = TestClient(create_app(run_manager))
            self.assertIsNone(
                first_page.get("/api/workbench/runs/current").json()["run"]
            )
            started = first_page.post(
                "/api/workbench/runs",
                json={"game_id": "demo", "max_steps": 10, "memory_mode": "resume"},
            ).json()

            reloaded_page = TestClient(create_app(run_manager))
            current = reloaded_page.get("/api/workbench/runs/current")
            self.assertEqual(current.status_code, 200)
            self.assertEqual(current.headers["cache-control"], "no-store")
            self.assertEqual(current.json()["run"]["run_id"], started["run_id"])
            self.assertIn(
                current.json()["run"]["status"],
                {"starting", "running", "stopping"},
            )

            stopped = reloaded_page.post(
                f"/api/workbench/runs/{started['run_id']}/stop"
            )
            self.assertEqual(stopped.status_code, 202)
            wait_finished(run_manager.get(started["run_id"]))
            self.assertEqual(run_manager.get(started["run_id"]).status, "cancelled")

    def test_prompts_can_be_read_edited_and_reset_when_idle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_root = Path(tmpdir) / "prompts"
            shutil.copytree(default_prompt_dir() / "defaults", prompt_root / "defaults")
            prompt_store = PromptStore(prompt_root)
            client = TestClient(create_app(manager(tmpdir, prompt_store=prompt_store)))

            catalog = client.get("/api/workbench/prompts").json()["prompts"]
            self.assertIn("natural_rule", {item["id"] for item in catalog})
            saved = client.put(
                "/api/workbench/prompts/natural_rule",
                json={"content": "Custom causal instruction."},
            )
            self.assertEqual(saved.status_code, 200)
            self.assertTrue(saved.json()["prompt"]["customized"])
            self.assertEqual(
                prompt_store.get("natural_rule"), "Custom causal instruction."
            )

            reset = client.delete("/api/workbench/prompts/natural_rule")
            self.assertEqual(reset.status_code, 200)
            self.assertFalse(reset.json()["prompt"]["customized"])
            self.assertNotEqual(
                prompt_store.get("natural_rule"), "Custom causal instruction."
            )

    def test_health_and_start_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_manager = manager(tmpdir)
            client = TestClient(create_app(run_manager))
            self.assertTrue(client.get("/api/workbench/health").json()["ok"])

            response = client.post(
                "/api/workbench/runs",
                json={
                    "backend": "puzzlescript",
                    "game_id": "ps_sokoban_basic-v1",
                    "max_steps": 12,
                    "memory_mode": "resume",
                },
            )

            self.assertEqual(response.status_code, 202)
            run_id = response.json()["run_id"]
            snapshot = client.get(f"/api/workbench/runs/{run_id}").json()
            self.assertEqual(snapshot["config"]["max_steps"], 12)
            self.assertEqual(snapshot["config"]["provider"], "openrouter")
            self.assertEqual(
                snapshot["config"]["model"], "anthropic/claude-opus-4.8"
            )
            wait_finished(run_manager.get(run_id))

    def test_run_config_accepts_legend_and_goal_controls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_manager = manager(tmpdir)
            client = TestClient(create_app(run_manager))
            response = client.post(
                "/api/workbench/runs",
                json={
                    "game_id": "demo",
                    "memory_mode": "resume",
                    "provide_legend": False,
                    "provide_end_goal": True,
                    "end_goal": "put every crate on a target",
                },
            )
            self.assertEqual(response.status_code, 202)
            config = response.json()["config"]
            self.assertFalse(config["provide_legend"])
            self.assertEqual(config["end_goal"], "put every crate on a target")
            wait_finished(run_manager.get(response.json()["run_id"]))

    def test_model_catalog_exposes_openrouter_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(create_app(manager(tmpdir)))
            payload = client.get("/api/workbench/models").json()
            self.assertEqual(payload["provider"]["id"], "openrouter")
            self.assertEqual(payload["default_model"], "anthropic/claude-opus-4.8")
            models = {item["id"]: item for item in payload["models"]}
            self.assertEqual(
                models["x-ai/grok-4.5"]["supported_efforts"],
                ["high", "medium", "low"],
            )
            self.assertEqual(models["xiaomi/mimo-v2.5"]["supported_efforts"], [])
            self.assertEqual(
                payload["codex"]["default_model"],
                "gpt-5.6-sol",
            )

    def test_codex_live_run_uses_oauth_session_and_exposes_live_decision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            FakeCodexSession.configs.clear()
            FakeCodexRunner.calls.clear()
            run_manager = manager(tmpdir)
            client = TestClient(create_app(run_manager))
            response = client.post(
                "/api/workbench/runs",
                json={
                    "agent_mode": "codex",
                    "backend": "puzzlescript",
                    "game_id": "ps_sokoban_basic-v1",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "low",
                    "max_steps": 2,
                },
            )

            self.assertEqual(response.status_code, 202)
            run_id = response.json()["run_id"]
            run = run_manager.get(run_id)
            wait_finished(run)
            snapshot = run.snapshot()
            self.assertEqual(snapshot["config"]["provider"], "codex_oauth")
            self.assertEqual(snapshot["config"]["model"], "gpt-5.6-sol")
            self.assertEqual(snapshot["reasoning"]["decision"]["action"], "ACTION4")
            self.assertEqual(snapshot["reasoning"]["decision"]["note"], "move right")
            self.assertEqual(snapshot["timeline"][0]["id"], "T000001")
            self.assertIn("Decision 1: ACTION4", snapshot["events"][-1])
            self.assertEqual(FakeCodexSession.configs[-1].effort, "low")
            self.assertIs(
                FakeCodexRunner.calls[-1]["stop_event"],
                run.stop_event,
            )

    def test_codex_status_endpoint_reports_desktop_oauth_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_manager = manager(tmpdir)
            run_manager.codex_status = lambda: {
                "available": True,
                "logged_in": True,
                "state": "ready",
                "version": "codex-cli test",
                "message": "Logged in using ChatGPT",
            }
            response = TestClient(create_app(run_manager)).get(
                "/api/workbench/codex/status"
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["logged_in"])
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_openrouter_status_returns_visible_key_without_caching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            status = {
                "configured": True,
                "state": "usable",
                "api_key": "sk-or-visible-test",
                "usage": 1.25,
            }
            with patch("workbench.app.openrouter_account.get_status", return_value=status):
                response = TestClient(create_app(manager(tmpdir))).get(
                    "/api/workbench/openrouter/status"
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["api_key"], "sk-or-visible-test")
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_openrouter_key_can_be_replaced_when_idle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            status = {
                "configured": True,
                "state": "usable",
                "api_key": "sk-or-replacement",
            }
            with patch(
                "workbench.app.openrouter_account.replace_key", return_value=status
            ) as replace_key:
                response = TestClient(create_app(manager(tmpdir))).post(
                    "/api/workbench/openrouter/key",
                    json={"api_key": "sk-or-replacement"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["saved"])
            self.assertEqual(response.json()["status"]["api_key"], "sk-or-replacement")
            self.assertEqual(response.headers["cache-control"], "no-store")
            replace_key.assert_called_once_with("sk-or-replacement")

    def test_openrouter_key_replacement_is_rejected_during_a_run(self):
        BlockingLoop.release.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            run_manager = manager(tmpdir, BlockingLoop)
            client = TestClient(create_app(run_manager))
            started = client.post(
                "/api/workbench/runs",
                json={"game_id": "demo", "max_steps": 10, "memory_mode": "resume"},
            )
            response = client.post(
                "/api/workbench/openrouter/key",
                json={"api_key": "sk-or-replacement"},
            )

            self.assertEqual(response.status_code, 409)
            client.post(f"/api/workbench/runs/{started.json()['run_id']}/stop")

    def test_validation_rejects_invalid_step_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TestClient(create_app(manager(tmpdir)))
            response = client.post(
                "/api/workbench/runs",
                json={"game_id": "demo", "max_steps": 0},
            )
            self.assertEqual(response.status_code, 422)

            blank_game = client.post(
                "/api/workbench/runs",
                json={"game_id": "   ", "max_steps": 12},
            )
            self.assertEqual(blank_game.status_code, 422)

            unknown_model = client.post(
                "/api/workbench/runs",
                json={"game_id": "demo", "model": "unknown/model"},
            )
            self.assertEqual(unknown_model.status_code, 422)

            unsupported_effort = client.post(
                "/api/workbench/runs",
                json={
                    "game_id": "demo",
                    "model": "xiaomi/mimo-v2.5",
                    "reasoning_effort": "high",
                },
            )
            self.assertEqual(unsupported_effort.status_code, 422)

    def test_fresh_mode_archives_current_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "demo"
            base.mkdir()
            for name in ("timeline.jsonl", "rules.json", "natural_rules.json"):
                (base / name).write_text(name, encoding="utf-8")
            run = manager(tmpdir).start(
                {
                    "backend": "puzzlescript",
                    "game_id": "demo",
                    "max_steps": 1,
                    "memory_mode": "fresh",
                }
            )
            wait_finished(run)
            archives = list((base / "archive").glob("*"))
            self.assertEqual(len(archives), 1)
            self.assertTrue((archives[0] / "rules.json").exists())
            self.assertFalse((base / "rules.json").exists())

    def test_artifact_replay_returns_embedded_images_and_deletes_archives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "demo" / "archive" / "saved-run"
            memory = EngineMemory(base / "timeline.jsonl")
            state = EngineState(
                grid=((2, 0),),
                state=GameState.PLAYING,
                levels_completed=0,
                win_levels=1,
                game_id="demo",
                image=EngineImage(
                    mime_type="image/png",
                    data_url="data:image/png;base64,replay-frame",
                ),
            )
            memory.append_initial_state(state)
            memory.append_action_result(
                GameAction.ACTION4,
                state,
                predictions=[state],
                prediction_rule_ids=["G000001"],
                decision_source="exploratory_probe",
                prediction_recorded=True,
            )
            (base / "llm_attempt.jsonl").write_text(
                '{"purpose":"subgoal","parsed_response":'
                '{"subgoal":"move right to inspect the empty cell"},'
                '"raw_response":"{\\"subgoal\\":\\"move right to inspect the empty cell\\"}"}\n'
                '{"purpose":"action plan","parsed_response":'
                '{"plan":["ACTION4"]},'
                '"raw_response":"{\\"plan\\":[\\"ACTION4\\"]}"}\n',
                encoding="utf-8",
            )
            (base / "legend.json").write_text(
                '{"0":"Background","2":"Player"}', encoding="utf-8"
            )
            (base / "natural_rules.json").write_text(
                '{"rules":[{"id":"N000001","summary":"Player moved right.",'
                '"evidence_ids":["T000001"],"status":"compiled"}]}',
                encoding="utf-8",
            )
            (base / "rules.json").write_text(
                '{"rules":[{"ruleID":"G000001","natural_language":"Move right.",'
                '"logical_rule":{"action":"ACTION4"},'
                '"evidence":{"supports":["T000001"]}}]}',
                encoding="utf-8",
            )
            client = TestClient(create_app(manager(tmpdir)))

            listed = client.get(
                "/api/workbench/artifacts", params={"game_id": "demo"}
            ).json()["artifacts"]
            self.assertEqual(listed[0]["id"], "saved-run")
            replay = client.get(
                "/api/workbench/artifacts/saved-run",
                params={"game_id": "demo"},
            ).json()
            self.assertEqual(len(replay["frames"]), 2)
            self.assertEqual(
                replay["frames"][0]["state"]["image"]["data_url"],
                "data:image/png;base64,replay-frame",
            )
            self.assertEqual(replay["legend"]["2"], "Player")
            self.assertEqual(replay["frames"][1]["transition_id"], "T000001")
            prediction = replay["frames"][1]["prediction"]
            self.assertTrue(prediction["recorded"])
            self.assertEqual(prediction["result"], "exact_match")
            self.assertEqual(prediction["rule_ids"], ["G000001"])
            self.assertEqual(prediction["decision_source"], "exploratory_probe")
            self.assertEqual(prediction["closest_cell_differences"], [])
            self.assertEqual(
                replay["frames"][1]["plan"],
                {
                    "transition_id": "T000001",
                    "subgoal": "move right to inspect the empty cell",
                    "actions": ["ACTION4"],
                    "source": "exploratory_probe",
                    "origin": "raw_log_backfill",
                    "step_index": 1,
                    "total_steps": 1,
                },
            )
            self.assertTrue((base / "plan.json").exists())
            self.assertEqual(replay["natural_rules"][0]["id"], "N000001")
            self.assertEqual(replay["logical_rules"][0]["ruleID"], "G000001")
            deleted = client.delete(
                "/api/workbench/artifacts/saved-run",
                params={"game_id": "demo"},
            )
            self.assertEqual(deleted.status_code, 204)
            self.assertFalse(base.exists())

    def test_concurrent_start_is_rejected_and_stop_is_cooperative(self):
        BlockingLoop.release.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            run_manager = manager(tmpdir, BlockingLoop)
            client = TestClient(create_app(run_manager))
            payload = {
                "backend": "puzzlescript",
                "game_id": "demo",
                "max_steps": 10,
                "memory_mode": "resume",
            }
            first = client.post("/api/workbench/runs", json=payload)
            self.assertEqual(first.status_code, 202)
            self.assertEqual(client.post("/api/workbench/runs", json=payload).status_code, 409)
            run_id = first.json()["run_id"]
            stopped = client.post(f"/api/workbench/runs/{run_id}/stop")
            self.assertEqual(stopped.status_code, 202)
            run = run_manager.get(run_id)
            wait_finished(run)
            self.assertEqual(run.status, "cancelled")

    def test_provider_errors_are_sanitized_in_snapshots_and_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_manager = manager(tmpdir, ProviderFailureLoop)
            run = run_manager.start(
                {
                    "backend": "puzzlescript",
                    "game_id": "demo",
                    "max_steps": 1,
                    "memory_mode": "resume",
                }
            )
            wait_finished(run)
            snapshot = run.snapshot()
            serialized = str(snapshot)
            self.assertIn("LLM provider error (403)", snapshot["error"])
            self.assertNotIn("secret-key-id", serialized)
            self.assertNotIn("provider.invalid", serialized)


if __name__ == "__main__":
    unittest.main()
