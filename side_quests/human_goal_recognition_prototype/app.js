const K = 3;
const MANIFEST_PATH = '/dataset/manifest.json';
const EXCLUDED_GAMES_PATH = '/dataset/excluded_games.json';

const state = {
  participantId: crypto.randomUUID(),
  games: [],
};

const loading = document.querySelector('#loading');
const survey = document.querySelector('#survey');
const gamesRoot = document.querySelector('#games');
const sampleCount = document.querySelector('#sample-count');
const result = document.querySelector('#result');
const payload = document.querySelector('#payload');
const resampleButton = document.querySelector('#resample-button');

async function main() {
  const [manifest, excludedGames] = await Promise.all([
    loadManifest(),
    loadExcludedGames(),
  ]);
  state.games = sampleGames(activeGames(manifest, excludedGames), K);
  renderSurvey();
}

async function loadManifest() {
  const response = await fetch(MANIFEST_PATH);
  if (!response.ok) {
    throw new Error(`Could not load ${MANIFEST_PATH}: ${response.status}`);
  }
  return response.json();
}

async function loadExcludedGames() {
  const response = await fetch(EXCLUDED_GAMES_PATH);
  if (response.status === 404) {
    return new Set();
  }
  if (!response.ok) {
    throw new Error(`Could not load ${EXCLUDED_GAMES_PATH}: ${response.status}`);
  }

  const data = await response.json();
  const entries = Array.isArray(data.excluded_games) ? data.excluded_games : [];
  return new Set(entries.map(excludedGameId).filter(Boolean));
}

function activeGames(manifest, excludedGames) {
  return manifest.games.filter(game => game.status === 'ok' && !excludedGames.has(game.game));
}

function excludedGameId(entry) {
  return typeof entry === 'string' ? entry : entry?.game;
}

function sampleGames(games, count) {
  const copy = [...games];
  cryptoShuffle(copy);
  return copy.slice(0, count);
}

function cryptoShuffle(items) {
  for (let index = items.length - 1; index > 0; index--) {
    const swapIndex = cryptoRandomInt(index + 1);
    [items[index], items[swapIndex]] = [items[swapIndex], items[index]];
  }
}

function cryptoRandomInt(maxExclusive) {
  const values = new Uint32Array(1);
  const limit = Math.floor(0x100000000 / maxExclusive) * maxExclusive;

  do {
    crypto.getRandomValues(values);
  } while (values[0] >= limit);

  return values[0] % maxExclusive;
}

function renderSurvey() {
  loading.hidden = true;
  survey.hidden = false;
  result.hidden = true;
  sampleCount.textContent = `${state.games.length} / ${K}`;
  gamesRoot.replaceChildren(...state.games.map(renderGameCard));
}

