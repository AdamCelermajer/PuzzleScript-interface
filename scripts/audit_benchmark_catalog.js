#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { inspectGameSource } = require("../experiement/bfs_solver/solver");

const REPO_ROOT = path.resolve(__dirname, "..");
const GAMES_ROOT = path.join(REPO_ROOT, "puzzlescript_interface", "games");
const BENCHMARK_INDEX = path.join(REPO_ROOT, "benchmark", "games", "index.json");
const EXISTING_RESULTS = path.join(
  REPO_ROOT,
  "experiement",
  "bfs_solver",
  "semantic_all_60s_results.json",
);
const OUTPUT_ROOT = path.join(REPO_ROOT, "benchmark", "vetting");
const SELECTION_PATH = path.join(OUTPUT_ROOT, "selection-v0.json");
const SMOKE_PATH = path.join(OUTPUT_ROOT, "runtime-smoke.json");

function readJson(filePath, fallback) {
  if (!fs.existsSync(filePath)) return fallback;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function visibleSymbolCount(source) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n").map((line) => line.trim());
  let inLegend = false;
  let count = 0;
  for (const line of lines) {
    if (line === "LEGEND") {
      inLegend = true;
      continue;
    }
    if (inLegend && line === "COLLISIONLAYERS") break;
    if (inLegend && /^[A-Za-z0-9.\-]\s*=\s*/.test(line)) count += 1;
  }
  return count;
}

function renderSignature(sprite) {
  if (sprite.pixels) {
    return sprite.pixels
      .map((row) => row.map((pixel) => pixel.hex ?? "transparent").join(","))
      .join(";");
  }
  return `solid:${sprite.color?.hex ?? String(sprite.color ?? "unknown")}`;
}

function visualAliases(objects) {
  const grouped = new Map();
  for (const sprite of objects) {
    const signature = renderSignature(sprite);
    if (!grouped.has(signature)) grouped.set(signature, []);
    grouped.get(signature).push(sprite.name);
  }
  return [...grouped.values()].filter((names) => names.length > 1);
}

function featureFlags(source, data) {
  const has = (pattern) => pattern.test(source);
  return {
    action_button: !data.metadata.noAction && has(/\bACTION\b/i),
    again: has(/\bAGAIN\b/i),
    cancel: has(/\bCANCEL\b/i),
    late_rules: has(/^\s*LATE\b/im),
    directional_rules: has(/^\s*(UP|DOWN|LEFT|RIGHT|HORIZONTAL|VERTICAL)\b/im),
    movement_modifiers: has(/\b(MOVING|STATIONARY|ORTHOGONAL|PERPENDICULAR|PARALLEL)\b/i),
    negation: has(/\bNO\s+[A-Za-z]/i),
    ellipsis: has(/\.\.\./),
    rigid: has(/\bRIGID\b/i),
    rule_loops: has(/\b(STARTLOOP|ENDLOOP)\b/i),
    explicit_win_command: has(/\bWIN\b/i),
    restart_command: has(/\bRESTART\b/i),
    run_rules_on_level_start: Boolean(data.metadata.runRulesOnLevelStart),
  };
}

function boardStats(levels) {
  const maps = levels.filter((level) => level.type === "LEVEL_MAP");
  const areas = maps.map((level) => {
    const rows = level.cells?.length ?? 0;
    const cols = level.cells?.[0]?.length ?? 0;
    return rows * cols;
  });
  return {
    map_levels: maps.length,
    message_levels: levels.length - maps.length,
    min_area: areas.length ? Math.min(...areas) : 0,
    max_area: areas.length ? Math.max(...areas) : 0,
    mean_area: areas.length
      ? Math.round(areas.reduce((sum, value) => sum + value, 0) / areas.length)
      : 0,
  };
}

