const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const defaultRunId = "2026-05-31T19-29-42-openrouter-matrix";

const runDirArg = process.argv[2];
const runDir = path.resolve(
  repoRoot,
  runDirArg || `side_quests/codex_goal_recognition_3shot/artifacts/${defaultRunId}`,
);
const reportPath = path.resolve(repoRoot, "report.json");
const outputDir = path.resolve(repoRoot, "deploy/goal-recognition-results");
const outputPath = path.join(outputDir, "app-data.js");

function readJson(filePath) {
  const raw = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(raw);
}

function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) {
    return [];
  }

  return fs.readFileSync(filePath, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function normalizeText(value) {
  return value === undefined || value === null ? "" : String(value).trim();
}

function normalizeConfidence(value) {
  if (typeof value === "string") {
    const label = value.trim().toLowerCase();
    if (label === "low") return 0.25;
    if (label === "moderate" || label === "medium") return 0.5;
    if (label === "high") return 0.75;
  }
  return Number(value) || 0;
}

function firstPresent(source, keys) {
  for (const key of keys) {
    if (source?.[key] !== undefined && source?.[key] !== null) {
      return source[key];
    }
  }
  return undefined;
}

function relativeFromOutput(filePath) {
  return path.relative(outputDir, filePath).replaceAll(path.sep, "/");
}

function staticScreenshotName(gameId) {
  return `${gameId.replace(/[^a-zA-Z0-9_.-]/g, "_")}.png`;
}

function firstExistingScreenshot(gameId) {
  const candidates = [
    path.join(repoRoot, "deploy/human-goal-recognition/dataset", gameId, "screenshot.png"),
    path.join(repoRoot, "deploy/railway-human-goal-study/dataset", gameId, "screenshot.png"),
    path.join(runDir, "sources", gameId, "screenshot.png"),
    path.join(repoRoot, "dataset", gameId, "screenshot.png"),
  ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) {
    return "";
  }

  const screenshotsDir = path.join(outputDir, "assets", "screenshots");
  const target = path.join(screenshotsDir, staticScreenshotName(gameId));
  fs.mkdirSync(screenshotsDir, { recursive: true });
  fs.copyFileSync(found, target);
  return relativeFromOutput(target);
}

function groupHumanAnswers(report) {
  if (!Array.isArray(report.submissions)) {
    throw new Error("Expected report.json to contain a submissions array.");
  }

  const answersByGame = new Map();
  for (const submission of report.submissions) {
    const responses = Array.isArray(submission.responses) ? submission.responses : [];
    for (const response of responses) {
      const gameId = normalizeText(response.game_id);
      if (!gameId) {
        continue;
      }

      if (!answersByGame.has(gameId)) {
        answersByGame.set(gameId, []);
      }

      answersByGame.get(gameId).push({
        participant_id: normalizeText(submission.participant_id),
        submitted_at: normalizeText(submission.submitted_at),
        colorblind: Boolean(submission.colorblind),
        game_order: response.game_order ?? null,
        answer_text: normalizeText(response.answer_text),
      });
    }
  }

  for (const answers of answersByGame.values()) {
    answers.sort((left, right) => left.submitted_at.localeCompare(right.submitted_at));
  }

  return answersByGame;
}

function compactPrediction(row) {
  const raw = row.raw_response || {};
  const prediction = row.prediction || {};
  const source = {
    ...raw,
    goal_guess: firstPresent(prediction, ["goal_guess"]) || raw.goal_guess,
    win_condition_guess:
      firstPresent(prediction, ["win_condition_guess"]) || raw.win_condition_guess,
    key_objects: prediction.key_objects?.length ? prediction.key_objects : raw.key_objects,
    confidence: prediction.confidence || raw.confidence,
    uncertainties: prediction.uncertainties?.length ? prediction.uncertainties : raw.uncertainties,
    rationale: prediction.rationale || raw.rationale,
  };
  return {
    run_id: normalizeText(row.run_id),
    game_id: normalizeText(row.game_id),
    evidence_mode: normalizeText(row.evidence_mode),
    input_mode: normalizeText(row.input_mode),
    prompt_id: normalizeText(row.prompt_id),
    model: normalizeText(row.model),
    prediction: {
      goal_guess: normalizeText(
        firstPresent(source, [
          "goal_guess",
          "goal",
          "game_goal",
          "likely_goal",
          "likely_game_goal",
          "inferred_goal",
          "most_likely_goal",
          "plain_english_goal",
          "goal_hypothesis",
          "goal_description",
          "goal_plain_english",
          "objective",
          "goalGuess",
          "answer",
        ]),
      ),
      win_condition_guess: normalizeText(
        firstPresent(source, [
          "win_condition_guess",
          "success_condition",
          "win_condition",
          "successCondition",
          "winning_condition",
          "success_criteria",
          "goal_condition",
          "success_condition_hypothesis",
          "likely_success_condition",
        ]),
      ),
      confidence: normalizeConfidence(source.confidence),
      key_objects: normalizeKeyObjects(source),
      uncertainties: normalizeList(source.uncertainties),
      rationale: normalizeText(source.rationale),
    },
  };
}

function normalizeKeyObjects(source) {
  if (Array.isArray(source.key_objects)) {
    return source.key_objects.map((item) => ({
      value:
        item && typeof item === "object"
          ? item?.value ?? item?.id ?? item?.symbol ?? ""
          : item,
      role_guess:
        item && typeof item === "object"
          ? normalizeText(item?.role_guess ?? item?.role ?? item?.description)
          : "",
    }));
  }

  const objectMap =
    source.important_visual_ids || source.important_ids || source.visual_ids || source.objects;
  if (objectMap && typeof objectMap === "object" && !Array.isArray(objectMap)) {
    return Object.entries(objectMap).map(([value, role]) => ({
      value,
      role_guess: normalizeText(
        typeof role === "object"
          ? role.role_guess ?? role.role ?? role.description ?? JSON.stringify(role)
          : role,
      ),
    }));
  }

  return [];
}

function normalizeList(value) {
  if (Array.isArray(value)) {
    return value;
  }
  const text = normalizeText(value);
  return text ? [text] : [];
}

function matrixKey(row) {
  return [
    normalizeText(row.game_id),
    normalizeText(row.evidence_mode),
    normalizeText(row.input_mode),
    normalizeText(row.prompt_id),
    normalizeText(row.model),
  ].join("\t");
}

function latestUniqueRows(rows) {
  const byKey = new Map();
  for (const row of rows) {
    byKey.set(matrixKey(row), row);
  }
  return [...byKey.values()];
}

function countRowsByGame(rows) {
  const counts = new Map();
  for (const row of rows) {
    const gameId = normalizeText(row.game_id);
    if (!gameId) {
      continue;
    }
    counts.set(gameId, (counts.get(gameId) || 0) + 1);
  }
  return counts;
}

function buildViewerData() {
  const manifest = readJson(path.join(runDir, "manifest.json"));
  const report = readJson(reportPath);
  const humanAnswers = groupHumanAnswers(report);
  const predictions = latestUniqueRows(
    readJsonl(path.join(runDir, "predictions.jsonl")).map(compactPrediction),
  );
  const skips = latestUniqueRows(readJsonl(path.join(runDir, "skips.jsonl")));
  const completedKeys = new Set([
    ...predictions.map(matrixKey),
    ...skips.map(matrixKey),
  ]);
  const unresolvedErrors = latestUniqueRows(
    readJsonl(path.join(runDir, "errors.jsonl"))
      .filter((row) => !completedKeys.has(matrixKey(row))),
  );
  const errorsByGame = countRowsByGame(unresolvedErrors);
  const skipsByGame = countRowsByGame(skips);
  const predictionsByGame = new Map();

  for (const prediction of predictions) {
    if (!predictionsByGame.has(prediction.game_id)) {
      predictionsByGame.set(prediction.game_id, []);
    }
    predictionsByGame.get(prediction.game_id).push(prediction);
  }

  for (const rows of predictionsByGame.values()) {
    rows.sort((left, right) => {
      return [
        left.model.localeCompare(right.model),
        left.evidence_mode.localeCompare(right.evidence_mode),
        left.input_mode.localeCompare(right.input_mode),
      ].find((value) => value !== 0) || 0;
    });
  }

  const gameIds = Array.isArray(manifest.games)
    ? manifest.games
    : [...new Set([...humanAnswers.keys(), ...predictionsByGame.keys()])].sort();

  const games = gameIds.map((gameId) => ({
    game_id: gameId,
    screenshot: firstExistingScreenshot(gameId),
      human_answers: humanAnswers.get(gameId) || [],
      llm_answers: predictionsByGame.get(gameId) || [],
      error_count: errorsByGame.get(gameId) || 0,
    skip_count: skipsByGame.get(gameId) || 0,
  }));

  return {
    generated_at: new Date().toISOString(),
    run_id: manifest.run_id || path.basename(runDir),
    source_run_dir: path.relative(repoRoot, runDir).replaceAll(path.sep, "/"),
    totals: {
      games: games.length,
      human_answers: [...humanAnswers.values()].reduce((total, rows) => total + rows.length, 0),
      llm_answers: predictions.length,
      errors: unresolvedErrors.length,
      skips: skips.length,
    },
    filters: {
      models: [...new Set(predictions.map((row) => row.model))].sort(),
      evidence_modes: [...new Set(predictions.map((row) => row.evidence_mode))].sort(),
      input_modes: [...new Set(predictions.map((row) => row.input_mode))].sort(),
    },
    games,
  };
}

fs.mkdirSync(outputDir, { recursive: true });
const data = buildViewerData();
fs.writeFileSync(
  outputPath,
  `window.GOAL_RECOGNITION_RESULTS = ${JSON.stringify(data, null, 2)};\n`,
  "utf8",
);

console.log(
  `Wrote ${data.totals.games} games, ${data.totals.human_answers} human answers, ` +
  `${data.totals.llm_answers} LLM answers to ${path.relative(repoRoot, outputPath)}`,
);
