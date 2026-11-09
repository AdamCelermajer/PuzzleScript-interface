At cp024 (225 moves), the player retains the artificial heights: white 1=h2, grey 4=h3, black 2=h4; target 9 is black.
M1 partial: four directions, no explicit conclusion about ACTION5.
M2 correct in both sources: solver2.py preserves the box on non-push walks; the explicit restart therefore does not lose this belief.
M3 partial: bounds understood, no belief about another crate blocking a push.
M4/M5 correct: symmetric walking through grey; climb-2 remains an explicit test, not a replacement belief.
M6 partial: wrongly extends symmetric |dh|<=1 walking to pushes, including grey/black.
M7 correct: box may move to any floor regardless of destination height. M8 partial: one box onto target, no all-crates generalization.
After the restart, revisits display meanings, fails saved plan M12 at move213 and adopts BFS with its inferred rules.
solver4.py and level4b.md now record symmetric pushes and a 16-move experiment testing white-to-black pushing.
At225 the test has been issued; no result yet. A false terrain-swap claim and misremembered initial box position persist.
