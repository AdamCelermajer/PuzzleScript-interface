const state = { run: null, monitor: null, timer: null, artifacts: null };
const $ = (id) => document.getElementById(id);

async function api(path, options = {}, auth = null) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (auth === "monitor" && state.run?.monitor_token) {
    headers["X-Monitor-Key"] = state.run.monitor_token;
  } else if (auth === "agent" && state.run?.run_token) {
    headers["X-API-Key"] = state.run.run_token;
  }
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function pct(value, fallback = "—") {
  return value === null || value === undefined
    ? fallback
    : `${Math.round(Number(value) * 100)}%`;
}

function setBar(id, value) {
  $(id).style.width = `${Math.max(0, Math.min(100, Number(value || 0) * 100))}%`;
}

async function loadPage() {
  try {
    const [health, artifacts] = await Promise.all([
      api("/api/benchmark/health"),
      api("/api/benchmark/artifacts"),
    ]);
    state.artifacts = artifacts;
    $("health").className = "server-status ok";
    $("health").innerHTML = `<i></i>${health.games} game artifacts ready`;
    renderArtifacts(artifacts);
    updateSampleLimit();
    restoreRun();
  } catch (error) {
    $("health").className = "server-status error";
    $("health").innerHTML = `<i></i>${escapeHtml(error.message)}`;
  }
}

function renderArtifacts(payload) {
  const summary = payload.summary;
  $("artifact-games").textContent = summary.games;
  $("verified-games").textContent = summary.replay_verified;
  $("rule-probes").textContent = summary.rule_probes;
  $("closeness-games").textContent = summary.closeness_ready_games;
  $("artifact-count").textContent = `(${payload.games.length})`;
  $("scope-note").textContent = payload.scope_note;
  $("artifact-rows").innerHTML = payload.games.map((game) => {
    const probeClass = game.rule_probes === game.requested_rule_probes
      ? "verified"
      : "partial";
    return `<tr>
      <td><code>${escapeHtml(game.game_id)}</code></td>
      <td>${game.artifact_level}</td>
      <td>${game.solution_actions} actions</td>
      <td class="${probeClass}">${game.rule_probes} / ${game.requested_rule_probes}</td>
      <td>${game.rule_probe_levels.join(", ")}</td>
      <td>${game.rule_families}</td>
      <td>${game.closeness_trace_states}</td>
      <td class="${game.replay_verified ? "verified" : "partial"}">${game.replay_verified ? "verified" : "invalid"}</td>
    </tr>`;
  }).join("");
}

function selectedCapabilities() {
  return [...document.querySelectorAll('input[name="capability"]:checked')]
    .map((input) => input.value);
}

function updateSampleLimit() {
  if (!state.artifacts) return;
  const needsRules = selectedCapabilities().includes("rule_learning");
  const maximum = needsRules
    ? state.artifacts.summary.rule_ready_games
    : state.artifacts.summary.games;
  $("sample-size").max = maximum;
  if (Number($("sample-size").value) > maximum) {
    $("sample-size").value = maximum;
  }
}

async function createRun(event) {
  event.preventDefault();
  const button = $("create-run");
  $("form-error").classList.add("hidden");
  const capabilities = selectedCapabilities();
  if (!capabilities.length) {
    showFormError("Select at least one measurement.");
    return;
  }
  button.disabled = true;
  button.textContent = "Creating…";
  try {
    state.run = await api("/api/benchmark/runs", {
      method: "POST",
      body: JSON.stringify({
        capabilities,
        sample_size: Number($("sample-size").value),
        seed: Number($("seed").value),
        representation: {
          rendered_image: $("rendered-image").checked,
          legend: $("legend").checked,
          action_semantics: $("action-semantics").checked,
        },
      }),
    });
    sessionStorage.setItem("puzzlescript-benchmark-run", JSON.stringify(state.run));
    renderRunShell();
    await refreshMonitor();
    startPolling();
    $("run-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showFormError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Create benchmark run";
  }
}

async function runPartialAgent() {
  return runLiveAgent(
    "/api/benchmark/simulated-partial-agent/live?delay_seconds=0.5",
    $("run-partial-agent"),
    "Watch partial agent",
  );
}

async function runRandomAgent() {
  return runLiveAgent(
    "/api/benchmark/random-agent/live?delay_seconds=0.5",
    $("run-random-agent"),
    "Watch random agent",
  );
}

async function runLiveAgent(endpoint, button, label) {
  $("form-error").classList.add("hidden");
  button.disabled = true;
  button.textContent = "Starting...";
  try {
    state.run = await api(endpoint, { method: "POST" });
    sessionStorage.setItem(
      "puzzlescript-benchmark-run",
      JSON.stringify(state.run),
    );
    renderRunShell();
    await refreshMonitor();
    startPolling();
    $("run-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showFormError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function showFormError(message) {
  $("form-error").textContent = message;
  $("form-error").classList.remove("hidden");
}

function restoreRun() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("puzzlescript-benchmark-run"));
    if (!saved?.run_id || !saved?.monitor_token) return;
    state.run = saved;
    renderRunShell();
    refreshMonitor().then(startPolling).catch(() => {
      sessionStorage.removeItem("puzzlescript-benchmark-run");
      state.run = null;
      $("run-panel").classList.add("hidden");
    });
  } catch {
    sessionStorage.removeItem("puzzlescript-benchmark-run");
  }
}

