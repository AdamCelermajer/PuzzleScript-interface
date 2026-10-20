import json
from pathlib import Path

import pytest

from harness2.core import context, tree
from harness2.core.proposer import Reply
from harness2.core.spec import BenchmarkAdapter, RunView

from frameworks.harness2.adapter import PuzzleScriptAdapter, read_result
from frameworks.harness2.framework import HARNESS2
from frameworks.harness2.render import render_workspace
from frameworks.harness2.run import adopt, main, run


def spec(**options):
    return {"schema": "run-spec-v2", "framework": "harness2", "harness": "opencode",
            "model": "openrouter/qwen/qwen3.8-27b", "effort": "low",
            "optimizer_model": "openrouter/anthropic/claude-opus-4.8", "optimizer_effort": "high",
            "game_id": "ps_modality-v1", "backend_url": "http://localhost:8000", "provider": "",
            "max_wall_seconds": 0, "options": HARNESS2.check_options(options)}


class FakePlayer:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, run_dir, timeout):
        self.calls.append((argv, run_dir, timeout))
        label = run_dir.name
        levels = 3 if label.startswith("inv") else 0 if label == "final" else 1
        result = {"status": "completed", "solved": False, "levels_completed": levels,
                  "win_levels": 5, "action_count": 12, "reason": "step_budget_exhausted"}
        (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (run_dir / "raw").mkdir()
        (run_dir / "raw" / "turn-1.jsonl").write_text("\n".join(json.dumps(event) for event in (
            {"type": "text", "part": {"type": "text", "text": "Trying the first action."}},
            {"type": "tool_use", "part": {"type": "tool", "tool": "bash", "state": {
                "status": "completed", "input": {"command": "python game.py do ACTION1"},
                "output": "ACTION1: changed (0,1) 2->5"}}})) + "\n")
        (run_dir / "world_model.md").write_text("# Objects\n- red tile\n", encoding="utf-8")


class FakeProposer:
    def __init__(self):
        self.calls = []

    def call(self, mission, context_dir, label, **kwargs):
        self.calls.append(label)
        context.assert_no_grader_verdicts(context_dir)
        evidence = list((context_dir / "rollouts").glob("*.md"))
        assert evidence and all("Outcome of this run: completed" in p.read_text() for p in evidence)
        pool = list((context_dir / "pool").glob("*/rollout.md"))
        if label.startswith(("agg", "c")):
            assert len(pool) >= 2
        for path in pool:
            assert "Outcome of this run: completed" in path.read_text()
        workspace = context_dir / "harness"
        # Upstream's README-stub exclusion compares native strings with POSIX paths;
        # strip scaffolding from this fake harvest so the offline test also runs on Windows.
        for stub in workspace.rglob("README.md"):
            stub.unlink()
        (workspace / "systemprompt.md").write_text("Track action outcomes before repeating a plan.\n")
        return Reply(label=label, text="<notes>Use observed transitions.</notes>", ok=True,
                     workspace=workspace, attempts=1)


def test_declaration_and_entry():
    assert HARNESS2.id == "harness2" and HARNESS2.optimizer and HARNESS2.restart == "resume"
    assert HARNESS2.artifact == "" and HARNESS2.check_options({}) == {"k": 1, "recursion": "parallel", "max_steps": 200}
    argv = HARNESS2.entry(spec(k=2), True, Path("/results"), Path("/parent"))
    for flag, value in (("--k", "2"), ("--optimizer-effort", "high"), ("--recursion", "parallel"),
                        ("--max-steps", "200"), ("--harness", "opencode")):
        assert argv[argv.index(flag) + 1] == value
    assert argv[0] == "frameworks.harness2.run" and argv[-1] == "--resume"
    with pytest.raises(ValueError, match="opencode"):
        HARNESS2.entry({**spec(), "harness": "bare"}, False, Path("/results"), Path("/parent"))


def test_adapter_protocol_trajectory_and_deliverables(tmp_path):
    player = FakePlayer()
    adapter = PuzzleScriptAdapter(spec(), tmp_path, player=player)
    assert isinstance(adapter, BenchmarkAdapter)
    assert adapter.tasks() == ["ps_modality-v1"] and adapter.domain_of(adapter.tasks()[0]) == "puzzlescript"
    assert adapter.task_files(adapter.tasks()[0]) is None
    assert not any(tree.read_tree(adapter.substrate.surface(), adapter.base_harness()).values())
    rd = adapter.execute(adapter.tasks()[0], None, "base1")
    assert adapter.delivered(rd)
    text = adapter.trajectory(rd, obs_trunc=10_000)
    assert text.startswith("Outcome of this run: completed 1 of 5 levels in 12 game actions (ended: step_budget_exhausted).")
    assert "python game.py do ACTION1" in text and "changed (0,1) 2->5" in text
    assert adapter.deliverable_text(rd) == "# Objects\n- red tile\n"
    assert adapter.deliverable_files(rd) == {"world_model.md": adapter.deliverable_text(rd)}
    assert "levels_completed" not in adapter.deliverable_text(rd)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "trajectory.md").write_text(text)
    context.assert_no_grader_verdicts(evidence)
    assert adapter.score(rd, adapter.tasks()[0])["levels_completed"] == 1
    argv = player.calls[0][0]
    assert argv[argv.index("-m") + 1] == "frameworks.harness2.player"
    assert argv[argv.index("--harness") + 1] == "opencode"
    assert list((rd / "seed").iterdir()) == []  # stock OpenCode: the base harness adds no files
    (rd / "world_model.md").unlink()
    assert adapter.deliverable_text(rd) == "" and adapter.deliverable_files(rd) == {}


