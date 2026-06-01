const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { Parser, GameEngine, EmptyGameEngineHandler } = require('puzzlescript');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const GAMES_DIR = path.join(REPO_ROOT, 'puzzlescript_interface', 'games');
const DATASET_DIR = path.join(REPO_ROOT, 'dataset');
const EXCLUDED_GAMES_PATH = path.join(DATASET_DIR, 'excluded_games.json');
const DEFAULT_SCALE = 10;

class CaptureHandler extends EmptyGameEngineHandler {
    constructor() {
        super();
        this.currentLevel = 0;
        this.currentCells = null;
        this.currentMessage = null;
    }

    onLevelLoad(level) {
        this.currentLevel = level;
        this.currentMessage = null;
    }

    onLevelChange(level, cells, message) {
        this.currentLevel = level;
        this.currentCells = cells || null;
        this.currentMessage = message || null;
    }
}

class AsciiRenderer {
    constructor(gameData) {
        this.renderList = this.buildRenderList(gameData);
    }

    buildRenderList(gameData) {
        const list = [];
        for (const tile of gameData.legends || []) {
            const key = tile.spriteNameOrLevelChar;
            if (key && key.length === 1) {
                list.push({ key, tile });
            }
        }

        list.sort((a, b) => {
            const aIsOr = a.tile.isOr ? a.tile.isOr() : false;
            const bIsOr = b.tile.isOr ? b.tile.isOr() : false;
            if (aIsOr && !bIsOr) {
                return 1;
            }
            if (!aIsOr && bIsOr) {
                return -1;
            }

            return b.tile.getSprites().length - a.tile.getSprites().length;
        });

        return list;
    }

    render(cells) {
        return cells.map(row => row.map(cell => this.cellChar(cell)).join('')).join('\n') + '\n';
    }

    cellChar(cell) {
        for (const sprite of cell.getSprites()) {
            const match = this.renderList.find(entry => {
                const sprites = entry.tile.getSprites();
                if (!sprites.includes(sprite)) {
                    return false;
                }

                const present = cell.getSprites();
                if (entry.tile.isOr && entry.tile.isOr()) {
                    return sprites.some(item => present.includes(item));
                }
                return sprites.every(item => present.includes(item));
            });

            if (match) {
                return match.key;
            }

            if (sprite.getName().toLowerCase() !== 'background') {
                const name = sprite.getName().toLowerCase();
                if (!name.includes('spawn')) {
                    return sprite.getName().charAt(0).toUpperCase();
                }
            }
        }

        return '.';
    }
}

