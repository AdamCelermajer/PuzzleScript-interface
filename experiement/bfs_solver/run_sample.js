#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { inspectGameSource } = require("./solver");

const EXPERIMENT_DIR = __dirname;
const REPO_ROOT = path.resolve(EXPERIMENT_DIR, "..", "..");
const GAMES_DIR = path.join(REPO_ROOT, "puzzlescript_interface", "games");
const SOLVE_GAME_SCRIPT = path.join(EXPERIMENT_DIR, "solve_game.js");
const VERIFY_RESULTS_SCRIPT = path.join(EXPERIMENT_DIR, "verify_results.js");

function parseArgs(argv) {
  const args = {
    sampleSize: 30,
    seed: "3838",
    maxStates: 100_000,
    timeoutMs: 10_000,
    maxAgainTicks: 100,
  };
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    const value = argv[index + 1];
    if (!name?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument sequence near ${name ?? "<end>"}`);
    }
    const key = name.slice(2);
    args[key] = key === "seed" ? value : Number(value);
  }
  return args;
}

function deterministicOrder(gameIds, seed) {
  return gameIds.slice().sort((left, right) => {
    const leftHash = crypto.createHash("sha256").update(`${seed}:${left}`).digest("hex");
    const rightHash = crypto.createHash("sha256").update(`${seed}:${right}`).digest("hex");
    return leftHash.localeCompare(rightHash) || left.localeCompare(right);
  });
}

function collectCandidates() {
  const counts = {
    directories: 0,
    scripts: 0,
    parseErrors: 0,
    noFormalGoal: 0,
    noPlayableLevel: 0,
    unsupported: 0,
    eligible: 0,
  };
  const candidates = [];
  const excluded = [];

  const gameIds = fs.readdirSync(GAMES_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
  counts.directories = gameIds.length;

  for (const gameId of gameIds) {
    const gamePath = path.join(GAMES_DIR, gameId, "script.txt");
    if (!fs.existsSync(gamePath)) {
      continue;
    }
    counts.scripts += 1;

    try {
      const source = fs.readFileSync(gamePath, "utf8");
      const inspection = inspectGameSource(source);
      if (inspection.formalGoalCount === 0) {
        counts.noFormalGoal += 1;
        excluded.push({ gameId, reason: "no_formal_win_condition" });
        continue;
      }
      if (inspection.firstLevelIndex < 0) {
        counts.noPlayableLevel += 1;
        excluded.push({ gameId, reason: "no_playable_level" });
        continue;
      }
      if (inspection.unsupportedReasons.length > 0) {
        counts.unsupported += 1;
        excluded.push({
          gameId,
          reason: inspection.unsupportedReasons.join(","),
        });
        continue;
      }

      candidates.push({
        gameId,
        gamePath,
        levelIndex: inspection.firstLevelIndex,
        formalGoalCount: inspection.formalGoalCount,
      });
    } catch (error) {
      counts.parseErrors += 1;
      excluded.push({ gameId, reason: "parse_error", error: error.message });
    }
  }

  counts.eligible = candidates.length;
  return { candidates, excluded, counts };
}

function runOne(sample, config) {
  const child = spawnSync(
    process.execPath,
    [
      "--max-old-space-size=1536",
      SOLVE_GAME_SCRIPT,
      "--gamePath", sample.gamePath,
      "--gameId", sample.gameId,
      "--levelIndex", String(sample.levelIndex),
      "--maxStates", String(config.maxStates),
      "--timeoutMs", String(config.timeoutMs),
      "--maxAgainTicks", String(config.maxAgainTicks),
    ],
    {
      cwd: REPO_ROOT,
      encoding: "utf8",
      timeout: config.timeoutMs + 15_000,
      maxBuffer: 10 * 1024 * 1024,
    },
  );

  if (child.error) {
    return {
      gameId: sample.gameId,
      levelIndex: sample.levelIndex,
      status: child.error.code === "ETIMEDOUT" ? "process_timeout" : "process_error",
      solved: false,
      error: child.error.message,
    };
  }
  if (child.status !== 0) {
    return {
      gameId: sample.gameId,
      levelIndex: sample.levelIndex,
      status: "error",
      solved: false,
      error: child.stderr.trim() || `Child exited with status ${child.status}`,
    };
  }

  const lines = child.stdout.trim().split(/\r?\n/).filter(Boolean);
  try {
    return JSON.parse(lines.at(-1));
  } catch (error) {
    return {
      gameId: sample.gameId,
      levelIndex: sample.levelIndex,
      status: "invalid_output",
      solved: false,
      error: `${error.message}; output=${child.stdout.slice(-1000)}`,
    };
  }
}

function csvCell(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const stringValue = Array.isArray(value) ? value.join(" ") : String(value);
  return /[",\r\n]/.test(stringValue)
    ? `"${stringValue.replaceAll('"', '""')}"`
    : stringValue;
}

function writeCsv(results, outputPath) {
  const columns = [
    "gameId", "levelIndex", "status", "solved", "optimalityProven",
    "solutionDepth", "solutionActions", "expandedStates", "uniqueStates",
    "transitions", "engineActions", "replayedActions", "ticks", "duplicates", "unchanged", "parseMs", "initMs",
    "searchMs", "engineMs", "codecMs", "totalMs", "searchTransitionsPerSecond",
    "engineActionsPerSecond", "engineTicksPerSecond", "compactBytesPerState", "peakHeapBytes",
  ];
  const lines = [columns.join(",")];
  for (const result of results) {
    lines.push(columns.map((column) => csvCell(result[column])).join(","));
  }
  fs.writeFileSync(outputPath, `${lines.join("\n")}\n`, "utf8");
}

function median(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (sorted.length === 0) {
    return 0;
  }
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function fixed(value, digits = 1) {
  return Number.isFinite(value) ? value.toFixed(digits) : "-";
}

function buildReport({ config, counts, sample, results, verification }) {
  const solved = results.filter((result) => result.solved);
  const unsolved = results.filter((result) => !result.solved);
  const measured = results.filter((result) => Number.isFinite(result.searchTransitionsPerSecond));
  const totalTransitions = measured.reduce((sum, result) => sum + result.transitions, 0);
  const totalEngineActions = measured.reduce((sum, result) => sum + result.engineActions, 0);
  const totalSearchMs = measured.reduce((sum, result) => sum + result.searchMs, 0);
  const totalEngineMs = measured.reduce((sum, result) => sum + result.engineMs, 0);
  const medianSearchTps = median(measured.map((result) => result.searchTransitionsPerSecond));
  const medianEngineAps = median(measured.map((result) => result.engineActionsPerSecond));

  const lines = [
    "# PuzzleScript BFS Sample Report",
    "",
    "## Configuration",
    "",
    `- Sample seed: \`${config.seed}\``,
    `- Sample size: ${sample.length}`,
    `- Level: first playable level of each game`,
    `- Per-game limits: ${config.maxStates.toLocaleString()} unique states or ${(config.timeoutMs / 1000).toFixed(1)} seconds`,
    "- Actions: UP, DOWN, LEFT, RIGHT, ACTION",
    "- Loop filtering: exact compact-state duplicate detection",
    "- Eligible games: parsed, non-empty formal WINCONDITIONS, deterministic turn-based source, no checkpoint token",
    "",
    "## Dataset scan",
    "",
    `- Script files: ${counts.scripts}`,
    `- Eligible deterministic goal-defined games: ${counts.eligible}`,
    `- Excluded without formal goals: ${counts.noFormalGoal}`,
    `- Excluded unsupported random/realtime/checkpoint games: ${counts.unsupported}`,
    `- Parse errors: ${counts.parseErrors}`,
    "",
    "## Summary",
    "",
    `- Solved: **${solved.length}/${results.length}**`,
    `- Independently replay-verified: **${verification.verifiedCount}/${verification.solvedCount}**`,
    `- Total attempted transitions: ${totalTransitions.toLocaleString()}`,
    `- Total engine actions including prefix replay: ${totalEngineActions.toLocaleString()}`,
    `- Aggregate search throughput: ${totalSearchMs > 0 ? fixed(totalTransitions / (totalSearchMs / 1000), 0) : "-"} transitions/s`,
    `- Median per-game search throughput: ${fixed(medianSearchTps, 0)} transitions/s`,
    `- Aggregate raw engine throughput: ${totalEngineMs > 0 ? fixed(totalEngineActions / (totalEngineMs / 1000), 0) : "-"} actions/s`,
    `- Median per-game raw engine throughput: ${fixed(medianEngineAps, 0)} actions/s`,
    "",
    "For correctness, each attempted BFS edge starts a fresh engine, replays the node's action prefix, and then applies the candidate action. `engine actions` includes that prefix-replay work; `attempted transitions` counts only candidate BFS edges.",
    "",
    "## Simulator verdict",
    "",
    `- The engine itself is usable for modest forward simulation: ${totalEngineMs > 0 ? fixed(totalEngineActions / (totalEngineMs / 1000), 0) : "-"} actions/s in aggregate on this sample.`,
    `- Correct baseline BFS is much slower: ${totalSearchMs > 0 ? fixed(totalTransitions / (totalSearchMs / 1000), 0) : "-"} new edges/s, with ${(totalEngineActions / Math.max(totalTransitions, 1)).toFixed(1)} engine actions executed per candidate edge because of prefix replay.`,
    "- Therefore this engine is fast enough for small first levels and a baseline experiment, but not for scalable uninformed BFS over most games. A trustworthy fast solver needs an engine-supported clone/restore API that captures all transition-relevant rule state, or heuristic search that expands far fewer nodes.",
    "",
    "## Solved games",
    "",
    "| Game | Level index | Optimal actions | Expanded | Transitions | Search ms | Transitions/s |",
    "|---|---:|---:|---:|---:|---:|---:|",
  ];

  for (const result of solved) {
    lines.push(
      `| ${result.gameId} | ${result.levelIndex} | ${result.solutionDepth} | ${result.expandedStates.toLocaleString()} | ${result.transitions.toLocaleString()} | ${fixed(result.searchMs)} | ${fixed(result.searchTransitionsPerSecond, 0)} |`,
    );
  }

  lines.push(
    "",
    "## Unsolved within the bounds",
    "",
    "| Game | Level index | Status | Expanded | Unique states | Transitions | Search ms |",
    "|---|---:|---|---:|---:|---:|---:|",
  );
  for (const result of unsolved) {
    lines.push(
      `| ${result.gameId} | ${result.levelIndex ?? "-"} | ${result.status} | ${(result.expandedStates ?? 0).toLocaleString()} | ${(result.uniqueStates ?? 0).toLocaleString()} | ${(result.transitions ?? 0).toLocaleString()} | ${fixed(result.searchMs)} |`,
    );
  }

  lines.push(
    "",
    "## Interpretation limits",
    "",
    "- A solved result is shortest in the five-action input space under the modeled cell state because the frontier is FIFO and duplicate filtering stores exact compact cell states.",
    "- Compact states include both sprite membership and per-sprite movement intent. Every reported path must also pass an independent fresh-engine replay check.",
    "- A timeout or state-limit result means unknown, not unsolvable.",
    "- This is forward BFS. Generic backward BFS was not used because PuzzleScript exposes successor execution but no complete predecessor generator, and win conditions describe a set of states rather than a concrete goal board.",
    "- The experiment uses the first playable level only; later levels can be substantially harder.",
    "- Games with randomness, realtime execution, checkpoints, or only rule-command goals are outside this first exact-state experiment.",
    "",
  );
  return lines.join("\n");
}

function main() {
  const config = parseArgs(process.argv.slice(2));
  const { candidates, excluded, counts } = collectCandidates();
  if (candidates.length < config.sampleSize) {
    throw new Error(`Only ${candidates.length} eligible games for sample size ${config.sampleSize}`);
  }

  const orderedIds = deterministicOrder(candidates.map((candidate) => candidate.gameId), config.seed);
  const candidateById = new Map(candidates.map((candidate) => [candidate.gameId, candidate]));
  const sample = orderedIds.slice(0, config.sampleSize).map((gameId) => candidateById.get(gameId));

  fs.writeFileSync(
    path.join(EXPERIMENT_DIR, "sample.json"),
    `${JSON.stringify({ config, counts, sample, excluded }, null, 2)}\n`,
    "utf8",
  );

  const results = [];
  for (let index = 0; index < sample.length; index += 1) {
    const item = sample[index];
    process.stdout.write(`[${index + 1}/${sample.length}] ${item.gameId} ... `);
    const result = runOne(item, config);
    results.push(result);
    const detail = result.solved
      ? `solved depth=${result.solutionDepth}`
      : result.status;
    process.stdout.write(`${detail}\n`);
  }

  const resultBundle = {
    generatedAt: new Date().toISOString(),
    config,
    counts,
    sample: sample.map(({ gameId, levelIndex, formalGoalCount }) => ({
      gameId,
      levelIndex,
      formalGoalCount,
    })),
    results,
  };
  fs.writeFileSync(
    path.join(EXPERIMENT_DIR, "results.json"),
    `${JSON.stringify(resultBundle, null, 2)}\n`,
    "utf8",
  );
  writeCsv(results, path.join(EXPERIMENT_DIR, "results.csv"));

  const verificationRun = spawnSync(process.execPath, [VERIFY_RESULTS_SCRIPT], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    timeout: 60_000,
  });
  if (verificationRun.status !== 0) {
    throw new Error(
      `Solution replay verification failed: ${verificationRun.stderr || verificationRun.stdout}`,
    );
  }
  const verification = JSON.parse(
    fs.readFileSync(path.join(EXPERIMENT_DIR, "verification.json"), "utf8"),
  );
  fs.writeFileSync(
    path.join(EXPERIMENT_DIR, "REPORT.md"),
    `${buildReport({ config, counts, sample, results, verification })}\n`,
    "utf8",
  );

  const solvedCount = results.filter((result) => result.solved).length;
  process.stdout.write(verificationRun.stdout);
  process.stdout.write(`Done: ${solvedCount}/${results.length} solved. See experiement/bfs_solver/REPORT.md\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
}
