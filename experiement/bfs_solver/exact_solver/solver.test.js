"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { solveSourceExact } = require("./solver");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

function sourceFor(gameId) {
  return fs.readFileSync(path.join(
    REPO_ROOT,
    "puzzlescript_interface",
    "games",
    gameId,
    "script.txt",
  ), "utf8");
}

test("certified exact A* preserves Sokoban's known optimal depth", async () => {
  const result = await solveSourceExact({
    source: sourceFor("ps_sokoban_basic-v1"),
    gameId: "ps_sokoban_basic-v1",
    levelIndex: 0,
    maxStates: 10_000,
    timeoutMs: 10_000,
  });
  assert.equal(result.status, "solved");
  assert.equal(result.solutionDepth, 33);
  assert.equal(result.optimalityProven, true);
  assert.ok(result.heuristic.initialValue > 1);
});

test("priority search safely eliminates exact no-op actions", async () => {
  const result = await solveSourceExact({
    source: sourceFor("ps_sokoban_basic-v1"),
    gameId: "ps_sokoban_basic-v1",
    levelIndex: 0,
    maxStates: 10_000,
    timeoutMs: 10_000,
    visitedMode: "semantic",
  });
  assert.equal(result.status, "solved");
  assert.equal(result.solutionDepth, 33);
  assert.ok(result.unchanged > 0);
});

test("game-file certified animation quotient is available only when proven", async () => {
  const result = await solveSourceExact({
    source: sourceFor("ps_the_art_of_storage-v1"),
    gameId: "ps_the_art_of_storage-v1",
    levelIndex: 2,
    maxStates: 20,
    timeoutMs: 5_000,
    visitedMode: "certified",
  });
  assert.equal(result.stateQuotient.certified, true);
  assert.ok(result.stateQuotient.certificates.length >= 2);
});