function renderGameCard(game, index) {
  const card = document.createElement('section');
  card.className = 'game-card';
  card.dataset.gameId = game.game;
  card.innerHTML = `
    <div class="game-image-wrap">
      <img class="game-image" src="/${game.screenshot}" alt="First frame screenshot for ${escapeHtml(game.game)}">
    </div>
    <div class="game-form">
      <div class="game-title">
        <h2>Game ${index + 1}</h2>
        <span class="game-index">${escapeHtml(game.game)}</span>
      </div>

      <div class="field">
        <div class="field-label">Is the goal apparent from this first frame?</div>
        <div class="choice-row" role="radiogroup" aria-label="Goal apparent">
          <label class="choice">
            <input type="radio" name="apparent-${index}" value="yes" required>
            Yes
          </label>
          <label class="choice">
            <input type="radio" name="apparent-${index}" value="no">
            No
          </label>
          <label class="choice">
            <input type="radio" name="apparent-${index}" value="unsure">
            Unsure
          </label>
        </div>
      </div>

      <div class="field">
        <div class="field-label">Confidence</div>
        <div class="confidence-row" role="radiogroup" aria-label="Confidence from 1 to 5">
          ${[1, 2, 3, 4, 5].map(value => `
            <label class="choice">
              <input type="radio" name="confidence-${index}" value="${value}" required>
              ${value}
            </label>
          `).join('')}
        </div>
        <div class="helper">1 = very uncertain, 5 = very confident</div>
      </div>

      <div class="field">
        <label class="field-label" for="answer-${index}">Your answer</label>
        <textarea id="answer-${index}" name="answer-${index}" required></textarea>
        <div class="helper" id="answer-help-${index}">Choose whether the goal is apparent.</div>
        <div class="error-text" id="answer-error-${index}" aria-live="polite"></div>
      </div>
    </div>
  `;

  const radios = card.querySelectorAll(`input[name="apparent-${index}"]`);
  const textarea = card.querySelector(`#answer-${index}`);
  const help = card.querySelector(`#answer-help-${index}`);

  radios.forEach(radio => {
    radio.addEventListener('change', () => {
      const apparent = selectedValue(card, `apparent-${index}`);
      if (apparent === 'yes') {
        textarea.placeholder = 'Write the apparent goal of the game.';
        help.textContent = 'Write one concise goal statement.';
      } else {
        textarea.placeholder = 'Write 1-3 hypotheses about the apparent next goal or milestone.';
        help.textContent = 'Use separate lines or short numbered hypotheses.';
      }
    });
  });

  return card;
}

function collectResponses() {
  const submittedAt = new Date().toISOString();

  return state.games.map((game, index) => {
    const card = gamesRoot.querySelector(`[data-game-id="${cssEscape(game.game)}"]`);
    const goalApparent = selectedValue(card, `apparent-${index}`);
    const confidence = selectedValue(card, `confidence-${index}`);
    const answer = card.querySelector(`#answer-${index}`).value.trim();

    return {
      participant_id: state.participantId,
      submitted_at: submittedAt,
      game_id: game.game,
      game_order: index + 1,
      screenshot_url: game.screenshot,
      goal_apparent: goalApparent,
      confidence: Number(confidence),
      answer_text: answer,
    };
  });
}

function validateResponses() {
  let valid = true;

  state.games.forEach((game, index) => {
    const card = gamesRoot.querySelector(`[data-game-id="${cssEscape(game.game)}"]`);
    const apparent = selectedValue(card, `apparent-${index}`);
    const textarea = card.querySelector(`#answer-${index}`);
    const error = card.querySelector(`#answer-error-${index}`);
    const answer = textarea.value.trim();
    error.textContent = '';

    if (!answer) {
      error.textContent = 'This answer is required.';
      valid = false;
      return;
    }

    if (apparent !== 'yes' && hypothesisCount(answer) > 3) {
      error.textContent = 'Please keep this to 1-3 hypotheses.';
      valid = false;
    }
  });

  return valid;
}

function hypothesisCount(answer) {
  const lines = answer
    .split(/\n+/)
    .map(line => line.trim())
    .filter(Boolean);

  if (lines.length > 1) {
    return lines.length;
  }

  const numbered = answer.match(/(^|\s)(1\.|2\.|3\.|1\)|2\)|3\))/g);
  return numbered ? numbered.length : 1;
}

function selectedValue(root, name) {
  return root.querySelector(`input[name="${name}"]:checked`)?.value || '';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function cssEscape(value) {
  if (window.CSS && CSS.escape) {
    return CSS.escape(value);
  }
  return String(value).replace(/["\\]/g, '\\$&');
}

survey.addEventListener('submit', event => {
  event.preventDefault();
  if (!survey.reportValidity() || !validateResponses()) {
    return;
  }

  const rows = collectResponses();
  localStorage.setItem('goal-recognition-prototype-last-submit', JSON.stringify(rows));
  payload.textContent = JSON.stringify(rows, null, 2);
  result.hidden = false;
  result.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

resampleButton.addEventListener('click', async () => {
  loading.hidden = false;
  survey.hidden = true;
  state.participantId = crypto.randomUUID();
  await main();
});

main().catch(error => {
  loading.textContent = error.message;
});
