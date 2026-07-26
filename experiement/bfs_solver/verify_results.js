#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const {
  Parser,
  GameEngine,
  INPUT_BUTTON,
  EmptyGameEngineHandler,
} = require("puzzlescript");

const EXPERIMENT_DIR = __dirname;
const REPO_ROOT = path.resolve(EXPERIMENT_DIR, "..", "..");
const ACTIONS = {
  UP: INPUT_BUTTON.UP,
  DOWN: INPUT_BUTTON.DOWN,
  LEFT: INPUT_BUTTON.LEFT,
  RIGHT: INPUT_BUTTON.RIGHT,
  ACTION: INPUT_BUTTON.ACTION,
};

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    const value = argv[index + 1];
    if (!name?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument sequence near ${name ?? "<end>"}`);
    }
    args[name.slice(2)] = value;
  }
  return args;
}

async function replay(result) {
  const gamePath = path.join(
    REPO_ROOT,
    "puzzlescript_interface",
    "games",
    result.gameId,
    "script.txt",
  );
  const source = fs.readFileSync(gamePath, "utf8").replace(/\r\n?/g, "\n");
  const { data } = Parser.parse(source);
  const engine = new GameEngine(data, new EmptyGameEngineHandler());
  engine.setLevel(result.levelIndex, null);

  for (let index = 0; index < result.solutionActions.length; index += 1) {
    const actionName = result.solutionActions[index];
    const button = ACTIONS[actionName];
    if (!button) {
      throw new Error(`Unknown action ${actionName}`);
    }
    engine.press(button);

    let againTicks = 0;
    do {
      const tickResult = await engine.tick();
      againTicks += 1;
      if (tickResult.didLevelChange || tickResult.didWinGame) {
        return {
          gameId: result.gameId,
          verified: index === result.solutionActions.length - 1,
          wonAtAction: index + 1,
          expectedActions: result.solutionActions.length,
        };
      }
      if (againTicks >= 100) {
        return {
          gameId: result.gameId,
          verified: false,
          reason: "again_limit",
        };
      }
    } while (engine.hasAgain());
  }

  return {
    gameId: result.gameId,
    verified: false,
    reason: "solution_did_not_win",
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const resultsPath = path.resolve(EXPERIMENT_DIR, args.results ?? "results.json");
  const outputPath = path.resolve(EXPERIMENT_DIR, args.output ?? "verification.json");
  const bundle = JSON.parse(fs.readFileSync(resultsPath, "utf8"));
  const solved = bundle.results.filter((result) => result.solved);
  const verification = [];
  for (const result of solved) {
    verification.push(await replay(result));
  }

  const verifiedCount = verification.filter((item) => item.verified).length;
  const output = {
    generatedAt: new Date().toISOString(),
    solvedCount: solved.length,
    verifiedCount,
    allVerified: verifiedCount === solved.length,
    verification,
  };
  fs.writeFileSync(
    outputPath,
    `${JSON.stringify(output, null, 2)}\n`,
    "utf8",
  );
  process.stdout.write(`${verifiedCount}/${solved.length} solved paths replay-verified\n`);
  if (!output.allVerified) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
