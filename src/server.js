const fs = require('fs');
const express = require('express');
const { Parser, GameEngine, INPUT_BUTTON, EmptyGameEngineHandler } = require('puzzlescript');
const path = require('path');

const app = express();
const port = 3000;

app.use(express.json({ limit: '50mb' }));
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    next();
});

const gameSessions = new Map();

// Logging Helper
function logHistory(sessionId, level, action, board, boardJSON) {
    try {
        const entry = JSON.stringify({
            timestamp: new Date().toISOString(),
            sessionId,
            level,
            action,
            board,
            boardJSON
        });
        fs.appendFileSync('game_history.jsonl', entry + '\n');
    } catch (e) {
        console.error("Logging failed:", e.message);
    }
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

app.post('/init', (req, res) => {
    try {
        let { gameSource, gameName } = req.body;

        if (gameName) {
            const gamePath = path.join(__dirname, '../games', gameName.endsWith('.txt') ? gameName : `${gameName}.txt`);
            if (fs.existsSync(gamePath)) {
                gameSource = fs.readFileSync(gamePath, 'utf8');
            } else {
                return res.status(404).json({ error: `Game "${gameName}" not found.` });
            }
        }

        if (!gameSource) {
            return res.status(400).json({ error: "No gameSource or gameName provided." });
        }

        // Normalize line endings to LF to satisfy strict parser
        const normalizedSource = gameSource.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        const { data } = Parser.parse(normalizedSource);

        const sessionId = Date.now().toString();
        const session = new Session(sessionId, data);
        gameSessions.set(sessionId, session);

        // Pre-render to board so we can log it
        const boardRender = session.render();
        const boardJSON = session.renderJSON();

        // Log Init
        logHistory(sessionId, session.engine.currentLevelNum + 1, "INIT", boardRender, boardJSON);

        // --- SERVER SIDE RENDERING ---
        console.clear();
        console.log(`Game Initialized: ${gameName || 'unknown'}`);
        console.log(boardRender);
        console.log('='.repeat(40));
        // -----------------------------

        res.json({
            sessionId,
            board: boardRender,
            boardJSON,
            level: 1,
            legend: session.getDisplayLegend(),
            totalLevels: data.levels.length
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

        // Map input
        let dir = null;
        const a = action.toLowerCase();
        if (a === 'up' || a === 'w') dir = INPUT_BUTTON.UP;
        else if (a === 'down' || a === 's') dir = INPUT_BUTTON.DOWN;
        else if (a === 'left' || a === 'a') dir = INPUT_BUTTON.LEFT;
        else if (a === 'right' || a === 'd') dir = INPUT_BUTTON.RIGHT;
        else if (a === 'r' || a === 'reset') dir = INPUT_BUTTON.RESTART;
        else if (a === 'z' || a === 'undo') dir = INPUT_BUTTON.UNDO;
        else if (a === ' ' || a === 'action' || a === 'x') dir = INPUT_BUTTON.ACTION;

        session.handler.messages = []; // Clear old messages

        let status = 'playing';
        let message = '';

        if (dir) {
            if (dir === INPUT_BUTTON.RESTART) {
                // Workaround: The built-in RESTART input sometimes crashes with "Unreachable code" in doRestart.
                // We perform a "Hard Restart" by reloading the current level.
                // Note: This wipes the undo stack, but ensures stability.
                session.engine.setLevel(session.engine.currentLevelNum);
            } else {
                session.engine.press(dir);
                // Tick loop to handle animations/AGAIN
                let ticks = 0;
                const maxTicks = 50; // Safety break

                do {
                    const tickResult = await session.engine.tick();

                    // Check result
                    if (tickResult.didWinGame) {
                        status = 'game_complete';
                        message = "YOU WIN!";
                        break;
                    }
                    // didLevelChange is true if advanced level
                    if (tickResult.didLevelChange && !tickResult.didWinGame) {
                        // Level advanced
                        message = "Level Complete";
                        // If message level, it might have already advanced in tick?
                        break; // Stop animating; return the new level (or message) state immediately
                    }

                    ticks++;
                } while (session.engine.hasAgain() && ticks < maxTicks);
            }
        }

        if (session.handler.messages.length > 0) {
            message = session.handler.messages.join(' | ');
        }

        if (session.handler.won) {
            status = 'game_complete';
            message = "YOU WIN THE GAME!";
        }

        const boardRender = session.render();
        const currentLevelInfo = session.engine.currentLevelNum + 1;

        // Log Action
        logHistory(sessionId, currentLevelInfo, action, boardRender, session.renderJSON());

        // --- SERVER SIDE RENDERING ---
        console.clear();
        console.log(`Action: ${action.toUpperCase()}`);
        if (message) console.log(`📢 ${message}`);
        console.log(`Level ${currentLevelInfo}`);
        console.log(boardRender);
        console.log('='.repeat(40));
        // -----------------------------

        res.json({
            board: boardRender,
            boardJSON: session.renderJSON(),
            level: currentLevelInfo,
            message,
            status
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
            board: session.render(),
            boardJSON: session.renderJSON(),
            level: session.engine.currentLevelNum + 1,
            legend: session.getDisplayLegend()
        });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(port, () => console.log(`PuzzleEngine (Official) running on ${port}`));
