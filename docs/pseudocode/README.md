# Architecture Pseudocode

This folder expands the conceptual architecture in `docs/architecture/arc-agi-architecture.svg`.

The pseudocode is intentionally not production code. It describes the intended responsibilities and data flow for each major component:

- `environment_surface.md` - PuzzleScript / ARC interaction surface.
- `perceive.md` - Converts observations into agent-readable state.
- `transition_history.md` - Stores useful state-action-next-state evidence.
- `active_task_context.md` - Holds the current working beliefs.
- `reasoning.md` - Induces, compresses, refines, and verifies rules.
- `subgoal_planning.md` - Chooses useful goals, probes, and action plans.
- `act.md` - Selects and executes the next environment action.
- `persistent_knowledge_store.md` - Reads and writes reusable knowledge.
- `learning_loop.md` - Shows how the components cooperate in one run.

Current implementation details may differ. For example, the current agent still does some batch-style analysis, while the target architecture leaves the trigger policy open.
