const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function exists(relativePath) {
  return fs.existsSync(path.join(root, relativePath));
}

test("website shell pages and route templates are present", () => {
  const requiredFiles = [
    "website/index.html",
    "website/notes.html",
    "website/experiments/index.html",
    "website/experiments/goal-recognition/index.html",
    "website/experiments/thinking-comparison.html",
    "website/experiments/thinking-traces.js",
    "website/docs/architecture.html",
    "website/src/main.js",
    "website/src/notes.js",
    "website/src/workbench.js",
    "website/src/style.css",
    "website/src/goal-recognition-viewer.js",
  ];

  for (const file of requiredFiles) {
    assert.equal(exists(file), true, `${file} should exist`);
  }
});

test("vite config maps experiment source folders into website routes", () => {
  const config = read("website/vite.config.js");

  assert.match(config, /goalRecognitionSource/);
  assert.match(config, /studies\/goal_recognition\/website/);
  assert.match(config, /thinkingComparisonSource/);
  assert.match(config, /thinking-comparison/);
  assert.match(config, /experimentSourceRoutes/);
  assert.match(config, /copySourceRoutes/);
  assert.match(config, /resolve\(config\.root, config\.build\.outDir\)/);
  assert.match(config, /experiments\/goal-recognition\/assets/);
  assert.match(config, /experiments\/thinking-comparison/);
});

test("website runtime imports experiment viewer sources without local copies", () => {
  const html = read("website/experiments/goal-recognition/index.html");
  const loader = read("website/src/goal-recognition-viewer.js");

  assert.match(html, /\/src\/main\.js/);
  assert.match(html, /\/src\/goal-recognition-viewer\.js/);
  assert.match(loader, /@goal-recognition\/styles\.css/);
  assert.match(loader, /@goal-recognition\/app-data\.js/);
  assert.match(loader, /@goal-recognition\/app\.js/);

  assert.equal(exists("website/experiments/goal-recognition/app-data.js"), false);
  assert.equal(exists("website/experiments/goal-recognition/app.js"), false);
  assert.equal(exists("website/experiments/goal-recognition/viewer.css"), false);
  assert.equal(exists("website/experiments/goal-recognition/assets"), false);
  assert.equal(exists("website/public"), false);
});

