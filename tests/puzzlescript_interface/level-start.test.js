const test = require('node:test');
const assert = require('node:assert/strict');
const { app } = require('../../puzzlescript_interface/runtime/server');

async function init(body) {
    const server = app.listen(0);
    try {
        const response = await fetch(`http://127.0.0.1:${server.address().port}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return { status: response.status, body: await response.json() };
    } finally {
        server.close();
    }
}

test('level counts playable levels only, skipping message screens', async () => {
    // IceCrates opens with a message screen: raw index 0 is a message, playable level 2 is raw index 3.
    const first = await init({ gameName: 'ps_icecrates-v1', level: 1 });
    const second = await init({ gameName: 'ps_icecrates-v1', level: 2 });
    assert.equal(first.status, 200);
    assert.equal(first.body.levels_completed, 0);
    assert.equal(second.body.levels_completed, 1);
    assert.equal(second.body.win_levels, 6);
    assert.notDeepEqual(first.body.frame, second.body.frame);
});

test('an out-of-range level or level index is a 400, not a 500', async () => {
    const level = await init({ gameName: 'ps_modality-v1', level: 5 });
    assert.equal(level.status, 400);
    assert.equal(level.body.error, 'level must be between 1 and 4, not 5.');
    assert.equal((await init({ gameName: 'ps_modality-v1', levelIndex: 4 })).status, 400);
    assert.equal((await init({ gameName: 'ps_modality-v1', level: 0 })).status, 400);
});
