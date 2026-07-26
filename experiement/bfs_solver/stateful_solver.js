"use strict";

const { performance } = require("node:perf_hooks");
const { availableSearchActions, inspectGameSource } = require("./solver");
const { PuzzleScriptMachineAdapter } = require("./machine_state_adapter");
const { MachineStateCodec } = require("./machine_state_codec");

function canonicalSemanticKey(state) {
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

function reconstructActions(nodes, parentIndex, finalAction) {
  const reversed = [finalAction];
  let nodeIndex = parentIndex;
  while (nodeIndex >= 0) {
    const node = nodes[nodeIndex];
    if (node.action !== null) reversed.push(node.action);
    nodeIndex = node.parent;
  }
  return reversed.reverse();
}

async function solveSourceStateful({
  source,
  gameId,
  levelIndex = null,
  maxStates = 100_000,
  timeoutMs = 10_000,
  maxAgainTicks = 100,
  visitedMode = "exact",
  onProgress = null,
  progressIntervalMs = 200,
}) {
  if (visitedMode !== "exact" && visitedMode !== "semantic") {
    throw new Error(`Unknown visitedMode: ${visitedMode}`);
  }
  const totalStarted = performance.now();
  const inspection = inspectGameSource(source);
  const selectedLevel = levelIndex ?? inspection.firstLevelIndex;
  const searchActions = availableSearchActions(inspection.data);
  if (inspection.formalGoalCount === 0) {
    return { gameId, levelIndex: selectedLevel, status: "ineligible", solved: false };
  }
  if (inspection.unsupportedReasons.length > 0) {
    return {
      gameId,
      levelIndex: selectedLevel,
      status: "unsupported",
      solved: false,
      reason: inspection.unsupportedReasons.join(","),
    };
  }

  const initStarted = performance.now();
  const adapter = new PuzzleScriptMachineAdapter({ source, levelIndex: selectedLevel });
  const initialState = adapter.initialState;
  const codec = new MachineStateCodec(initialState);
  const initialEncoded = codec.encode(initialState);
  const initialFullKey = codec.key(initialEncoded);
  const initialKey = visitedMode === "exact"
    ? initialFullKey
    : canonicalSemanticKey(initialState);
  const rows = initialState.cells.length;
  const cols = initialState.cells[0]?.length ?? 0;
  const initMs = performance.now() - initStarted;

  const nodes = [{
    state: initialEncoded,
    key: initialKey,
    fullKey: initialFullKey,
    parent: -1,
    action: null,
    depth: 0,
  }];
  const visited = new Map([[initialKey, 0]]);
  let head = 0;
  let transitions = 0;
  let ticks = 0;
  let duplicates = 0;
  let unchanged = 0;
  let cacheVariantDuplicates = 0;
  let transitionMs = 0;
  let keyMs = 0;
  let peakHeapBytes = process.memoryUsage().heapUsed;
  let status = "exhausted";
  let solutionActions = null;
  let solutionDepth = null;
  let maxDepthDiscovered = 0;
  const searchStarted = performance.now();
  let lastProgressAt = -Infinity;

  const reportProgress = (force = false) => {
    if (typeof onProgress !== "function") return;
    const now = performance.now();
    if (!force && now - lastProgressAt < progressIntervalMs) return;
    lastProgressAt = now;
    const elapsedMs = now - searchStarted;
    onProgress({
      elapsedMs,
      timeoutMs,
      timeFraction: timeoutMs > 0 ? Math.min(1, elapsedMs / timeoutMs) : 0,
      expandedStates: head,
      uniqueStates: visited.size,
      frontierStates: nodes.length - head,
      transitions,
      maxDepthDiscovered,
      currentDepth: nodes[head]?.depth ?? maxDepthDiscovered,
      transitionsPerSecond: elapsedMs > 0
        ? transitions / (elapsedMs / 1000)
        : 0,
      maxStates,
      stateFraction: maxStates > 0 ? Math.min(1, visited.size / maxStates) : 0,
    });
  };

  reportProgress(true);

  searchLoop:
  while (head < nodes.length) {
    if (performance.now() - searchStarted >= timeoutMs) {
      status = "time_limit";
      break;
    }
    if (visited.size >= maxStates) {
      status = "state_limit";
      break;
    }

    const parentIndex = head;
    const parent = nodes[head++];
    maxDepthDiscovered = Math.max(maxDepthDiscovered, parent.depth);
    const parentState = codec.decode(parent.state);
    for (const action of searchActions) {
      if (performance.now() - searchStarted >= timeoutMs) {
        status = "time_limit";
        break searchLoop;
      }

      const transitionStarted = performance.now();
      const result = await adapter.transition(parentState, action.button, maxAgainTicks);
      transitionMs += performance.now() - transitionStarted;
      transitions += 1;
      ticks += result.ticks;

      if (result.againLimit) {
        status = "again_limit";
        break searchLoop;
      }
      if (result.won) {
        status = "solved";
        solutionActions = reconstructActions(nodes, parentIndex, action.name);
        solutionDepth = solutionActions.length;
        break searchLoop;
      }

      const keyStarted = performance.now();
      const childState = codec.encode(result.state);
      const childFullKey = codec.key(childState);
      const childKey = visitedMode === "exact"
        ? childFullKey
        : canonicalSemanticKey(result.state);
      keyMs += performance.now() - keyStarted;
      if (childKey === parent.key) {
        unchanged += 1;
        continue;
      }
      if (visited.has(childKey)) {
        const existingNode = nodes[visited.get(childKey)];
        if (existingNode.fullKey !== childFullKey) cacheVariantDuplicates += 1;
        duplicates += 1;
        continue;
      }

      const nodeIndex = nodes.length;
      visited.set(childKey, nodeIndex);
      nodes.push({
        state: childState,
        key: childKey,
        fullKey: childFullKey,
        parent: parentIndex,
        action: action.name,
        depth: parent.depth + 1,
      });
      maxDepthDiscovered = Math.max(maxDepthDiscovered, parent.depth + 1);
      if (visited.size >= maxStates) {
        status = "state_limit";
        break searchLoop;
      }
    }

    if (transitions % 5_000 === 0) {
      peakHeapBytes = Math.max(peakHeapBytes, process.memoryUsage().heapUsed);
    }
    reportProgress();
  }

  reportProgress(true);
  peakHeapBytes = Math.max(peakHeapBytes, process.memoryUsage().heapUsed);
  const searchMs = performance.now() - searchStarted;
  return {
    gameId,
    levelIndex: selectedLevel,
    board: { rows, cols, cells: rows * cols },
    status,
    solved: status === "solved",
    optimalityProven: status === "solved" && visitedMode === "exact",
    shortestInSemanticStateGraph: status === "solved" && visitedMode === "semantic",
    solutionDepth,
    solutionActions,
    expandedStates: head,
    uniqueStates: visited.size,
    frontierStates: nodes.length - head,
    maxDepthDiscovered,
    transitions,
    ticks,
    duplicates,
    unchanged,
    cacheVariantDuplicates,
    visitedMode,
    parseMs: inspection.parseMs,
    initMs,
    searchMs,
    transitionMs,
    keyMs,
    totalMs: performance.now() - totalStarted,
    searchTransitionsPerSecond: searchMs > 0 ? transitions / (searchMs / 1000) : 0,
    engineTransitionsPerSecond: transitionMs > 0
      ? transitions / (transitionMs / 1000)
      : 0,
    compactBytesPerInitialState: codec.byteLength(initialEncoded),
    initialStateKeyBytes: Buffer.byteLength(initialKey),
    peakHeapBytes,
    limits: { maxStates, timeoutMs, maxAgainTicks, visitedMode },
  };
}

module.exports = {
  canonicalSemanticKey,
  solveSourceStateful,
};
