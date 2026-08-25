# Durable game knowledge

- The board is a 7x6 integer grid. Values present initially: 0,1,2,3,4,5.
- The action mapping is supplied by the harness: ACTION1 Up, ACTION2 Down,
  ACTION3 Left, ACTION4 Right, ACTION5 Space/Action, ACTION7 Undo, RESET restart.
- Confirmed from T000001: value 2 is the player/avatar, value 0 is traversable
  floor, and a cardinal move into adjacent 0 moves only the avatar (old cell
  becomes 0; destination becomes 2).
- Confirmed from T000002: the player cannot simply enter value 3. The attempted
  Down move made no change while the cell beyond value 3 was value 1. This is
  explained by the push rule below.
- Confirmed from T000005: value 3 is a pushable object. When the player moves
  toward it and the cell beyond is 0, the object advances one cell, the player
  enters its former cell, and the player's former cell becomes 0.
- T000009 contradicts the former destination hypothesis: a push of value 3
  toward adjacent value 4 made no change. Thus 3 cannot be pushed onto/through
  4 by ordinary movement; 4 is not an ordinary destination for 3.
- Value 5 is reachable by the player from below in the initial state, but has
  not yet been interaction-tested.
