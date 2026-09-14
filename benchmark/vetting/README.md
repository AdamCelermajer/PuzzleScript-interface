# Benchmark game vetting

This folder separates three different claims that must not be conflated:

1. `catalog-audit.json` and `catalog-audit.csv` inventory every game directory
   and record parser, source, level, mechanic, and existing-solver properties.
2. `runtime-smoke.json` records fresh-engine action checks for every playable
   level of each deterministic formal-goal candidate.
3. `selection-v0.json` is the balanced 30-game stage-one selection. It is not a
   claim that every level already has a verified solution or gold rule annotation.

## Current counts

- Game directories: 206
- Supported one-directory `script.txt` games: 193
- Deterministic games with formal win conditions: 137
- Candidates passing the all-level fresh-engine smoke: 135
- Stage-one selection: 30 (`5` easy, `17` medium, `8` hard)

`ps_hack_the_net-v1` failed the smoke because one initial action on level index
19 exceeded the 100-tick `AGAIN` limit. `ps_mc_escher_s_equestrian_armageddon-v1`
raised an installed-engine `TypeError` during a level transition. Neither game
is in the stage-one selection.

## Meaning of the difficulty tiers

Difficulty is based on mechanic inference, planning depth, latent state, rule
composition, and transfer across levels. It is not derived from source rule
count alone. Source implementations often contain cosmetic animation and
rendering rules that are not separate conceptual mechanics.

The easy tier is deliberately above `ps_sokoban_basic-v1`: each selected game
adds at least one transformation, mode, tool, pull, or propagation mechanic.

## Next acceptance stage

A game becomes fully benchmark-vetted only after every included level has a
replay-verified solution, every conceptual rule has behavioral probes, and its
rule curriculum identifies both:

- the first level where the rule is observable from available evidence; and
- the first level where using the rule is necessary for successful play.

Latent-state games such as Midas need history-aware probes. A challenge that
contains only one visible frame and one action can be underdetermined when two
internal states render identically.
