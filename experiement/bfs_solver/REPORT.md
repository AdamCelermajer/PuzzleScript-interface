# PuzzleScript BFS Sample Report

## Configuration

- Sample seed: `3838`
- Sample size: 30
- Level: first playable level of each game
- Per-game limits: 100,000 unique states or 10.0 seconds
- Actions: UP, DOWN, LEFT, RIGHT, ACTION
- Loop filtering: exact compact-state duplicate detection
- Eligible games: parsed, non-empty formal WINCONDITIONS, deterministic turn-based source, no checkpoint token

## Dataset scan

- Script files: 193
- Eligible deterministic goal-defined games: 137
- Excluded without formal goals: 14
- Excluded unsupported random/realtime/checkpoint games: 42
- Parse errors: 0

## Summary

- Solved: **13/30**
- Independently replay-verified: **13/13**
- Total attempted transitions: 35,448
- Total engine actions including prefix replay: 314,979
- Aggregate search throughput: 185 transitions/s
- Median per-game search throughput: 140 transitions/s
- Aggregate raw engine throughput: 1654 actions/s
- Median per-game raw engine throughput: 929 actions/s

For correctness, each attempted BFS edge starts a fresh engine, replays the node's action prefix, and then applies the candidate action. `engine actions` includes that prefix-replay work; `attempted transitions` counts only candidate BFS edges.

## Simulator verdict

- The engine itself is usable for modest forward simulation: 1654 actions/s in aggregate on this sample.
- Correct baseline BFS is much slower: 185 new edges/s, with 8.9 engine actions executed per candidate edge because of prefix replay.
- Therefore this engine is fast enough for small first levels and a baseline experiment, but not for scalable uninformed BFS over most games. A trustworthy fast solver needs an engine-supported clone/restore API that captures all transition-relevant rule state, or heuristic search that expands far fewer nodes.

## Solved games

| Game | Level index | Optimal actions | Expanded | Transitions | Search ms | Transitions/s |
|---|---:|---:|---:|---:|---:|---:|
| ps_coin_counter-v1 | 0 | 9 | 14 | 69 | 584.9 | 118 |
| ps_enqueue-v1 | 0 | 7 | 21 | 105 | 343.7 | 306 |
| ps_spacekoban-v1 | 0 | 1 | 1 | 4 | 17.5 | 228 |
| ps_fatigued_square_maze-v1 | 1 | 12 | 136 | 678 | 801.3 | 846 |
| ps_knightoban-v1 | 1 | 20 | 888 | 4,440 | 8747.4 | 508 |
| ps_icecrates-v1 | 1 | 4 | 10 | 46 | 106.7 | 431 |
| ps_atlas_shrank-v1 | 1 | 6 | 12 | 59 | 832.7 | 71 |
| ps_sokoban_basic-v1 | 0 | 33 | 559 | 2,791 | 1193.3 | 2339 |
| ps_maera_public_works-v1 | 0 | 1 | 1 | 1 | 142.8 | 7 |
| ps_extra_step-v1 | 2 | 9 | 62 | 309 | 5209.4 | 59 |
| ps_moving_target-v1 | 2 | 5 | 23 | 111 | 874.9 | 127 |
| ps_take_heart_lass-v1 | 1 | 3 | 9 | 43 | 118.1 | 364 |
| ps_midas-v1 | 0 | 7 | 170 | 849 | 2987.3 | 284 |

## Unsolved within the bounds

| Game | Level index | Status | Expanded | Unique states | Transitions | Search ms |
|---|---:|---|---:|---:|---:|---:|
| ps_fire_in_winter-v1 | 2 | time_limit | 358 | 588 | 1,788 | 10006.6 |
| ps_punt_mazes-v1 | 1 | time_limit | 308 | 448 | 1,536 | 10002.6 |
| ps_compressed-v1 | 2 | time_limit | 487 | 870 | 2,433 | 10001.6 |
| ps_self_alteration-v1 | 2 | time_limit | 79 | 151 | 395 | 10012.8 |
| ps_wall_shuffle-v1 | 2 | time_limit | 247 | 333 | 1,233 | 10007.1 |
| ps_collapsing_tiles-v1 | 2 | time_limit | 231 | 618 | 1,154 | 10003.2 |
| ps_fuse_to_green-v1 | 2 | time_limit | 203 | 328 | 1,012 | 10004.3 |
| ps_dark_pellets-v1 | 3 | time_limit | 140 | 291 | 698 | 10006.4 |
| ps_wall_virus-v1 | 2 | time_limit | 381 | 532 | 1,904 | 10001.9 |
| ps_infected-v1 | 2 | time_limit | 595 | 1,404 | 2,973 | 10001.3 |
| ps_extra_push-v1 | 2 | time_limit | 175 | 234 | 875 | 10002.2 |
| ps_the_art_of_storage-v1 | 2 | time_limit | 1,049 | 1,907 | 5,242 | 10000.4 |
| ps_side_painting-v1 | 2 | time_limit | 78 | 128 | 388 | 10011.3 |
| ps_on_and_off-v1 | 2 | time_limit | 202 | 344 | 1,009 | 10006.7 |
| ps_rotaters_cause-v1 | 2 | time_limit | 65 | 95 | 325 | 10011.2 |
| ps_the_switch-v1 | 2 | time_limit | 157 | 208 | 785 | 10017.0 |
| ps_some_pits-v1 | 1 | time_limit | 439 | 518 | 2,193 | 10001.5 |

## Interpretation limits

- A solved result is shortest in the five-action input space under the modeled cell state because the frontier is FIFO and duplicate filtering stores exact compact cell states.
- Compact states include both sprite membership and per-sprite movement intent. Every reported path must also pass an independent fresh-engine replay check.
- A timeout or state-limit result means unknown, not unsolvable.
- This is forward BFS. Generic backward BFS was not used because PuzzleScript exposes successor execution but no complete predecessor generator, and win conditions describe a set of states rather than a concrete goal board.
- The experiment uses the first playable level only; later levels can be substantially harder.
- Games with randomness, realtime execution, checkpoints, or only rule-command goals are outside this first exact-state experiment.
