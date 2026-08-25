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

function getFallbackDisplayChars(gameData) {
    const singleCharTiles = Array.isArray(gameData.legends)
        ? gameData.legends.filter(tile => {
            const key = tile.spriteNameOrLevelChar;
            return key && key.length === 1;
        })
        : Object.entries(gameData.legends || {})
            .filter(([key]) => key.length === 1)
            .map(([, tile]) => tile);
    const directlyRenderable = new Set();
    for (const tile of singleCharTiles) {
        const sprites = tile.getSprites();
        if ((tile.isOr && tile.isOr()) || sprites.length === 1) {
            for (const sprite of sprites) directlyRenderable.add(sprite);
        }
    }

    const fallbackChars = [];
    const objects = Array.isArray(gameData.objects)
        ? gameData.objects
        : Object.values(gameData.objects || {});
    for (const sprite of objects) {
        const name = String(sprite.getName ? sprite.getName() : sprite.name || '');
        const normalized = name.toLowerCase();
        if (!name || normalized === 'background' || normalized.includes('spawn')) continue;
        if (directlyRenderable.has(sprite)) continue;
        const char = name.charAt(0).toUpperCase();
        if (!fallbackChars.includes(char)) fallbackChars.push(char);
    }
    return fallbackChars;
}

function buildArcProjectionSpec(gameData) {
    const displayLegend = getDisplayLegend(gameData);
    const fallbackChars = getFallbackDisplayChars(gameData);
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

    for (const key of fallbackChars) {
        if (charToInt[key] !== undefined) continue;
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
