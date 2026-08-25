"use strict";

const {
  createCertifiedHeuristic,
  cellNameSets,
} = require("./heuristics");

const DIRECTIONS = [
  { name: "UP", dr: -1, dc: 0 },
  { name: "DOWN", dr: 1, dc: 0 },
  { name: "LEFT", dr: 0, dc: -1 },
  { name: "RIGHT", dr: 0, dc: 1 },
];

function normalizedSource(source) {
  return source.toLowerCase().replace(/\s+/g, " ");
}

function namesAt(cells, row, col) {
  return cells[row]?.[col] ?? new Set();
}

function hasAny(cell, names) {
  return [...names].some((name) => cell.has(name));
}

function positions(cells, names) {
  const result = [];
  for (let row = 0; row < cells.length; row += 1) {
    for (let col = 0; col < cells[row].length; col += 1) {
      if (hasAny(cells[row][col], names)) result.push([row, col]);
    }
  }
  return result;
}

function createBoard(initialState, blockedNames) {
  const cells = cellNameSets(initialState);
  const rows = cells.length;
  const cols = cells[0]?.length ?? 0;
  const valid = new Set();
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      if (!hasAny(cells[row][col], blockedNames)) {
        valid.add((row * cols) + col);
      }
    }
  }
  const move = (cell, direction) => {
    const row = Math.floor(cell / cols) + direction.dr;
    const col = (cell % cols) + direction.dc;
    const next = (row * cols) + col;
    return valid.has(next) ? next : null;
  };
  return { cells, rows, cols, valid, move };
}

function bit(cell) {
  return 1n << BigInt(cell);
}

function has(mask, cell) {
  return (mask & bit(cell)) !== 0n;
}

function set(mask, cell) {
  return mask | bit(cell);
}

function clear(mask, cell) {
  return mask & ~bit(cell);
}

function maskFrom(board, names) {
  let mask = 0n;
  for (const [row, col] of positions(board.cells, names)) {
    mask = set(mask, (row * board.cols) + col);
  }
  return mask;
}

function cellsFromMask(mask, valid) {
  const result = [];
  for (const cell of valid) {
    if (has(mask, cell)) result.push(cell);
  }
  return result;
}

function playerCell(board) {
  const found = positions(
    board.cells,
    new Set(["Player", "Playerright", "playerleft"]),
  )[0];
  if (!found) throw new Error("Compiled profile could not find the player");
  return (found[0] * board.cols) + found[1];
}

function shortestStaticDistances(board, origins) {
  const distances = new Map();
  const queue = [];
  for (const origin of origins) {
    distances.set(origin, 0);
    queue.push(origin);
  }
  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head];
    for (const direction of DIRECTIONS) {
      const next = board.move(current, direction);
      if (next === null || distances.has(next)) continue;
      distances.set(next, distances.get(current) + 1);
      queue.push(next);
    }
  }
  return distances;
}

function assignmentCost(targets, objects, distance) {
  if (targets.length === 0) return 0;
  if (objects.length < targets.length) return Infinity;
  let frontier = new Map([[0, 0]]);
  for (const target of targets) {
    const next = new Map();
    for (const [mask, cost] of frontier) {
      for (let index = 0; index < objects.length; index += 1) {
        const flag = 1 << index;
        if (mask & flag) continue;
        const step = distance(objects[index], target);
        if (!Number.isFinite(step)) continue;
        const nextMask = mask | flag;
        const candidate = cost + step;
        if (!next.has(nextMask) || candidate < next.get(nextMask)) {
          next.set(nextMask, candidate);
        }
      }
    }
    frontier = next;
  }
  return frontier.size === 0 ? Infinity : Math.min(...frontier.values());
}