test("goal recognition experiment remains the data and asset source", () => {
  const data = read("studies/goal_recognition/website/app-data.js");

  assert.match(data, /source_run_dir/);
  assert.match(data, /studies\/goal_recognition\/experiment\/artifacts/);
  assert.match(data, /assets\/screenshots\//);
  assert.equal(
    exists("studies/goal_recognition/website/assets/screenshots/ps_sokoban_basic-v1.png"),
    true,
  );
});

test("thinking comparison artifacts stay outside website source", () => {
  const requiredArtifacts = [
    "thinking-comparison/deepseek-thinking/log.txt",
    "thinking-comparison/deepseek-thinking/rules.json",
    "thinking-comparison/kimi-thinking/thinking_20260622T124354.json",
    "thinking-comparison/kimi-no-thinking/timeline.jsonl",
  ];

  for (const file of requiredArtifacts) {
    assert.equal(exists(file), true, `${file} should exist`);
  }
  assert.equal(exists("website/experiments/thinking-comparison"), false);
  assert.equal(exists("website/public/experiments/thinking-comparison"), false);
});

test("sidebar promotes architecture and groups experiment pages", () => {
  const shell = read("website/src/main.js");
  const architectureIndex = shell.indexOf("Architecture");
  const experimentIndex = shell.indexOf("Research traces");

  assert.notEqual(architectureIndex, -1, "Architecture should be a primary nav item");
  assert.notEqual(experimentIndex, -1, "Research traces group should exist");
  assert.ok(architectureIndex < experimentIndex, "Architecture should appear before the experiment group");
  assert.doesNotMatch(shell, /href:\s*['"]\/experiments\/['"],\s*label:\s*['"]Experiments/);
  assert.match(shell, /<details class="nav-group"/);
});

test("local pseudocode editor buffers Markdown and saves only manifest files", () => {
  const shell = read("website/src/main.js");
  const config = read("website/vite.config.js");
  const architecture = read("website/docs/architecture.html");
  const manifest = JSON.parse(read("docs/pseudocode/manifest.json"));

  assert.match(shell, /import\.meta\.env\.DEV/);
  assert.match(shell, /dblclick/);
  assert.match(shell, /data-pseudocode-draft/);
  assert.match(shell, /data-pseudocode-save/);
  assert.match(shell, /data-pseudocode-cancel/);
  assert.match(shell, /markdownByFile/);
  assert.match(shell, /pseudocodeSavePath/);
  assert.equal(manifest.at(-1).file, "perception.md");
  assert.match(read("docs/pseudocode/perception.md"), /legend_inferer\.infer/);
  // The save route moved to FastAPI (workbench/avo_console.py); Vite only proxies it.
  const api = read("workbench/avo_console.py");
  assert.match(config, /'\/__pseudocode\/save'/);
  assert.match(config, /\/api\/workbench\/pseudocode/);
  assert.match(api, /@router\.post\("\/pseudocode"\)/);
  assert.match(api, /Only pseudocode files listed in the manifest can be saved/);
  assert.match(api, /suffix\.lower\(\) != "\.md"/);
  assert.match(architecture, /\.pseudocode-editor textarea/);
  assert.match(architecture, /\.pseudocode-editor-actions/);
});

test("notes page loads and persists its repository Markdown source", () => {
  const html = read("website/notes.html");
  const notes = read("website/src/notes.js");
  const config = read("website/vite.config.js");
  const markdown = read("docs/notes/workbench-notes.md");

  assert.match(html, /<title>Notes/);
  assert.match(html, /data-notes-editor/);
  assert.match(html, /data-notes-save/);
  assert.match(html, /data-notes-document="todo"/);
  assert.match(html, /data-notes-document="benchmark"/);
  assert.match(notes, /\/docs\/notes\/workbench-notes\.md/);
  assert.match(notes, /\/docs\/notes\/todo\.md/);
  assert.match(notes, /\/docs\/notes\/benchmark-positioning\.md/);
  assert.match(notes, /\/__notes\/save/);
  assert.match(notes, /import\.meta\.env\.DEV/);
  assert.match(notes, /makeSectionsCollapsible/);
  const api = read("workbench/avo_console.py");
  assert.match(config, /'\/__notes\/save'/);
  assert.match(config, /\/api\/workbench\/notes/);
  assert.match(api, /NOTES_FILES = \{"workbench-notes\.md", "todo\.md", "benchmark-positioning\.md"\}/);
  assert.match(config, /notes:\s*resolve\(__dirname, 'notes\.html'\)/);
  assert.match(markdown, /# Project Notes/);
  assert.match(markdown, /## Rule Induction/);
  assert.match(markdown, /## Demo Flow/);
  assert.match(read("docs/notes/todo.md"), /# Todo/);
  assert.match(read("docs/notes/benchmark-positioning.md"), /# PuzzleScript World Benchmark/);
  assert.match(read("docs/notes/benchmark-positioning.md"), /Comparison with ARC-AGI-3/);
  assert.match(read("docs/notes/benchmark-positioning.md"), /complete model-plus-harness system/);
  assert.match(read("docs/notes/benchmark-positioning.md"), /Comparison with PuzzleJAX/);
});

test("home page provides the live main-client workbench", () => {
  const html = read("website/index.html");
  const workbench = read("website/src/workbench.js");
  const config = read("website/vite.config.js");

  assert.match(html, /<title>Workbench<\/title>/);
  assert.match(html, /<h1>Workbench<\/h1>/);
  assert.doesNotMatch(html, /Professor Demo Workbench/);
  assert.match(html, /data-run-start/);
  assert.match(html, /data-run-stop/);
  assert.match(html, /name="memory-mode"/);
  assert.match(html, /data-view-tab="settings"/);
  assert.match(html, /data-view-tab="prompts"/);
  assert.match(html, /data-prompt-editor/);
  assert.match(html, /data-prompt-save/);
  assert.match(html, /name="backend"/);
  assert.match(html, /data-max-steps/);
  assert.match(html, /LLM provider/);
  assert.match(html, /OpenRouter/);
  assert.match(html, /data-model/);
  assert.match(html, /anthropic\/claude-opus-4\.8/);
  assert.match(html, /openai\/gpt-5\.6-luna/);
  assert.match(html, /x-ai\/grok-4\.5/);
  assert.match(html, /xiaomi\/mimo-v2\.5/);
  assert.match(html, /data-reasoning-effort/);
  assert.match(html, /data-openrouter-state/);
  assert.match(html, /type="text"[^>]*data-openrouter-key/);
  assert.match(html, /data-openrouter-save/);
  assert.match(workbench, /\/api\/workbench/);
  assert.match(workbench, /setInterval\(poll, 500\)/);
  assert.match(workbench, /request\('\/runs\/current'/);
  assert.match(workbench, /restoreCurrentRun/);
  assert.match(workbench, /request\('\/models'\)/);
  assert.match(workbench, /request\('\/prompts'/);
  assert.match(workbench, /method: 'PUT'/);
  assert.match(workbench, /request\('\/openrouter\/status'/);
  assert.match(workbench, /request\('\/openrouter\/key'/);
  assert.match(workbench, /natural_rules/);
  assert.match(workbench, /logical_rules/);
  assert.match(workbench, /renderReplayRules/);
  assert.match(workbench, /renderReplayPrediction/);
  assert.match(workbench, /transitionNumber/);
  assert.match(html, /Rules at this point/);
  assert.match(html, /Prediction vs observed/);
  assert.match(html, /data-replay-rule-tab="logical"/);
  assert.match(config, /workbenchApiPort/);
  assert.match(config, /'\/api\/workbench'/);
});

test("optimal path experiment exposes live BFS progress and rendered replay", () => {
  const html = read("website/experiments/optimal-path.html");
  const client = read("website/src/optimal-path.js");
  const config = read("website/vite.config.js");
  const shell = read("website/src/main.js");

  assert.match(html, /<h1>Optimal Path<\/h1>/);
  assert.match(html, /data-optimal-game/);
  assert.match(html, /data-time-progress/);
  assert.match(html, /data-depth/);
  assert.match(html, /data-level-progress/);
  assert.match(html, /whole-game path found/);
  assert.match(html, /data-result-failure/);
  assert.match(html, /data-replay-image/);
  assert.match(client, /\/api\/optimal-path/);
  assert.match(client, /setInterval\(poll, 500\)/);
  assert.match(client, /restoreCurrentRun/);
  assert.match(client, /renderedFrame/);
  assert.match(config, /'\/api\/optimal-path'/);
  assert.match(config, /optimalPath: resolve/);
  assert.match(shell, /label: 'Optimal path'/);
});

test("thinking comparison is trace-first and loads source artifacts through routes", () => {
  const html = read("website/experiments/thinking-comparison.html");
  const traces = read("website/experiments/thinking-traces.js");

  assert.match(html, /trace-viewer/);
  assert.match(html, /trace-condition-list/);
  assert.match(html, /Kimi thinking/);
  assert.match(html, /thinking-traces\.js/);
  assert.doesNotMatch(html, /<h2>Conditions<\/h2>/);
  assert.match(traces, /\/experiments\/thinking-comparison\/kimi-thinking\/log\.txt/);
  assert.match(traces, /fetch\(path\)/);
});
