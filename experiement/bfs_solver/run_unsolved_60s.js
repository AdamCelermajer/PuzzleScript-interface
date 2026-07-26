#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const EXPERIMENT_DIR = __dirname;
const REPO_ROOT = path.resolve(EXPERIMENT_DIR, "..", "..");
const BASE_RESULTS_PATH = path.join(EXPERIMENT_DIR, "results.json");
const OUTPUT_PATH = path.join(EXPERIMENT_DIR, "results_unsolved_60s.json");
const CSV_PATH = path.join(EXPERIMENT_DIR, "results_unsolved_60s.csv");
const REPORT_PATH = path.join(EXPERIMENT_DIR, "REPORT_60s.md");
const VERIFY_OUTPUT = path.join(EXPERIMENT_DIR, "verification_unsolved_60s.json");
const SOLVER_SCRIPT = path.join(EXPERIMENT_DIR, "solve_game.js");
const VERIFY_SCRIPT = path.join(EXPERIMENT_DIR, "verify_results.js");
const TIMEOUT_MS = 60_000;

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = Array.isArray(value) ? value.join(" ") : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function writeArtifacts(base, targets, results) {
  const bundle = {
    generatedAt: new Date().toISOString(),
    sourceResults: "results.json",
    config: { ...base.config, timeoutMs: TIMEOUT_MS },
    targetCount: targets.length,
    completedCount: results.length,
    results,
  };
  fs.writeFileSync(OUTPUT_PATH, `${JSON.stringify(bundle, null, 2)}\n`, "utf8");

  const columns = [
    "gameId", "levelIndex", "status", "solved", "solutionDepth",
    "solutionActions", "expandedStates", "uniqueStates", "transitions",
    "engineActions", "replayedActions", "searchMs", "engineMs",
    "searchTransitionsPerSecond", "engineActionsPerSecond", "peakHeapBytes",
  ];
  const rows = [columns.join(",")];
  for (const result of results) {
    rows.push(columns.map((column) => csvCell(result[column])).join(","));
  }
  fs.writeFileSync(CSV_PATH, `${rows.join("\n")}\n`, "utf8");
}

function runOne(target, config) {
  const gamePath = path.join(
    REPO_ROOT,
    "puzzlescript_interface",
    "games",
    target.gameId,
    "script.txt",
  );
  const child = spawnSync(
    process.execPath,
    [
      "--max-old-space-size=1536",
      SOLVER_SCRIPT,
      "--gamePath", gamePath,
      "--gameId", target.gameId,
      "--levelIndex", String(target.levelIndex),
      "--maxStates", String(config.maxStates),
      "--timeoutMs", String(TIMEOUT_MS),
      "--maxAgainTicks", String(config.maxAgainTicks),
    ],
    {
      cwd: REPO_ROOT,
      encoding: "utf8",
      timeout: TIMEOUT_MS + 15_000,
      maxBuffer: 10 * 1024 * 1024,
    },
  );

  if (child.error || child.status !== 0) {
    return {
      gameId: target.gameId,
      levelIndex: target.levelIndex,
      status: child.error?.code === "ETIMEDOUT" ? "process_timeout" : "error",
      solved: false,
      error: child.error?.message ?? child.stderr.trim(),
    };
  }
  return JSON.parse(child.stdout.trim().split(/\r?\n/).filter(Boolean).at(-1));
}

function writeReport(base, results, verification) {
  const newlySolved = results.filter((result) => result.solved);
  const stillUnsolved = results.filter((result) => !result.solved);
  const baseSolved = base.results.filter((result) => result.solved).length;
  const lines = [
    "# PuzzleScript BFS: 60-second rerun",
    "",
    `Only the ${results.length} games unsolved in the original 10-second run were rerun.`,
    "",
    `- Newly solved: **${newlySolved.length}/${results.length}**`,
    `- Total solved across the original sample: **${baseSolved + newlySolved.length}/${base.results.length}**`,
    `- Fresh-engine replay verified: **${verification.verifiedCount}/${verification.solvedCount}**`,
    `- Limits: 60 seconds or ${base.config.maxStates.toLocaleString()} unique states per game`,
    "",
    "## Newly solved",
    "",
    "| Game | Optimal actions | Expanded | Transitions | Search seconds |",
    "|---|---:|---:|---:|---:|",
  ];
  for (const result of newlySolved) {
    lines.push(`| ${result.gameId} | ${result.solutionDepth} | ${result.expandedStates.toLocaleString()} | ${result.transitions.toLocaleString()} | ${(result.searchMs / 1000).toFixed(1)} |`);
  }
  if (newlySolved.length === 0) lines.push("| _None_ | - | - | - | - |");

  lines.push(
    "",
    "## Still unsolved within the bounds",
    "",
    "| Game | Status | Expanded | Unique states | Search seconds |",
    "|---|---|---:|---:|---:|",
  );
  for (const result of stillUnsolved) {
    lines.push(`| ${result.gameId} | ${result.status} | ${(result.expandedStates ?? 0).toLocaleString()} | ${(result.uniqueStates ?? 0).toLocaleString()} | ${((result.searchMs ?? 0) / 1000).toFixed(1)} |`);
  }
  lines.push("", "A timeout or state-limit result remains unknown, not proven unsolvable.", "");
  fs.writeFileSync(REPORT_PATH, lines.join("\n"), "utf8");
}

function main() {
  const base = JSON.parse(fs.readFileSync(BASE_RESULTS_PATH, "utf8"));
  const targets = base.results.filter((result) => !result.solved);
  const results = [];

  for (let index = 0; index < targets.length; index += 1) {
    const target = targets[index];
    process.stdout.write(`[${index + 1}/${targets.length}] ${target.gameId} ... `);
    const result = runOne(target, base.config);
    results.push(result);
    writeArtifacts(base, targets, results);
    process.stdout.write(result.solved ? `solved depth=${result.solutionDepth}\n` : `${result.status}\n`);
  }

  const verificationRun = spawnSync(
    process.execPath,
    [VERIFY_SCRIPT, "--results", path.basename(OUTPUT_PATH), "--output", path.basename(VERIFY_OUTPUT)],
    { cwd: REPO_ROOT, encoding: "utf8", timeout: 60_000 },
  );
  if (verificationRun.status !== 0) {
    throw new Error(`Solution replay verification failed: ${verificationRun.stderr || verificationRun.stdout}`);
  }
  const verification = JSON.parse(fs.readFileSync(VERIFY_OUTPUT, "utf8"));
  writeReport(base, results, verification);
  process.stdout.write(verificationRun.stdout);
  process.stdout.write(`Done. See experiement/bfs_solver/REPORT_60s.md\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
}
