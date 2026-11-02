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


LEVEL_DEFAULTS = {"levels": 0, "budgets": "30,50,100,200,500", "skip_below_shortest": False, "max_rounds": 5}


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
    assert HARNESS2.artifact == "" and HARNESS2.check_options({}) == {"k": 1, "recursion": "parallel", "max_steps": 200,
                                                                      "stop_after_levels": 0, **LEVEL_DEFAULTS}
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
    assert argv[argv.index("-m") + 1] == "frameworks.baseline.agent"
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
    assert calls[0][0]["options"] == {"k": 2, "recursion": "sequential", "max_steps": 200, "stop_after_levels": 0,
                                       **LEVEL_DEFAULTS}
    assert calls[0][2] is True


def test_stop_after_levels_reaches_every_player_and_old_runs_still_resume(tmp_path):
    player = FakePlayer()
    adapter = PuzzleScriptAdapter(spec(stop_after_levels=3), tmp_path, player=player)
    adapter.execute(adapter.tasks()[0], None, "base1")
    argv = player.calls[0][0]
    assert argv[argv.index("--stop-after-levels") + 1] == "3"
    plain = PuzzleScriptAdapter(spec(), tmp_path / "other", player=player)
    plain.execute(plain.tasks()[0], None, "base1")
    assert "--stop-after-levels" not in player.calls[-1][0]
    # A run saved before the option existed resumes with its default, not with a changed one.
    saved = {**spec(), "options": {"k": 1, "recursion": "parallel", "max_steps": 200}}
    (tmp_path / "harness2_config.json").write_text(json.dumps(saved))
    HARNESS2.check_restart(spec(), tmp_path)
    with pytest.raises(ValueError, match="options"):
        HARNESS2.check_restart(spec(stop_after_levels=3), tmp_path)


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