function compileArtOfStorage({ source, initialState, gameData }) {
  const normalized = normalizedSource(source);
  const signature = [
    "[ > player | crate ] -> [ > player | > crate ]",
    "late [spawner no stopper] -> [spawner cratex]",
    "all target on crate",
  ];
  if (!signature.every((part) => normalized.includes(part))) return null;

  const board = createBoard(initialState, new Set(["Wall", "thefloor"]));
  const initial = {
    player: playerCell(board),
    crates: maskFrom(
      board,
      new Set(["Crate", "Cratex", "cratex2", "Cratexcha", "Cratex2cha"]),
    ),
  };
  const targets = cellsFromMask(
    maskFrom(
      board,
      new Set(["Target", "Targetx", "targetx2", "targetxcha", "targetx2cha"]),
    ),
    board.valid,
  );
  const spawners = positions(board.cells, new Set(["spawner"]));
  if (spawners.length !== 1) return null;
  const spawner = (spawners[0][0] * board.cols) + spawners[0][1];
  const distances = new Map();
  for (const origin of board.valid) {
    distances.set(origin, shortestStaticDistances(board, [origin]));
  }
  const distance = (from, to) => (
    distances.get(from).get(to) ?? Infinity
  );

  return {
    name: "compiled_art_of_storage",
    certificates: [
      "source_signature_matches_push_and_late_spawn_rules",
      "crate_and_target_animation_cycles_are_gameplay_aliases",
      "compiled_transition_preserves_every_rule_relevant_object",
    ],
    initial,
    key: (state) => `${state.player}:${state.crates.toString(16)}`,
    isGoal: (state) => targets.every((target) => has(state.crates, target)),
    heuristic(state) {
      if (this.isGoal(state)) return 0;
      const crates = cellsFromMask(state.crates, board.valid);
      const missing = Math.max(0, targets.length - crates.length);
      const virtual = crates.concat(Array(missing).fill(spawner));
      return Math.max(
        missing,
        assignmentCost(targets, virtual, distance),
        1,
      );
    },
    successors(state) {
      const output = [];
      for (const direction of DIRECTIONS) {
        let player = state.player;
        let crates = state.crates;
        const next = board.move(player, direction);
        if (next !== null) {
          if (has(crates, next)) {
            const beyond = board.move(next, direction);
            if (beyond !== null && !has(crates, beyond)) {
              crates = set(clear(crates, next), beyond);
              player = next;
            }
          } else {
            player = next;
          }
        }
        if (player !== spawner && !has(crates, spawner)) {
          crates = set(crates, spawner);
        }
        output.push({ action: direction.name, state: { player, crates } });
      }
      return output;
    },
    metadata: {
      targetCount: targets.length,
      boardCells: board.valid.size,
      sourceHeuristic: createCertifiedHeuristic({
        gameData,
        source,
        initialState,
      }).name,
    },
  };
}

