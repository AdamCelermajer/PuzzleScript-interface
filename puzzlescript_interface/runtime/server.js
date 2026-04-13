const fs = require('fs');
const express = require('express');
const { Parser, GameEngine, INPUT_BUTTON, EmptyGameEngineHandler } = require('puzzlescript');
const path = require('path');
const {
    buildArcProjectionSpec,
    projectRawGrid,
    countPlayableLevels,
    countCompletedPlayableLevels,
} = require('./arc_projection');

const app = express();
const port = Number(process.env.PORT || 3000);
const runtimeDir = path.join(__dirname, '..', '.runtime');
const historyPath = path.join(runtimeDir, 'game_history.jsonl');

app.use(express.json({ limit: '50mb' }));
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    next();
});

const gameSessions = new Map();

function getAvailableActions(gameData) {
    const actions = ["RESET", "ACTION1", "ACTION2", "ACTION3", "ACTION4"];
    if (!gameData?.metadata?.noAction) {
        actions.push("ACTION5");
    }
    if (!gameData?.metadata?.noUndo) {
        actions.push("ACTION7");
    }
    return actions;
}

// Logging Helper
function logHistory(sessionId, level, action, board, boardJSON) {
    try {
        fs.mkdirSync(runtimeDir, { recursive: true });
        const entry = JSON.stringify({
            timestamp: new Date().toISOString(),
            sessionId,
            level,
            action,
            board,
            boardJSON
        });
        fs.appendFileSync(historyPath, entry + '\n');
    } catch (e) {
        console.error("Logging failed:", e.message);
    }
}

function formatSideBySide(asciiStr, intGrid) {
    if (!intGrid || intGrid.length === 0) return asciiStr;
    const asciiLines = asciiStr.trim().split('\n');
    const maxLen = Math.max(...asciiLines.map(l => l.length));
    
    let out = [];
    for (let i = 0; i < Math.max(asciiLines.length, intGrid.length); i++) {
        let left = asciiLines[i] || "";
        let right = intGrid[i] ? JSON.stringify(intGrid[i]) : "";
        out.push(left.padEnd(maxLen + 4, ' ') + right);
    }
    return out.join('\n');
}

class SessionHandler extends EmptyGameEngineHandler {
    constructor() {
        super();
        this.messages = [];
        this.won = false;
        this.currentLevel = 0;
        this.currentMessage = null; // Store active level message
    }

    onMessage(msg) {
        // console.log("Message:", msg);
        this.messages.push(msg);
    }

    onWin() {
        // console.log("Game Won!");
        this.won = true;
    }

    onLevelLoad(num, size) {
        this.currentLevel = num;
        // console.log("Level loaded:", num);
        this.won = false;
        this.currentMessage = null; // Clear message on load
    }

    onLevelChange(num, cells, message) {
        this.currentLevel = num;
        if (message) {
            this.currentMessage = message; // Set message if present
        } else {
            this.currentMessage = null;
        }
    }
}

class Session {
    constructor(id, gameData) {
        this.id = id;
        this.gameData = gameData;
        this.handler = new SessionHandler();
        this.engine = new GameEngine(gameData, this.handler);
        this.renderList = this.buildRenderList(gameData);
        this.winLevels = countPlayableLevels(gameData.levels || []);
        this.availableActions = getAvailableActions(gameData);
        this.buildIntMapping();
        // Start directly
        this.engine.setLevel(0);
    }

    buildRenderList(gameData) {
        // Collect single-char legend entries
        // gameData.legends is an array, not a map
        const list = [];
        if (Array.isArray(gameData.legends)) {
            for (const tile of gameData.legends) {
                const key = tile.spriteNameOrLevelChar;
                if (key && key.length === 1) {
                    list.push({ key, tile });
                }
            }
        } else {
            // Fallback if structure changes
            for (const [key, tile] of Object.entries(gameData.legends || {})) {
                if (key.length === 1) list.push({ key, tile });
            }
        }

        // Sort priority: AND > Simple > OR
        // Also respect Z-order? To render the "topmost" matching thing?
        // GameLegendTile doesn't easily expose "primary sprite".
        // Let's stick to type priority for now.
        list.sort((a, b) => {
            const aIsOr = a.tile.isOr();
            const bIsOr = b.tile.isOr();
            // We can check if it's an AND tile by checking class name or behavior, 
            // but isOr() returns false for both Simple and And.
            // We can check equality.

            // Heuristic: specific matches (AND / Simple) should come before broad (OR)
            if (aIsOr && !bIsOr) return 1;
            if (!aIsOr && bIsOr) return -1;

            return 0; // maintain relative order
        });

        // Further refinement: If both are Simple/And, maybe prioritize those covering Top layers?
        // We'll leave that for now.
        return list;
    }

