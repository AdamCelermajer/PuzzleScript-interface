"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const {
  Parser,
  GameEngine,
  INPUT_BUTTON,
  EmptyGameEngineHandler,
} = require("puzzlescript");
const {
  PuzzleScriptMachineAdapter,
  captureMachineState,
  findCellLinkageCaches,
  findOrderedCellCaches,
} = require("./machine_state_adapter");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const ACTIONS = {
  UP: INPUT_BUTTON.UP,
  DOWN: INPUT_BUTTON.DOWN,
  LEFT: INPUT_BUTTON.LEFT,
  RIGHT: INPUT_BUTTON.RIGHT,
  ACTION: INPUT_BUTTON.ACTION,
};

function readGame(gameId) {
  return fs.readFileSync(path.join(
    REPO_ROOT,
    "puzzlescript_interface",
    "games",
    gameId,
    "script.txt",
  ), "utf8").replace(/\r\n?/g, "\n");
}

async function apply(engine, button) {
  let ticks = 0;
  do {
    const result = await engine.tick();
    ticks += 1;
    if (result.didLevelChange || result.didWinGame) {
      return { won: true, ticks };
    }
  } while (engine.hasAgain());
  return { won: false, ticks };
}

async function referenceTransition(source, levelIndex, prefix, candidate) {
  const { data } = Parser.parse(source);
  const engine = new GameEngine(data, new EmptyGameEngineHandler());
  engine.setLevel(levelIndex, null);
  const orderedCellCaches = findOrderedCellCaches(data);
  const cellLinkageCaches = findCellLinkageCaches(data);
  for (const actionName of [...prefix, candidate]) {
    engine.press(ACTIONS[actionName]);
    const result = await apply(engine, ACTIONS[actionName]);
    if (result.won) {
      return { state: null, won: true };
    }
  }
  return {
    state: captureMachineState(engine, orderedCellCaches, cellLinkageCaches),
    won: false,
  };
}

async function adapterStateAfter(adapter, prefix) {
  let state = adapter.initialState;
  for (const actionName of prefix) {
    const result = await adapter.transition(state, ACTIONS[actionName]);
    assert.equal(result.won, false, "test prefix unexpectedly won");
    state = result.state;
  }
  return state;
}

test("adapter branches match fresh uninterrupted Sokoban transitions", async () => {
  const source = readGame("ps_sokoban_basic-v1");
  const adapter = new PuzzleScriptMachineAdapter({ source, levelIndex: 0 });
  const prefixes = [
    [],
    ["RIGHT", "RIGHT"],
    ["RIGHT", "RIGHT", "DOWN", "DOWN", "LEFT"],
  ];

  for (const prefix of prefixes) {
    const parent = await adapterStateAfter(adapter, prefix);
    for (const candidate of Object.keys(ACTIONS)) {
      const actual = await adapter.transition(parent, ACTIONS[candidate]);
      const expected = await referenceTransition(source, 0, prefix, candidate);
      assert.equal(actual.won, expected.won, `${prefix} + ${candidate} win mismatch`);
      assert.deepEqual(actual.state, expected.state, `${prefix} + ${candidate} state mismatch`);
    }
  }
});

test("adapter handles run_rules_on_level_start without false compressed transitions", async () => {
  const source = readGame("ps_compressed-v1");
  const levelIndex = 2;
  const adapter = new PuzzleScriptMachineAdapter({ source, levelIndex });
  const suspiciousPath = [
    "UP", "RIGHT", "RIGHT", "UP", "UP",
    "UP", "UP", "RIGHT", "DOWN", "LEFT",
  ];

  let parent = adapter.initialState;
  const prefix = [];
  for (const candidate of suspiciousPath) {
    const actual = await adapter.transition(parent, ACTIONS[candidate]);
    const expected = await referenceTransition(source, levelIndex, prefix, candidate);
    assert.equal(actual.won, expected.won, `${prefix} + ${candidate} win mismatch`);
    assert.deepEqual(actual.state, expected.state, `${prefix} + ${candidate} state mismatch`);
    assert.equal(actual.won, false, "known false-positive path must not win");
    parent = actual.state;
    prefix.push(candidate);
  }
});

test("adapter matches branches across varied solved games", async () => {
  const base = JSON.parse(fs.readFileSync(
    path.join(__dirname, "results.json"),
    "utf8",
  ));
  const extended = JSON.parse(fs.readFileSync(
    path.join(__dirname, "results_unsolved_60s.json"),
    "utf8",
  ));
  const solvedById = new Map(
    [...base.results, ...extended.results]
      .filter((result) => result.solved)
      .map((result) => [result.gameId, result]),
  );

  for (const gameId of [
    "ps_knightoban-v1",
    "ps_moving_target-v1",
    "ps_wall_shuffle-v1",
    "ps_on_and_off-v1",
  ]) {
    const solved = solvedById.get(gameId);
    assert.ok(solved, `missing solved fixture for ${gameId}`);
    const source = readGame(gameId);
    const adapter = new PuzzleScriptMachineAdapter({
      source,
      levelIndex: solved.levelIndex,
    });
    const lengths = [...new Set([
      0,
      Math.floor(solved.solutionActions.length / 2),
      solved.solutionActions.length - 1,
    ])];

    for (const length of lengths) {
      const prefix = solved.solutionActions.slice(0, length);
      const parent = await adapterStateAfter(adapter, prefix);
      for (const candidate of Object.keys(ACTIONS)) {
        const actual = await adapter.transition(parent, ACTIONS[candidate]);
        const expected = await referenceTransition(
          source,
          solved.levelIndex,
          prefix,
          candidate,
        );
        assert.equal(
          actual.won,
          expected.won,
          `${gameId}: ${prefix} + ${candidate} win mismatch`,
        );
        assert.deepEqual(
          actual.state,
          expected.state,
          `${gameId}: ${prefix} + ${candidate} state mismatch`,
        );
      }
    }
  }
});