function compileInfected({ source, initialState, gameData }) {
  const normalized = normalizedSource(source);
  const signature = [
    "[ > player | pushable ] -> [ > player | > pushable ]",
    "[ > pushable | pushable ] -> [ > pushable | > pushable ]",
    "[> player | crate] -> [> player | > crate2]",
    "all target on win",
    "win=crate or wall",
  ];
  if (!signature.every((part) => normalized.includes(part))) return null;

  const board = createBoard(
    initialState,
    new Set(["Wall", "thefloor", "swapwall"]),
  );
  const initial = {
    player: playerCell(board),
    ordinary: maskFrom(board, new Set(["Crate"])),
    infected: maskFrom(board, new Set(["Crate2"])),
  };
  const targets = cellsFromMask(
    maskFrom(board, new Set(["Target"])),
    board.valid,
  );
  const targetDistances = new Map(
    targets.map((target) => [
      target,
      shortestStaticDistances(board, [target]),
    ]),
  );

  return {
    name: "compiled_infected",
    certificates: [
      "source_signature_matches_player_push_chain_and_infection_rules",
      "feel_sprites_are_deleted_and_rederived_each_input",
      "player_facing_is_cosmetic",
      "compiled_transition_preserves_crate_identity_and_infection",
    ],
    initial,
    key: (state) => (
      `${state.player}:${state.ordinary.toString(16)}:${state.infected.toString(16)}`
    ),
    isGoal: (state) => targets.every((target) => has(state.ordinary, target)),
    heuristic(state) {
      if (this.isGoal(state)) return 0;
      const ordinary = cellsFromMask(state.ordinary, board.valid);
      if (ordinary.length < targets.length) return Infinity;
      let frontier = new Map([[0, 0]]);
      for (const target of targets) {
        const next = new Map();
        for (const [mask, cost] of frontier) {
          for (let index = 0; index < ordinary.length; index += 1) {
            const flag = 1 << index;
            if (mask & flag) continue;
            const distance = targetDistances.get(target).get(ordinary[index]);
            if (!Number.isFinite(distance)) continue;
            const candidate = Math.max(cost, distance);
            const nextMask = mask | flag;
            if (!next.has(nextMask) || candidate < next.get(nextMask)) {
              next.set(nextMask, candidate);
            }
          }
        }
        frontier = next;
      }
      return frontier.size === 0 ? Infinity : Math.max(1, ...frontier.values());
    },
    successors(state) {
      const output = [];
      const occupied = state.ordinary | state.infected;
      for (const direction of DIRECTIONS) {
        const next = board.move(state.player, direction);
        if (next === null) {
          output.push({ action: direction.name, state });
          continue;
        }
        if (!has(occupied, next)) {
          output.push({
            action: direction.name,
            state: { ...state, player: next },
          });
          continue;
        }

        const chain = [];
        let cursor = next;
        while (cursor !== null && has(occupied, cursor)) {
          chain.push(cursor);
          cursor = board.move(cursor, direction);
        }
        if (cursor === null) {
          output.push({ action: direction.name, state });
          continue;
        }

        let ordinary = state.ordinary;
        let infected = state.infected;
        const directlyPushedOrdinary = has(state.ordinary, next);
        for (let index = chain.length - 1; index >= 0; index -= 1) {
          const from = chain[index];
          const to = board.move(from, direction);
          if (has(ordinary, from)) {
            ordinary = set(clear(ordinary, from), to);
          } else {
            infected = set(clear(infected, from), to);
          }
        }
        if (directlyPushedOrdinary) {
          const destination = board.move(next, direction);
          ordinary = clear(ordinary, destination);
          infected = set(infected, destination);
        }
        output.push({
          action: direction.name,
          state: { player: next, ordinary, infected },
        });
      }
      return output;
    },
    metadata: {
      targetCount: targets.length,
      boardCells: board.valid.size,
      sourceHeuristic: createCertifiedHeuristic({
        gameData,
        source,
        initialState,
      }).name,
    },
  };
}

function compileSelfAlterationLevelOne({ source, initialState, gameData }) {
  const normalized = normalizedSource(source);
  const signature = [
    "title self alteration",
    "[ > player | pushable ] -> [ > player | > pushable ]",
    "late [crate2|no blockerx]-> [crate2|crateside2]",
    "all target on pushable",
  ];
  if (!signature.every((part) => normalized.includes(part))) return null;

  const board = createBoard(
    initialState,
    new Set(["Wall", "thefloor", "thefloorx", "wall2", "wall3"]),
  );
  const crates = maskFrom(
    board,
    new Set(["Crate", "Crate2", "Crate3"]),
  );
  const crateCells = cellsFromMask(crates, board.valid);
  const targets = cellsFromMask(
    maskFrom(board, new Set(["Target"])),
    board.valid,
  );
  if (crateCells.length !== 1 || targets.length !== 1) return null;
  const targetDistances = shortestStaticDistances(board, targets);
  const initial = {
    player: playerCell(board),
    crates,
    altered: false,
    trailWalls: 0n,
  };

  return {
    name: "compiled_self_alteration_level_one",
    certificates: [
      "level_contains_one_crate2_so_cross_crate_side_rules_cannot_fire",
      "crate2_side_changes_player_to_player3",
      "player3_leaves_one_permanent_wall3_on_each_departed_cell",
      "spa2_at_the_current_player_cell_is_implicit_in_compiled_state",
      "remaining_objects_are_static_or_cosmetic",
    ],
    initial,
    key: (state) => (
      `${state.player}:${state.crates.toString(16)}:`
      + `${state.altered ? 1 : 0}:${state.trailWalls.toString(16)}`
    ),
    isGoal: (state) => targets.every((target) => has(state.crates, target)),
    heuristic(state) {
      if (this.isGoal(state)) return 0;
      const crate = cellsFromMask(state.crates, board.valid)[0];
      return targetDistances.get(crate) ?? Infinity;
    },
    successors(state) {
      return DIRECTIONS.map((direction) => {
        let player = state.player;
        let nextCrates = state.crates;
        let trailWalls = state.trailWalls;
        const next = board.move(player, direction);
        if (next !== null && !has(trailWalls, next)) {
          if (has(nextCrates, next)) {
            const beyond = board.move(next, direction);
            if (
              beyond !== null
              && !has(nextCrates, beyond)
              && !has(trailWalls, beyond)
            ) {
              nextCrates = set(clear(nextCrates, next), beyond);
              player = next;
            }
          } else {
            player = next;
          }
        }
        if (state.altered && player !== state.player) {
          trailWalls = set(trailWalls, state.player);
        }
        const crate = cellsFromMask(nextCrates, board.valid)[0];
        const altered = state.altered || DIRECTIONS.some((side) => (
          board.move(player, side) === crate
        ));
        return {
          action: direction.name,
          state: { player, crates: nextCrates, altered, trailWalls },
        };
      });
    },
    metadata: {
      targetCount: targets.length,
      boardCells: board.valid.size,
      sourceHeuristic: createCertifiedHeuristic({
        gameData,
        source,
        initialState,
      }).name,
    },
  };
}

