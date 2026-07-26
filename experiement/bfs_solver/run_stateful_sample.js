#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const EXPERIMENT_DIR = __dirname;
const REPO_ROOT = path.resolve(EXPERIMENT_DIR, "..", "..");
const SAMPLE_PATH = path.join(EXPERIMENT_DIR, "sample.json");
const BASE_RESULTS_PATH = path.join(EXPERIMENT_DIR, "results.json");
const EXTENDED_RESULTS_PATH = path.join(EXPERIMENT_DIR, "results_unsolved_60s.json");
const SOLVER_SCRIPT = path.join(EXPERIMENT_DIR, "stateful_solve_game.js");
const VERIFY_SCRIPT = path.join(EXPERIMENT_DIR, "verify_results.js");

function parseArgs(argv) {
  const args = {
    timeoutMs: 60_000,
    maxStates: 100_000,
    maxAgainTicks: 100,
    onlyPreviousUnsolved: false,
    outputPrefix: "stateful_60s",
    visitedMode: "semantic",
  };
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    const value = argv[index + 1];
    if (!name?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument sequence near ${name ?? "<end>"}`);
    }
    const key = name.slice(2);
    if (key === "outputPrefix" || key === "visitedMode") args[key] = value;
    else if (key === "onlyPreviousUnsolved") args[key] = value === "true";
    else args[key] = Number(value);
  }
  if (!/^[A-Za-z0-9_-]+$/.test(args.outputPrefix)) {
    throw new Error("outputPrefix may contain only letters, numbers, underscores, and hyphens");
  }
  return args;
}

function outputPaths(prefix) {
  return {
    json: path.join(EXPERIMENT_DIR, `${prefix}_results.json`),
    csv: path.join(EXPERIMENT_DIR, `${prefix}_results.csv`),
    report: path.join(EXPERIMENT_DIR, `${prefix}_REPORT.md`),
    verification: path.join(EXPERIMENT_DIR, `${prefix}_verification.json`),
  };
}

function runOne(item, config) {
  const child = spawnSync(
    process.execPath,
    [
      "--max-old-space-size=1536",
      SOLVER_SCRIPT,
      "--gamePath", item.gamePath,
      "--gameId", item.gameId,
      "--levelIndex", String(item.levelIndex),
      "--maxStates", String(config.maxStates),
      "--timeoutMs", String(config.timeoutMs),
      "--maxAgainTicks", String(config.maxAgainTicks),
      "--visitedMode", config.visitedMode,
    ],
    {
      cwd: REPO_ROOT,
      encoding: "utf8",
      timeout: config.timeoutMs + 15_000,
      maxBuffer: 10 * 1024 * 1024,
    },
  );
  if (child.error || child.status !== 0) {
    return {
      gameId: item.gameId,
      levelIndex: item.levelIndex,
      status: child.error?.code === "ETIMEDOUT" ? "process_timeout" : "error",
      solved: false,
      optimalityProven: false,
      error: child.error?.message ?? child.stderr.trim(),
    };
  }
  return JSON.parse(child.stdout.trim().split(/\r?\n/).filter(Boolean).at(-1));
}

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = Array.isArray(value) ? value.join(" ") : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function writeCheckpoint(paths, config, sourceSample, targets, results) {
  const bundle = {
    generatedAt: new Date().toISOString(),
    solver: "complete_machine_state_bfs",
    sourceSample: "sample.json",
    sourceSeed: sourceSample.config.seed,
    config,
    targetCount: targets.length,
    completedCount: results.length,
    results,
  };
  fs.writeFileSync(paths.json, `${JSON.stringify(bundle, null, 2)}\n`, "utf8");

  const columns = [
    "gameId", "levelIndex", "status", "solved", "optimalityProven",
    "solutionDepth", "solutionActions", "expandedStates", "uniqueStates",
    "transitions", "ticks", "duplicates", "unchanged", "searchMs",
    "transitionMs", "keyMs", "searchTransitionsPerSecond",
    "engineTransitionsPerSecond", "compactBytesPerInitialState", "peakHeapBytes",
    "previousStatus", "previousSolved", "previousSearchMs", "previousLimitMs",
    "visitedMode", "cacheVariantDuplicates", "shortestInSemanticStateGraph",
  ];
  const rows = [columns.join(",")];
  for (const result of results) {
    rows.push(columns.map((column) => csvCell(result[column])).join(","));
  }
  fs.writeFileSync(paths.csv, `${rows.join("\n")}\n`, "utf8");
}

function writeReport(paths, config, targets, results, verification) {
  const solved = results.filter((result) => result.solved);
  const unsolved = results.filter((result) => !result.solved);
  const maximumDepth = solved.reduce(
    (maximum, result) => Math.max(maximum, result.solutionDepth ?? 0),
    0,
  );
  const lines = [
    "# Complete-machine-state BFS report",
    "",
    `- Games attempted: ${results.length}/${targets.length}`,
    `- Solved: **${solved.length}/${results.length}**`,
    `- Replay verified: **${verification.verifiedCount}/${verification.solvedCount}**`,
    `- Deepest solution: **${maximumDepth} actions**`,
    `- Limits: ${(config.timeoutMs / 1000).toFixed(0)} seconds or ${config.maxStates.toLocaleString()} states per game`,
    `- Previous-timeout subset only: ${config.onlyPreviousUnsolved}`,
    `- Visited-state equivalence: ${config.visitedMode}`,
    "",
    "## Solved",
    "",
    "| Game | Depth | Previous -> complete-state time | Change | Expanded | Edges/s |",
    "|---|---:|---:|---:|---:|---:|",
  ];
  for (const result of solved) {
    const currentSeconds = result.searchMs / 1000;
    let timeComparison;
    let timeChange;
    if (result.previousSolved && Number.isFinite(result.previousSearchMs)) {
      const previousSeconds = result.previousSearchMs / 1000;
      const ratio = previousSeconds / currentSeconds;
      timeComparison = `${previousSeconds.toFixed(1)}s -> ${currentSeconds.toFixed(1)}s`;
      timeChange = ratio >= 1
        ? `${ratio.toFixed(1)}x faster`
        : `${(1 / ratio).toFixed(1)}x slower`;
    } else if (result.previousStatus === "time_limit") {
      const previousLimitSeconds = (result.previousLimitMs ?? 60_000) / 1000;
      timeComparison = `>${previousLimitSeconds.toFixed(0)}s -> ${currentSeconds.toFixed(1)}s`;
      timeChange = "newly solved";
    } else {
      timeComparison = `${result.previousStatus ?? "unknown"} -> ${currentSeconds.toFixed(1)}s`;
      timeChange = "newly solved";
    }
    lines.push(`| ${result.gameId} | ${result.solutionDepth} | ${timeComparison} | ${timeChange} | ${result.expandedStates.toLocaleString()} | ${result.searchTransitionsPerSecond.toFixed(0)} |`);
  }
  lines.push(
    "",
    "## Unsolved within bounds",
    "",
    "| Game | Status | Expanded | Unique states | Seconds |",
    "|---|---|---:|---:|---:|",
  );
  for (const result of unsolved) {
    lines.push(`| ${result.gameId} | ${result.status} | ${(result.expandedStates ?? 0).toLocaleString()} | ${(result.uniqueStates ?? 0).toLocaleString()} | ${((result.searchMs ?? 0) / 1000).toFixed(1)} |`);
  }
  lines.push(
    "",
    "Timeout and state-limit results remain unknown, not proven unsolvable.",
    "",
    "Semantic mode stores and branches from complete real engine states, but merges states that differ only in derived cache history. Solutions are replay-verified and shortest in that semantic graph; strict optimality over cache-history variants is not claimed.",
    "",
  );
  fs.writeFileSync(paths.report, lines.join("\n"), "utf8");
}

function main() {
  const config = parseArgs(process.argv.slice(2));
  const paths = outputPaths(config.outputPrefix);
  const sourceSample = JSON.parse(fs.readFileSync(SAMPLE_PATH, "utf8"));
  const baseResults = JSON.parse(fs.readFileSync(BASE_RESULTS_PATH, "utf8"));
  const extendedResults = JSON.parse(fs.readFileSync(EXTENDED_RESULTS_PATH, "utf8"));
  const previousById = new Map(
    baseResults.results.map((result) => [result.gameId, {
      ...result,
      previousLimitMs: baseResults.config.timeoutMs,
    }]),
  );
  for (const result of extendedResults.results) {
    previousById.set(result.gameId, {
      ...result,
      previousLimitMs: extendedResults.config.timeoutMs,
    });
  }
  let targets = sourceSample.sample;
  if (config.onlyPreviousUnsolved) {
    const unsolvedIds = new Set(
      baseResults.results.filter((result) => !result.solved).map((result) => result.gameId),
    );
    targets = targets.filter((item) => unsolvedIds.has(item.gameId));
  }

  const results = [];
  for (let index = 0; index < targets.length; index += 1) {
    const item = targets[index];
    process.stdout.write(`[${index + 1}/${targets.length}] ${item.gameId} ... `);
    const result = runOne(item, config);
    const previous = previousById.get(item.gameId);
    result.previousStatus = previous?.status ?? null;
    result.previousSolved = previous?.solved ?? false;
    result.previousSearchMs = previous?.searchMs ?? null;
    result.previousLimitMs = previous?.previousLimitMs ?? null;
    results.push(result);
    writeCheckpoint(paths, config, sourceSample, targets, results);
    process.stdout.write(result.solved ? `solved depth=${result.solutionDepth}\n` : `${result.status}\n`);
  }

  const verifyRun = spawnSync(
    process.execPath,
    [
      VERIFY_SCRIPT,
      "--results", path.basename(paths.json),
      "--output", path.basename(paths.verification),
    ],
    { cwd: REPO_ROOT, encoding: "utf8", timeout: 60_000 },
  );
  if (verifyRun.status !== 0) {
    throw new Error(`Solution replay verification failed: ${verifyRun.stderr || verifyRun.stdout}`);
  }
  const verification = JSON.parse(fs.readFileSync(paths.verification, "utf8"));
  writeReport(paths, config, targets, results, verification);
  process.stdout.write(verifyRun.stdout);
  process.stdout.write(`Done. See ${path.relative(REPO_ROOT, paths.report)}\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
}
