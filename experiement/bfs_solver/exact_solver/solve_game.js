"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { solveSourceExact } = require("./solver");
const { ACTIONS } = require("../solver");
const { PuzzleScriptMachineAdapter } = require("../machine_state_adapter");

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
    const action = actionByName.get(actions[index]);
    if (!action) throw new Error(`Unknown replay action: ${actions[index]}`);
    const result = await adapter.transition(state, action.button, 100);
    if (result.won) return index === actions.length - 1;
    state = result.state;
  }
  return false;
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.gameId && !args.gamePath) {
    throw new Error("Use --gameId <id> or --gamePath <script.txt>");
  }
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const gamePath = args.gamePath
    ? path.resolve(args.gamePath)
    : path.join(
      repoRoot,
      "puzzlescript_interface",
      "games",
      args.gameId,
      "script.txt",
    );
  const source = fs.readFileSync(gamePath, "utf8");
  const result = await solveSourceExact({
    source,
    gameId: args.gameId ?? path.basename(path.dirname(gamePath)),
    levelIndex: args.levelIndex === undefined ? null : Number(args.levelIndex),
    maxStates: Number(args.maxStates ?? 250_000),
    timeoutMs: Number(args.timeoutMs ?? 60_000),
    visitedMode: args.visitedMode ?? "exact",
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
  process.stderr.write("\n");
  if (result.solved) {
    result.replayVerified = await verify(
      source,
      result.levelIndex,
      result.solutionActions,
    );
  } else {
    result.replayVerified = false;
  }
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
