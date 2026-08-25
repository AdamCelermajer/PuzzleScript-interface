"use strict";

const {
  buildIndistinguishablePlacementPdb,
} = require("./pattern_database");

function tokenName(token) {
  const separator = token.indexOf(" ");
  return separator < 0 ? token : token.slice(separator + 1);
}

function cellNameSets(state) {
  return state.cells.map((row) => row.map((cell) => (
    new Set(cell.map(tokenName))
  )));
}

function tileNames(tile, names = new Set()) {
  if (!tile) return names;
  if (typeof tile.name === "string") {
    names.add(tile.name);
    return names;
  }
  if (Array.isArray(tile.tiles)) {
    for (const child of tile.tiles) tileNames(child, names);
  }
  return names;
}

function positionsOf(cells, names) {
  const positions = [];
  for (let row = 0; row < cells.length; row += 1) {
    for (let col = 0; col < cells[row].length; col += 1) {
      if ([...names].some((name) => cells[row][col].has(name))) {
        positions.push([row, col]);
      }
    }
  }
  return positions;
}

function cellHasAny(cell, names) {
  return [...names].some((name) => cell.has(name));
}

function manhattan(left, right) {
  return Math.abs(left[0] - right[0]) + Math.abs(left[1] - right[1]);
}

function assignmentCost(targets, objects, distance, mode) {
  if (targets.length === 0) return 0;
  if (objects.length < targets.length) return null;
  if (objects.length > 20) return 0;

  let frontier = new Map([[0, 0]]);
  for (const target of targets) {
    const next = new Map();
    for (const [mask, cost] of frontier) {
      for (let index = 0; index < objects.length; index += 1) {
        const bit = 1 << index;
        if (mask & bit) continue;
        const step = distance(objects[index], target);
        if (!Number.isFinite(step)) continue;
        const candidate = mode === "sum"
          ? cost + step
          : Math.max(cost, step);
        const nextMask = mask | bit;
        if (!next.has(nextMask) || candidate < next.get(nextMask)) {
          next.set(nextMask, candidate);
        }
      }
    }
    frontier = next;
    if (frontier.size === 0) return Infinity;
  }
  return Math.min(...frontier.values());
}

function reversePushDistances(rows, cols, walls, targets) {
  const key = (row, col) => `${row},${col}`;
  const distances = new Map();
  const queue = [];
  for (const [row, col] of targets) {
    const cellKey = key(row, col);
    if (!distances.has(cellKey)) {
      distances.set(cellKey, 0);
      queue.push([row, col]);
    }
  }
  const directions = [[-1, 0], [1, 0], [0, -1], [0, 1]];
  let head = 0;
  while (head < queue.length) {
    const [row, col] = queue[head++];
    const current = distances.get(key(row, col));
    for (const [dr, dc] of directions) {
      const previous = [row - dr, col - dc];
      const pusher = [row - (2 * dr), col - (2 * dc)];
      const inside = ([r, c]) => r >= 0 && r < rows && c >= 0 && c < cols;
      if (!inside(previous) || !inside(pusher)) continue;
      if (walls.has(key(...previous)) || walls.has(key(...pusher))) continue;
      const previousKey = key(...previous);
      if (!distances.has(previousKey)) {
        distances.set(previousKey, current + 1);
        queue.push(previous);
      }
    }
  }
  return (position) => distances.get(key(...position)) ?? Infinity;
}

