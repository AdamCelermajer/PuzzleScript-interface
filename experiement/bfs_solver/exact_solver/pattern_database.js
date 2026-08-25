"use strict";

function combinations(values, choose, start = 0, prefix = [], output = []) {
  if (prefix.length === choose) {
    output.push(prefix.slice());
    return output;
  }
  const remaining = choose - prefix.length;
  for (let index = start; index <= values.length - remaining; index += 1) {
    prefix.push(values[index]);
    combinations(values, choose, index + 1, prefix, output);
    prefix.pop();
  }
  return output;
}

function placementKey(positions) {
  return positions.slice().sort((left, right) => left - right).join(",");
}

function chainPushSuccessors(positions, rows, cols, validCells) {
  const occupied = new Set(positions);
  const successors = new Map();
  const directions = [
    [-1, 0],
    [1, 0],
    [0, -1],
    [0, 1],
  ];
  for (const start of positions) {
    const startRow = Math.floor(start / cols);
    const startCol = start % cols;
    for (const [dr, dc] of directions) {
      const chain = [];
      let row = startRow;
      let col = startCol;
      while (
        row >= 0 && row < rows && col >= 0 && col < cols
        && occupied.has((row * cols) + col)
      ) {
        chain.push((row * cols) + col);
        row += dr;
        col += dc;
      }
      const destination = (row * cols) + col;
      if (
        row < 0 || row >= rows || col < 0 || col >= cols
        || !validCells.has(destination)
        || occupied.has(destination)
      ) {
        continue;
      }
      const moved = new Set(occupied);
      for (const cell of chain) moved.delete(cell);
      for (const cell of chain) {
        const cellRow = Math.floor(cell / cols);
        const cellCol = cell % cols;
        moved.add(((cellRow + dr) * cols) + cellCol + dc);
      }
      const next = [...moved].sort((left, right) => left - right);
      successors.set(placementKey(next), next);
    }
  }
  return successors.values();
}

function buildIndistinguishablePlacementPdb({
  rows,
  cols,
  validCells,
  objectCount,
  requiredCells,
}) {
  const allCells = [...validCells].sort((left, right) => left - right);
  const required = [...requiredCells].sort((left, right) => left - right);
  if (required.some((cell) => !validCells.has(cell))) {
    throw new Error("Pattern database goal contains a blocked cell");
  }
  if (objectCount < required.length) {
    return {
      size: 0,
      lookup: () => Infinity,
    };
  }
  const remainingCells = allCells.filter((cell) => !requiredCells.has(cell));
  const roots = combinations(
    remainingCells,
    objectCount - required.length,
  ).map((extra) => [...required, ...extra].sort((left, right) => left - right));
  const distances = new Map();
  const queue = [];
  for (const root of roots) {
    const key = placementKey(root);
    if (!distances.has(key)) {
      distances.set(key, 0);
      queue.push(root);
    }
  }
  let head = 0;
  while (head < queue.length) {
    const state = queue[head++];
    const distance = distances.get(placementKey(state));
    for (const next of chainPushSuccessors(
      state,
      rows,
      cols,
      validCells,
    )) {
      const key = placementKey(next);
      if (!distances.has(key)) {
        distances.set(key, distance + 1);
        queue.push(next);
      }
    }
  }
  return {
    size: distances.size,
    lookup(positions) {
      return distances.get(placementKey(positions)) ?? Infinity;
    },
  };
}

module.exports = {
  buildIndistinguishablePlacementPdb,
  chainPushSuccessors,
  combinations,
  placementKey,
};
