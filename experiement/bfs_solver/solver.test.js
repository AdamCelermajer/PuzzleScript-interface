"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const {
  CompactStateCodec,
  inspectGameSource,
  solveSource,
} = require("./solver");

const REPO_ROOT = path.resolve(__dirname, "..", "..");

test("compact codec round-trips layered cell contents", () => {
  const snapshot = [
    [["Background", "Player"], ["Background"]],
    [["Target", "Crate"], ["Wall"]],
  ];
  const codec = new CompactStateCodec(2, 2);
  const encoded = codec.encode(snapshot);
  assert.equal(encoded.byteLength, 8);
  assert.deepEqual(codec.decode(encoded), [
    [["Background", "Player"], ["Background"]],
    [["Crate", "Target"], ["Wall"]],
  ]);
  assert.equal(codec.key(encoded), codec.key(codec.encode(snapshot)));
});

test("Sokoban first level is solved optimally with compact-state BFS", async () => {
  const gamePath = path.join(
    REPO_ROOT,
    "puzzlescript_interface",
    "games",
    "ps_sokoban_basic-v1",
    "script.txt",
  );
  const source = fs.readFileSync(gamePath, "utf8");
  const inspection = inspectGameSource(source);
  assert.equal(inspection.formalGoalCount, 1);
  assert.equal(inspection.firstLevelIndex, 0);

  const result = await solveSource({
    source,
    gameId: "ps_sokoban_basic-v1",
    levelIndex: 0,
    maxStates: 5_000,
    timeoutMs: 5_000,
  });
  assert.equal(result.status, "solved");
  assert.equal(result.solutionDepth, 33);
  assert.equal(result.optimalityProven, true);
});
