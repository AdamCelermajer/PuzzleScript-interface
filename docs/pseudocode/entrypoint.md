# Entrypoint

## Card Title

**File role** Wire one runnable session

## Pseudocode

```text
cfg <- Config(game, max_steps, backend_url)
run <- WorkbenchRun(cfg, memory_mode)
env <- ArcadeEnv(game_id, backend_url, run.render)
llm <- LlmClient(cfg, run.push_event)
engine <- EngineArchitecture.from_config(cfg, llm, run.push_event)
loop <- RuleReasoningLoop(env, engine, run.push_event, run.stop_event)
run.background_thread <- function: loop.run(max_steps, game_id)
website polls run.snapshot() until completed, failed, or cancelled
```
