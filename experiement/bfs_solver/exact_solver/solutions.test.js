"use strict";

const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");
const { ACTIONS } = require("../solver");
const { PuzzleScriptMachineAdapter } = require("../machine_state_adapter");
const saved = require("./solutions.json");

const actionByName = new Map(ACTIONS.map((action) => [action.name, action]));
const repoRoot = path.resolve(__dirname, "..", "..", "..");

for (const solution of saved.solutions) {
  test(`${solution.gameId} saved exact solution replays to a win`, async () => {
    assert.equal(solution.actions.length, solution.depth);
    const source = fs.readFileSync(path.join(
      repoRoot,
      "puzzlescript_interface",
      "games",
      solution.gameId,
      "script.txt",
    ), "utf8");
    const adapter = new PuzzleScriptMachineAdapter({
      source,
      levelIndex: solution.levelIndex,
    });
    let state = adapter.initialState;
    for (let index = 0; index < solution.actions.length; index += 1) {
      const action = actionByName.get(solution.actions[index]);
      assert.ok(action, `Unknown action ${solution.actions[index]}`);
      const result = await adapter.transition(state, action.button, 100);
      assert.equal(
        result.won,
        index === solution.actions.length - 1,
        `Unexpected win state after action ${index + 1}`,
      );
      state = result.state;
    }
  });
}
