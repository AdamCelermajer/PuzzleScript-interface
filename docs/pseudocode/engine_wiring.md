# Engine Wiring

## Card Title

**File role** Build the reasoning modules

## Pseudocode

```text
base_path <- game_rules_path(cfg.rules_dir, cfg.game)
memory <- EngineMemory(base_path / "timeline.jsonl")
rulebook <- Rulebook(base_path)
verifier <- RuleVerifier(memory)
inducer <- RuleInducer(llm, rulebook, verifier)
planner <- Planner(rulebook, memory, llm)
return EngineArchitecture(perceiver, memory, rulebook, inducer, planner)
```