def test_execute_reuses_finished_and_retries_interrupted(tmp_path):
    player = FakePlayer()
    adapter = PuzzleScriptAdapter(spec(), tmp_path, player=player)
    rd = adapter.execute(adapter.tasks()[0], None, "base1")
    assert adapter.execute(adapter.tasks()[0], None, "base1") == rd and len(player.calls) == 1
    (rd / "result.json").write_text('{"status": "cancelled"}')
    (rd / "stale.txt").write_text("discard me")
    adapter.execute(adapter.tasks()[0], None, "base1")
    assert len(player.calls) == 2 and not (rd / "stale.txt").exists()
    with pytest.raises(ValueError, match="run id"):
        adapter.execute(adapter.tasks()[0], None, "../escape")


@pytest.mark.parametrize("bad", [{"../secret.py": ""}, {"rogue.txt": ""},
                                  {"systemprompt.md": '"pass_rate"'}, {"scripts/broken.py": "x = ("}])
def test_validate_tree_rejects_invalid_harness(tmp_path, bad):
    adapter = PuzzleScriptAdapter(spec(), tmp_path)
    with pytest.raises(ValueError):
        adapter.validate_tree(bad)


def test_render_full_surface(tmp_path):
    source = tmp_path / "tree"
    source.mkdir()
    files = {"systemprompt.md": "First instruction", "guardrails.md": "Second instruction",
             "skills/plan/SKILL.md": "---\nname: plan\ndescription: Planning\n---\nPlan.",
             "skills/plan/scripts/check.py": "print(1)",
             "sub_agents/think/AGENT.md": "---\nmode: subagent\ndescription: Think\n---\nThink.",
             "scripts/check.py": "print(1)", "plugin/check.ts": "export const Check = async () => ({})"}
    for name, body in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    result = render_workspace(source, tmp_path / "seed")
    assert (result / "AGENTS.md").read_text() == "First instruction\n\nSecond instruction\n"
    for name in (".opencode/skills/plan/SKILL.md", ".opencode/skills/plan/scripts/check.py",
                 ".opencode/agents/think.md", ".opencode/plugins/check.ts", "scripts/check.py"):
        assert (result / name).is_file()


def view(root, label, levels, actions, *, ok=True):
    rd = root / label
    rd.mkdir()
    (rd / "result.json").write_text(json.dumps({"status": "completed", "levels_completed": levels,
                                               "action_count": actions}))
    return RunView(label, label, rd, ok=ok, delivered=ok)


@pytest.mark.parametrize("levels,actions,expected", [(2, 4, "inv1"), (1, 4, "inv1"), (1, 5, "base1"), (0, 1, "base1")])
def test_adoption_tiebreaks_and_nonfinal_candidates(tmp_path, levels, actions, expected):
    base = view(tmp_path, "base1", 1, 5)
    inv = view(tmp_path, "inv1", levels, actions)
    failed = view(tmp_path, "agg1", 99, 1, ok=False)
    assert adopt({r.label: r for r in (inv, base, failed)}).label == expected


def test_adoption_requires_a_finished_rollout(tmp_path):
    failed = view(tmp_path, "inv1", 99, 1, ok=False)
    with pytest.raises(RuntimeError, match="No completed"):
        adopt({failed.label: failed})


