const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const path = require('node:path');

const SERVER_PORT = 3100;
const SERVER_URL = `http://127.0.0.1:${SERVER_PORT}`;

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

test('init counts only playable PuzzleScript levels in win_levels', async () => {
    const server = spawn('node', ['src/server.js'], {
        cwd: path.join(__dirname, '..', '..'),
        env: { ...process.env, PORT: String(SERVER_PORT) },
        stdio: 'ignore',
    });

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const response = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'midas' }),
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
    const server = spawn('node', ['src/server.js'], {
        cwd: path.join(__dirname, '..', '..'),
        env: { ...process.env, PORT: String(SERVER_PORT) },
        stdio: 'ignore',
    });

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const initResponse = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'sokoban-basic' }),
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
    const server = spawn('node', ['src/server.js'], {
        cwd: path.join(__dirname, '..', '..'),
        env: { ...process.env, PORT: String(SERVER_PORT) },
        stdio: 'ignore',
    });

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const initResponse = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'sokoban-basic' }),
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
