# Complete-machine-state BFS report

- Games attempted: 30/30
- Solved: **21/30**
- Replay verified: **21/21**
- Deepest solution: **33 actions**
- Limits: 60 seconds or 100,000 states per game
- Previous-timeout subset only: false
- Visited-state equivalence: semantic

## Solved

| Game | Depth | Previous -> complete-state time | Change | Expanded | Edges/s |
|---|---:|---:|---:|---:|---:|
| ps_coin_counter-v1 | 9 | 0.6s -> 0.2s | 2.7x faster | 14 | 323 |
| ps_enqueue-v1 | 7 | 0.3s -> 0.3s | 1.3x faster | 21 | 412 |
| ps_punt_mazes-v1 | 11 | 27.2s -> 6.9s | 3.9x faster | 628 | 455 |
| ps_compressed-v1 | 12 | >60s -> 23.2s | newly solved | 3,514 | 757 |
| ps_spacekoban-v1 | 1 | 0.0s -> 0.0s | 1.2x slower | 1 | 191 |
| ps_fatigued_square_maze-v1 | 12 | 0.8s -> 0.5s | 1.6x faster | 136 | 1339 |
| ps_wall_shuffle-v1 | 11 | 15.8s -> 1.9s | 8.5x faster | 339 | 729 |
| ps_knightoban-v1 | 20 | 8.7s -> 4.3s | 2.0x faster | 888 | 1032 |
| ps_icecrates-v1 | 4 | 0.1s -> 0.1s | 1.9x faster | 10 | 643 |
| ps_atlas_shrank-v1 | 6 | 0.8s -> 0.8s | 1.0x faster | 13 | 81 |
| ps_sokoban_basic-v1 | 33 | 1.2s -> 0.3s | 3.4x faster | 559 | 8043 |
| ps_wall_virus-v1 | 30 | >60s -> 29.3s | newly solved | 6,192 | 846 |
| ps_maera_public_works-v1 | 1 | 0.1s -> 0.1s | 1.0x slower | 1 | 7 |
| ps_extra_step-v1 | 9 | 5.2s -> 2.0s | 2.6x faster | 63 | 124 |
| ps_moving_target-v1 | 5 | 0.9s -> 0.5s | 1.9x faster | 24 | 200 |
| ps_on_and_off-v1 | 10 | 51.5s -> 10.5s | 4.9x faster | 555 | 211 |
| ps_take_heart_lass-v1 | 3 | 0.1s -> 0.1s | 1.1x slower | 9 | 338 |
| ps_midas-v1 | 7 | 3.0s -> 2.6s | 1.1x faster | 170 | 321 |
| ps_rotaters_cause-v1 | 12 | >60s -> 51.8s | newly solved | 501 | 39 |
| ps_the_switch-v1 | 16 | >60s -> 10.6s | newly solved | 637 | 241 |
| ps_some_pits-v1 | 23 | >60s -> 38.7s | newly solved | 9,687 | 1002 |

## Unsolved within bounds

| Game | Status | Expanded | Unique states | Seconds |
|---|---|---:|---:|---:|
| ps_fire_in_winter-v1 | time_limit | 4,664 | 7,021 | 60.0 |
| ps_self_alteration-v1 | time_limit | 775 | 1,585 | 60.0 |
| ps_collapsing_tiles-v1 | time_limit | 3,221 | 7,077 | 60.0 |
| ps_fuse_to_green-v1 | time_limit | 2,855 | 4,096 | 60.0 |
| ps_dark_pellets-v1 | time_limit | 1,428 | 2,487 | 60.0 |
| ps_infected-v1 | time_limit | 15,290 | 33,104 | 60.0 |
| ps_extra_push-v1 | time_limit | 10,658 | 12,135 | 60.0 |
| ps_the_art_of_storage-v1 | time_limit | 10,537 | 18,440 | 60.0 |
| ps_side_painting-v1 | time_limit | 775 | 998 | 60.0 |

Timeout and state-limit results remain unknown, not proven unsolvable.

Semantic mode stores and branches from complete real engine states, but merges states that differ only in derived cache history. Solutions are replay-verified and shortest in that semantic graph; strict optimality over cache-history variants is not claimed.
