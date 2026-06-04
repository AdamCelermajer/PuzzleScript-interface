const data = window.GOAL_RECOGNITION_RESULTS;

const state = {
  selectedGameId: null,
  search: "",
  model: "all",
  evidence: "all",
  input: "all",
};

const runSummary = document.querySelector("#run-summary");
const totalGames = document.querySelector("#total-games");
const totalHuman = document.querySelector("#total-human");
const totalLlm = document.querySelector("#total-llm");
const visibleCount = document.querySelector("#visible-count");
const gameList = document.querySelector("#game-list");
const gameDetail = document.querySelector("#game-detail");
const searchInput = document.querySelector("#search-input");
const modelFilter = document.querySelector("#model-filter");
const evidenceFilter = document.querySelector("#evidence-filter");
const inputFilter = document.querySelector("#input-filter");

function init() {
  if (!data) {
    gameDetail.innerHTML = `<div class="empty-state">Missing app-data.js. Run the data builder script first.</div>`;
    return;
  }

  runSummary.textContent = `${data.run_id} from ${data.source_run_dir}`;
  totalGames.textContent = String(data.totals.games);
  totalHuman.textContent = String(data.totals.human_answers);
  totalLlm.textContent = String(data.totals.llm_answers);

  fillSelect(modelFilter, data.filters.models, "All models");
  fillSelect(evidenceFilter, data.filters.evidence_modes, "All evidence");
  fillSelect(inputFilter, data.filters.input_modes, "All inputs");

  searchInput.addEventListener("input", () => {
    state.search = searchInput.value.trim().toLowerCase();
    render();
  });
  modelFilter.addEventListener("change", () => {
    state.model = modelFilter.value;
    render();
  });
  evidenceFilter.addEventListener("change", () => {
    state.evidence = evidenceFilter.value;
    render();
  });
  inputFilter.addEventListener("change", () => {
    state.input = inputFilter.value;
    render();
  });

  state.selectedGameId = filteredGames()[0]?.game_id || data.games[0]?.game_id || null;
  render();
}

function fillSelect(select, values, allLabel) {
  select.replaceChildren(
    option("all", allLabel),
    ...values.map((value) => option(value, value)),
  );
}

function option(value, text) {
  const element = document.createElement("option");
  element.value = value;
  element.textContent = text;
  return element;
}

function render() {
  const games = filteredGames();
  if (!games.some((game) => game.game_id === state.selectedGameId)) {
    state.selectedGameId = games[0]?.game_id || null;
  }

  visibleCount.textContent = `${games.length} ${games.length === 1 ? "game" : "games"}`;
  gameList.replaceChildren(...games.map(renderGameButton));

  const selected = games.find((game) => game.game_id === state.selectedGameId);
  renderDetail(selected);
}

function filteredGames() {
  return data.games.filter((game) => {
    const llmAnswers = filteredLlmAnswers(game);
    if (!llmAnswers.length && game.llm_answers.length) {
      return false;
    }

    if (!state.search) {
      return true;
    }

    const haystack = [
      game.game_id,
      ...game.human_answers.map((answer) => answer.answer_text),
      ...llmAnswers.flatMap((answer) => [
        answer.prediction.goal_guess,
        answer.prediction.win_condition_guess,
        answer.prediction.rationale,
      ]),
    ].join("\n").toLowerCase();
    return haystack.includes(state.search);
  });
}

function filteredLlmAnswers(game) {
  return game.llm_answers.filter((answer) => {
    return (state.model === "all" || answer.model === state.model)
      && (state.evidence === "all" || answer.evidence_mode === state.evidence)
      && (state.input === "all" || answer.input_mode === state.input);
  });
}

function renderGameButton(game) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `game-button${game.game_id === state.selectedGameId ? " active" : ""}`;
  button.addEventListener("click", () => {
    state.selectedGameId = game.game_id;
    render();
  });

  const label = document.createElement("div");
  label.innerHTML = `
    <strong>${escapeHtml(game.game_id)}</strong>
    <span>${game.human_answers.length} human, ${filteredLlmAnswers(game).length} LLM</span>
  `;

  const pill = document.createElement("span");
  pill.className = "count-pill";
  pill.textContent = String(filteredLlmAnswers(game).length);

  button.append(label, pill);
  return button;
}

