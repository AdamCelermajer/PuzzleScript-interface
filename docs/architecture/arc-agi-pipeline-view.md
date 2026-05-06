# ARC-AGI Architecture Pipeline View

This note is a companion to `arc-agi-architecture.svg`. The SVG uses the richer layered view. This file keeps the simpler pipeline view available when the intended data flow needs to be explained quickly.

## Linear Pipeline

```mermaid
flowchart TD
    Environment[Environment surface<br/>PuzzleScript or ARC-AGI-3]
    Agent[Agent reasoning core<br/>LLM, search, heuristics, rule engine, or learned model]
    Buffer[Transition buffer<br/>state before, action, state after, reward/status]
    Rules[Rule induction]
    Subgoals[Subgoal engineering]
    Context[Active task context<br/>known rules, hypotheses, goals, recent observations]
    Memory[Persistent knowledge store<br/>validated rules, abstractions, priors, solved patterns]

    Environment -->|observation| Agent
    Agent -->|action| Environment
    Agent -->|record executed transition| Buffer
    Buffer -->|evidence for mechanics| Rules
    Buffer -->|evidence for goals and probes| Subgoals
    Rules -->|candidate or validated rules| Context
    Subgoals -->|goals, probes, strategy hints| Context
    Context -->|context guides reasoning| Agent
    Memory -->|retrieve relevant prior knowledge| Context
    Context -->|promote validated discoveries| Memory
```

## Important Distinctions

The reasoning core is intentionally not named "LLM reasoning core". An LLM can be one implementation mechanism, but the architecture should stay open to search, heuristics, learned models, and explicit rule engines.

The active task context and persistent knowledge store are linked, but they are not the same object. The active context is the working state for the current environment: known rules, current hypotheses, recent observations, and current goals. The persistent store is longer-lived memory: validated rules, reusable abstractions, prior solved patterns, and cross-task knowledge.

The transition buffer is the shared evidence source for both rule induction and subgoal engineering. Rule induction uses transitions to infer mechanics. Subgoal engineering uses the same evidence to create useful probes, local objectives, and strategy hints.

The target architecture does not require periodic refinement. The current implementation may batch some inference work, but the diagram should leave the trigger open: after every transition, after meaningful novelty, when confidence changes, or by another policy selected later.
