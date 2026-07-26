"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { solveWholeGameStateful } = require("./whole_game_solver");

const source = fs.readFileSync(path.resolve(
  __dirname,
  "..",
  "..",
  "puzzlescript_interface",
  "games",
  "ps_sokoban_basic-v1",
  "script.txt",
), "utf8");

test("whole-game BFS solves every playable Sokoban level in order", async () => {
  const progress = [];
  const result = await solveWholeGameStateful({
    source,
    gameId: "ps_sokoban_basic-v1",
    maxStates: 10_000,
    timeoutMs: 10_000,
    visitedMode: "semantic",
    progressIntervalMs: 0,
    onProgress: (item) => progress.push(item),
  });

  assert.equal(result.solved, true);
  assert.equal(result.totalLevels, 2);
  assert.equal(result.levelsSolved, 2);
  assert.deepEqual(result.levelResults.map((item) => item.solutionDepth), [33, 16]);
  assert.equal(result.solutionDepth, 49);
  assert.equal(result.solutionActions.length, 49);
  assert.ok(progress.some((item) => item.levelNumber === 2));
  assert.equal(progress.at(-1).totalLevels, 2);
});
