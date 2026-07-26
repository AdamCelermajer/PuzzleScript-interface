# PuzzleScript BFS: 60-second rerun

Only the 17 games unsolved in the original 10-second run were rerun.

- Newly solved: **3/17**
- Total solved across the original sample: **16/30**
- Fresh-engine replay verified: **3/3**
- Limits: 60 seconds or 100,000 unique states per game

## Newly solved

| Game | Optimal actions | Expanded | Transitions | Search seconds |
|---|---:|---:|---:|---:|
| ps_punt_mazes-v1 | 11 | 628 | 3,137 | 27.2 |
| ps_wall_shuffle-v1 | 11 | 338 | 1,686 | 15.8 |
| ps_on_and_off-v1 | 10 | 554 | 2,766 | 51.5 |

## Still unsolved within the bounds

| Game | Status | Expanded | Unique states | Search seconds |
|---|---|---:|---:|---:|
| ps_fire_in_winter-v1 | time_limit | 1,566 | 2,477 | 60.0 |
| ps_compressed-v1 | time_limit | 2,102 | 3,466 | 60.0 |
| ps_self_alteration-v1 | time_limit | 373 | 798 | 60.0 |
| ps_collapsing_tiles-v1 | time_limit | 1,066 | 2,491 | 60.0 |
| ps_fuse_to_green-v1 | time_limit | 859 | 1,326 | 60.0 |
| ps_dark_pellets-v1 | time_limit | 708 | 1,281 | 60.0 |
| ps_wall_virus-v1 | time_limit | 1,571 | 1,854 | 60.0 |
| ps_infected-v1 | time_limit | 2,585 | 5,898 | 60.0 |
| ps_extra_push-v1 | time_limit | 565 | 768 | 60.0 |
| ps_the_art_of_storage-v1 | time_limit | 3,718 | 6,929 | 60.0 |
| ps_side_painting-v1 | time_limit | 294 | 405 | 60.0 |
| ps_rotaters_cause-v1 | time_limit | 234 | 312 | 60.0 |
| ps_the_switch-v1 | time_limit | 527 | 679 | 60.0 |
| ps_some_pits-v1 | time_limit | 1,463 | 2,075 | 60.0 |

A timeout or state-limit result remains unknown, not proven unsolvable.