function renderRunShell() {
  const run = state.run;
  $("run-panel").classList.remove("hidden");
  $("run-title").textContent = `Run ${run.run_id.slice(0, 8)}`;
  $("run-id").textContent = run.run_id;
  $("run-token").textContent = run.run_token;
  $("run-status").textContent = run.status;
}

function startPolling() {
  clearInterval(state.timer);
  if (state.run?.status !== "closed") {
    state.timer = setInterval(refreshMonitor, 500);
  }
}

async function refreshMonitor() {
  if (!state.run) return;
  try {
    state.monitor = await api(
      `/api/benchmark/runs/${state.run.run_id}/monitor`,
      {},
      "monitor",
    );
    state.run.status = state.monitor.status;
    sessionStorage.setItem(
      "puzzlescript-benchmark-run",
      JSON.stringify(state.run),
    );
    renderMonitor(state.monitor);
    if (state.monitor.status === "closed" || state.monitor.status === "error") {
      clearInterval(state.timer);
    }
  } catch (error) {
    $("last-update").textContent = `Monitor error: ${error.message}`;
  }
}

function renderMonitor(monitor) {
  $("run-status").textContent = monitor.status;
  $("last-update").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  renderScores(monitor.scores, monitor.environments);
  renderEnvironments(monitor.environments);
  renderCurve(monitor.scores.rule_learning?.learning_curve || []);
  renderTimeline(monitor.events || []);
  $("monitor-json").textContent = JSON.stringify(monitor, null, 2);
}

function renderScores(scores, environments) {
  const rule = scores.rule_learning?.summary;
  const ruleValue = rule?.latest_exact_frame;
  $("rule-score-value").textContent = pct(ruleValue);
  $("rule-edit-f1").textContent = pct(rule?.latest_transition_edit_f1);
  $("rule-coverage").textContent = pct(rule?.latest_coverage);
  $("challenge-count").textContent =
    `${rule?.challenges_submitted || 0} / ${rule?.challenges_created || 0}`;
  setBar("rule-score-bar", ruleValue);

  const close = scores.closeness?.summary;
  const closeValue = close?.mean_level_closeness;
  $("closeness-score-value").textContent = pct(closeValue);
  $("closeness-coverage").textContent = pct(close?.coverage);
  $("closeness-count").textContent =
    `${close?.available_games || 0} / ${close?.total_games || 0}`;
  $("completed-count").textContent = environments.filter((item) => item.completed).length;
  setBar("closeness-score-bar", closeValue);
}

const palette = [
  "#222c26", "#e7e0cf", "#e75d39", "#16867a",
  "#efd34f", "#8f5da8", "#4a7cb7", "#cc8b35",
  "#8eaa6b", "#db8ba6", "#686f9e", "#c2b168",
  "#795548", "#9dada4", "#f4f0e5", "#121714",
];

function board(frame) {
  if (!Array.isArray(frame) || !frame.length || !Array.isArray(frame[0])) {
    return "";
  }
  const cols = frame[0].length;
  const cells = frame.flat().map((value) =>
    `<i class="cell" style="background:${palette[Math.abs(Number(value)) % palette.length]}"></i>`
  ).join("");
  return `<div class="board" style="grid-template-columns:repeat(${cols},1fr)">${cells}</div>`;
}

