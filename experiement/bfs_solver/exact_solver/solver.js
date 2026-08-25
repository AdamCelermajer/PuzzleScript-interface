"use strict";

const { performance } = require("node:perf_hooks");
const {
  availableSearchActions,
  inspectGameSource,
} = require("../solver");
const { PuzzleScriptMachineAdapter } = require("../machine_state_adapter");
const { MachineStateCodec } = require("../machine_state_codec");
const {
  createCertifiedCanonicalizer,
  createCertifiedHeuristic,
} = require("./heuristics");
const { PriorityQueue } = require("./priority_queue");

function semanticKey(state) {
  const cells = state.cells.map((row) => (
    row.map((cell) => [...cell].sort())
  ));
  return JSON.stringify([
    state.levelIndex,
    state.pendingInput,
    state.hasAgain,
    cells,
  ]);
}

function reconstruct(nodes, nodeIndex) {
  const actions = [];
  let current = nodeIndex;
  while (current >= 0) {
    const node = nodes[current];
    if (node.action !== null) actions.push(node.action);
    current = node.parent;
  }
  return actions.reverse();
}

async function solveSourceExact({
  source,
  gameId,
  levelIndex = null,
  maxStates = 250_000,
  timeoutMs = 60_000,
  maxAgainTicks = 100,
  visitedMode = "exact",
  progressIntervalMs = 1_000,
  onProgress = null,
}) {
  if (!["exact", "semantic", "certified"].includes(visitedMode)) {
    throw new Error(`Unknown visited mode: ${visitedMode}`);
  }
  const inspection = inspectGameSource(source);
  const selectedLevel = levelIndex ?? inspection.firstLevelIndex;
  if (inspection.formalGoalCount === 0) {
    return { gameId, status: "ineligible", solved: false };
  }
  if (inspection.unsupportedReasons.length > 0) {
    return {
      gameId,
      status: "unsupported",
      solved: false,
      reason: inspection.unsupportedReasons.join(","),
    };
  }

  const adapter = new PuzzleScriptMachineAdapter({
    source,
    levelIndex: selectedLevel,
  });
  const codec = new MachineStateCodec(adapter.initialState);
  const heuristic = createCertifiedHeuristic({
    gameData: adapter.gameData,
    source,
    initialState: adapter.initialState,
  });
  const canonicalizer = createCertifiedCanonicalizer(source);
  if (visitedMode === "certified" && !canonicalizer.certified) {
    throw new Error("No certified state quotient is available for this game");
  }
  const keyFor = (state, encoded) => (
    visitedMode === "exact"
      ? codec.key(encoded)
      : visitedMode === "certified"
        ? canonicalizer.key(state)
        : semanticKey(state)
  );
  const initialEncoded = codec.encode(adapter.initialState);
  const initialKey = keyFor(adapter.initialState, initialEncoded);
  const initialH = heuristic.evaluate(adapter.initialState);
  const nodes = [{
    state: initialEncoded,
    key: initialKey,
    parent: -1,
    action: null,
    g: 0,
    h: initialH,
    terminal: false,
  }];
  let serial = 0;
  const open = new PriorityQueue((left, right) => (
    (left.f - right.f)
    || (left.h - right.h)
    || (right.g - left.g)
    || (left.serial - right.serial)
  ));
  open.push({ nodeIndex: 0, f: initialH, h: initialH, g: 0, serial: serial++ });
  const bestG = new Map([[initialKey, 0]]);
  let expandedStates = 0;
  let transitions = 0;
  let ticks = 0;
  let unchanged = 0;
  let duplicateSuccessors = 0;
  let visitedDuplicates = 0;
  let deadlocks = 0;
  let reopened = 0;
  let maxDepth = 0;
  let lastProgress = -Infinity;
  let status = "exhausted";
  let solutionNode = null;
  const started = performance.now();

  const report = (force = false) => {
    if (typeof onProgress !== "function") return;
    const now = performance.now();
    if (!force && now - lastProgress < progressIntervalMs) return;
    lastProgress = now;
    onProgress({
      elapsedMs: now - started,
      expandedStates,
      uniqueStates: bestG.size,
      frontierEntries: open.size,
      transitions,
      maxDepth,
      bestF: open.peek()?.f ?? null,
      bestH: open.peek()?.h ?? null,
      deadlocks,
    });
  };
  report(true);

  search:
  while (open.size > 0) {
    if (performance.now() - started >= timeoutMs) {
      status = "time_limit";
      break;
    }
    if (bestG.size >= maxStates) {
      status = "state_limit";
      break;
    }
    const entry = open.pop();
    const node = nodes[entry.nodeIndex];
    if (node.terminal) {
      status = "solved";
      solutionNode = entry.nodeIndex;
      break;
    }
    if (bestG.get(node.key) !== node.g) continue;

    expandedStates += 1;
    maxDepth = Math.max(maxDepth, node.g);
    const parentState = codec.decode(node.state);
    const localSuccessors = new Set();
    for (const action of availableSearchActions(adapter.gameData)) {
      if (performance.now() - started >= timeoutMs) {
        status = "time_limit";
        break search;
      }
      const result = await adapter.transition(
        parentState,
        action.button,
        maxAgainTicks,
      );
      transitions += 1;
      ticks += result.ticks;
      if (result.againLimit) {
        status = "again_limit";
        break search;
      }
      const childG = node.g + 1;
      if (result.won) {
        const goalKey = "__TERMINAL_GOAL__";
        const previous = bestG.get(goalKey);
        if (previous === undefined || childG < previous) {
          bestG.set(goalKey, childG);
          const goalIndex = nodes.length;
          nodes.push({
            state: null,
            key: goalKey,
            parent: entry.nodeIndex,
            action: action.name,
            g: childG,
            h: 0,
            terminal: true,
          });
          open.push({
            nodeIndex: goalIndex,
            f: childG,
            h: 0,
            g: childG,
            serial: serial++,
          });
        }
        continue;
      }

      const childEncoded = codec.encode(result.state);
      const childKey = keyFor(result.state, childEncoded);
      if (childKey === node.key) {
        unchanged += 1;
        continue;
      }
      if (localSuccessors.has(childKey)) {
        duplicateSuccessors += 1;
        continue;
      }
      localSuccessors.add(childKey);
      const childH = heuristic.evaluate(result.state);
      if (!Number.isFinite(childH)) {
        deadlocks += 1;
        continue;
      }
      const previousG = bestG.get(childKey);
      if (previousG !== undefined && previousG <= childG) {
        visitedDuplicates += 1;
        continue;
      }
      if (previousG !== undefined) reopened += 1;
      bestG.set(childKey, childG);
      const childIndex = nodes.length;
      nodes.push({
        state: childEncoded,
        key: childKey,
        parent: entry.nodeIndex,
        action: action.name,
        g: childG,
        h: childH,
        terminal: false,
      });
      open.push({
        nodeIndex: childIndex,
        f: childG + childH,
        h: childH,
        g: childG,
        serial: serial++,
      });
    }
    report();
  }
  report(true);

  const elapsedMs = performance.now() - started;
  const solutionActions = solutionNode === null
    ? null
    : reconstruct(nodes, solutionNode);
  return {
    gameId,
    levelIndex: selectedLevel,
    status,
    solved: status === "solved",
    optimalityProven: status === "solved"
      && (visitedMode === "exact" || visitedMode === "certified"),
    shortestInSemanticStateGraph: status === "solved" && visitedMode === "semantic",
    solutionDepth: solutionActions?.length ?? null,
    solutionActions,
    heuristic: {
      name: heuristic.name,
      certificates: heuristic.certificates,
      initialValue: initialH,
    },
    stateQuotient: visitedMode === "certified"
      ? {
        certified: canonicalizer.certified,
        certificates: canonicalizer.certificates,
      }
      : null,
    visitedMode,
    expandedStates,
    uniqueStates: bestG.size,
    frontierEntries: open.size,
    transitions,
    ticks,
    unchanged,
    duplicateSuccessors,
    visitedDuplicates,
    deadlocks,
    reopened,
    maxDepth,
    elapsedMs,
    transitionsPerSecond: elapsedMs > 0
      ? transitions / (elapsedMs / 1000)
      : 0,
    limits: { maxStates, timeoutMs, maxAgainTicks },
  };
}

module.exports = {
  reconstruct,
  semanticKey,
  solveSourceExact,
};
