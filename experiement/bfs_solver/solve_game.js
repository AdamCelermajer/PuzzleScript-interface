#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { solveSource } = require("./solver");

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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.gamePath || !args.gameId) {
    throw new Error("Required arguments: --gamePath PATH --gameId ID");
  }

  const source = fs.readFileSync(path.resolve(args.gamePath), "utf8");
  const result = await solveSource({
    source,
    gameId: args.gameId,
    levelIndex: args.levelIndex === undefined ? null : Number(args.levelIndex),
    maxStates: Number(args.maxStates ?? 100_000),
    timeoutMs: Number(args.timeoutMs ?? 10_000),
    maxAgainTicks: Number(args.maxAgainTicks ?? 100),
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
