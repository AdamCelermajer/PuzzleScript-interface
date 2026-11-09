# Independent source verification - run-F

Source: `puzzlescript_interface/games/ps_icecrates-v1/script.txt`, reviewed directly, including legend, collision layers, movement rules and win condition. No gameplay run.

- I1: directional activation at lines 356, 364, 372, 380 establishes four moves.
- I2: Obstacle = Wall or StillCrate or Water (291); directional player stops (361,369,377,385) and repeated movement (362,370,378,386).
- I3: sliding player pushes crate (357,365,373,381); crate becomes StillCrate at obstacle (360,368,376,384); player stops adjacent via Obstacle. StillCrate resets to Crate (388).
- I4: moving crate propagates movement to next crate (358,366,374,382). The learner's categorical no-chain rule is false.
- I5: all six animated water sprites belong to Water (279), all are Obstacle (291) on player collision layer (305). Animation (344-351) does not create passable phases.
- I6: crate + Water becomes empty + FilledWater (359,367,375,383). FilledWater is a separate floor layer (302), allowing player crossing. This is not a timed feeding gate.
- I7: Some PlayerStill on Goal (395), excluding moving PlayerL/R/U/D. Passing through cannot win.

No rule-definition correction needed. Object names may differ, but the learner's wrong passable-phase account matters behaviorally, not lexically.
