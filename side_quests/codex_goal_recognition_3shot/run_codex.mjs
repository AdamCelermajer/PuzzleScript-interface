import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { llm_call } from "./llm_call.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const DEFAULT_CODEX_MODEL = "gpt-5.3-codex-spark";
const OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models";

const OPENROUTER_MATRIX = [
  { model: "deepseek/deepseek-v4-pro", supportsImages: false },
  {
    model: "moonshotai/kimi-k2.6",
    supportsImages: true,
    reasoning: { effort: "none", exclude: true },
    includeReasoning: false,
    maxTokens: 1600,
  },
  { model: "anthropic/claude-opus-4.8", supportsImages: true },
  {
    model: "openai/gpt-5.5",
    supportsImages: true,
    reasoning: { effort: "low", exclude: true },
    includeReasoning: false,
    maxTokens: 2500,
  },
];

const GOAL_OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    goal_guess: { type: "string" },
    win_condition_guess: { type: "string" },
    key_objects: {
      type: "array",
      items: {
        type: "object",
        properties: {
          value: { type: ["integer", "string"] },
          role_guess: { type: "string" },
        },
        required: ["value", "role_guess"],
        additionalProperties: false,
      },
    },
    confidence: { type: "number" },
    uncertainties: { type: "array", items: { type: "string" } },
    rationale: { type: "string" },
  },
  required: [
    "goal_guess",
    "win_condition_guess",
    "key_objects",
    "confidence",
    "uncertainties",
    "rationale",
  ],
  additionalProperties: false,
};

function parseArgs(argv) {
  const args = {
    runDir: null,
    client: "openrouter",
    model: DEFAULT_CODEX_MODEL,
    modelMatrix: "openrouter_goal_recognition",
    reasoningEffort: "high",
    limit: 0,
    resume: false,
    estimateOnly: false,
    writePlan: true,
    concurrency: 10,
    launchIntervalSeconds: 30,
    maxTokens: 1200,
    completionTokensEstimate: 300,
    imageTokensEstimate: 1000,
    workingDirectory: REPO_ROOT,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--run-dir") args.runDir = argv[++index];
    else if (arg === "--client") args.client = argv[++index];
    else if (arg === "--model") {
      args.model = argv[++index];
      args.modelMatrix = null;
    } else if (arg === "--model-matrix") args.modelMatrix = argv[++index];
    else if (arg === "--reasoning-effort") args.reasoningEffort = argv[++index];
    else if (arg === "--limit") args.limit = Number(argv[++index]);
    else if (arg === "--resume") args.resume = true;
    else if (arg === "--estimate-only") args.estimateOnly = true;
    else if (arg === "--no-plan") args.writePlan = false;
    else if (arg === "--concurrency") args.concurrency = Number(argv[++index]);
    else if (arg === "--launch-interval-seconds") {
      args.launchIntervalSeconds = Number(argv[++index]);
    }
    else if (arg === "--max-tokens") args.maxTokens = Number(argv[++index]);
    else if (arg === "--completion-tokens-estimate") {
      args.completionTokensEstimate = Number(argv[++index]);
    } else if (arg === "--image-tokens-estimate") {
      args.imageTokensEstimate = Number(argv[++index]);
    } else if (arg === "--working-directory") args.workingDirectory = argv[++index];
    else throw new Error(`Unknown argument: ${arg}`);
  }

  if (!args.runDir) {
    throw new Error(
      "Usage: node run_codex.mjs --run-dir <artifact-run-dir> " +
        "[--client openrouter|codex_sdk] " +
        "[--model MODEL|--model-matrix openrouter_goal_recognition] " +
        "[--resume] [--limit N] [--estimate-only]",
    );
  }
  return args;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function appendJsonl(filePath, row) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.appendFileSync(filePath, `${JSON.stringify(row)}\n`, "utf8");
}

function writeJsonl(filePath, rows) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(
    filePath,
    rows.map((row) => JSON.stringify(row)).join("\n") + (rows.length ? "\n" : ""),
    "utf8",
  );
}