@pytest.mark.parametrize("mode,k", [("parallel", 1), ("sequential", 1), ("parallel", 2), ("sequential", 2)])
def test_offline_driver_all_rollouts_and_fresh_final(tmp_path, mode, k):
    config, player, proposer = spec(recursion=mode, k=k), FakePlayer(), FakeProposer()
    adapter = PuzzleScriptAdapter(config, tmp_path, player=player)
    result = run(config, tmp_path, adapter=adapter, proposer=proposer)
    assert result["levels_completed"] == 0 and result["best_of_pool_levels"] == 3
    assert result["adopted_label"] == "inv1" and result["base_levels"] == [1] * k
    assert len(result["rollouts"]) == 4 * k and len(player.calls) == 4 * k + 1
    assert len(proposer.calls) == 3 * k and not result["improver"]["fell_back"]
    assert (tmp_path / "adopted/systemprompt.md").read_text().startswith("Track action outcomes")
    for name in ("harness2_config.json", "adoption.json", "recursion.json", "result.json", "rollouts/final/result.json"):
        assert (tmp_path / name).is_file()
    saved = json.loads((tmp_path / "result.json").read_text())
    assert saved["status"] == "completed" and saved["action_count"] == 12 and saved["solved"] is False
    # Completed players, including final, are never charged again on resume.
    again = run(config, tmp_path, resume=True, adapter=adapter, proposer=proposer)
    assert again["levels_completed"] == 0 and len(player.calls) == 4 * k + 1
    with pytest.raises(ValueError, match="use --resume"):
        run(config, tmp_path, adapter=adapter, proposer=proposer)
    with pytest.raises(ValueError, match="options"):
        HARNESS2.check_restart(spec(k=5), tmp_path)


def test_catalog_discovers_framework_without_rollout_duplicates(tmp_path):
    from workbench import catalog

    root = tmp_path / "output/harness2/offline"
    root.mkdir(parents=True)
    config = spec()
    (root / "run_spec.json").write_text(json.dumps(config))
    player = FakePlayer()
    run(config, root, adapter=PuzzleScriptAdapter(config, root, player=player), proposer=FakeProposer())
    assert catalog.discover(tmp_path)[0] == [root]
    rows = catalog.snapshot(tmp_path, containers={})["runs"]
    assert len(rows) == 1
    assert rows[0]["framework"] == "harness2" and rows[0]["variant"] == "Harness²"
    assert rows[0]["levels"] == 0 and rows[0]["actions"] == 12 and rows[0]["status"] == "completed"


def test_main_builds_spec_from_entry_argv(tmp_path, monkeypatch):
    import frameworks.harness2.run as module

    calls = []
    monkeypatch.setattr(module, "run", lambda config, root, resume=False: calls.append((config, root, resume)) or
                        {"levels_completed": 1, "adopted_label": "base1", "final_run": "final"})
    argv = HARNESS2.entry(spec(k=2, recursion="sequential"), True, tmp_path, Path("/parent"))
    main(argv[1:])
    assert calls[0][0]["options"] == {"k": 2, "recursion": "sequential", "max_steps": 200}
    assert calls[0][2] is True


def test_installed_proposer_uses_private_config_and_preserves_credentials(tmp_path, monkeypatch):
    from frameworks.harness2.proposer import InstalledProposer
    from harnesses.opencode import OpenCodeSession
    from harnesses.base import TurnResult

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("HARNESS_ALLOW_HOST", "1")
    monkeypatch.setenv("HARNESS_PRIVATE_ROOT", str(tmp_path / "private"))
    adapter = PuzzleScriptAdapter(spec(), tmp_path / "run")
    proposer = InstalledProposer(adapter.spec.channels["proposer"], audit_dir=tmp_path / "audit")

    def turn(session, instruction, images=(), timeout=None):
        config = json.loads(Path(session.env["OPENCODE_CONFIG"]).read_text())
        assert config["agent"]["build"]["steps"] == 120
        assert session.env["OPENROUTER_API_KEY"] == "test-key"
        assert session.model == spec()["optimizer_model"] and session.effort == "high"
        assert all(str(tmp_path / "private") in session.env[name]
                   for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"))
        command = session.command(instruction, [])
        assert "bun" not in command and "--variant" in command and command[1] == "run"
        assert "Read MISSION.md" in instruction and timeout == 10
        return TurnResult(text="<notes>Done.</notes>", session_id="x", usage={"cost_usd": 0.1})

    monkeypatch.setattr(OpenCodeSession, "turn", turn)
    cwd = tmp_path / "session"
    cwd.mkdir()
    assert proposer._opencode(cwd, "Do this.", "System", 10) == ("<notes>Done.</notes>", 0.1, "")
