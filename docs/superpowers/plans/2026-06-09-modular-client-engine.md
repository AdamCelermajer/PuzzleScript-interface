# Modular Client Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the current client engine so the code reflects the simple module architecture: environment, perception, memory, rulebook, induction, planning, actions, and loop.

**Architecture:** Preserve current behavior and CLI while moving orchestration out of `agent.py` into focused modules. Keep compatibility imports during the refactor, but make `loop.py` the real runtime center.

**Tech Stack:** Python, pytest/unittest, current `client.engine` modules.

---

### File Structure

- Create: `client/engine/environment.py` for a narrow environment facade over `BaseEnv`.
- Create: `client/engine/perception.py` to expose the perception boundary and keep compatibility with `perceiver.py`.
- Create: `client/engine/memory.py` for transition evidence access.
- Create: `client/engine/rulebook.py` for rule prediction/update operations.
- Create: `client/engine/planning.py` for the current rule-first planner facade.
- Create: `client/engine/actions.py` for executing a decision and returning a before/after outcome.
- Create: `client/engine/loop.py` for the learn/solve orchestration.
- Modify: `client/engine/architecture.py` to compose the new modules.
- Modify: `client/engine/agent.py` into a compatibility shim.
- Modify: `client/run_arc_agent.py` to use `RuleReasoningLoop`.
- Add/modify tests under `tests/client/`.

### Task 1: Add Step Data And Action Execution

**Files:**
- Create: `client/engine/actions.py`
- Test: `tests/client/test_modular_engine_loop.py`

- [ ] **Step 1: Write failing test**

```python
def test_action_executor_returns_before_after_outcome():
    env = FakeEnv([frame_after])
    perceiver = Perceiver()
    decision = PlanDecision(GameAction.ACTION4, "test", [GameAction.ACTION4])

    outcome = ActionExecutor(env, perceiver).execute(frame_before, state_before, decision)

    assert outcome.before_frame is frame_before
    assert outcome.before_state == state_before
    assert outcome.action == GameAction.ACTION4
    assert outcome.after_frame is frame_after
    assert outcome.after_state.grid == ((0, 2), (0, 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/client/test_modular_engine_loop.py::ModularEngineLoopTests::test_action_executor_returns_before_after_outcome -q`
Expected: FAIL because `client.engine.actions` does not exist.

- [ ] **Step 3: Implement minimal code**

Define `StepOutcome` and `ActionExecutor.execute()` in `client/engine/actions.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/client/test_modular_engine_loop.py::ModularEngineLoopTests::test_action_executor_returns_before_after_outcome -q`
Expected: PASS.

### Task 2: Add Memory And Rulebook Facades

**Files:**
- Create: `client/engine/memory.py`
- Create: `client/engine/rulebook.py`
- Test: `tests/client/test_modular_engine_loop.py`

- [ ] **Step 1: Write failing tests**

```python
def test_engine_memory_records_transition():
    memory = EngineMemory(TransitionHistory(path))
    record = memory.record_transition(state_before, GameAction.ACTION4, state_after)
    assert record.id == "T000001"
    assert memory.recent(1) == [record]

def test_engine_rulebook_records_prediction_and_observation():
    rulebook = EngineRulebook(RuleLibrary(tmp_path))
    rulebook.record_prediction_result(state_before, GameAction.ACTION4, state_after, [])
    rule = rulebook.record_observed_transition(record)
    assert rule.status == "verified"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/client/test_modular_engine_loop.py -q`
Expected: FAIL because new facades do not exist.

- [ ] **Step 3: Implement facades**

Wrap existing `TransitionHistory` and `RuleLibrary` without changing their persistence formats.

- [ ] **Step 4: Run tests**

Run: `pytest tests/client/test_modular_engine_loop.py -q`
Expected: PASS for new tests.

### Task 3: Add Loop Module And Shrink Agent Orchestration

**Files:**
- Create: `client/engine/loop.py`
- Modify: `client/engine/architecture.py`
- Modify: `client/engine/agent.py`
- Test: `tests/client/test_modular_engine_loop.py`, existing `tests/client/test_agent.py`

- [ ] **Step 1: Write failing loop test**

```python
def test_rule_reasoning_loop_records_one_learning_step():
    loop = RuleReasoningLoop(...)
    loop.run_learning(max_steps=1)
    assert loop.memory.recent(1)[0].action == GameAction.ACTION4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/client/test_modular_engine_loop.py::ModularEngineLoopTests::test_rule_reasoning_loop_records_one_learning_step -q`
Expected: FAIL because `RuleReasoningLoop` does not exist.

- [ ] **Step 3: Implement `RuleReasoningLoop`**

Move the current learn/solve orchestration from `agent.py` into `loop.py`, but keep `run_learning_loop`, `run_solving_loop`, and `Agent` as compatibility wrappers in `agent.py`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/client/test_modular_engine_loop.py tests/client/test_agent.py tests/client/test_engine_architecture.py -q`
Expected: PASS.

### Task 4: Add Named Facade Modules

**Files:**
- Create: `client/engine/environment.py`
- Create: `client/engine/perception.py`
- Create: `client/engine/planning.py`
- Modify: `client/engine/architecture.py`
- Test: `tests/client/test_modular_engine_loop.py`

- [ ] **Step 1: Write import/contract test**

```python
def test_named_architecture_modules_are_importable():
    from client.engine.environment import EnvironmentSurface
    from client.engine.perception import Perception
    from client.engine.planning import RuleFirstPlanner
    assert EnvironmentSurface
    assert Perception
    assert RuleFirstPlanner
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/client/test_modular_engine_loop.py::ModularEngineLoopTests::test_named_architecture_modules_are_importable -q`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement facades**

Expose named module boundaries while delegating to existing `BaseEnv`, `Perceiver`, and `Planner`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/client/test_modular_engine_loop.py tests/client/test_agent.py tests/client/test_engine_architecture.py -q`
Expected: PASS.

### Task 5: Wire CLI To The New Loop

**Files:**
- Modify: `client/run_arc_agent.py`
- Test: `tests/client/test_entrypoints.py`

- [ ] **Step 1: Write/update entrypoint expectation**

Patch the new loop entrypoint or compatibility wrapper so the test proves the CLI still chooses learn/solve correctly.

- [ ] **Step 2: Run entrypoint test**

Run: `pytest tests/client/test_entrypoints.py -q`
Expected: current tests pass or fail only where imports changed.

- [ ] **Step 3: Wire `run_arc_agent.py` through new runtime**

Import `RuleReasoningLoop` and construct it from the architecture.

- [ ] **Step 4: Run focused client tests**

Run: `pytest tests/client -q`
Expected: PASS.

### Self-Review

- Spec coverage: the plan creates each requested module and removes `agent.py` as the real orchestrator.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: shared types are `PlanDecision`, `StepOutcome`, `TransitionRecord`, `EngineState`, and existing `FrameData`.
