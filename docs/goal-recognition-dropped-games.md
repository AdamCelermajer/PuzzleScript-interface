# Goal Recognition Dropped Games

This record tracks games removed from the human goal-recognition experiment pool.
Source games are not deleted from `puzzlescript_interface/games`; experiment samplers filter them out through `dataset/excluded_games.json`.

## Current Count

- Base `ok` games in the generated manifest: 193
- Dropped games: 143
- Active experiment games remaining: 50

The 50-game pool is built from:

- 44 games already present in `report.json`
- 6 added quality games

`ps_liquid_war_alpha-v1` is intentionally kept because the user explicitly marked Liquid War as acceptable.

## Current Policy

- Preserve games that already have participant responses in `report.json`, even if some were previously flagged as weak.
- Fill the remaining slots with deterministic, static, visually readable puzzle games with explicit objectives.
- Keep the final experiment pool to exactly 50 active games.
- Keep source games on disk; remove games only from the experiment sampler through `dataset/excluded_games.json`.

## Added Quality Games

- `ps_2d_whale_world-v1` - explicit goal: push a whale off to free it.
- `ps_always_magnets-v1` - explicit goal: reach the target.
- `ps_bomb_n_ice-v1` - explicit goal: have ice on all targets.
- `ps_bruised-v1` - explicit goal: have a cube on all targets.
- `ps_icecrates-v1` - explicit goal: get to the goal, then crates/holes.
- `ps_teleporters-v1` - explicit goal: have blocks on all crosses.

## Active Games

- `ps_2d_whale_world-v1`
- `ps_alternatey-v1`
- `ps_always_magnets-v1`
- `ps_baba_is_you-v1`
- `ps_barrier_trail-v1`
- `ps_bomb_n_ice-v1`
- `ps_bruised-v1`
- `ps_castlemouse-v1`
- `ps_coin_counter-v1`
- `ps_copy_pellets-v1`
- `ps_count_mover-v1`
- `ps_enqueue-v1`
- `ps_explod-v1`
- `ps_extra_step-v1`
- `ps_fire_in_winter-v1`
- `ps_fish_friend-v1`
- `ps_fused_copy-v1`
- `ps_hue_change-v1`
- `ps_icecrates-v1`
- `ps_jam3_game-v1`
- `ps_knightoban-v1`
- `ps_life_is_hard-v1`
- `ps_liquid_war_alpha-v1`
- `ps_mc_escher_s_equestrian_armageddon-v1`
- `ps_midas-v1`
- `ps_moving_target-v1`
- `ps_multi_word_dictionary_game-v1`
- `ps_paralands-v1`
- `ps_pretender_to_the_crown-v1`
- `ps_push-v1`
- `ps_roll_those_sixes-v1`
- `ps_singleton_traffic-v1`
- `ps_skipping_stones-v1`
- `ps_sleepy_players-v1`
- `ps_sliding_ground-v1`
- `ps_sok7-v1`
- `ps_sokoban_basic-v1`
- `ps_sokofun_clone-v1`
- `ps_stairs-v1`
- `ps_stairways-v1`
- `ps_stand_off-v1`
- `ps_teleporters-v1`
- `ps_test_gist_script-v1`
- `ps_the_big_dig-v1`
- `ps_the_walls_you_leave_behind-v1`
- `ps_tidy_the_cafe-v1`
- `ps_train_braining-v1`
- `ps_unclean_residues-v1`
- `ps_using_pushers-v1`
- `ps_vines-v1`

## Notes

The canonical machine-readable drop list is `dataset/excluded_games.json`. It includes the full 143 excluded games and marks 16 previously flagged games as `preserve_existing_report_data` because `report.json` already contains participant responses for them.
