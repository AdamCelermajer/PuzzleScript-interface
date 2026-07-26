"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { solveSourceStateful } = require("./stateful_solver");
const { PuzzleScriptMachineAdapter } = require("./machine_state_adapter");
const { MachineStateCodec } = require("./machine_state_codec");

const REPO_ROOT = path.resolve(__dirname, "..", "..");

function sourceFor(gameId) {
  return fs.readFileSync(path.join(
    REPO_ROOT,
    "puzzlescript_interface",
    "games",
    gameId,
    "script.txt",
  ), "utf8");
}

test("complete machine state codec round-trips exactly", () => {
  const adapter = new PuzzleScriptMachineAdapter({
    source: sourceFor("ps_compressed-v1"),
    levelIndex: 2,
  });
  const codec = new MachineStateCodec(adapter.initialState);
  const encoded = codec.encode(adapter.initialState);
  assert.deepEqual(codec.decode(encoded), adapter.initialState);
  assert.equal(codec.key(encoded), codec.key(codec.encode(adapter.initialState)));
  assert.ok(codec.byteLength(encoded) < Buffer.byteLength(JSON.stringify(adapter.initialState)));
});

test("stateful BFS preserves Sokoban optimal depth without replay", async () => {
  const result = await solveSourceStateful({
    source: sourceFor("ps_sokoban_basic-v1"),
    gameId: "ps_sokoban_basic-v1",
    levelIndex: 0,
    maxStates: 5_000,
    timeoutMs: 5_000,
  });
  assert.equal(result.status, "solved");
  assert.equal(result.solutionDepth, 33);
  assert.equal(result.optimalityProven, true);
  assert.equal(result.transitions, result.ticks);
});

test("stateful BFS reports live depth and state progress", async () => {
  const progress = [];
  const result = await solveSourceStateful({
    source: sourceFor("ps_sokoban_basic-v1"),
    gameId: "sokoban-progress",
    maxStates: 10_000,
    timeoutMs: 10_000,
    visitedMode: "semantic",
    progressIntervalMs: 0,
    onProgress: (snapshot) => progress.push(snapshot),
  });

  assert.equal(result.solved, true);
  assert.ok(progress.length >= 2);
  assert.ok(progress.at(-1).maxDepthDiscovered >= result.solutionDepth - 1);
  assert.equal(progress.at(-1).uniqueStates, result.uniqueStates);
  assert.equal(progress.at(-1).transitions, result.transitions);
});

test("semantic visited keys merge cache variants while preserving the solution", async () => {
  const result = await solveSourceStateful({
    source: sourceFor("ps_sokoban_basic-v1"),
    gameId: "ps_sokoban_basic-v1",
    levelIndex: 0,
    maxStates: 5_000,
    timeoutMs: 5_000,
    visitedMode: "semantic",
  });
  assert.equal(result.status, "solved");
  assert.equal(result.solutionDepth, 33);
  assert.equal(result.optimalityProven, false);
  assert.equal(result.shortestInSemanticStateGraph, true);
  assert.ok(result.cacheVariantDuplicates > 0);
});

test("stateful BFS does not reproduce the compressed false goal", async () => {
  const result = await solveSourceStateful({
    source: sourceFor("ps_compressed-v1"),
    gameId: "ps_compressed-v1",
    levelIndex: 2,
    maxStates: 2_000,
    timeoutMs: 5_000,
  });
  assert.notEqual(result.status, "solved");
});