function normalizeSource(source) {
    return source.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

function firstPlayableCells(engine, gameData, handler) {
    let lastError = null;

    for (let index = 0; index < (gameData.levels || []).length; index++) {
        try {
            engine.setLevel(index);
            const cells = engine.getCurrentLevelCells();
            if (cells && cells.length > 0) {
                return {
                    cells,
                    levelIndex: index,
                    message: handler.currentMessage,
                    source: 'engine',
                };
            }
        } catch (error) {
            lastError = error;
            continue;
        }
    }

    for (let index = 0; index < (gameData.levels || []).length; index++) {
        const level = gameData.levels[index];
        if (level && level.type === 'LEVEL_MAP' && level.cells && level.cells.length > 0) {
            return {
                cells: level.cells,
                levelIndex: index,
                message: null,
                source: 'parsed_level',
                engineError: lastError ? lastError.message : null,
            };
        }
    }

    throw new Error(lastError ? lastError.message : 'No playable level cells found');
}

function playerCell(gameData, cells) {
    let playerTile = null;
    try {
        playerTile = gameData.getPlayer();
    } catch (error) {
        return null;
    }

    const flatCells = cells.flat();
    try {
        const playerCells = playerTile.getCellsThatMatch(flatCells);
        if (playerCells.size === 1) {
            return [...playerCells][0];
        }
    } catch (error) {
        // Parsed level-map cells are legend tiles, not runtime Cell objects.
    }

    let found = null;
    for (let row = 0; row < cells.length; row++) {
        for (let col = 0; col < cells[row].length; col++) {
            const sprites = getSprites(cells[row][col]);
            if (sprites.some(sprite => playerTile.getSprites().includes(sprite))) {
                if (found) {
                    return null;
                }
                found = { rowIndex: row, colIndex: col };
            }
        }
    }
    return found;
}

function visibleWindow(gameData, cells) {
    const height = cells.length;
    const width = cells[0].length;
    const player = playerCell(gameData, cells);
    const flickscreen = gameData.metadata.flickscreen;
    const zoomscreen = gameData.metadata.zoomscreen;

    if (flickscreen) {
        const screenWidth = Math.min(flickscreen.width, width);
        const screenHeight = Math.min(flickscreen.height, height);
        const left = player
            ? player.colIndex - (player.colIndex % screenWidth)
            : 0;
        const top = player
            ? player.rowIndex - (player.rowIndex % screenHeight)
            : 0;
        return {
            left: Math.min(left, Math.max(width - screenWidth, 0)),
            top: Math.min(top, Math.max(height - screenHeight, 0)),
            width: screenWidth,
            height: screenHeight,
        };
    }

    if (zoomscreen) {
        const screenWidth = Math.min(zoomscreen.width, width);
        const screenHeight = Math.min(zoomscreen.height, height);
        const centeredLeft = player ? player.colIndex - Math.floor(screenWidth / 2) : 0;
        const centeredTop = player ? player.rowIndex - Math.floor(screenHeight / 2) : 0;
        return {
            left: clamp(centeredLeft, 0, Math.max(width - screenWidth, 0)),
            top: clamp(centeredTop, 0, Math.max(height - screenHeight, 0)),
            width: screenWidth,
            height: screenHeight,
        };
    }

    return { left: 0, top: 0, width, height };
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function colorToRgba(color) {
    if (!color || color.isTransparent()) {
        return null;
    }

    const rgb = color.toRgb();
    return {
        r: rgb.r,
        g: rgb.g,
        b: rgb.b,
        a: rgb.a === null ? 1 : rgb.a,
    };
}

function blend(front, back) {
    if (!front) {
        return back;
    }
    if (!back || front.a >= 1) {
        return front;
    }

    const a = front.a + back.a * (1 - front.a);
    if (a <= 0) {
        return null;
    }

    return {
        r: Math.round((front.r * front.a + back.r * back.a * (1 - front.a)) / a),
        g: Math.round((front.g * front.a + back.g * back.a * (1 - front.a)) / a),
        b: Math.round((front.b * front.a + back.b * back.a * (1 - front.a)) / a),
        a,
    };
}

function pixelsForCell(gameData, cell, spriteHeight, spriteWidth) {
    const sprites = getSprites(cell).filter(sprite => !sprite.isTransparent());
    const magicBackground = gameData.getMagicBackgroundSprite();
    if (magicBackground && !sprites.includes(magicBackground)) {
        sprites.push(magicBackground);
    }

    const out = Array.from({ length: spriteHeight }, () =>
        Array.from({ length: spriteWidth }, () => null)
    );

    for (let spriteIndex = sprites.length - 1; spriteIndex >= 0; spriteIndex--) {
        const spritePixels = sprites[spriteIndex].getPixels(spriteHeight, spriteWidth);
        for (let y = 0; y < spriteHeight; y++) {
            for (let x = 0; x < spriteWidth; x++) {
                out[y][x] = blend(colorToRgba(spritePixels[y][x]), out[y][x]);
            }
        }
    }

    const fallback = colorToRgba(gameData.metadata.backgroundColor) || {
        r: 0,
        g: 0,
        b: 0,
        a: 1,
    };

    for (let y = 0; y < spriteHeight; y++) {
        for (let x = 0; x < spriteWidth; x++) {
            if (!out[y][x]) {
                out[y][x] = fallback;
            }
        }
    }

    return out;
}

function getSprites(cellOrTile) {
    if (!cellOrTile || typeof cellOrTile.getSprites !== 'function') {
        return [];
    }
    return cellOrTile.getSprites();
}

function renderImage(gameData, cells, scale) {
    const { spriteHeight, spriteWidth } = gameData.getSpriteSize();
    const viewport = visibleWindow(gameData, cells);
    const imageWidth = viewport.width * spriteWidth * scale;
    const imageHeight = viewport.height * spriteHeight * scale;
    const rgba = Buffer.alloc(imageWidth * imageHeight * 4);

    for (let row = 0; row < viewport.height; row++) {
        for (let col = 0; col < viewport.width; col++) {
            const cell = cells[viewport.top + row][viewport.left + col];
            const pixels = pixelsForCell(gameData, cell, spriteHeight, spriteWidth);

            for (let spriteY = 0; spriteY < spriteHeight; spriteY++) {
                for (let spriteX = 0; spriteX < spriteWidth; spriteX++) {
                    const color = pixels[spriteY][spriteX];
                    const baseX = (col * spriteWidth + spriteX) * scale;
                    const baseY = (row * spriteHeight + spriteY) * scale;

                    for (let dy = 0; dy < scale; dy++) {
                        for (let dx = 0; dx < scale; dx++) {
                            const imageX = baseX + dx;
                            const imageY = baseY + dy;
                            const offset = (imageY * imageWidth + imageX) * 4;
                            rgba[offset] = color.r;
                            rgba[offset + 1] = color.g;
                            rgba[offset + 2] = color.b;
                            rgba[offset + 3] = Math.round(color.a * 255);
                        }
                    }
                }
            }
        }
    }

    return { width: imageWidth, height: imageHeight, rgba, viewport };
}

function pngChunk(type, data) {
    const typeBuffer = Buffer.from(type, 'ascii');
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length, 0);

    const crcInput = Buffer.concat([typeBuffer, data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(crcInput), 0);

    return Buffer.concat([length, typeBuffer, data, crc]);
}

function writePng(filePath, image) {
    const header = Buffer.alloc(13);
    header.writeUInt32BE(image.width, 0);
    header.writeUInt32BE(image.height, 4);
    header[8] = 8;
    header[9] = 6;
    header[10] = 0;
    header[11] = 0;
    header[12] = 0;

    const stride = image.width * 4;
    const raw = Buffer.alloc((stride + 1) * image.height);
    for (let y = 0; y < image.height; y++) {
        raw[y * (stride + 1)] = 0;
        image.rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
    }

    const png = Buffer.concat([
        Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
        pngChunk('IHDR', header),
        pngChunk('IDAT', zlib.deflateSync(raw)),
        pngChunk('IEND', Buffer.alloc(0)),
    ]);

    fs.writeFileSync(filePath, png);
}

function crc32(buffer) {
    let crc = 0xffffffff;
    for (const byte of buffer) {
        crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
}

const CRC_TABLE = (() => {
    const table = [];
    for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) {
            c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        }
        table[n] = c >>> 0;
    }
    return table;
})();

function gameDirs() {
    return fs.readdirSync(GAMES_DIR, { withFileTypes: true })
        .filter(entry => entry.isDirectory())
        .map(entry => entry.name)
        .filter(name => fs.existsSync(path.join(GAMES_DIR, name, 'script.txt')))
        .sort();
}

function loadExcludedGames() {
    if (!fs.existsSync(EXCLUDED_GAMES_PATH)) {
        return new Set();
    }

    const data = JSON.parse(fs.readFileSync(EXCLUDED_GAMES_PATH, 'utf8'));
    const entries = Array.isArray(data.excluded_games) ? data.excluded_games : [];
    return new Set(entries.map(excludedGameId).filter(Boolean));
}

function excludedGameId(entry) {
    return typeof entry === 'string' ? entry : entry && entry.game;
}

function exportGame(gameName, scale) {
    const sourcePath = path.join(GAMES_DIR, gameName, 'script.txt');
    const outDir = path.join(DATASET_DIR, gameName);
    fs.mkdirSync(outDir, { recursive: true });

    const source = normalizeSource(fs.readFileSync(sourcePath, 'utf8'));
    const { data } = Parser.parse(source);
    const handler = new CaptureHandler();
    const engine = new GameEngine(data, handler);
    const frame = firstPlayableCells(engine, data, handler);
    const { cells, levelIndex, message, engineError } = frame;
    const ascii = new AsciiRenderer(data).render(cells);
    const image = renderImage(data, cells, scale);

    fs.writeFileSync(path.join(outDir, 'ascii.txt'), ascii, 'utf8');
    writePng(path.join(outDir, 'screenshot.png'), image);

    return {
        game: gameName,
        status: 'ok',
        level_index: levelIndex,
        source: frame.source,
        engine_error: engineError || null,
        message: message || null,
        board_width: cells[0].length,
        board_height: cells.length,
        viewport: image.viewport,
        screenshot: path.relative(REPO_ROOT, path.join(outDir, 'screenshot.png')).replace(/\\/g, '/'),
        ascii: path.relative(REPO_ROOT, path.join(outDir, 'ascii.txt')).replace(/\\/g, '/'),
    };
}

function parseArgs() {
    const args = process.argv.slice(2);
    const options = {
        games: null,
        limit: null,
        scale: DEFAULT_SCALE,
    };

    for (let i = 0; i < args.length; i++) {
        const arg = args[i];
        if (arg === '--game') {
            options.games = [args[++i]];
        } else if (arg === '--games') {
            options.games = args[++i].split(',').map(item => item.trim()).filter(Boolean);
        } else if (arg === '--limit') {
            options.limit = Number(args[++i]);
        } else if (arg === '--scale') {
            options.scale = Number(args[++i]);
        }
    }

    if (!Number.isInteger(options.scale) || options.scale < 1) {
        throw new Error('--scale must be a positive integer');
    }
    if (options.limit !== null && (!Number.isInteger(options.limit) || options.limit < 1)) {
        throw new Error('--limit must be a positive integer');
    }

    return options;
}

function main() {
    const options = parseArgs();
    fs.mkdirSync(DATASET_DIR, { recursive: true });

    const excludedGames = loadExcludedGames();
    const candidateGames = options.games || gameDirs();
    const selectedGames = options.games
        ? candidateGames
        : candidateGames.filter(gameName => !excludedGames.has(gameName));
    const games = options.limit ? selectedGames.slice(0, options.limit) : selectedGames;
    const manifest = [];

    for (const gameName of games) {
        try {
            const row = exportGame(gameName, options.scale);
            manifest.push(row);
            console.log(`[ok] ${gameName}`);
        } catch (error) {
            manifest.push({
                game: gameName,
                status: 'error',
                error: error.message,
            });
            console.log(`[error] ${gameName}: ${error.message}`);
        }
    }

    const summary = {
        total: manifest.length,
        ok: manifest.filter(row => row.status === 'ok').length,
        errors: manifest.filter(row => row.status === 'error').length,
        scale: options.scale,
        games: manifest,
    };
    fs.writeFileSync(
        path.join(DATASET_DIR, 'manifest.json'),
        JSON.stringify(summary, null, 2) + '\n',
        'utf8'
    );
    console.log(`Wrote ${summary.ok}/${summary.total} games to ${path.relative(REPO_ROOT, DATASET_DIR)}`);
}

main();
