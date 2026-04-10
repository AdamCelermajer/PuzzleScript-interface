# PuzzleScript Benchmark Scaffold

This folder is reserved for curated PuzzleScript benchmark manifests.

For now it only defines the on-disk shape that the ARC-compatible PuzzleScript
service will grow into:

- versioned `game_id` values such as `sokoban-basic-v1`
- per-game metadata and tags
- future split definitions and exclusions
- optional run budgets such as `max_steps`

The environment restructure is the current priority, so scoring and benchmark
execution are intentionally deferred.
