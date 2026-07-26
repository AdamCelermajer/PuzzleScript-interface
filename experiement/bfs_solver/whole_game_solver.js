"use strict";

const { performance } = require("node:perf_hooks");
const { inspectGameSource } = require("./solver");
const { solveSourceStateful } = require("./stateful_solver");

function playableLevelIndexes(gameData) {
  return gameData.levels
    .map((level, index) => (level.type === "LEVEL_MAP" ? index : -1))
    .filter((index) => index >= 0);
}

function totalsBefore(levelResults) {
  return levelResults.reduce((totals, result) => ({
    expandedStates: totals.expandedStates + (result.expandedStates || 0),
    uniqueStates: totals.uniqueStates + (result.uniqueStates || 0),
    transitions: totals.transitions + (result.transitions || 0),
    ticks: totals.ticks + (result.ticks || 0),
    duplicates: totals.duplicates + (result.duplicates || 0),
    unchanged: totals.unchanged + (result.unchanged || 0),
    cacheVariantDuplicates:
      totals.cacheVariantDuplicates + (result.cacheVariantDuplicates || 0),
  }), {
    expandedStates: 0,
    uniqueStates: 0,
    transitions: 0,
    ticks: 0,
    duplicates: 0,
    unchanged: 0,
    cacheVariantDuplicates: 0,
  });
}

async function solveWholeGameStateful({
  source,
  gameId,
  maxStates = 100_000,
  timeoutMs = 10_000,
  maxAgainTicks = 100,
  visitedMode = "semantic",
  onProgress = null,
  progressIntervalMs = 200,
}) {
  const started = performance.now();
  const inspection = inspectGameSource(source);
  const levels = playableLevelIndexes(inspection.data);
  if (levels.length === 0) {
    return {
      gameId,
      status: "ineligible",
      reason: "no_playable_level",
      solved: false,
      levelsSolved: 0,
      totalLevels: 0,
    };
  }
  if (inspection.formalGoalCount === 0) {
    return {
      gameId,
      status: "ineligible",
      reason: "no_formal_win_condition",
      solved: false,
      levelsSolved: 0,
      totalLevels: levels.length,
    };
  }
  if (inspection.unsupportedReasons.length > 0) {
    return {
      gameId,
      status: "unsupported",
      reason: inspection.unsupportedReasons.join(","),
      solved: false,
      levelsSolved: 0,
      totalLevels: levels.length,
    };
  }

  const levelResults = [];
  const solutionActions = [];
  let maxDepthDiscovered = 0;

  for (const [levelOffset, levelIndex] of levels.entries()) {
    const prior = totalsBefore(levelResults);
    const elapsedBeforeLevel = performance.now() - started;
    const remainingTimeoutMs = Math.max(0, timeoutMs - elapsedBeforeLevel);
    const remainingStates = Math.max(0, maxStates - prior.uniqueStates);
    if (remainingTimeoutMs <= 0 || remainingStates <= 0) {
      return buildWholeGameResult({
        gameId,
        status: remainingTimeoutMs <= 0 ? "time_limit" : "state_limit",
        levels,
        levelResults,
        solutionActions,
        maxDepthDiscovered,
        started,
        limits: { maxStates, timeoutMs, maxAgainTicks, visitedMode },
        failedLevelNumber: levelOffset + 1,
        failedLevelIndex: levelIndex,
      });
    }

    const result = await solveSourceStateful({
      source,
      gameId,
      levelIndex,
      maxStates: remainingStates,
      timeoutMs: remainingTimeoutMs,
      maxAgainTicks,
      visitedMode,
      progressIntervalMs,
      onProgress: typeof onProgress === "function"
        ? (progress) => {
          maxDepthDiscovered = Math.max(
            maxDepthDiscovered,
            progress.maxDepthDiscovered,
          );
          const elapsedMs = performance.now() - started;
          onProgress({
            ...progress,
            elapsedMs,
            timeoutMs,
            timeFraction: Math.min(1, elapsedMs / timeoutMs),
            expandedStates: prior.expandedStates + progress.expandedStates,
            uniqueStates: prior.uniqueStates + progress.uniqueStates,
            transitions: prior.transitions + progress.transitions,
            maxStates,
            stateFraction: Math.min(
              1,
              (prior.uniqueStates + progress.uniqueStates) / maxStates,
            ),
            levelNumber: levelOffset + 1,
            totalLevels: levels.length,
            currentLevelIndex: levelIndex,
            levelsSolved: levelOffset,
            actionsSolved: solutionActions.length,
          });
        }
        : null,
    });

    levelResults.push(result);
    maxDepthDiscovered = Math.max(
      maxDepthDiscovered,
      result.maxDepthDiscovered || 0,
    );
    if (!result.solved) {
      return buildWholeGameResult({
        gameId,
        status: result.status,
        reason: result.reason,
        levels,
        levelResults,
        solutionActions,
        maxDepthDiscovered,
        started,
        limits: { maxStates, timeoutMs, maxAgainTicks, visitedMode },
        failedLevelNumber: levelOffset + 1,
        failedLevelIndex: levelIndex,
      });
    }
    solutionActions.push(...result.solutionActions);
  }

  return buildWholeGameResult({
    gameId,
    status: "solved",
    levels,
    levelResults,
    solutionActions,
    maxDepthDiscovered,
    started,
    limits: { maxStates, timeoutMs, maxAgainTicks, visitedMode },
  });
}

function buildWholeGameResult({
  gameId,
  status,
  reason = "",
  levels,
  levelResults,
  solutionActions,
  maxDepthDiscovered,
  started,
  limits,
  failedLevelNumber = null,
  failedLevelIndex = null,
}) {
  const totals = totalsBefore(levelResults);
  const solvedResults = levelResults.filter((result) => result.solved);
  const solved = status === "solved" && solvedResults.length === levels.length;
  const searchMs = performance.now() - started;
  return {
    gameId,
    status,
    reason,
    solved,
    wholeGame: true,
    levelsSolved: solvedResults.length,
    totalLevels: levels.length,
    playableLevelIndexes: levels,
    failedLevelNumber,
    failedLevelIndex,
    solutionDepth: solved ? solutionActions.length : null,
    solutionActions: solved ? solutionActions : null,
    partialSolutionDepth: solutionActions.length,
    levelResults,
    maxDepthDiscovered,
    ...totals,
    searchMs,
    totalMs: searchMs,
    searchTransitionsPerSecond: searchMs > 0
      ? totals.transitions / (searchMs / 1000)
      : 0,
    optimalityProven: solved && limits.visitedMode === "exact",
    shortestInSemanticStateGraph: solved && limits.visitedMode === "semantic",
    limits,
  };
}

module.exports = {
  playableLevelIndexes,
  solveWholeGameStateful,
};
