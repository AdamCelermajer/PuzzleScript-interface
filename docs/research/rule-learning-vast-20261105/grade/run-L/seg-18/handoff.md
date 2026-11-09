At cp061 (400 moves), the model has reset the final board and repeated horizontal goal passes without winning.
It reads the reset position as (9,13), then corrects a later right edge to (9,12); state transcription remains unreliable.
I1/I2/I3/I5/I6 are correct; I4 is partial (contiguous chains accepted, the general solver still blocks other crates).
I7 is wrong again: it adopts a timing/transformation account because its solver and geometry declare stop-on-goal impossible.
The newest full solver earns correct automatic single-crate pushing, water blocking and absorption/continuation.
The files alone retain stop-on-goal, so I7's error is in newer thinking; other files contain contradictory older experiments.
The changing blue IDs prompt timer speculation, but solid-blue pushability is still posed as a test, not adopted.
Next action intended is up to (3,12), followed by a chain push into blue (3,6).