function relaxedGridDistances({
  rows,
  cols,
  blocked,
  goals,
  zeroCostLinks = [],
}) {
  const key = (row, col) => `${row},${col}`;
  const distances = new Map();
  const frontier = [];
  for (const goal of goals) {
    const goalKey = key(...goal);
    distances.set(goalKey, 0);
    frontier.push({ position: goal, distance: 0 });
  }
  while (frontier.length > 0) {
    frontier.sort((left, right) => left.distance - right.distance);
    const current = frontier.shift();
    const currentKey = key(...current.position);
    if (distances.get(currentKey) !== current.distance) continue;
    const edges = [
      ...[[-1, 0], [1, 0], [0, -1], [0, 1]].map(([dr, dc]) => ({
        position: [current.position[0] + dr, current.position[1] + dc],
        cost: 1,
      })),
      ...zeroCostLinks
        .filter(([from]) => key(...from) === currentKey)
        .map(([, to]) => ({ position: to, cost: 0 })),
    ];
    for (const edge of edges) {
      const [row, col] = edge.position;
      if (row < 0 || row >= rows || col < 0 || col >= cols) continue;
      const edgeKey = key(row, col);
      if (blocked.has(edgeKey)) continue;
      const candidate = current.distance + edge.cost;
      if (!distances.has(edgeKey) || candidate < distances.get(edgeKey)) {
        distances.set(edgeKey, candidate);
        frontier.push({ position: edge.position, distance: candidate });
      }
    }
  }
  return (position) => distances.get(key(...position)) ?? Infinity;
}

function connectedComponents(cells, names) {
  const rows = cells.length;
  const cols = cells[0]?.length ?? 0;
  const seen = new Set();
  const components = [];
  const key = (row, col) => `${row},${col}`;
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      if (!cellHasAny(cells[row][col], names) || seen.has(key(row, col))) {
        continue;
      }
      const component = [];
      const queue = [[row, col]];
      seen.add(key(row, col));
      for (let head = 0; head < queue.length; head += 1) {
        const [cr, cc] = queue[head];
        component.push([cr, cc]);
        for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
          const nr = cr + dr;
          const nc = cc + dc;
          if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) continue;
          const nextKey = key(nr, nc);
          if (
            !seen.has(nextKey)
            && cellHasAny(cells[nr][nc], names)
          ) {
            seen.add(nextKey);
            queue.push([nr, nc]);
          }
        }
      }
      components.push(component);
    }
  }
  return components;
}

function componentTourLowerBound(player, components, finish) {
  if (!player || !finish) return components.length > 0 ? 1 : 0;
  if (components.length === 0) return manhattan(player, finish);
  if (components.length > 15) return components.length;

  const pointToComponent = (point, component) => (
    Math.min(...component.map((candidate) => manhattan(point, candidate)))
  );
  const componentDistance = (left, right) => {
    let best = Infinity;
    for (const a of left) {
      for (const b of right) best = Math.min(best, manhattan(a, b));
    }
    return best;
  };

  let frontier = new Map();
  components.forEach((component, index) => {
    frontier.set(`${1 << index}:${index}`, pointToComponent(player, component));
  });
  for (let visitedCount = 1; visitedCount < components.length; visitedCount += 1) {
    const next = new Map();
    for (const [stateKey, cost] of frontier) {
      const [maskText, lastText] = stateKey.split(":");
      const mask = Number(maskText);
      const last = Number(lastText);
      for (let index = 0; index < components.length; index += 1) {
        const bit = 1 << index;
        if (mask & bit) continue;
        const candidate = cost + componentDistance(
          components[last],
          components[index],
        );
        const nextKey = `${mask | bit}:${index}`;
        if (!next.has(nextKey) || candidate < next.get(nextKey)) {
          next.set(nextKey, candidate);
        }
      }
    }
    frontier = next;
  }
  let best = Infinity;
  for (const [stateKey, cost] of frontier) {
    const last = Number(stateKey.split(":")[1]);
    best = Math.min(
      best,
      cost + pointToComponent(finish, components[last]),
    );
  }
  return best;
}

function compileConditions(gameData) {
  return gameData.winConditions.map((condition) => ({
    type: condition.onTile ? "on" : "simple",
    qualifier: String(condition.qualifier).toUpperCase(),
    tile: tileNames(condition.tile),
    onTile: tileNames(condition.onTile),
  }));
}

function conditionSatisfied(cells, condition) {
  const subjectCells = cells.flat().filter((cell) => (
    cellHasAny(cell, condition.tile)
  ));
  if (condition.type === "simple") {
    if (condition.qualifier === "NO") return subjectCells.length === 0;
    if (condition.qualifier === "SOME") return subjectCells.length > 0;
    return subjectCells.length > 0;
  }
  const matches = subjectCells.filter((cell) => (
    cellHasAny(cell, condition.onTile)
  )).length;
  if (condition.qualifier === "ALL") return matches === subjectCells.length;
  if (condition.qualifier === "NO") return matches === 0;
  return matches > 0;
}

