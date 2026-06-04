# LIVE Sokoban Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one readable LIVE-style Sokoban POC under `studies/LIVE_framework`.

**Architecture:** Start from the existing symbol-percept experiment, rename it as the only supported LIVE Sokoban path, and add sibling-rule revision on prediction failure. Keep the runner and artifacts simple and visible.

**Tech Stack:** Python standard library, `unittest`, existing ARC-compatible `ArcadeEnv`.

---

### Task 1: Add Focused Behavior Tests

**Files:**
- Create: `tests/studies/LIVE_framework/test_percepts.py`
- Create: `tests/studies/LIVE_framework/test_rules.py`
- Create: `tests/studies/LIVE_framework/test_runner.py`

- [ ] Add percept tests copied from the existing percept experiment, updated to import `studies.LIVE_framework`.
- [ ] Add rule tests for learned action deltas, coordinate-general line rules, persistence without object names, and sibling creation after prediction failure.
- [ ] Add runner tests for planning reuse and exploration priorities.
- [ ] Run the new tests and confirm they fail before production code exists.

### Task 2: Create `studies/LIVE_framework`

**Files:**
- Create: `studies/LIVE_framework/model.py`
- Create: `studies/LIVE_framework/perceiver.py`
- Create: `studies/LIVE_framework/rules.py`
- Create: `studies/LIVE_framework/runner.py`
- Create: `studies/LIVE_framework/run.py`
- Create: `studies/LIVE_framework/goals/level1_goal.json`
- Create: `studies/LIVE_framework/__init__.py`

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

- [ ] Document `python -m studies.LIVE_framework.run` as the single LIVE Sokoban POC.
- [ ] State that it uses percepts and sibling-rule revision.

### Task 5: Verify Narrowly

**Files:**
- Run: `python -m unittest discover -s tests/studies/LIVE_framework -p "test_*.py"`
- Run: `python -m studies.LIVE_framework.run --help`
- Run: stale-reference search for removed package names.

- [ ] Confirm new tests pass.
- [ ] Confirm CLI imports and help output work.
- [ ] Confirm no old LIVE package references remain.