def test_trajectory_is_compact_and_keeps_every_game_call(tmp_path):
    from frameworks.harness2.adapter import compact_events, level_times
    rd = tmp_path / "rollouts" / "base1"
    rd.mkdir(parents=True)
    (rd / "result.json").write_text(json.dumps({"status": "completed", "levels_completed": 1, "win_levels": 4,
                                                "action_count": 2, "reason": "step_budget_exhausted"}))
    (rd / "transitions.jsonl").write_text("\n".join(json.dumps(r) for r in (
        {"action_index": 1, "before": {"levels_completed": 0}, "after": {"levels_completed": 0}},
        {"action_index": 2, "before": {"levels_completed": 0}, "after": {"levels_completed": 1}})) + "\n")
    events = [{"type": "reasoning", "text": "x" * 5000},
              {"type": "command", "text": "python game.py do ACTION1",
               "output": "ACTION1: changed (0,1) 2->5\nstate=PLAYING levels=0/4\ngrid:\n" + "1 2 3\n" * 50},
              {"type": "tool", "tool": "read", "text": '{"filePath": "frame.png"}', "output": "Image read successfully"},
              {"type": "usage", "usage": {}}]
    (rd / "agent_events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    adapter = PuzzleScriptAdapter(spec(), tmp_path, player=FakePlayer())
    text = adapter.trajectory(rd, obs_trunc=50_000)
    assert "Levels completed at game action: level 1 at 2." in text and level_times(rd) == [(1, 2)]
    assert "[ACTION] python game.py do ACTION1\n[OBSERVATION] ACTION1: changed (0,1) 2->5\nstate=PLAYING levels=0/4" in text
    assert "grid:" not in text and "…(+4300 chars)" in text and "[ACTION] read:" in text
    assert len(compact_events(rd / "agent_events.jsonl")) < 1200


# Per-level runs: each level one task, rounds at a growing budget.

class FakeLevelPlayer:
    """Solves level L when the budget reaches NEEDS[L] and the harness carries the coach's note."""

    def __init__(self, needs, broken=()):
        self.needs, self.broken, self.calls = needs, set(broken), []

    def __call__(self, argv, run_dir, timeout):
        level, budget = int(argv[argv.index("--start-level") + 1]), int(argv[argv.index("--max-steps") + 1])
        coached = (Path(argv[argv.index("--harness-dir") + 1]) / "AGENTS.md").is_file()
        self.calls.append((level, budget, run_dir.parent.parent.name, run_dir.name, coached))
        if level in self.broken:
            raise RuntimeError("player crashed")
        solved = coached and budget >= self.needs[level]
        actions = min(budget, self.needs[level]) if solved else budget
        (run_dir / "result.json").write_text(json.dumps({
            "status": "completed", "level_solved": solved,
            "levels_completed": level if solved else level - 1,
            "action_count": actions, "reason": "level_target_reached" if solved else "step_budget_exhausted"}))
        (run_dir / "world_model.md").write_text("# Objects\n- red tile\n", encoding="utf-8")


class FakeLevelProposer(FakeProposer):
    def call(self, mission, context_dir, label, **kwargs):
        self.calls.append(label)
        evidence = list((context_dir / "rollouts").glob("*.md"))
        assert evidence and all("Outcome of this run: " in p.read_text() and "the level in" in p.read_text()
                                for p in evidence)
        workspace = context_dir / "harness"
        for stub in workspace.rglob("README.md"):
            stub.unlink()
        (workspace / "systemprompt.md").write_text("Track action outcomes before repeating a plan.\n")
        return Reply(label=label, text="<notes>Use observed transitions.</notes>", ok=True,
                     workspace=workspace, attempts=1)


def level_run(tmp_path, player, **options):
    from frameworks.harness2.run import run_levels
    config = spec(levels=3, budgets="30,50,100", max_rounds=3, **options)
    proposer = FakeLevelProposer()
    factory = lambda *a, **kw: PuzzleScriptAdapter(*a, player=player, **kw)
    result = run_levels(config, tmp_path, adapter_factory=factory, proposer_factory=lambda adapter, rdir: proposer)
    return config, factory, proposer, result


def test_levels_escalate_carry_the_harness_and_reuse_unchanged_rollouts(tmp_path):
    player = FakeLevelPlayer({1: 6, 2: 66, 3: 80})
    config, factory, proposer, result = level_run(tmp_path, player)
    levels = {row["level"]: row for row in result["levels"]}
    # L1: base1 (empty harness) fails at 30; the coached rollouts solve it and agg1 is kept.
    assert levels[1]["solved"] and levels[1]["rounds"] == 1 and levels[1]["kept"] == "agg1"
    # L2 starts at 30 with L1's kept harness; it needs 66, so rounds go 30 -> 50 -> 100.
    assert levels[2]["solved"] and levels[2]["rounds"] == 3 and levels[2]["budget"] == 100
    # L3 starts at the budget L2 ended on and never goes back down.
    assert levels[3]["solved"] and levels[3]["rounds"] == 1 and levels[3]["budget"] == 100
    assert result["levels_completed"] == 3 and result["solved"] and result["action_count"] == 6 + 66 + 80
    l2 = [(budget, label, coached) for level, budget, _, label, coached in player.calls if level == 2]
    # Every L2 harness equals the carried one, so each budget is played once and reused after.
    assert [(budget, coached) for budget, _, coached in l2] == [(30, True), (50, True), (100, True)]
    assert l2[0][1] == "base1" and {l2[1][1], l2[2][1]} <= {"inv1", "dom1"}
    r2 = json.loads((tmp_path / "levels/L2/rounds/R2/round.json").read_text())
    played = l2[1][1]  # inv1 and dom1 play side by side; whichever starts first is played
    assert r2["reused"] == {label: f"R2/{played}" for label in ("inv1", "dom1", "agg1") if label != played}
    assert Path(r2["evidence"]).parts[-3:] == ("R1", "rollouts", "base1")
    assert (tmp_path / "levels/L1/kept/systemprompt.md").read_text().startswith("Track action outcomes")
    assert len(proposer.calls) == 3 * (1 + 3 + 1)
    # Resume: finished levels are read back, nothing is played or coached again.
    from frameworks.harness2.run import run_levels
    calls = len(player.calls)
    again = run_levels(config, tmp_path, resume=True, adapter_factory=factory,
                       proposer_factory=lambda adapter, rdir: proposer)
    assert again["levels_completed"] == 3 and len(player.calls) == calls


def test_unsolved_level_stops_at_the_round_cap_and_a_broken_level_does_not_stop_the_run(tmp_path):
    player = FakeLevelPlayer({1: 500, 2: 6, 3: 6}, broken={2})
    _, _, _, result = level_run(tmp_path, player)
    levels = {row["level"]: row for row in result["levels"]}
    assert not levels[1]["solved"] and levels[1]["rounds"] == 3 and levels[1]["status"] == "completed"
    assert levels[2]["status"] == "error" and "base rollout" in levels[2]["error"]
    assert levels[3]["solved"] and levels[3]["budget"] == 100 and result["levels_completed"] == 1
    # The last budget repeats at the cap; unsolved rounds keep the composer's harness.
    assert [json.loads((tmp_path / f"levels/L1/rounds/R{n}/round.json").read_text())["kept"] for n in (1, 2, 3)] \
        == ["agg1"] * 3


def test_level_options_reach_the_player_and_runner(tmp_path):
    from frameworks.harness2.run import keep, parse_budgets
    argv = HARNESS2.entry(spec(levels=4, skip_below_shortest=True), False, tmp_path, Path("/parent"))
    assert argv[argv.index("--levels") + 1] == "4" and "--skip-below-shortest" in argv
    assert "False" not in argv and "True" not in argv
    assert parse_budgets("30, 50,500") == [30, 50, 500]
    for bad in ("", "50,30", "0,10", "x"):
        with pytest.raises(ValueError):
            parse_budgets(bad)
    solved = {"status": "completed", "level_solved": True, "levels_completed": 1}
    runs = {}
    for label, actions, ok in (("base1", 9, True), ("inv1", 9, True), ("agg1", 12, True), ("dom1", 3, False)):
        rd = tmp_path / label
        rd.mkdir()
        (rd / "result.json").write_text(json.dumps({**solved, "action_count": actions}))
        runs[label] = RunView(label, label, rd, ok=ok, delivered=ok)
    assert keep(runs).label == "base1"  # equal actions: the starting harness


def test_skip_below_shortest_starts_each_level_at_a_budget_that_can_solve_it(tmp_path):
    player = FakeLevelPlayer({1: 6, 2: 33, 3: 66})  # Modality's shortest solutions
    _, _, _, result = level_run(tmp_path, player, skip_below_shortest=True)
    assert [(row["budget"], row["rounds"]) for row in result["levels"]] == [(30, 1), (50, 1), (100, 1)]
    assert [budget for level, budget, _, label, _ in player.calls if label == "base1"] == [30, 50, 100]


def test_run_page_reads_levels_rounds_and_reused_rollouts(tmp_path):
    from workbench import catalog
    from workbench.harness2_view import levels as level_view

    class ConfiguredPlayer(FakeLevelPlayer):
        def __call__(self, argv, run_dir, timeout):
            (run_dir / "run_config.json").write_text("{}")
            super().__call__(argv, run_dir, timeout)

    root = tmp_path / "output/harness2/levels"
    _, _, _, result = level_run(root, ConfiguredPlayer({1: 6, 2: 66, 3: 80}))
    view = level_view(root)
    assert [row["level"] for row in view] == [1, 2, 3] and all(row["solved"] for row in view)
    assert view[0]["kept_files"]["systemprompt.md"].startswith("Track action outcomes")
    rounds = view[1]["rounds"]
    assert [r["round"] for r in rounds] == ["R1", "R2", "R3"] and [r["budget"] for r in rounds] == [30, 50, 100]
    reused = {r["label"]: r["reused"] for r in rounds[1]["rollouts"]}
    assert sorted(reused) == ["agg1", "dom1", "inv1"] and list(reused.values()).count(None) == 1
    assert all(r["result"]["status"] == "completed" for r in rounds[1]["rollouts"])
    progress = catalog.harness2_rollouts(root, {"levels": 3})
    assert progress["total"] is None and progress["current"] is None and progress["done"] == 6  # the rest were reused