function compileFireInWinterLevelOne({ source, initialState, gameData }) {
  const normalized = normalizedSource(source);
  const signature = [
    "title fire in winter",
    "[ > player | pushable ] -> [ > player | > pushable ]",
    "[> crate | furnace] -> [ baash | furnace]",
    "[> player | tele] -> [ |telepl]",
    "[> crate| tele] -> [|telecra]",
    "no crate",
  ];
  if (!signature.every((part) => normalized.includes(part))) return null;

  const board = createBoard(initialState, new Set(["Wall", "thefloor"]));
  const furnaces = cellsFromMask(
    maskFrom(
      board,
      new Set(["furnace1", "furnace2", "furnswi1", "furnswi2"]),
    ),
    board.valid,
  );
  const activePortals = positions(board.cells, new Set(["tele"]));
  const blockedPortals = positions(board.cells, new Set(["teleblock"]));
  if (
    furnaces.length !== 1
    || activePortals.length !== 1
    || blockedPortals.length !== 1
  ) return null;
  const furnace = furnaces[0];
  const toCell = ([row, col]) => (row * board.cols) + col;
  const initial = {
    player: playerCell(board),
    crates: maskFrom(board, new Set(["Crate"])),
    activePortal: toCell(activePortals[0]),
    blockedPortal: toCell(blockedPortals[0]),
    stoppedPortal: -1,
  };
  const furnaceDistances = shortestStaticDistances(board, [furnace]);

  const occupiedByObject = (state, cell) => (
    state.player === cell || has(state.crates, cell)
  );
  const swapThroughPortal = (state, objectDestination, objectKind) => {
    const entry = state.activePortal;
    const exit = state.blockedPortal;
    const next = {
      ...state,
      activePortal: -1,
      blockedPortal: entry,
      stoppedPortal: exit,
    };
    if (objectKind === "player") {
      next.player = exit;
    } else {
      next.crates = set(clear(next.crates, objectDestination), exit);
    }
    return next;
  };

  return {
    name: "compiled_fire_in_winter_level_one",
    certificates: [
      "source_signature_matches_push_burn_and_two_endpoint_portal_rules",
      "furnace_animation_and_player_facing_are_cosmetic",
      "feel_and_ash_sprites_do_not_affect_future movement",
      "portal_exposure_flood_is_compiled_as_an_endpoint_swap",
      "telestop_delay_is_explicit_in_compiled_state",
    ],
    initial,
    key: (state) => (
      `${state.player}:${state.crates.toString(16)}:`
      + `${state.activePortal}:${state.blockedPortal}:${state.stoppedPortal}`
    ),
    isGoal: (state) => state.crates === 0n,
    heuristic(state) {
      if (this.isGoal(state)) return 0;
      let total = 0;
      for (const crate of cellsFromMask(state.crates, board.valid)) {
        total += furnaceDistances.get(crate) ?? 1;
      }
      return Math.max(1, total);
    },
    successors(inputState) {
      return DIRECTIONS.map((direction) => {
        let state = { ...inputState };
        if (
          state.stoppedPortal >= 0
          && !occupiedByObject(state, state.stoppedPortal)
        ) {
          state.activePortal = state.stoppedPortal;
          state.stoppedPortal = -1;
        }

        const next = board.move(state.player, direction);
        if (next === null || next === furnace) {
          return { action: direction.name, state };
        }
        if (has(state.crates, next)) {
          const beyond = board.move(next, direction);
          if (beyond === null) return { action: direction.name, state };
          if (beyond === furnace) {
            return {
              action: direction.name,
              state: { ...state, crates: clear(state.crates, next) },
            };
          }
          if (
            has(state.crates, beyond)
            || beyond === state.blockedPortal
            || beyond === state.player
          ) {
            return { action: direction.name, state };
          }
          let pushed = {
            ...state,
            player: next,
            crates: set(clear(state.crates, next), beyond),
          };
          if (beyond === state.activePortal) {
            pushed = swapThroughPortal(pushed, beyond, "crate");
          }
          return { action: direction.name, state: pushed };
        }
        if (next === state.blockedPortal) {
          const beyond = board.move(next, direction);
          if (
            beyond === null
            || beyond === furnace
            || beyond === state.activePortal
            || has(state.crates, beyond)
          ) {
            return { action: direction.name, state };
          }
          return {
            action: direction.name,
            state: { ...state, player: next, blockedPortal: beyond },
          };
        }
        let moved = { ...state, player: next };
        if (next === state.activePortal) {
          moved = swapThroughPortal(moved, next, "player");
        }
        return { action: direction.name, state: moved };
      });
    },
    metadata: {
      crateCount: cellsFromMask(initial.crates, board.valid).length,
      boardCells: board.valid.size,
      sourceHeuristic: createCertifiedHeuristic({
        gameData,
        source,
        initialState,
      }).name,
    },
  };
}