function createCertifiedHeuristic({ gameData, source, initialState }) {
  const normalized = source.toLowerCase().replace(/\s+/g, " ");
  const conditions = compileConditions(gameData);
  const initialCells = cellNameSets(initialState);
  const certificates = ["unfinished_state_requires_one_action"];
  const evaluators = [];

  const allOn = conditions.find((condition) => (
    condition.type === "on" && condition.qualifier === "ALL"
  ));

  if (
    allOn
    && allOn.onTile.has("Crate2")
    && /\[\s*>\s*cratex\s*\|\s*cratex\s*\]/.test(normalized)
  ) {
    const wallNames = new Set(["Wall"]);
    const walls = positionsOf(initialCells, wallNames);
    const wallSet = new Set(walls.map(([row, col]) => `${row},${col}`));
    const targets = positionsOf(initialCells, allOn.tile);
    const pushDistance = reversePushDistances(
      initialCells.length,
      initialCells[0].length,
      wallSet,
      targets,
    );
    evaluators.push((cells) => {
      const unsatisfied = positionsOf(cells, allOn.tile).filter(([row, col]) => (
        !cellHasAny(cells[row][col], allOn.onTile)
      ));
      if (unsatisfied.length === 0) return 0;
      const objects = positionsOf(cells, allOn.onTile);
      return assignmentCost(
        unsatisfied,
        objects,
        (object) => pushDistance(object),
        "sum",
      ) ?? 1;
    });
    certificates.push(
      "crate2_moves_at_most_one_cell_per_input",
      "relaxed_reverse_push_distance",
    );
  } else if (
    allOn
    && /\[\s*>\s*pushable\s*\|\s*pushable\s*\]/.test(normalized)
    && /\[\s*>\s*player\s*\|\s*crate\s*\]\s*->\s*\[\s*>\s*player\s*\|\s*>\s*crate2\s*\]/.test(normalized)
  ) {
    const rows = initialCells.length;
    const cols = initialCells[0].length;
    const validCells = new Set();
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const cell = initialCells[row][col];
        if (!cell.has("Wall") && !cell.has("thefloor")) {
          validCells.add((row * cols) + col);
        }
      }
    }
    const initialObjects = positionsOf(
      initialCells,
      new Set(["Crate", "Crate2"]),
    );
    const requiredCells = new Set(
      positionsOf(initialCells, allOn.tile).map(([row, col]) => (
        (row * cols) + col
      )),
    );
    const placementPdb = buildIndistinguishablePlacementPdb({
      rows,
      cols,
      validCells,
      objectCount: initialObjects.length,
      requiredCells,
    });
    evaluators.push((cells) => {
      const targets = positionsOf(cells, allOn.tile);
      const unsatisfied = targets.filter(([row, col]) => (
        !cellHasAny(cells[row][col], allOn.onTile)
      ));
      if (unsatisfied.length === 0) return 0;
      const ordinary = positionsOf(cells, new Set(["Crate"]));
      if (ordinary.length < unsatisfied.length) return Infinity;
      const bottleneck = assignmentCost(
        unsatisfied,
        ordinary,
        manhattan,
        "bottleneck",
      );
      const abstractObjects = positionsOf(
        cells,
        new Set(["Crate", "Crate2"]),
      ).map(([row, col]) => (row * cols) + col);
      return Math.max(bottleneck, placementPdb.lookup(abstractObjects));
    });
    certificates.push(
      "parallel_chain_moves_at_most_one_cell_per_input",
      "crate_to_crate2_is_irreversible",
      "bottleneck_target_matching",
      `relaxed_chain_push_pattern_database_${placementPdb.size}_states`,
    );
  } else if (allOn && normalized.includes("spawner no stopper")) {
    evaluators.push((cells) => {
      const targets = positionsOf(cells, allOn.tile);
      const crates = positionsOf(cells, allOn.onTile);
      const missing = Math.max(0, targets.length - crates.length);
      const spawner = positionsOf(cells, new Set(["spawner"]))[0];
      const virtualCrates = crates.slice();
      if (spawner) {
        for (let index = 0; index < missing; index += 1) {
          virtualCrates.push(spawner);
        }
      }
      const pushDistance = assignmentCost(
        targets,
        virtualCrates,
        manhattan,
        "sum",
      );
      return Math.max(missing, pushDistance ?? 0);
    });
    certificates.push(
      "spawner_creates_at_most_one_goal_object_per_input",
      "each_goal_object_originates_at_spawner_or_existing_crate",
      "at_most_one_goal_object_moves_one_cell_per_input",
      "serial_transport_assignment",
    );
  } else if (
    allOn
    && normalized.includes("all bend on player")
  ) {
    const starts = positionsOf(
      initialCells,
      new Set(["begina", "beginb"]),
    );
    const finish = starts[0] ?? null;
    evaluators.push((cells) => {
      const player = positionsOf(
        cells,
        new Set(["Playerright", "playerleft"]),
      )[0] ?? null;
      const components = connectedComponents(
        cells,
        new Set(["back1", "back2", "back2_2"]),
      );
      return componentTourLowerBound(player, components, finish);
    });
    certificates.push(
      "colored_components_relaxed_to_single_visit",
      "player_moves_at_most_one_cell_per_input",
    );
  } else if (
    allOn
    && !/\bagain\b|\brigid\b|\btele(?:port)?\b|\brandom\b/.test(normalized)
  ) {
    evaluators.push((cells) => {
      const targets = positionsOf(cells, allOn.tile).filter(([row, col]) => (
        !cellHasAny(cells[row][col], allOn.onTile)
      ));
      if (targets.length === 0) return 0;
      const objects = positionsOf(cells, allOn.onTile);
      return assignmentCost(targets, objects, manhattan, "sum") ?? 1;
    });
    certificates.push(
      "goal_objects_move_at_most_one_cell_per_input",
      "serial_manhattan_assignment",
    );
  } else if (
    allOn
    && normalized.includes("rigid")
    && allOn.onTile.has("Crate")
  ) {
    evaluators.push((cells) => {
      const targets = positionsOf(cells, allOn.tile).filter(([row, col]) => (
        !cellHasAny(cells[row][col], allOn.onTile)
      ));
      if (targets.length === 0) return 0;
      const objects = positionsOf(cells, allOn.onTile);
      return assignmentCost(
        targets,
        objects,
        manhattan,
        "bottleneck",
      ) ?? 1;
    });
    certificates.push(
      "rigid_parallel_objects_move_at_most_one_cell_per_input",
      "bottleneck_target_matching",
    );
  }

  const noCrate = conditions.find((condition) => (
    condition.type === "simple"
    && condition.qualifier === "NO"
    && condition.tile.has("Crate")
  ));
  if (
    noCrate
    && normalized.includes("[> crate | furnace]")
    && !normalized.includes("[]->again")
  ) {
    const rows = initialCells.length;
    const cols = initialCells[0].length;
    const blocked = new Set();
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const cell = initialCells[row][col];
        if (cell.has("Wall") || cell.has("thefloor")) {
          blocked.add(`${row},${col}`);
        }
      }
    }
    const furnaces = positionsOf(
      initialCells,
      new Set(["furnace1", "furnace2", "furnswi1", "furnswi2"]),
    );
    const portals = positionsOf(
      initialCells,
      new Set(["tele", "teleblock"]),
    );
    const links = [];
    for (const from of portals) {
      for (const to of portals) {
        if (from !== to) links.push([from, to]);
      }
    }
    const distance = relaxedGridDistances({
      rows,
      cols,
      blocked,
      goals: furnaces,
      zeroCostLinks: links,
    });
    evaluators.push((cells) => {
      const crates = positionsOf(cells, noCrate.tile);
      const total = crates.reduce((sum, crate) => sum + distance(crate), 0);
      return Number.isFinite(total) ? total : crates.length;
    });
    certificates.push(
      "at_most_one_crate_destroyed_per_input",
      "free_pusher_relaxation",
      "bidirectional_zero_cost_portal_relaxation",
      "serial_crate_to_furnace_distance",
    );
  }

  const heuristic = (state) => {
    const cells = cellNameSets(state);
    if (conditions.every((condition) => conditionSatisfied(cells, condition))) {
      return 0;
    }
    let value = 1;
    for (const evaluator of evaluators) {
      value = Math.max(value, evaluator(cells));
    }
    return value;
  };

  return {
    name: evaluators.length > 0 ? "certified_game_file" : "unit_lower_bound",
    certificates,
    conditions,
    evaluate: heuristic,
  };
}