    render() {
        // The engine might be in a message state or simple level state
        let cells = null;
        try {
            cells = this.engine.getCurrentLevelCells();
        } catch (e) {
            // Check if we have a pending message
            if (this.handler.currentMessage) {
                return `MESSAGE:\n\n   ${this.handler.currentMessage}\n\n(Press ACTION to continue)`;
            }
            return "Loading... (or Error: " + e.message + ")";
        }

        if (!cells || cells.length === 0) return "Message/Empty Level";

        const height = cells.length;
        const width = cells[0].length;

        let output = '';

        for (let y = 0; y < height; y++) {
            let line = '';
            for (let x = 0; x < width; x++) {
                const cell = cells[y][x];
                let bestChar = '.'; // default

                // Stack scanning approach:
                // Look at sprites from Top (0) to Bottom.
                // The first one that has a Legend mapping wins.
                // If a Top-level object has NO mapping, we should probably show it as '?'
                // so it doesn't become invisible (like FogOfWar).

                const cellSprites = cell.getSprites(); // [Top, ..., Bottom]

                let found = false;
                for (const sprite of cellSprites) {
                    // Find a legend definition that:
                    // 1. Includes this sprite (so it represents this layer)
                    // 2. actually matches the current cell state (respects AND/OR rules)

                    const match = this.renderList.find(entry => {
                        // Optimization: Check inclusion first
                        const s = entry.tile.getSprites();
                        if (!s.includes(sprite)) return false;

                        // Validation: Check full match logic
                        // We avoid calling matchesCell directly because of "Unreachable code" bug in lib
                        // if (entry.tile.matchesCell) { return entry.tile.matchesCell(cell); } 

                        const isOr = entry.tile.isOr ? entry.tile.isOr() : false;
                        const present = cell.getSprites();

                        if (isOr) {
                            return s.some(es => present.includes(es));
                        } else {
                            return s.every(es => present.includes(es));
                        }
                    });

                    if (match) {
                        bestChar = match.key;
                        found = true;
                        break;
                    } else {
                        // Fallback logic
                        if (sprite === cellSprites[0] && sprite.getName().toLowerCase() !== 'background') {
                            const name = sprite.getName().toLowerCase();
                            // Heuristic: If it has no legend, but it's a "spawn" marker, keep it invisible.
                            if (name.includes('spawn')) {
                                break; // Transparent
                            }

                            // Otherwise, show it as its first letter (e.g. Crate1 -> C)
                            bestChar = sprite.getName().charAt(0).toUpperCase();
                            found = true;
                            break;
                        }
                    }
                }

                if (!found) {
                    // Fallback check: maybe an OR mapping matches the combination?
                    // (Leaving as '.' for now as simple fallback)
                }

                line += bestChar;
            }
            output += line + '\n';
        }
        return output;
    }


    getDisplayLegend() {
        const displayLegend = {};
        const data = this.gameData;
        if (Array.isArray(data.legends)) {
            for (const v of data.legends) {
                const k = v.spriteNameOrLevelChar;
                if (k && k.length === 1) {
                    try {
                        const sprites = v.getSprites();
                        displayLegend[k] = sprites.map(s => s.getName()).join(' + ');
                    } catch (e) {
                        displayLegend[k] = v.getName ? v.getName() : "Object";
                    }
                }
            }
        } else {
            for (const [k, v] of Object.entries(data.legends || {})) {
                if (k.length === 1) displayLegend[k] = v.getName ? v.getName() : "Object";
            }
        }
        return displayLegend;
    }