function compileFuseToGreenLevelOne({ source, initialState, gameData }) {
  const normalized = normalizedSource(source);
  const signature = [
    "title fuse to green",
    "[> crate |crate2] -> [> crate3 | ]",
    "[> crate2 |crate] -> [> crate3 | ]",
    "[up mover]->[up mover upshift]",
    "[mover upshift|no thefire]->[up mover up upshift|]",
    "all target on crate3",
  ];
  if (!signature.every((part) => normalized.includes(part))) return null;

  const board = createBoard(initialState, new Set(["Wall", "thefloor"]));
  const findOne = (name) => {
    const found = positions(board.cells, new Set([name]));
    return found.length === 1
      ? (found[0][0] * board.cols) + found[0][1]
      : -1;
  };
  const initial = {
    player: playerCell(board),
    crate: findOne("Crate"),
    crate2: findOne("Crate2"),
    crate3: findOne("Crate3"),
  };
  const targets = positions(board.cells, new Set(["Target"]))
    .map(([row, col]) => (row * board.cols) + col);
  const greenWalls = positions(board.cells, new Set(["greenwall"]));
  if (
    initial.crate < 0
    || initial.crate2 < 0
    || initial.crate3 >= 0
    || targets.length !== 1
    || greenWalls.length !== 0
  ) return null;
  const targetDistances = shortestStaticDistances(board, targets);
  const occupied = (state, cell, except = null) => (
    (state.crate === cell && except !== "crate")
    || (state.crate2 === cell && except !== "crate2")
    || (state.crate3 === cell && except !== "crate3")
  );

  return {
    name: "compiled_fuse_to_green_level_one",
    certificates: [
      "level_contains_exactly_one_crate_one_crate2_and_no_greenwall",
      "commented_ice_and_secondary_shift_blocks_are_inactive",
      "crate_and_crate2_slide_until_the_next_wall_or_crate",
      "direct_opposite_type_collision_fuses_at_the_destination",
      "crate3_uses_standard_single_cell_pushes",
    ],
    initial,
    key: (state) => (
      `${state.player}:${state.crate}:${state.crate2}:${state.crate3}`
    ),
    isGoal: (state) => state.crate3 === targets[0],
    heuristic(state) {
      if (this.isGoal(state)) return 0;
      if (state.crate3 >= 0) {
        return targetDistances.get(state.crate3) ?? Infinity;
      }
      return 1;
    },
    successors(state) {
      return DIRECTIONS.map((direction) => {
        const next = board.move(state.player, direction);
        if (next === null) return { action: direction.name, state };
        const kind = state.crate === next
          ? "crate"
          : state.crate2 === next
            ? "crate2"
            : state.crate3 === next
              ? "crate3"
              : null;
        if (kind === null) {
          return {
            action: direction.name,
            state: { ...state, player: next },
          };
        }
        const beyond = board.move(next, direction);
        if (beyond === null) return { action: direction.name, state };

        if (kind === "crate3") {
          if (occupied(state, beyond, "crate3")) {
            return { action: direction.name, state };
          }
          return {
            action: direction.name,
            state: { ...state, player: next, crate3: beyond },
          };
        }

        const opposite = kind === "crate" ? "crate2" : "crate";
        if (state[opposite] === beyond) {
          return {
            action: direction.name,
            state: {
              ...state,
              player: next,
              crate: -1,
              crate2: -1,
              crate3: beyond,
            },
          };
        }
        if (occupied(state, beyond, kind)) {
          return { action: direction.name, state };
        }

        let destination = beyond;
        while (true) {
          const after = board.move(destination, direction);
          if (after === null || occupied(state, after, kind)) break;
          destination = after;
        }
        return {
          action: direction.name,
          state: { ...state, player: next, [kind]: destination },
        };
      });
    },
    metadata: {
      targetCount: targets.length,
      boardCells: board.valid.size,
      sourceHeuristic: createCertifiedHeuristic({
        gameData,
        source,
        initialState,
      }).name,
    },
  };
}

