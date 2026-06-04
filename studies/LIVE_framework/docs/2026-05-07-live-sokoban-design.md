# LIVE Sokoban POC Design

## Goal

Replace the competing LIVE Sokoban experiments with one readable PuzzleScript POC under `studies/LIVE_framework`.

## Scope

The POC targets `ps_sokoban_basic-v1` through the existing ARC-compatible PuzzleScript service. It learns from perceived symbols and state transitions. It does not hard-code Sokoban object names, push rules, blocked rules, or action directions.

## State Representation

State is represented by perception:

- generalized wall facts such as `At(#,0,0)`; walls do not receive individual object IDs
- singleton actor facts such as `At(P,2,3)`
- numbered target and crate facts such as `At(O1,2,1)`, `At(O2,1,3)`, `At(*1,1,3)`, and `At(*2,3,4)`
- derived covered-target facts: if a target and any crate occupy the same coordinate, emit `At(@n,x,y)` and `At(@,x,y)`
- changed positions between before and after frames
- learned static `O/@` cells, so target/floor rendering does not become a separate movement rule

The representation is intentionally neutral. It gives the learner a stable perceptual surface, not domain mechanics.

## Rule Learning

The rule model attributes raw controller actions to the observed actor. For Sokoban-basic, a raw `ACTION2` transition involving `P` is represented internally as `ACTION2(P)`, similar to the paper's object-attributed actions such as `PICK(BALL1, PLATE1)`.

Rules are stored as percept conditions and effects, not as PuzzleScript line rewrites. A push observation such as `P * . -> . P *` becomes:

- action: `ACTION2(P)`
- conditions: `At(P,x,y)`, `At(*a,x,y+1)`, `NOT At(#,x,y+2)`, `NOT At(*b,x,y+2)`
- effects: `Remove(At(P,x,y))`, `Add(At(P,x,y+1))`, `Remove(At(*a,x,y+1))`, `Add(At(*a,x,y+2))`

The line-rewrite form can still be shown to humans, but it is not the core rule representation.

Observed action directions are kept as internal metadata so the rule learner can map `ACTION2(P)` to a relative coordinate change. They are not presented as learned rules.

## LIVE-Style Revision

Prediction failure triggers sibling-rule revision:

- the failed parent remains visible as a broad attempted rule
- one sibling preserves the successful context
- another sibling captures the failed context
- prediction prefers the most specific active sibling that matches the current percepts

This follows the LIVE paper idea of complementary discrimination: rules are specialized into complementary siblings after failures instead of silently discarding evidence.

## Runner

The runner loops through perceive, predict, act, observe, and revise. It first uses learned predictions to plan to the goal. If no plan exists, it probes unseen percept contexts, then unprobed actions, then falls back to the least-tried action.

## Artifacts

The experiment writes readable artifacts under `studies/LIVE_framework/output`:

- `live_rules.md`
- `live_rules.json`
- `live_journal.md`

## Removal

The old variant folders are removed:

- `client/helped_live_sokoban`
- `client/percept_live_sokoban`
- `client/strict_live_sokoban`
- their matching tests
