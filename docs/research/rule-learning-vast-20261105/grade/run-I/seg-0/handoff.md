At cp-013 (225 moves), three levels are complete and level four is underway.
M1/M2/M3/M4/M5/M7/M8 correct; M6 partial: same-colour pushing plus an overgeneralised neutral-grey exception.
The player calls the grey connector the "goal", blue targets "markers", light/dark floors bright/dark.
Crates are orange: 3 on bright, 8 on dark, now 10 on grey; players 7/5/6 respectively.
It learned pushing at 49 and immediate crate-on-marker completion at 56; crate colour crossing at 56/70, confirmed both ways at 122.
Notebook notes.md stores mechanics and long routes; solve.py encodes a single-crate BFS with overly permissive pushes from grey.
M3 full belief comes from thinking at 49 (empty destination plus edge refusal), reaffirmed at 216; notebook alone lacks the other-crate case.
Earlier major error: immovable crate, corrected by trying a push away from the boundary.
At 147-150 diagonal-position confusion led to an accidental edge push and reset, followed by replay to level-three completion at 216.
Level-four manual plan includes directional errors; BFS reported no solution and was set aside. No conversation restart seen.