function acquireRunLock(runDir) {
  const lockPath = path.join(runDir, "stage3.lock");
  try {
    const fd = fs.openSync(lockPath, "wx");
    fs.writeFileSync(
      fd,
      JSON.stringify({
        pid: process.pid,
        started_at: new Date().toISOString(),
      }),
      "utf8",
    );
    fs.closeSync(fd);
  } catch (error) {
    throw new Error(
      `Stage 3 lock exists at ${lockPath}. ` +
        "Another run may be active; remove it only after confirming no runner is running.",
    );
  }
  process.on("exit", () => {
    try {
      fs.unlinkSync(lockPath);
    } catch {}
  });
  return lockPath;
}

function cleanString(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function cleanFloat(value) {
  if (typeof value === "string") {
    const label = value.trim().toLowerCase();
    if (label === "low") return 0.25;
    if (label === "moderate" || label === "medium") return 0.5;
    if (label === "high") return 0.75;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function firstPresent(data, keys) {
  for (const key of keys) {
    if (data?.[key] !== undefined && data?.[key] !== null) {
      return data[key];
    }
  }
  return undefined;
}

function normalizeKeyObjects(data) {
  const keyObjects = data?.key_objects;
  if (Array.isArray(keyObjects)) {
    return keyObjects.map((item) => ({
      value:
        item && typeof item === "object"
          ? item?.value ?? item?.id ?? item?.symbol ?? ""
          : item,
      role_guess:
        item && typeof item === "object"
          ? cleanString(item?.role_guess ?? item?.role ?? item?.description)
          : "",
    }));
  }

  const objectMap =
    data?.important_visual_ids ?? data?.important_ids ?? data?.visual_ids ?? data?.objects;
  if (objectMap && typeof objectMap === "object" && !Array.isArray(objectMap)) {
    return Object.entries(objectMap).map(([value, role]) => ({
      value,
      role_guess: cleanString(
        typeof role === "object"
          ? role.role_guess ?? role.role ?? role.description ?? JSON.stringify(role)
          : role,
      ),
    }));
  }

  return [];
}

function normalizePrediction(data) {
  const uncertainties = data?.uncertainties;
  return {
    goal_guess: cleanString(
      firstPresent(data, [
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
    win_condition_guess: cleanString(
      firstPresent(data, [
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
    key_objects: normalizeKeyObjects(data),
    confidence: cleanFloat(data?.confidence),
    uncertainties: Array.isArray(uncertainties)
      ? uncertainties
      : cleanString(uncertainties)
        ? [cleanString(uncertainties)]
        : [],
    rationale: cleanString(data?.rationale),
  };
}

function matrixKey(row) {
  return [
    row.game_id,
    row.evidence_mode,
    row.input_mode,
    row.prompt_id,
    row.model,
  ].join("\t");
}

function jsonlKeys(filePath) {
  if (!fs.existsSync(filePath)) return new Set();
  return new Set(
    fs.readFileSync(filePath, "utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => matrixKey(JSON.parse(line))),
  );
}

function modelConfigs(args) {
  if (
    args.client === "openrouter" &&
    args.modelMatrix === "openrouter_goal_recognition"
  ) {
    return OPENROUTER_MATRIX;
  }
  return [{ model: args.model, supportsImages: true }];
}

function listPromptFiles(runDir) {
  const promptsDir = path.join(runDir, "prompts");
  if (!fs.existsSync(promptsDir)) {
    throw new Error(`Prompt directory not found: ${promptsDir}`);
  }

  const files = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir)) {
      const item = path.join(dir, entry);
      if (fs.statSync(item).isDirectory()) walk(item);
      else if (entry.endsWith(".json")) files.push(item);
    }
  }
  walk(promptsDir);
  return files.sort();
}

function promptSortKey(prompt, model) {
  const inputRank = prompt.input_mode === "text_only" ? "0" : "1";
  return [
    model,
    prompt.game_id,
    prompt.evidence_mode,
    inputRank,
    prompt.input_mode,
  ].join("\t");
}

function plannedRows(promptFiles, models, args, done) {
  const rows = [];
  for (const promptFile of promptFiles) {
    const prompt = readJson(promptFile);
    for (const modelConfig of models) {
      const row = {
        game_id: prompt.game_id,
        evidence_mode: prompt.evidence_mode,
        input_mode: prompt.input_mode,
        prompt_id: prompt.prompt_id,
        model: modelConfig.model,
        prompt,
        promptFile,
        modelConfig,
        unsupportedImage:
          (prompt.image_paths || []).length > 0 &&
          modelConfig.supportsImages === false,
        sortKey: promptSortKey(prompt, modelConfig.model),
      };
      if (!done.has(matrixKey(row))) rows.push(row);
    }
  }

  rows.sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  return args.limit > 0 ? rows.slice(0, args.limit) : rows;
}

function estimateTextTokens(text) {
  return Math.ceil(String(text || "").length / 4);
}

async function openRouterPricing() {
  const response = await fetch(OPENROUTER_MODELS_URL);
  if (!response.ok) return new Map();
  const data = await response.json();
  return new Map((data?.data || []).map((model) => [model.id, model.pricing || {}]));
}

function numberPrice(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function newEstimateBucket() {
  return {
    planned: 0,
    runnable: 0,
    skips: 0,
    noCache: 0,
    cacheOptimized: 0,
  };
}

function estimateCost(rows, pricingByModel, args) {
  const byModel = new Map();
  const warmed = new Set();

  for (const row of rows) {
    if (!byModel.has(row.model)) byModel.set(row.model, newEstimateBucket());
    const bucket = byModel.get(row.model);
    bucket.planned += 1;

    if (row.unsupportedImage) {
      bucket.skips += 1;
      continue;
    }

    bucket.runnable += 1;
    const prompt = row.prompt;
    const pricing = pricingByModel.get(row.model) || {};
    const inputPrice = numberPrice(pricing.prompt);
    const outputPrice = numberPrice(pricing.completion);
    const cacheReadPrice = numberPrice(pricing.input_cache_read) || inputPrice;
    const cacheWritePrice = numberPrice(pricing.input_cache_write) || inputPrice;
    const prefixTokens = estimateTextTokens(prompt.prompt_prefix);
    const suffixTokens = estimateTextTokens(prompt.prompt_suffix);
    const imageTokens = (prompt.image_paths || []).length * args.imageTokensEstimate;
    const completionTokens = args.completionTokensEstimate;

    bucket.noCache +=
      (prefixTokens + suffixTokens + imageTokens) * inputPrice +
      completionTokens * outputPrice;

    const cacheKey = `${row.model}\t${
      prompt.cache_session_id || `${prompt.game_id}:${prompt.evidence_mode}`
    }`;
    const prefixPrice = warmed.has(cacheKey) ? cacheReadPrice : cacheWritePrice;
    warmed.add(cacheKey);

    bucket.cacheOptimized +=
      prefixTokens * prefixPrice +
      (suffixTokens + imageTokens) * inputPrice +
      completionTokens * outputPrice;
  }

  const total = newEstimateBucket();
  for (const bucket of byModel.values()) {
    total.planned += bucket.planned;
    total.runnable += bucket.runnable;
    total.skips += bucket.skips;
    total.noCache += bucket.noCache;
    total.cacheOptimized += bucket.cacheOptimized;
  }

  return { byModel, total };
}

function dollars(value) {
  return `$${value.toFixed(4)}`;
}

function printEstimate(estimate) {
  console.log("model                              runnable  skips  cache-est   no-cache");
  for (const [model, bucket] of estimate.byModel.entries()) {
    console.log(
      `${model.padEnd(34)} ${String(bucket.runnable).padStart(8)} ` +
        `${String(bucket.skips).padStart(6)} ` +
        `${dollars(bucket.cacheOptimized).padStart(10)} ` +
        `${dollars(bucket.noCache).padStart(10)}`,
    );
  }
  console.log(
    `${"TOTAL".padEnd(34)} ${String(estimate.total.runnable).padStart(8)} ` +
      `${String(estimate.total.skips).padStart(6)} ` +
      `${dollars(estimate.total.cacheOptimized).padStart(10)} ` +
      `${dollars(estimate.total.noCache).padStart(10)}`,
  );
}

function planRows(rows, runDir, args) {
  return rows.map((row, index) => ({
    index: index + 1,
    game_id: row.game_id,
    evidence_mode: row.evidence_mode,
    input_mode: row.input_mode,
    prompt_id: row.prompt_id,
    model: row.model,
    prompt_path: path.relative(runDir, row.promptFile),
    cache_session_id: row.prompt.cache_session_id,
    unsupported_image: row.unsupportedImage,
    estimated: {
      prompt_prefix_tokens: estimateTextTokens(row.prompt.prompt_prefix),
      prompt_suffix_tokens: estimateTextTokens(row.prompt.prompt_suffix),
      image_tokens: (row.prompt.image_paths || []).length * args.imageTokensEstimate,
    },
  }));
}

function formatSeconds(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m${String(rest).padStart(2, "0")}s`;
}

class Progress {
  constructor(total) {
    this.total = Math.max(total, 1);
    this.started = Date.now();
    this.done = 0;
    this.ok = 0;
    this.errors = 0;
    this.skips = 0;
  }

  step(kind) {
    this.done += 1;
    if (kind === "ok") this.ok += 1;
    else if (kind === "error") this.errors += 1;
    else if (kind === "skip") this.skips += 1;
    this.render();
  }

  render() {
    const width = 24;
    const filled = Math.floor((width * this.done) / this.total);
    const bar = `${"#".repeat(filled)}${"-".repeat(width - filled)}`;
    const elapsed = (Date.now() - this.started) / 1000;
    const perItem = this.done ? elapsed / this.done : 0;
    const eta = perItem * (this.total - this.done);
    process.stdout.write(
      `\rllm [${bar}] ${this.done}/${this.total} ` +
        `ok=${this.ok} skip=${this.skips} err=${this.errors} ` +
        `elapsed=${formatSeconds(elapsed)} eta=${formatSeconds(eta)}`,
    );
    if (this.done >= this.total) process.stdout.write("\n");
  }
}

function runnableRows(rows) {
  return rows.filter((row) => !row.unsupportedImage);
}

function skipUnsupportedRows(rows, manifest, args, skipsPath, progress) {
  for (const row of rows.filter((item) => item.unsupportedImage)) {
    appendJsonl(skipsPath, {
      run_id: manifest.run_id,
      game_id: row.game_id,
      evidence_mode: row.evidence_mode,
      input_mode: row.input_mode,
      prompt_id: row.prompt_id,
      prompt_path: path.relative(args.runDir, row.promptFile),
      provider: args.client,
      model: row.model,
      reason: "model_unsupported_image",
    });
    progress.step("skip");
  }
}

async function runAsyncRows(rows, manifest, args, paths, progress) {
  const queue = [...rows];
  const inFlight = new Set();
  const concurrency = Math.max(1, args.concurrency);
  const launchIntervalMs = Math.max(0, args.launchIntervalSeconds * 1000);

  async function start(row) {
    const task = (async () => {
      try {
        appendJsonl(
          paths.predictions,
          await runPrompt(row, args, manifest.run_id),
        );
        progress.step("ok");
      } catch (error) {
        appendJsonl(paths.errors, {
          run_id: manifest.run_id,
          game_id: row.game_id,
          evidence_mode: row.evidence_mode,
          input_mode: row.input_mode,
          prompt_id: row.prompt_id,
          prompt_path: path.relative(args.runDir, row.promptFile),
          provider: args.client,
          model: row.model,
          error: String(error?.message || error),
        });
        progress.step("error");
        process.stderr.write(
          `\nerror ${matrixKey(row)}: ${error?.message || error}\n`,
        );
      }
    })().finally(() => inFlight.delete(task));
    inFlight.add(task);
  }

  while (queue.length > 0 || inFlight.size > 0) {
    while (queue.length > 0 && inFlight.size < concurrency) {
      await start(queue.shift());
      if (queue.length > 0 && inFlight.size < concurrency && launchIntervalMs > 0) {
        await Promise.race([sleep(launchIntervalMs), ...inFlight]);
      }
    }

    if (inFlight.size > 0) {
      await Promise.race(inFlight);
    }
  }
}

function requireCredentials(args, runnableCount) {
  if (args.estimateOnly || runnableCount === 0) return;
  if (args.client === "openrouter" && !process.env.OPENROUTER_API_KEY) {
    throw new Error(
      "OPENROUTER_API_KEY is required to run stage 3. " +
        "Set it in the environment, or use --estimate-only to avoid LLM calls.",
    );
  }
}

async function runPrompt(row, args, runId) {
  const prompt = row.prompt;
  const llmResult = await llm_call(prompt, {
    client: args.client,
    model: row.modelConfig.model,
    maxTokens: row.modelConfig.maxTokens || args.maxTokens,
    includeReasoning: row.modelConfig.includeReasoning,
    reasoningEffort: args.reasoningEffort,
    reasoning: row.modelConfig.reasoning,
    sessionId: `goalrec:${row.model}:${
      prompt.cache_session_id || `${prompt.game_id}:${prompt.evidence_mode}`
    }`,
    workingDirectory: args.workingDirectory,
    outputSchema: GOAL_OUTPUT_SCHEMA,
  });
  return {
    run_id: runId,
    game_id: prompt.game_id,
    evidence_mode: prompt.evidence_mode,
    input_mode: prompt.input_mode,
    prompt_id: prompt.prompt_id,
    prompt_path: path.relative(args.runDir, row.promptFile),
    provider: llmResult.provider,
    model: llmResult.model,
    response_id: llmResult.id,
    usage: llmResult.usage,
    prediction: normalizePrediction(llmResult.raw_response),
    manual_verification: null,
    raw_response: llmResult.raw_response,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runDir = path.resolve(args.runDir);
  args.runDir = runDir;

  const manifest = readJson(path.join(runDir, "manifest.json"));
  const predictionsPath = path.join(runDir, "predictions.jsonl");
  const errorsPath = path.join(runDir, "errors.jsonl");
  const skipsPath = path.join(runDir, "skips.jsonl");
  const planPath = path.join(runDir, "batches", "llm_plan.jsonl");
  fs.closeSync(fs.openSync(predictionsPath, "a"));
  fs.closeSync(fs.openSync(errorsPath, "a"));
  fs.closeSync(fs.openSync(skipsPath, "a"));

  const done = args.resume
    ? new Set([...jsonlKeys(predictionsPath), ...jsonlKeys(skipsPath)])
    : new Set();
  const promptFiles = listPromptFiles(runDir);
  const models = modelConfigs(args);
  const rows = plannedRows(promptFiles, models, args, done);
  const pricingByModel = await openRouterPricing();
  const estimate = estimateCost(rows, pricingByModel, args);

  console.log(
    `planned rows: ${estimate.total.planned} ` +
      `(${estimate.total.runnable} runnable, ${estimate.total.skips} skips)`,
  );
  printEstimate(estimate);
  console.log(
    `assumptions: ${args.completionTokensEstimate} output tokens/call, ` +
      `${args.imageTokensEstimate} tokens/image`,
  );
  console.log(
    `async: max ${args.concurrency} in-flight, ` +
      `${args.launchIntervalSeconds}s launch interval, ` +
      `max_tokens=${args.maxTokens}, no request timeout`,
  );
  for (const model of models.filter((item) => item.maxTokens || item.reasoning)) {
    console.log(
      `override: ${model.model} max_tokens=${model.maxTokens || args.maxTokens} ` +
        `reasoning=${JSON.stringify(model.reasoning || {})}`,
    );
  }

  if (args.writePlan) {
    writeJsonl(planPath, planRows(rows, runDir, args));
    console.log(`plan: ${planPath}`);
  }

  requireCredentials(args, estimate.total.runnable);
  if (args.estimateOnly) return;
  const lockPath = acquireRunLock(runDir);
  console.log(`lock: ${lockPath}`);

  const progress = new Progress(rows.length);
  skipUnsupportedRows(rows, manifest, args, skipsPath, progress);
  await runAsyncRows(runnableRows(rows), manifest, args, {
    predictions: predictionsPath,
    errors: errorsPath,
  }, progress);

  console.log(`predictions: ${predictionsPath}`);
  console.log(`errors: ${errorsPath}`);
  console.log(`skips: ${skipsPath}`);
}

main().catch((error) => {
  console.error(error?.message || error);
  process.exit(1);
});