function renderDetail(game) {
  if (!game) {
    gameDetail.innerHTML = `<div class="empty-state">No games match the current filters.</div>`;
    return;
  }

  const llmAnswers = filteredLlmAnswers(game);
  gameDetail.innerHTML = `
    <div class="detail-header">
      <div>
        <h2>${escapeHtml(game.game_id)}</h2>
        <div class="meta-row">
          <span class="meta-chip">${game.human_answers.length} human answers</span>
          <span class="meta-chip">${llmAnswers.length} visible LLM answers</span>
          <span class="meta-chip">${game.error_count} LLM errors</span>
          <span class="meta-chip">${game.skip_count} skipped rows</span>
        </div>
      </div>
    </div>

    <div class="detail-grid">
      <div class="screenshot-panel">
        <div class="screenshot-wrap">
          ${game.screenshot
            ? `<img src="${escapeHtml(game.screenshot)}" alt="First frame for ${escapeHtml(game.game_id)}">`
            : `<div class="empty-state">No screenshot found.</div>`}
        </div>
        <div class="llm-frame-block">
          <h3>First Frame Seen By LLM</h3>
          ${game.first_llm_frame
            ? `<pre>${escapeHtml(game.first_llm_frame)}</pre>`
            : `<div class="empty-state">No first-frame text found.</div>`}
        </div>
      </div>

      <div class="section-stack">
        <section class="answer-section">
          <h3>Human Answers</h3>
          ${game.human_answers.length
            ? game.human_answers.map(renderHumanAnswer).join("")
            : `<div class="empty-state">No human answer for this game.</div>`}
        </section>

        <section class="answer-section">
          <h3>LLM Answers</h3>
          ${llmAnswers.length
            ? llmAnswers.map(renderLlmAnswer).join("")
            : `<div class="empty-state">No LLM answer matches the current filters.</div>`}
        </section>
      </div>
    </div>
  `;
}

function renderHumanAnswer(answer, index) {
  return `
    <article class="answer-card human">
      <div class="card-title">
        <strong>Human ${index + 1}</strong>
        <span>${escapeHtml(answer.submitted_at || "unknown time")}</span>
      </div>
      <p>${escapeHtml(answer.answer_text || "(empty answer)")}</p>
    </article>
  `;
}

function renderLlmAnswer(answer) {
  const prediction = answer.prediction;
  return `
    <article class="answer-card llm">
      <div class="card-title">
        <strong>${escapeHtml(answer.model)}</strong>
        <span>${escapeHtml(labelFor(answer.evidence_mode))} / ${escapeHtml(labelFor(answer.input_mode))}</span>
      </div>

      <div class="llm-grid">
        ${renderStructuredGuess(prediction)}
        <div class="field-block">
          <span>Confidence</span>
          <p>${formatConfidence(prediction.confidence)}</p>
        </div>
        <div class="field-block">
          <span>Key objects</span>
          ${renderKeyObjects(prediction.key_objects)}
        </div>
        <div class="field-block full">
          <span>Uncertainties</span>
          ${renderList(prediction.uncertainties)}
        </div>
        <div class="field-block full">
          <span>Rationale</span>
          <p>${escapeHtml(prediction.rationale || "(empty)")}</p>
        </div>
      </div>
    </article>
  `;
}

function renderStructuredGuess(prediction) {
  return `
    <div class="field-block full">
      <span>Goal guess</span>
      <p>${escapeHtml(prediction.goal_guess || "(not provided by model)")}</p>
    </div>
    <div class="field-block full">
      <span>Win condition guess</span>
      <p>${escapeHtml(prediction.win_condition_guess || "(not provided separately by model)")}</p>
    </div>
  `;
}

function renderKeyObjects(objects) {
  if (!objects.length) {
    return `<p class="muted">(none)</p>`;
  }
  return `
    <ul>
      ${objects.map((item) => `
        <li><strong>${escapeHtml(String(item.value ?? ""))}</strong>: ${escapeHtml(String(item.role_guess ?? ""))}</li>
      `).join("")}
    </ul>
  `;
}

function renderList(items) {
  if (!items.length) {
    return `<p class="muted">(none)</p>`;
  }
  return `<ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`;
}

function formatConfidence(value) {
  return Number.isFinite(value) ? value.toFixed(2) : "0.00";
}

function labelFor(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init();
