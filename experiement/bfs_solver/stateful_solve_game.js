#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { solveSourceStateful } = require("./stateful_solver");
const { solveWholeGameStateful } = require("./whole_game_solver");
const { ACTIONS } = require("./solver");
const { PuzzleScriptMachineAdapter } = require("./machine_state_adapter");
const { renderSessionFrame } = require("../../puzzlescript_interface/runtime/rendered_frame");

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    args[argv[index].slice(2)] = argv[index + 1];
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const source = fs.readFileSync(path.resolve(args.gamePath), "utf8");
  const streamProgress = args.progressJsonl === "true";
  const emit = (payload) => process.stdout.write(`${JSON.stringify(payload)}\n`);
  const solver = args.wholeGame === "true"
    ? solveWholeGameStateful
    : solveSourceStateful;
  const result = await solver({
    source,
    gameId: args.gameId,
    levelIndex: args.levelIndex === undefined ? null : Number(args.levelIndex),
    maxStates: Number(args.maxStates ?? 100_000),
    timeoutMs: Number(args.timeoutMs ?? 10_000),
    maxAgainTicks: Number(args.maxAgainTicks ?? 100),
    visitedMode: args.visitedMode ?? "exact",
    onProgress: streamProgress
      ? (progress) => emit({ kind: "progress", progress })
      : null,
  });

  if (result.solved && args.renderReplay === "true") {
    const actionsByName = new Map(ACTIONS.map((action) => [action.name, action]));
    const replay = [];
    const levelResults = result.wholeGame ? result.levelResults : [result];
    for (const [levelOffset, levelResult] of levelResults.entries()) {
      const adapter = new PuzzleScriptMachineAdapter({
        source,
        levelIndex: levelResult.levelIndex,
      });
      let state = adapter.initialState;
      replay.push({
        step: replay.length,
        action: `LEVEL ${levelOffset + 1}`,
        won: false,
        levelNumber: levelOffset + 1,
        totalLevels: levelResults.length,
        renderedFrame: renderSessionFrame(adapter),
      });
      for (const actionName of levelResult.solutionActions) {
        const action = actionsByName.get(actionName);
        if (!action) throw new Error(`Cannot replay unknown action: ${actionName}`);
        const transition = await adapter.transition(
          state,
          action.button,
          Number(args.maxAgainTicks ?? 100),
        );
        replay.push({
          step: replay.length,
          action: actionName,
          won: transition.won,
          levelNumber: levelOffset + 1,
          totalLevels: levelResults.length,
          renderedFrame: renderSessionFrame(adapter),
        });
        if (transition.won) break;
        state = transition.state;
      }
    }
    result.replay = replay;
    result.replayVerified = levelResults.every((levelResult, levelOffset) => (
      replay.some((frame) => frame.levelNumber === levelOffset + 1 && frame.won)
      && levelResult.solved
    ));
  }

  if (streamProgress) {
    emit({ kind: "result", result });
  } else {
    emit(result);
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