function csvCell(value) {
  const text = Array.isArray(value)
    ? value.map((item) => Array.isArray(item) ? item.join("+") : item).join("|")
    : String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function main() {
  const benchmark = readJson(BENCHMARK_INDEX, { games: [] });
  const benchmarkIds = new Set(benchmark.games.map((game) => game.game_id));
  const resultsDocument = readJson(EXISTING_RESULTS, { results: [] });
  const results = new Map(
    (resultsDocument.results ?? []).map((result) => [result.gameId, result]),
  );
  const selection = readJson(SELECTION_PATH, { selection: [] });
  const selectedTiers = new Map(
    selection.selection.map((game) => [game.game_id, game.tier]),
  );
  const smoke = readJson(SMOKE_PATH, { games: [] });
  const smokeResults = new Map(smoke.games.map((game) => [game.game_id, game.passed]));
  const rows = [];
  const directories = fs.readdirSync(GAMES_ROOT, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .sort((left, right) => left.name.localeCompare(right.name));

  for (const directory of directories) {
    const gameId = directory.name;
    const scriptPath = path.join(GAMES_ROOT, gameId, "script.txt");
    if (!fs.existsSync(scriptPath)) {
      rows.push({ game_id: gameId, status: "no_script" });
      continue;
    }
    const source = fs.readFileSync(scriptPath, "utf8");
    try {
      const inspection = inspectGameSource(source);
      const data = inspection.data;
      const board = boardStats(data.levels);
      const flags = featureFlags(source, data);
      const aliases = visualAliases(data.objects);
      const prior = results.get(gameId);
      rows.push({
        game_id: gameId,
        status: "parsed",
        arc_catalog_compatible: visibleSymbolCount(source) <= 15,
        deterministic_formal_candidate:
          inspection.formalGoalCount > 0 && inspection.unsupportedReasons.length === 0,
        exclusion_reasons: inspection.formalGoalCount === 0
          ? ["no_formal_win_condition", ...inspection.unsupportedReasons]
          : inspection.unsupportedReasons,
        title: data.title,
        author: data.metadata.author,
        homepage: data.metadata.homepage,
        has_readme: fs.existsSync(path.join(GAMES_ROOT, gameId, "readme.txt")),
        object_count: data.objects.length,
        parsed_rule_groups: data.rules.length,
        formal_goal_count: inspection.formalGoalCount,
        ...board,
        possible_visual_aliases: aliases,
        possible_visual_alias_count: aliases.length,
        features: flags,
        feature_count: Object.values(flags).filter(Boolean).length,
        current_benchmark: benchmarkIds.has(gameId),
        existing_first_level_solver: prior
          ? {
              level_index: prior.levelIndex,
              solved: Boolean(prior.solved),
              status: prior.status,
              solution_depth: prior.solutionDepth ?? null,
            }
          : null,
      });
    } catch (error) {
      rows.push({ game_id: gameId, status: "parse_error", error: error.message });
    }
  }

  for (const row of rows) {
    row.selected_tier = selectedTiers.get(row.game_id) ?? null;
    row.runtime_smoke_passed = smokeResults.get(row.game_id) ?? null;
    if (row.selected_tier) {
      row.stage_1_disposition = `selected_${row.selected_tier}`;
    } else if (row.status === "no_script") {
      row.stage_1_disposition = "excluded_no_script";
    } else if (row.status === "parse_error") {
      row.stage_1_disposition = "excluded_parse_error";
    } else if (!row.deterministic_formal_candidate) {
      row.stage_1_disposition = "excluded_initial_protocol";
    } else if (row.runtime_smoke_passed === false) {
      row.stage_1_disposition = "excluded_runtime_failure";
    } else {
      row.stage_1_disposition = "reserve_pool";
    }
  }

  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const jsonPath = path.join(OUTPUT_ROOT, "catalog-audit.json");
  fs.writeFileSync(jsonPath, `${JSON.stringify({ generated_at: new Date().toISOString(), games: rows }, null, 2)}\n`);

  const columns = [
    "game_id", "status", "stage_1_disposition", "selected_tier",
    "runtime_smoke_passed", "arc_catalog_compatible", "deterministic_formal_candidate",
    "exclusion_reasons", "title", "author", "has_readme", "object_count",
    "parsed_rule_groups", "formal_goal_count", "map_levels", "message_levels",
    "min_area", "max_area", "mean_area", "possible_visual_alias_count",
    "possible_visual_aliases", "feature_count", "current_benchmark",
    "existing_solver_solved", "existing_solution_depth",
  ];
  const csvLines = [columns.join(",")];
  for (const row of rows) {
    const flat = {
      ...row,
      existing_solver_solved: row.existing_first_level_solver?.solved ?? "",
      existing_solution_depth: row.existing_first_level_solver?.solution_depth ?? "",
    };
    csvLines.push(columns.map((column) => csvCell(flat[column])).join(","));
  }
  const csvPath = path.join(OUTPUT_ROOT, "catalog-audit.csv");
  fs.writeFileSync(csvPath, `${csvLines.join("\n")}\n`);

  const parsed = rows.filter((row) => row.status === "parsed");
  const eligible = parsed.filter((row) => row.deterministic_formal_candidate);
  process.stdout.write(JSON.stringify({
    directories: rows.length,
    scripts: parsed.length,
    arc_catalog_compatible: parsed.filter((row) => row.arc_catalog_compatible).length,
    deterministic_formal_candidates: eligible.length,
    current_benchmark_games: parsed.filter((row) => row.current_benchmark).length,
    json: path.relative(REPO_ROOT, jsonPath),
    csv: path.relative(REPO_ROOT, csvPath),
  }, null, 2) + "\n");
}

main();