function renderEnvironments(environments) {
  if (!environments.length) {
    $("environment-grid").innerHTML = '<div class="empty-state">No games in this run.</div>';
    return;
  }
  $("environment-grid").innerHTML = environments.map((env) => {
    const close = env.closeness || {};
    const challenge = env.latest_rule_challenge;
    const latestExact = challenge?.score?.summary?.exact_frame;
    const frame = env.observation?.frame?.at(-1);
    const closeLabel = close.available ? `${Math.round(close.percent)}%` : "unavailable";
    const challengeLabel = !challenge
      ? "No rule challenge"
      : `${challenge.checkpoint.replaceAll("_", " ")} · ${
          challenge.submitted ? `scored ${pct(latestExact)}` : `${challenge.probes.length} probes pending`
        }`;
    return `<article class="environment-card">
      <header>
        <h4>${escapeHtml(env.game_id)}</h4>
        <span>${escapeHtml(env.alias)} · level ${env.artifact_level}</span>
      </header>
      <div class="environment-meta">
        <div><small>Actions</small><strong>${env.actions_used} / ${env.action_budget}</strong></div>
        <div><small>Closeness</small><strong>${closeLabel}</strong></div>
        <div><small>Remaining</small><strong>${close.remaining_actions ?? "—"}</strong></div>
      </div>
      <div class="mini-bar"><i style="width:${close.available ? close.percent : 0}%"></i></div>
      <p class="challenge-note">${escapeHtml(challengeLabel)}</p>
      ${board(frame)}
    </article>`;
  }).join("");
}

function renderCurve(curve) {
  if (!curve.length) {
    $("learning-curve").className = "empty-state";
    $("learning-curve").textContent = "No submitted challenge yet.";
    return;
  }
  $("learning-curve").className = "curve-list";
  $("learning-curve").innerHTML = curve.map((item, index) => `
    <div class="curve-row">
      <span>#${index + 1} · ${escapeHtml(item.submitted ? item.checkpoint.replaceAll("_", " ") : "pending")}</span>
      <div class="curve-track"><i style="width:${item.exact_frame * 100}%"></i></div>
      <strong>${item.submitted ? pct(item.exact_frame) : "—"}</strong>
    </div>
  `).join("");
}

function eventText(event) {
  if (event.type === "rule_challenge_created") {
    return [`Challenge created`, `${event.game_id} · ${event.checkpoint} · ${event.probe_count} probes`, "challenge"];
  }
  if (event.type === "rule_challenge_scored") {
    return [`Challenge scored ${pct(event.score?.exact_frame)}`, `${event.game_id} · ${event.checkpoint}`, "score"];
  }
  if (event.type === "action") {
    const close = event.closeness?.available ? `${Math.round(event.closeness.percent)}% close` : "closeness unavailable";
    return [`${event.action} · action ${event.action_number}`, `${event.game_id} · ${close}`, ""];
  }
  if (event.type === "reset") return ["Level started", event.game_id, ""];
  if (event.type === "run_closed") return ["Run closed", "Final scores saved", "score"];
  return [event.type.replaceAll("_", " "), event.game_id || "", ""];
}

function renderTimeline(events) {
  const recent = [...events].reverse().slice(0, 40);
  $("timeline").innerHTML = recent.length
    ? recent.map((event) => {
        const [title, detail, kind] = eventText(event);
        return `<div class="timeline-item ${kind}">
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(detail)}</span>
        </div>`;
      }).join("")
    : '<div class="empty-state">Waiting for the first RESET.</div>';
}

async function copyConnection() {
  if (!state.run) return;
  const connection = {
    benchmark_url: window.location.origin,
    run_id: state.run.run_id,
    run_token: state.run.run_token,
    game_ids: state.run.game_ids,
    action_budgets: state.run.action_budgets,
  };
  await navigator.clipboard.writeText(JSON.stringify(connection, null, 2));
  const button = $("copy-config");
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = "Copy agent connection"; }, 1400);
}

async function closeRun() {
  if (!state.run || state.run.status === "closed") return;
  const result = await api(
    `/api/benchmark/runs/${state.run.run_id}/close`,
    { method: "POST" },
    "agent",
  );
  state.run.status = "closed";
  state.run.result = result;
  sessionStorage.setItem("puzzlescript-benchmark-run", JSON.stringify(state.run));
  clearInterval(state.timer);
  await refreshMonitor();
}

$("run-form").addEventListener("submit", createRun);
$("run-random-agent").addEventListener("click", runRandomAgent);
$("run-partial-agent").addEventListener("click", runPartialAgent);
document.querySelectorAll('input[name="capability"]').forEach((input) => {
  input.addEventListener("change", updateSampleLimit);
});
$("refresh-run").addEventListener("click", refreshMonitor);
$("copy-config").addEventListener("click", copyConnection);
$("close-run").addEventListener("click", closeRun);
loadPage();
