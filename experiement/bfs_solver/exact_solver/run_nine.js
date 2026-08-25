"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { ACTIONS, inspectGameSource } = require("../solver");
const { PuzzleScriptMachineAdapter } = require("../machine_state_adapter");
const { solveSourceExact } = require("./solver");
const { solveCompiledProfile } = require("./compiled_solver");
const saved = require("./solutions.json");

function parseArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 2) {
    args[argv[index].replace(/^--/, "")] = argv[index + 1];
  }
  return args;
}

async function verify(source, levelIndex, actions) {
  const adapter = new PuzzleScriptMachineAdapter({ source, levelIndex });
  const actionByName = new Map(ACTIONS.map((action) => [action.name, action]));
  let state = adapter.initialState;
  for (let index = 0; index < actions.length; index += 1) {
    const result = await adapter.transition(
      state,
      actionByName.get(actions[index]).button,
      100,
    );
    if (result.won) return index === actions.length - 1;
    state = result.state;
  }
  return false;
}

async function solveOne({ gameId, timeoutMs, maxStates }) {
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const source = fs.readFileSync(path.join(
    repoRoot,
    "puzzlescript_interface",
    "games",
    gameId,
    "script.txt",
  ), "utf8");
  const inspection = inspectGameSource(source);
  const adapter = new PuzzleScriptMachineAdapter({
    source,
    levelIndex: inspection.firstLevelIndex,
  });
  const onProgress = (progress) => {
    process.stderr.write(
      `\r${gameId} ${Math.round(progress.elapsedMs / 1000)}s `
      + `expanded=${progress.expandedStates} `
      + `unique=${progress.uniqueStates} `
      + `f=${progress.bestF ?? "-"} h=${progress.bestH ?? "-"}   `,
    );
  };
  let result = solveCompiledProfile({
    source,
    gameId,
    gameData: adapter.gameData,
    initialState: adapter.initialState,
    timeoutMs,
    maxStates,
    onProgress,
  });
  if (result === null) {
    result = await solveSourceExact({
      source,
      gameId,
      levelIndex: inspection.firstLevelIndex,
      timeoutMs,
      maxStates,
      visitedMode: "exact",
      onProgress,
    });
  }
  process.stderr.write("\n");
  result.replayVerified = result.solved
    ? await verify(source, inspection.firstLevelIndex, result.solutionActions)
    : false;
  return result;
}

async function main() {
  const args = parseArgs(process.argv);
  const selected = args.gameId
    ? [args.gameId]
    : saved.solutions.map((solution) => solution.gameId);
  const timeoutMs = Number(args.timeoutMs ?? 180_000);
  const maxStates = Number(args.maxStates ?? 5_000_000);
  const results = [];
  for (const gameId of selected) {
    results.push(await solveOne({ gameId, timeoutMs, maxStates }));
  }
  process.stdout.write(`${JSON.stringify({
    version: 1,
    scope: saved.scope,
    results,
  }, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
