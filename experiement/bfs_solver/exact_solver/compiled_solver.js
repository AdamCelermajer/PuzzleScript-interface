"use strict";

const { performance } = require("node:perf_hooks");
const { PriorityQueue } = require("./priority_queue");
const { compileProfile } = require("./compiled_profiles");

function reconstruct(nodes, nodeIndex) {
  const actions = [];
  for (let current = nodeIndex; current >= 0; current = nodes[current].parent) {
    const action = nodes[current].action;
    if (action !== null) actions.push(action);
  }
  return actions.reverse();
}

function solveCompiledProfile({
  source,
  gameId,
  gameData,
  initialState,
  timeoutMs = 60_000,
  maxStates = 2_000_000,
  onProgress = null,
  progressIntervalMs = 1_000,
}) {
  const profile = compileProfile({ source, gameId, gameData, initialState });
  if (!profile) return null;

  const started = performance.now();
  const initialH = profile.heuristic(profile.initial);
  const nodes = [{
    state: profile.initial,
    parent: -1,
    action: null,
    g: 0,
    h: initialH,
  }];
  let serial = 0;
  const open = new PriorityQueue((left, right) => (
    (left.f - right.f)
    || (left.h - right.h)
    || (right.g - left.g)
    || (left.serial - right.serial)
  ));
  open.push({ nodeIndex: 0, f: initialH, h: initialH, g: 0, serial: serial++ });
  const bestG = new Map([[profile.key(profile.initial), 0]]);
  let expandedStates = 0;
  let transitions = 0;
  let duplicateSuccessors = 0;
  let visitedDuplicates = 0;
  let deadlocks = 0;
  let reopened = 0;
  let maxDepth = 0;
  let solutionNode = null;
  let status = "exhausted";
  let lastProgress = -Infinity;

  while (open.size > 0) {
    const elapsedMs = performance.now() - started;
    if (elapsedMs >= timeoutMs) {
      status = "time_limit";
      break;
    }
    if (bestG.size >= maxStates) {
      status = "state_limit";
      break;
    }
    const entry = open.pop();
    const node = nodes[entry.nodeIndex];
    if (bestG.get(profile.key(node.state)) !== node.g) continue;
    if (profile.isGoal(node.state)) {
      solutionNode = entry.nodeIndex;
      status = "solved";
      break;
    }
    expandedStates += 1;
    const localKeys = new Set();
    for (const successor of profile.successors(node.state)) {
      transitions += 1;
      const key = profile.key(successor.state);
      if (key === profile.key(node.state) || localKeys.has(key)) {
        duplicateSuccessors += 1;
        continue;
      }
      localKeys.add(key);
      const g = node.g + 1;
      const previous = bestG.get(key);
      if (previous !== undefined && previous <= g) {
        visitedDuplicates += 1;
        continue;
      }
      const h = profile.heuristic(successor.state);
      if (!Number.isFinite(h)) {
        deadlocks += 1;
        continue;
      }
      if (previous !== undefined) reopened += 1;
      bestG.set(key, g);
      const nodeIndex = nodes.length;
      nodes.push({
        state: successor.state,
        parent: entry.nodeIndex,
        action: successor.action,
        g,
        h,
      });
      open.push({ nodeIndex, f: g + h, h, g, serial: serial++ });
      maxDepth = Math.max(maxDepth, g);
    }
    if (onProgress && elapsedMs - lastProgress >= progressIntervalMs) {
      lastProgress = elapsedMs;
      onProgress({
        elapsedMs,
        expandedStates,
        uniqueStates: bestG.size,
        frontierEntries: open.size,
        bestF: open.peek()?.f ?? null,
        bestH: open.peek()?.h ?? null,
      });
    }
  }

  const elapsedMs = performance.now() - started;
  const solutionActions = solutionNode === null
    ? null
    : reconstruct(nodes, solutionNode);
  return {
    gameId,
    levelIndex: initialState.levelIndex,
    status,
    solved: solutionNode !== null,
    optimalityProven: solutionNode !== null,
    solutionDepth: solutionActions?.length ?? null,
    solutionActions,
    engine: profile.name,
    proof: {
      graph: "compiled_rule_relevant_state_graph",
      edgeCost: "one_input",
      algorithm: "A_star",
      certificates: profile.certificates,
    },
    heuristic: {
      name: "compiled_certified_lower_bound",
      initialValue: initialH,
    },
    metadata: profile.metadata,
    expandedStates,
    uniqueStates: bestG.size,
    frontierEntries: open.size,
    transitions,
    duplicateSuccessors,
    visitedDuplicates,
    deadlocks,
    reopened,
    maxDepth,
    elapsedMs,
    transitionsPerSecond: transitions / Math.max(elapsedMs / 1000, 0.001),
    limits: { maxStates, timeoutMs },
  };
}

module.exports = { solveCompiledProfile };