    buildIntMapping() {
        const displayLegend = this.getDisplayLegend();
        const projection = buildArcProjectionSpec(this.gameData);

        this.charToInt = projection.charToInt;
        const intToName = {};
        for (const [char, value] of Object.entries(this.charToInt)) {
            intToName[value] = displayLegend[char] || (char === '?' ? 'Unknown' : char);
        }
        this.intToName = intToName;
    }

    getCellChar(cell) {
        let bestChar = '.';
        const cellSprites = cell.getSprites();
        let found = false;
        for (const sprite of cellSprites) {
            const match = this.renderList.find(entry => {
                const s = entry.tile.getSprites();
                if (!s.includes(sprite)) return false;
                const isOr = entry.tile.isOr ? entry.tile.isOr() : false;
                const present = cell.getSprites();
                if (isOr) { return s.some(es => present.includes(es)); }
                else { return s.every(es => present.includes(es)); }
            });
            if (match) { bestChar = match.key; found = true; break; }
            else {
                if (sprite === cellSprites[0] && sprite.getName().toLowerCase() !== 'background') {
                    const name = sprite.getName().toLowerCase();
                    if (name.includes('spawn')) break;
                    bestChar = sprite.getName().charAt(0).toUpperCase();
                    found = true;
                    break;
                }
            }
        }
        return bestChar;
    }

    renderRawGrid() {
        let cells = null;
        try { cells = this.engine.getCurrentLevelCells(); } catch(e) { return null; }
        if (!cells || cells.length === 0) return null;
        const height = cells.length;
        const width = cells[0].length;
        const grid = [];
        for (let y = 0; y < height; y++) {
            const row = [];
            for (let x = 0; x < width; x++) {
                row.push(this.getCellChar(cells[y][x]));
            }
            grid.push(row);
        }
        return grid;
    }

    renderIntGrid() {
        const grid = this.renderRawGrid();
        if (!grid) return []; // Fallback empty
        return projectRawGrid(grid, { charToInt: this.charToInt });
    }

    renderJSON() {
        let cells = null;
        try {
            cells = this.engine.getCurrentLevelCells();
        } catch (e) {
            return [];
        }

        if (!cells || cells.length === 0) return [];

        const height = cells.length;
        const width = cells[0].length;
        const result = [];

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const cell = cells[y][x];
                const cellSprites = cell.getSprites();
                const content = cellSprites.map(s => s.getName());
                result.push({ x, y, content });
            }
        }
        return result;
    }
}

