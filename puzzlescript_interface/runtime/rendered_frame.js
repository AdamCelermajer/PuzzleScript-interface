const zlib = require('zlib');
const { BaseUI } = require('puzzlescript');

class HeadlessPixelUI extends BaseUI {
    renderLevelScreen() {}
    setPixel() {}
    checkIfCellCanBeDrawnOnScreen() { return true; }
    getMaxSize() {
        return { columns: Number.MAX_SAFE_INTEGER, rows: Number.MAX_SAFE_INTEGER };
    }
    drawCellsAfterRecentering() {}
    clearScreen() {}
}

function makeCrcTable() {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) {
            c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
        }
        table[n] = c >>> 0;
    }
    return table;
}

const CRC_TABLE = makeCrcTable();

function crc32(buffer) {
    let crc = 0xffffffff;
    for (const byte of buffer) {
        crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
    const typeBuffer = Buffer.from(type, 'ascii');
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length, 0);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
    return Buffer.concat([length, typeBuffer, data, crc]);
}

function encodePng(width, height, rgba) {
    const signature = Buffer.from([
        0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    ]);
    const ihdr = Buffer.alloc(13);
    ihdr.writeUInt32BE(width, 0);
    ihdr.writeUInt32BE(height, 4);
    ihdr[8] = 8; // bit depth
    ihdr[9] = 6; // RGBA
    ihdr[10] = 0; // compression
    ihdr[11] = 0; // filter
    ihdr[12] = 0; // interlace

    const stride = width * 4;
    const raw = Buffer.alloc((stride + 1) * height);
    for (let y = 0; y < height; y++) {
        raw[y * (stride + 1)] = 0;
        rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
    }

    return Buffer.concat([
        signature,
        pngChunk('IHDR', ihdr),
        pngChunk('IDAT', zlib.deflateSync(raw)),
        pngChunk('IEND', Buffer.alloc(0)),
    ]);
}

function rgbaFromColor(color) {
    if (!color || color.isTransparent()) {
        return [0, 0, 0, 0];
    }
    const { r, g, b, a } = color.toRgb();
    return [r, g, b, a === null ? 255 : Math.round(a * 255)];
}

function renderSessionFrame(session) {
    let cells;
    try {
        cells = session.engine.getCurrentLevelCells();
    } catch (e) {
        return null;
    }
    if (!cells || cells.length === 0 || !cells[0] || cells[0].length === 0) {
        return null;
    }

    const ui = new HeadlessPixelUI();
    ui.onGameChange(session.gameData);

    const spriteHeight = ui.SPRITE_HEIGHT;
    const spriteWidth = ui.SPRITE_WIDTH;
    const rows = cells.length;
    const cols = cells[0].length;
    const width = cols * spriteWidth;
    const height = rows * spriteHeight;
    const rgba = Buffer.alloc(width * height * 4);

    for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
            const pixels = ui.getPixelsForCell(cells[row][col]);
            for (let py = 0; py < spriteHeight; py++) {
                for (let px = 0; px < spriteWidth; px++) {
                    const [r, g, b, a] = rgbaFromColor(pixels[py][px]);
                    const index =
                        ((row * spriteHeight + py) * width + (col * spriteWidth + px)) *
                        4;
                    rgba[index] = r;
                    rgba[index + 1] = g;
                    rgba[index + 2] = b;
                    rgba[index + 3] = a;
                }
            }
        }
    }

    const png = encodePng(width, height, rgba);
    return {
        mime_type: 'image/png',
        data_url: `data:image/png;base64,${png.toString('base64')}`,
        width,
        height,
    };
}

module.exports = { encodePng, renderSessionFrame };
