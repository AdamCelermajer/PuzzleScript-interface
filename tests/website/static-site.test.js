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
    "website/experiments/index.html",
    "website/experiments/goal-recognition/index.html",
    "website/experiments/thinking-comparison.html",
    "website/experiments/thinking-traces.js",
    "website/docs/architecture.html",
    "website/src/main.js",
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
