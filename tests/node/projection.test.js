const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { Parser } = require('puzzlescript');

const {
    buildArcProjectionSpec,
    projectRawGrid,
    countPlayableLevels,
    countCompletedPlayableLevels,
} = require('../../src/puzzlescript_arc_projection');

function parseGame(fileName) {
    const source = fs
        .readFileSync(path.join(__dirname, '..', '..', 'games', fileName), 'utf8')
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');
    return Parser.parse(source).data;
}

test('buildArcProjectionSpec creates a stable versioned mapping for visible legend chars', () => {
    const gameData = parseGame('sokoban-basic.txt');

    const projection = buildArcProjectionSpec(gameData);

    assert.deepEqual(projection.charToInt, {
        '.': 0,
        '#': 1,
        P: 2,
        '*': 3,
        '@': 4,
        O: 5,
        '?': 6,
    });
    assert.equal(projection.intToChar[0], '.');
    assert.equal(projection.intToChar[6], '?');
});

test('projectRawGrid maps unknown cells to the reserved unknown token instead of creating new ids', () => {
    const projection = {
        charToInt: { '.': 0, '#': 1, '?': 2 },
    };

    const frame = projectRawGrid([
        ['.', '#', 'X'],
        ['#', '.', '.'],
    ], projection);

    assert.deepEqual(frame, [
        [0, 1, 2],
        [1, 0, 0],
    ]);
});

test('countPlayableLevels excludes message-only PuzzleScript levels', () => {
    const gameData = parseGame('midas.txt');

    assert.equal(countPlayableLevels(gameData.levels), 15);
});

test('countCompletedPlayableLevels ignores message screens when tracking progress', () => {
    const gameData = parseGame('midas.txt');

    assert.equal(countCompletedPlayableLevels(gameData.levels, 0), 0);
    assert.equal(countCompletedPlayableLevels(gameData.levels, 1), 1);
    assert.equal(countCompletedPlayableLevels(gameData.levels, 2), 1);
    assert.equal(countCompletedPlayableLevels(gameData.levels, 3), 2);
});
