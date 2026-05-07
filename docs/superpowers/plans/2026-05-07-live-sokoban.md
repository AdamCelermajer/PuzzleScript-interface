# LIVE Sokoban Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one readable LIVE-style Sokoban POC under `client/live_sokoban`.

**Architecture:** Start from the existing symbol-percept experiment, rename it as the only supported LIVE Sokoban path, and add sibling-rule revision on prediction failure. Keep the runner and artifacts simple and visible.

**Tech Stack:** Python standard library, `unittest`, existing ARC-compatible `ArcadeEnv`.

---

### Task 1: Add Focused Behavior Tests

**Files:**
- Create: `tests/client/live_sokoban/test_percepts.py`
- Create: `tests/client/live_sokoban/test_rules.py`
- Create: `tests/client/live_sokoban/test_runner.py`

- [ ] Add percept tests copied from the existing percept experiment, updated to import `client.live_sokoban`.
- [ ] Add rule tests for learned action deltas, coordinate-general line rules, persistence without object names, and sibling creation after prediction failure.
- [ ] Add runner tests for planning reuse and exploration priorities.
- [ ] Run the new tests and confirm they fail before production code exists.

### Task 2: Create `client/live_sokoban`

**Files:**
- Create: `client/live_sokoban/model.py`
- Create: `client/live_sokoban/perceiver.py`
- Create: `client/live_sokoban/rules.py`
- Create: `client/live_sokoban/runner.py`
- Create: `client/live_sokoban/run.py`
- Create: `client/live_sokoban/goals/level1_goal.json`
- Create: `client/live_sokoban/__init__.py`

- [ ] Copy the useful symbol-percept model, perceiver, runner, CLI, and goal structure.
- [ ] Rename classes to `LiveRuleModel`, `LiveRule`, `LiveFailure`, and `LiveRunner`.
- [ ] Change output file names to `live_rules.md`, `live_rules.json`, and `live_journal.md`.
- [ ] Add sibling rule fields: `parent_id`, `sibling_group`, `specificity`, `created_from_failure`.
- [ ] On prediction failure, create complementary sibling rules for the successful parent context and observed failure context.
- [ ] Make prediction prefer the most specific matching active rules.

### Task 3: Remove Old Variants

**Files:**
- Delete: `client/helped_live_sokoban`
- Delete: `client/percept_live_sokoban`
- Delete: `client/strict_live_sokoban`
- Delete: `tests/client/helped_live_sokoban`
- Delete: `tests/client/percept_live_sokoban`
- Delete: `tests/client/strict_live_sokoban`

- [ ] Verify deletion paths resolve inside the workspace.
- [ ] Remove the old directories.
- [ ] Search for stale imports and names.

### Task 4: Update Documentation

**Files:**
- Modify: `client/README.md`

- [ ] Document `python -m client.live_sokoban.run` as the single LIVE Sokoban POC.
- [ ] State that it uses percepts and sibling-rule revision.

### Task 5: Verify Narrowly

**Files:**
- Run: `python -m unittest discover -s tests/client/live_sokoban -p "test_*.py"`
- Run: `python -m client.live_sokoban.run --help`
- Run: stale-reference search for removed package names.

- [ ] Confirm new tests pass.
- [ ] Confirm CLI imports and help output work.
- [ ] Confirm no old LIVE package references remain.