function newId(prefix) {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function loadGameSourceByName(gameName) {
    const gamePath = path.join(__dirname, '..', 'games', gameName, 'script.txt');
    if (!fs.existsSync(gamePath)) {
        return null;
    }
    return fs.readFileSync(gamePath, 'utf8');
}

function createSessionFromSource(gameSource) {
    const normalizedSource = gameSource.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const { data } = Parser.parse(normalizedSource);
    const sessionId = newId("ps");
    const session = new Session(sessionId, data);
    gameSessions.set(sessionId, session);
    return { sessionId, session, data };
}

function mapActionToButton(action) {
    const a = String(action || "").toLowerCase();
    if (a === 'action1' || a === 'up' || a === 'w' || a === '1') return INPUT_BUTTON.UP;
    if (a === 'action2' || a === 'down' || a === 's' || a === '2') return INPUT_BUTTON.DOWN;
    if (a === 'action3' || a === 'left' || a === 'a' || a === '3') return INPUT_BUTTON.LEFT;
    if (a === 'action4' || a === 'right' || a === 'd' || a === '4') return INPUT_BUTTON.RIGHT;
    if (a === 'action5' || a === ' ' || a === 'action' || a === 'x' || a === '5') return INPUT_BUTTON.ACTION;
    if (a === 'reset' || a === 'r') return INPUT_BUTTON.RESTART;
    if (a === 'z' || a === 'undo' || a === 'action7' || a === '7') return INPUT_BUTTON.UNDO;
    return null;
}

async function executeAction(session, action) {
    const dir = mapActionToButton(action);
    const framesList = [session.renderIntGrid()];
    let message = "";
    let arcState = "PLAYING";

    if (dir) {
        session.handler.messages = [];
        if (dir === INPUT_BUTTON.RESTART) {
            session.engine.setLevel(session.engine.currentLevelNum);
            framesList.push(session.renderIntGrid());
        } else {
            session.engine.press(dir);
            let ticks = 0;
            const maxTicks = 50;
            do {
                const tickResult = await session.engine.tick();
                framesList.push(session.renderIntGrid());
                if (tickResult.didWinGame) {
                    message = "YOU WIN!";
                    arcState = "WIN";
                    break;
                }
                if (tickResult.didLevelChange && !tickResult.didWinGame) {
                    message = "Level Complete";
                    break;
                }
                ticks++;
            } while (session.engine.hasAgain() && ticks < maxTicks);
        }
    }

    if (session.handler.messages.length > 0) {
        message = session.handler.messages.join(' | ');
    }

    if (session.handler.won) {
        message = "YOU WIN THE GAME!";
        arcState = "WIN";
    }

    const boardRender = session.render();
    const currentLevelInfo = session.engine.currentLevelNum + 1;
    const levelsCompleted = countCompletedPlayableLevels(session.gameData.levels || [], session.engine.currentLevelNum);
    logHistory(session.id, currentLevelInfo, String(action || ""), boardRender, session.renderJSON());

    console.clear();
    console.log(`Action: ${String(action || "").toUpperCase()}`);
    if (message) console.log(`📢 ${message}`);
    console.log(`Level ${currentLevelInfo}`);
    console.log(formatSideBySide(boardRender, session.renderIntGrid()));
    console.log('='.repeat(40));

    return {
        frame: framesList,
        state: arcState,
        levels_completed: levelsCompleted,
        message
    };
}

app.post('/init', (req, res) => {
    try {
        let { gameSource, gameName } = req.body;
        if (gameName) {
            gameSource = loadGameSourceByName(gameName);
            if (!gameSource) {
                return res.status(404).json({ error: `Game "${gameName}" not found.` });
            }
        }
        if (!gameSource) {
            return res.status(400).json({ error: "No gameSource or gameName provided." });
        }

        const { sessionId, session, data } = createSessionFromSource(gameSource);
        const boardRender = session.render();
        const boardJSON = session.renderJSON();
        logHistory(sessionId, session.engine.currentLevelNum + 1, "INIT", boardRender, boardJSON);

        console.clear();
        console.log(`Game Initialized: ${gameName || 'custom-source'}`);
        console.log(formatSideBySide(boardRender, session.renderIntGrid()));
        console.log('='.repeat(40));

        res.json({
            sessionId,
            frame: [session.renderIntGrid()],
            state: "PLAYING",
            levels_completed: 0,
            win_levels: session.winLevels,
            legend: session.intToName,
            available_actions: session.availableActions
        });
    } catch (e) {
        console.error(e);
        res.status(500).json({ error: e.message });
    }
});

app.post('/action', async (req, res) => {
    try {
        const { sessionId, action } = req.body;
        const session = gameSessions.get(sessionId);
        if (!session) return res.status(404).json({ error: "Session not found" });
        const result = await executeAction(session, action);
        res.json({
            frame: result.frame,
            state: result.state,
            levels_completed: result.levels_completed,
            message: result.message,
            legend: session.intToName,
            win_levels: session.winLevels,
            available_actions: session.availableActions
        });
    } catch (e) {
        console.error(e);
        res.status(500).json({ error: e.message });
    }
});

app.get('/observe', (req, res) => {
    try {
        const { sessionId } = req.query;
        const session = gameSessions.get(sessionId);
        if (!session) return res.status(404).json({ error: "Session not found" });
        res.json({
            frame: [session.renderIntGrid()],
            state: session.handler.won ? "WIN" : "PLAYING",
            levels_completed: countCompletedPlayableLevels(session.gameData.levels || [], session.engine.currentLevelNum),
            legend: session.intToName,
            available_actions: session.availableActions
        });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(port, () => console.log(`PuzzleEngine (Official) running on ${port}`));