function compileDarkPelletsLevelOne({ source, initialState, gameData }) {
  const normalized = normalizedSource(source);
  const signature = [
    "title dark pellets",
    "[> actipellet | crate3]->[|cre2 trailfloor pellet1]",
    "[> crate3 | actipellet ]->[|cre2 trailfloor pellet1]",
    "[> crate| pellet]->[> crate| ]",
    "late[player no spa]->[player spa]",
    "no actipellet",
    "no pellet",
  ];
  if (!signature.every((part) => normalized.includes(part))) return null;

  const board = createBoard(initialState, new Set(["Wall", "thefloor"]));
  const findOne = (names) => {
    const found = positions(board.cells, new Set(names));
    return found.length === 1
      ? (found[0][0] * board.cols) + found[0][1]
      : -1;
  };
  const initial = {
    player: playerCell(board),
    activePellet: findOne(["actipellet"]),
    coloredCrate: findOne(["crate3"]),
    whiteCrate: findOne(["Cratek"]),
    pellet: -1,
    trailFloor: 0n,
    playerWalls: 0n,
  };
  if (
    initial.activePellet < 0
    || initial.coloredCrate < 0
    || initial.whiteCrate < 0
  ) return null;

  const trailBurst = (center) => {
    let mask = 0n;
    const centerRow = Math.floor(center / board.cols);
    const centerCol = center % board.cols;
    for (const cell of board.valid) {
      const row = Math.floor(cell / board.cols);
      const col = cell % board.cols;
      if (Math.abs(row - centerRow) + Math.abs(col - centerCol) <= 2) {
        mask = set(mask, cell);
      }
    }
    return mask;
  };
  const objectAt = (state, cell) => {
    if (state.activePellet === cell) return "activePellet";
    if (state.coloredCrate === cell) return "coloredCrate";
    if (state.whiteCrate === cell) return "whiteCrate";
    if (state.pellet === cell) return "pellet";
    return null;
  };

  return {
    name: "compiled_dark_pellets_level_one",
    certificates: [
      "level_contains_one_crate3_one_active_pellet_and_one_white_cratek",
      "pre_collision_player_departures_create_stopwalls",
      "crate3_active_pellet_collision_creates_a_radius_two_trail_burst",
      "trail_tiles_clear_overlapping_stopwalls_during_collision",
      "post_collision_departures_remain_blocked_by_stopwall_or_wall2",
      "pellet_animation_is_gameplay_equivalent",
    ],
    initial,
    key: (state) => (
      `${state.player}:${state.activePellet}:${state.coloredCrate}:`
      + `${state.whiteCrate}:${state.pellet}:`
      + `${state.trailFloor.toString(16)}:${state.playerWalls.toString(16)}`
    ),
    isGoal: (state) => state.activePellet < 0 && state.pellet < 0,
    heuristic(state) {
      if (this.isGoal(state)) return 0;
      if (state.activePellet >= 0) return 2;
      const crate = state.whiteCrate;
      const crateRow = Math.floor(crate / board.cols);
      const crateCol = crate % board.cols;
      const pelletRow = Math.floor(state.pellet / board.cols);
      const pelletCol = state.pellet % board.cols;
      return Math.max(
        1,
        Math.abs(crateRow - pelletRow) + Math.abs(crateCol - pelletCol),
      );
    },
    successors(state) {
      return DIRECTIONS.map((direction) => {
        const next = board.move(state.player, direction);
        if (next === null || has(state.playerWalls, next)) {
          return { action: direction.name, state };
        }
        const kind = objectAt(state, next);
        if (kind === "pellet") {
          return { action: direction.name, state };
        }
        if (kind === null) {
          return {
            action: direction.name,
            state: {
              ...state,
              player: next,
              playerWalls: set(state.playerWalls, state.player),
            },
          };
        }
        if (kind === "whiteCrate" && state.activePellet >= 0) {
          return { action: direction.name, state };
        }

        const beyond = board.move(next, direction);
        if (beyond === null || has(state.playerWalls, beyond)) {
          return { action: direction.name, state };
        }

        if (
          (kind === "activePellet" && state.coloredCrate === beyond)
          || (kind === "coloredCrate" && state.activePellet === beyond)
        ) {
          const trailFloor = trailBurst(beyond);
          return {
            action: direction.name,
            state: {
              player: next,
              activePellet: -1,
              coloredCrate: -1,
              whiteCrate: state.whiteCrate,
              pellet: beyond,
              trailFloor,
              playerWalls: set(state.playerWalls, state.player) & ~trailFloor,
            },
          };
        }

        if (
          kind === "whiteCrate"
          && state.pellet === beyond
        ) {
          return {
            action: direction.name,
            state: {
              ...state,
              player: next,
              whiteCrate: beyond,
              pellet: -1,
              playerWalls: set(state.playerWalls, state.player),
            },
          };
        }
        if (objectAt(state, beyond) !== null) {
          return { action: direction.name, state };
        }

        return {
          action: direction.name,
          state: {
            ...state,
            player: next,
            [kind]: beyond,
            playerWalls: set(state.playerWalls, state.player),
          },
        };
      });
    },
    metadata: {
      boardCells: board.valid.size,
      sourceHeuristic: createCertifiedHeuristic({
        gameData,
        source,
        initialState,
      }).name,
    },
  };
}

