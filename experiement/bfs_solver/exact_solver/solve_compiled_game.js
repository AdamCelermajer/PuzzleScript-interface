"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { inspectGameSource, ACTIONS } = require("../solver");
const { PuzzleScriptMachineAdapter } = require("../machine_state_adapter");
const { solveCompiledProfile } = require("./compiled_solver");

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

async function main() {
  const args = parseArgs(process.argv);
  if (!args.gameId) throw new Error("Use --gameId <id>");
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const gamePath = path.join(
    repoRoot,
    "puzzlescript_interface",
    "games",
    args.gameId,
    "script.txt",
  );
  const source = fs.readFileSync(gamePath, "utf8");
  const inspection = inspectGameSource(source);
  const levelIndex = args.levelIndex === undefined
    ? inspection.firstLevelIndex
    : Number(args.levelIndex);
  const adapter = new PuzzleScriptMachineAdapter({ source, levelIndex });
  const result = solveCompiledProfile({
    source,
    gameId: args.gameId,
    gameData: adapter.gameData,
    initialState: adapter.initialState,
    timeoutMs: Number(args.timeoutMs ?? 60_000),
    maxStates: Number(args.maxStates ?? 2_000_000),
    onProgress: (progress) => {
      process.stderr.write(
        `\r${Math.round(progress.elapsedMs / 1000)}s `
        + `expanded=${progress.expandedStates} `
        + `unique=${progress.uniqueStates} `
        + `frontier=${progress.frontierEntries} `
        + `f=${progress.bestF ?? "-"} h=${progress.bestH ?? "-"}   `,
      );
    },
  });
  if (!result) throw new Error("No certified compiled profile matched this game");
  process.stderr.write("\n");
  result.replayVerified = result.solved
    ? await verify(source, levelIndex, result.solutionActions)
    : false;
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