function createCertifiedCanonicalizer(source) {
  const normalized = source.toLowerCase().replace(/\s+/g, " ");
  const spriteAliases = new Map();
  const certificates = [];
  if (
    normalized.includes("[cratex] ->[cratex2cha]")
    && normalized.includes("[cratex2] ->[cratexcha]")
    && normalized.includes("[cratex2cha]->[cratex2]")
    && normalized.includes("[cratexcha]->[cratex]")
    && normalized.includes("[targetx] ->[targetx2cha]")
    && normalized.includes("[targetx2] ->[targetxcha]")
    && normalized.includes("[targetx2cha]->[targetx2]")
    && normalized.includes("[targetxcha]->[targetx]")
  ) {
    for (const name of ["Cratex", "cratex2", "Cratexcha", "Cratex2cha"]) {
      spriteAliases.set(name.toLowerCase(), "Crate");
    }
    for (const name of ["Targetx", "targetx2", "targetxcha", "targetx2cha"]) {
      spriteAliases.set(name.toLowerCase(), "Target");
    }
    certificates.push(
      "four_phase_crate_cycle_is_gameplay_alias",
      "four_phase_target_cycle_is_gameplay_alias",
    );
  }
  if (
    normalized.includes("[furnace1]->[furnswi1]")
    && normalized.includes("[furnswi1]->[furnace2]")
    && normalized.includes("[furnace2]->[furnswi2]")
    && normalized.includes("[furnswi2]->[furnace1]")
    && normalized.includes("furnace = furnace1 or furnace2 or furnswi1 or furnswi2")
  ) {
    for (const name of ["furnace1", "furnswi1", "furnace2", "furnswi2"]) {
      spriteAliases.set(name, "Furnace");
    }
    for (const name of ["playerright", "playerleft"]) {
      spriteAliases.set(name, "Player");
    }
    for (const name of ["wallfeel", "cratefeel", "teleblofeel"]) {
      spriteAliases.set(name, null);
    }
    certificates.push(
      "four_phase_furnace_cycle_is_gameplay_alias",
      "player_facing_is_cosmetic",
      "feel_sprites_are_deleted_and_rederived_each_input",
    );
  }

  const normalizeToken = (token) => {
    const separator = token.indexOf(" ");
    const movement = separator < 0 ? "" : token.slice(0, separator);
    const name = separator < 0 ? token : token.slice(separator + 1);
    const mapped = spriteAliases.get(name.toLowerCase());
    if (mapped === null) return null;
    const alias = mapped ?? name;
    return movement ? `${movement} ${alias}` : alias;
  };
  return {
    certified: certificates.length > 0,
    certificates,
    key(state) {
      const cells = state.cells.map((row) => row.map((cell) => (
        cell.map(normalizeToken).filter((token) => token !== null).sort()
      )));
      return JSON.stringify([
        state.levelIndex,
        state.pendingInput,
        state.hasAgain,
        cells,
      ]);
    },
  };
}

module.exports = {
  assignmentCost,
  cellNameSets,
  compileConditions,
  conditionSatisfied,
  createCertifiedCanonicalizer,
  createCertifiedHeuristic,
  manhattan,
  reversePushDistances,
  relaxedGridDistances,
  tileNames,
  tokenName,
};
