#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { INPUT_BUTTON } = require("puzzlescript");
const { inspectGameSource } = require("../experiement/bfs_solver/solver");
const {
  PuzzleScriptMachineAdapter,
} = require("../experiement/bfs_solver/machine_state_adapter");

const REPO_ROOT = path.resolve(__dirname, "..");
const AUDIT_PATH = path.join(REPO_ROOT, "benchmark", "vetting", "catalog-audit.json");
const OUTPUT_PATH = path.join(REPO_ROOT, "benchmark", "vetting", "runtime-smoke.json");
const ACTIONS = [
  INPUT_BUTTON.UP,
  INPUT_BUTTON.DOWN,
  INPUT_BUTTON.LEFT,
  INPUT_BUTTON.RIGHT,
  INPUT_BUTTON.ACTION,
];

async function main() {
  const audit = JSON.parse(fs.readFileSync(AUDIT_PATH, "utf8"));
  const candidates = audit.games.filter((game) => game.deterministic_formal_candidate);
  const results = [];

  for (const candidate of candidates) {
    const sourcePath = path.join(
      REPO_ROOT,
      "puzzlescript_interface",
      "games",
      candidate.game_id,
      "script.txt",
    );
    try {
      const source = fs.readFileSync(sourcePath, "utf8");
      const inspection = inspectGameSource(source);
      const playableLevelIndexes = inspection.data.levels
        .map((level, levelIndex) => ({ level, levelIndex }))
        .filter(({ level }) => level.type === "LEVEL_MAP")
        .map(({ levelIndex }) => levelIndex);
      const levels = [];
      for (const levelIndex of playableLevelIndexes) {
        const adapter = new PuzzleScriptMachineAdapter({ source, levelIndex });
        const transitions = [];
        for (const action of ACTIONS) {
          const transition = await adapter.transition(adapter.initialState, action, 100);
          transitions.push({
            won: transition.won,
            ticks: transition.ticks,
            again_limit: transition.againLimit,
          });
        }
        levels.push({
          level_index: levelIndex,
          passed: transitions.every((transition) => !transition.again_limit),
          transitions,
        });
      }
      results.push({
        game_id: candidate.game_id,
        passed: levels.every((level) => level.passed),
        levels,
      });
    } catch (error) {
      results.push({
        game_id: candidate.game_id,
        passed: false,
        error: error.stack ?? error.message,
      });
    }
  }

  fs.writeFileSync(
    OUTPUT_PATH,
    `${JSON.stringify({ generated_at: new Date().toISOString(), games: results }, null, 2)}\n`,
  );
  process.stdout.write(JSON.stringify({
    tested: results.length,
    passed: results.filter((result) => result.passed).length,
    failed: results.filter((result) => !result.passed).map((result) => result.game_id),
    output: path.relative(REPO_ROOT, OUTPUT_PATH),
  }, null, 2) + "\n");
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
