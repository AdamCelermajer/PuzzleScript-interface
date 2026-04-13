const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const SERVER_PORT = 3100;
const SERVER_URL = `http://127.0.0.1:${SERVER_PORT}`;
const ROOT = path.join(__dirname, '..', '..');
const SERVER_ENTRY = 'puzzlescript_interface/runtime/server.js';
const RUNTIME_DIR = path.join(ROOT, 'puzzlescript_interface', '.runtime');
const HISTORY_PATH = path.join(RUNTIME_DIR, 'game_history.jsonl');
const LEGACY_HISTORY_PATH = path.join(ROOT, 'game_history.jsonl');

async function waitForServer(url, timeoutMs = 15000) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
        try {
            const response = await fetch(url, { method: 'GET' });
            if (response.status === 404 || response.status === 200) {
                return;
            }
        } catch (error) {
            // Keep polling until the server is ready.
        }
        await new Promise(resolve => setTimeout(resolve, 250));
    }
    throw new Error('PuzzleScript server did not start in time');
}

function startServer() {
    return spawn('node', [SERVER_ENTRY], {
        cwd: ROOT,
        env: { ...process.env, PORT: String(SERVER_PORT) },
        stdio: 'ignore',
    });
}

test('init counts only playable PuzzleScript levels in win_levels', async () => {
    const server = startServer();

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const response = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'ps_midas-v1' }),
        });

        assert.equal(response.status, 200);
        const body = await response.json();
        assert.equal(body.win_levels, 15);
        assert.deepEqual(body.available_actions, ['RESET', 'ACTION1', 'ACTION2', 'ACTION3', 'ACTION4', 'ACTION5', 'ACTION7']);
    } finally {
        server.kill();
    }
});

test('ACTION7 undoes the previous move', async () => {
    const server = startServer();

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const initResponse = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'ps_sokoban_basic-v1' }),
        });
        const initBody = await initResponse.json();

        const movedResponse = await fetch(`${SERVER_URL}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: initBody.sessionId, action: 'ACTION4' }),
        });
        const movedBody = await movedResponse.json();

        const undoResponse = await fetch(`${SERVER_URL}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: initBody.sessionId, action: 'ACTION7' }),
        });
        const undoBody = await undoResponse.json();

        assert.notDeepEqual(movedBody.frame.at(-1), initBody.frame.at(-1));
        assert.deepEqual(undoBody.frame.at(-1), initBody.frame.at(-1));
    } finally {
        server.kill();
    }
});

test('RESET returns the updated board immediately', async () => {
    const server = startServer();

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const initResponse = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'ps_sokoban_basic-v1' }),
        });
        const initBody = await initResponse.json();

        const movedResponse = await fetch(`${SERVER_URL}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: initBody.sessionId, action: 'ACTION4' }),
        });
        const movedBody = await movedResponse.json();

        const resetResponse = await fetch(`${SERVER_URL}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: initBody.sessionId, action: 'RESET' }),
        });
        const resetBody = await resetResponse.json();

        assert.notDeepEqual(movedBody.frame.at(-1), initBody.frame.at(-1));
        assert.notDeepEqual(resetBody.frame.at(-1), movedBody.frame.at(-1));
        assert.deepEqual(resetBody.frame.at(-1), initBody.frame.at(-1));
    } finally {
        server.kill();
    }
});

test('history is written under puzzlescript_interface/.runtime', async () => {
    fs.rmSync(RUNTIME_DIR, { recursive: true, force: true });
    fs.rmSync(LEGACY_HISTORY_PATH, { force: true });
    const server = startServer();

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const response = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'ps_sokoban_basic-v1' }),
        });

        assert.equal(response.status, 200);
        assert.equal(fs.existsSync(HISTORY_PATH), true);
        assert.equal(fs.existsSync(LEGACY_HISTORY_PATH), false);
    } finally {
        server.kill();
    }
});
