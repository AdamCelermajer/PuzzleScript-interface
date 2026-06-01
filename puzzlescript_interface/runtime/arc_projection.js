function getDisplayLegend(gameData) {
    const displayLegend = {};
    if (Array.isArray(gameData.legends)) {
        for (const tile of gameData.legends) {
            const key = tile.spriteNameOrLevelChar;
            if (key && key.length === 1 && displayLegend[key] === undefined) {
                displayLegend[key] = key;
            }
        }
        return displayLegend;
    }

    for (const [key] of Object.entries(gameData.legends || {})) {
        if (key.length === 1 && displayLegend[key] === undefined) {
            displayLegend[key] = key;
        }
    }
    return displayLegend;
}

function buildArcProjectionSpec(gameData) {
    const displayLegend = getDisplayLegend(gameData);
    const charToInt = {};
    const intToChar = {};
    let nextValue = 0;
    const maxDistinctVisibleValues = 15;
    const overflowValue = 15;
    const overflowChars = [];

    if (displayLegend['.'] !== undefined) {
        charToInt['.'] = nextValue;
        intToChar[nextValue] = '.';
        nextValue += 1;
    }

    for (const key of Object.keys(displayLegend)) {
        if (key === '.' || charToInt[key] !== undefined) {
            continue;
        }
        if (nextValue < maxDistinctVisibleValues) {
            charToInt[key] = nextValue;
            intToChar[nextValue] = key;
            nextValue += 1;
        } else {
            charToInt[key] = overflowValue;
            overflowChars.push(key);
        }
    }

    const unknownValue = overflowChars.length > 0 ? overflowValue : nextValue;
    charToInt['?'] = unknownValue;
    intToChar[unknownValue] = '?';

    return {
        charToInt,
        intToChar,
        compressed: overflowChars.length > 0,
        overflowChars,
    };
}

function projectRawGrid(grid, projection) {
    const unknownValue = projection.charToInt['?'];
    return grid.map(row => row.map(char => projection.charToInt[char] ?? unknownValue));
}

function countPlayableLevels(levels) {
    return levels.filter(level => level && level.type === 'LEVEL_MAP' && Array.isArray(level.cells) && level.cells.length > 0).length;
}

function countCompletedPlayableLevels(levels, currentLevelIndex) {
    return levels
        .slice(0, Math.max(currentLevelIndex, 0))
        .filter(level => level && level.type === 'LEVEL_MAP' && Array.isArray(level.cells) && level.cells.length > 0)
        .length;
}

module.exports = {
    buildArcProjectionSpec,
    projectRawGrid,
    countPlayableLevels,
    countCompletedPlayableLevels,
};