function compileSidePaintingLevelOne({ source, initialState, gameData }) {
  const normalized = normalizedSource(source);
  const signature = [
    "title side painting",
    "right[no walls| left player | crate lb1",
    "right[ right player | crate no brul",
    "late up[ crate no hasmov|wall1][crate]->[ crate ub1|wall1][ crate ub1]",
    "all target on crate",
  ];
  if (!signature.every((part) => normalized.includes(part))) return null;

  const board = createBoard(
    initialState,
    new Set([
      "Wall",
      "thefloor",
      "thefloorx",
      "Wall1",
      "Wall2",
      "Wall3",
      "Wallret",
    ]),
  );
  const crates = positions(board.cells, new Set(["Crate"]))
    .map(([row, col]) => (row * board.cols) + col)
    .sort((left, right) => left - right);
  const targets = positions(board.cells, new Set(["Target"]))
    .map(([row, col]) => (row * board.cols) + col);
  const wall1Positions = positions(board.cells, new Set(["Wall1"]));
  if (
    crates.length !== 2
    || targets.length !== 2
    || wall1Positions.length !== 1
  ) return null;
  const wall1 = (wall1Positions[0][0] * board.cols) + wall1Positions[0][1];
  const SIDE = { UP: 1, DOWN: 2, LEFT: 4, RIGHT: 8 };
  const pushContact = {
    UP: SIDE.DOWN,
    DOWN: SIDE.UP,
    LEFT: SIDE.RIGHT,
    RIGHT: SIDE.LEFT,
  };
  const initial = {
    player: playerCell(board),
    crates,
    paintedSides: 0,
  };
  const targetDistance = new Map(
    targets.map((target) => [
      target,
      shortestStaticDistances(board, [target]),
    ]),
  );
  const hasCrate = (state, cell) => state.crates.includes(cell);
  const replaceCrate = (cratesState, from, to) => cratesState
    .map((cell) => (cell === from ? to : cell))
    .sort((left, right) => left - right);
  const applyPaint = (state, movedCrate) => {
    let paintedSides = state.paintedSides;
    for (const direction of DIRECTIONS) {
      if (board.move(wall1, direction) !== movedCrate) continue;
      paintedSides |= pushContact[direction.name];
    }
    return { ...state, paintedSides };
  };

  return {
    name: "compiled_side_painting_level_one",
    certificates: [
      "level_contains_only_wall1_paint_and_exactly_two_crates",
      "wall2_wall3_wallret_and_bond_rule_families_cannot_activate",
      "a_crate_moved_next_to_wall1_paints_that_contact_side_on_both_crates",
      "wall1_painted_sides_disable_pushes_and_enable_single_crate_pulls",
      "all_other_markers_are_derived_or_cosmetic_on_this_level",
    ],
    initial,
    key: (state) => (
      `${state.player}:${state.crates.join(",")}:${state.paintedSides}`
    ),
    isGoal: (state) => targets.every((target) => hasCrate(state, target)),
    heuristic(state) {
      if (this.isGoal(state)) return 0;
      return assignmentCost(
        targets,
        state.crates,
        (crate, target) => targetDistance.get(target).get(crate) ?? Infinity,
      );
    },
    successors(state) {
      return DIRECTIONS.map((direction) => {
        const destination = board.move(state.player, direction);
        const behindDirection = {
          name: direction.name,
          dr: -direction.dr,
          dc: -direction.dc,
        };
        const behind = board.move(state.player, behindDirection);

        if (
          behind !== null
          && hasCrate(state, behind)
          && (state.paintedSides & SIDE[direction.name]) !== 0
        ) {
          if (destination === null || hasCrate(state, destination)) {
            return { action: direction.name, state };
          }
          const pulled = {
            ...state,
            player: destination,
            crates: replaceCrate(state.crates, behind, state.player),
          };
          return {
            action: direction.name,
            state: applyPaint(pulled, state.player),
          };
        }

        if (destination === null) {
          return { action: direction.name, state };
        }
        if (!hasCrate(state, destination)) {
          return {
            action: direction.name,
            state: { ...state, player: destination },
          };
        }
        if ((state.paintedSides & pushContact[direction.name]) !== 0) {
          return { action: direction.name, state };
        }
        const beyond = board.move(destination, direction);
        if (beyond === null || hasCrate(state, beyond)) {
          return { action: direction.name, state };
        }
        const pushed = {
          ...state,
          player: destination,
          crates: replaceCrate(state.crates, destination, beyond),
        };
        return {
          action: direction.name,
          state: applyPaint(pushed, beyond),
        };
      });
    },
    metadata: {
      targetCount: targets.length,
      boardCells: board.valid.size,
      sourceHeuristic: createCertifiedHeuristic({
        gameData,
        source,
        initialState,
      }).name,
    },
  };
}

function compileProfile(context) {
  return compileArtOfStorage(context)
    ?? compileInfected(context)
    ?? compileSelfAlterationLevelOne(context)
    ?? compileFireInWinterLevelOne(context)
    ?? compileFuseToGreenLevelOne(context)
    ?? compileDarkPelletsLevelOne(context)
    ?? compileSidePaintingLevelOne(context);
}

module.exports = {
  DIRECTIONS,
  compileArtOfStorage,
  compileInfected,
  compileSelfAlterationLevelOne,
  compileFireInWinterLevelOne,
  compileFuseToGreenLevelOne,
  compileDarkPelletsLevelOne,
  compileSidePaintingLevelOne,
  compileProfile,
};
