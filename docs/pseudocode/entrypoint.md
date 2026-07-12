# Entrypoint

## Card Title

**File role** Wire one runnable session

## Pseudocode

```text
cfg <- Config(game, max_steps, backend_url)
dashboard <- ScreenDashboard(game_id)
env <- ArcadeEnv(game_id, backend_url, dashboard.render)
llm <- LlmClient(cfg, dashboard.push_event)
engine <- EngineArchitecture.from_config(cfg, llm, dashboard.push_event)
loop <- RuleReasoningLoop(env, engine.perceiver, engine.memory, engine.rulebook, engine.planner, engine.inducer, dashboard, dashboard.push_event)
dashboard.run_engine(function: loop.run(max_steps, game_id))
```
