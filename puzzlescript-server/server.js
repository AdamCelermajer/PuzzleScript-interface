const express = require('express');
const { Parser, GameEngine, INPUT_BUTTON, EmptyGameEngineHandler } = require('puzzlescript');

const app = express();
const port = 3000;

app.use(express.json({ limit: '50mb' }));
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    next();
});

const gameSessions = new Map();

class SessionHandler extends EmptyGameEngineHandler {
    constructor() {
        super();
        this.messages = [];
        this.won = false;
        this.currentLevel = 0;
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
    }
}

class Session {
    constructor(id, gameData) {
        this.id = id;
        this.handler = new SessionHandler();
        this.engine = new GameEngine(gameData, this.handler);
        this.renderList = this.buildRenderList(gameData);
        // Start directly
        this.engine.setLevel(0);
    }

    buildRenderList(gameData) {
        // Collect single-char legend entries
        const list = [];
        for (const [key, tile] of Object.entries(gameData.legend)) {
            if (key.length === 1) {
                list.push({ key, tile });
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
        const cells = this.engine.getCurrentLevelCells();
        if (!cells || cells.length === 0) return "Message/Empty Level";

        const height = cells.length;
        const width = cells[0].length;

        let output = '';

        // Flatten logic matching the render list
        // Note: engine.getCurrentLevelCells() returns Cell[][]

        for (let y = 0; y < height; y++) {
            let line = '';
            for (let x = 0; x < width; x++) {
                const cell = cells[y][x];
                let bestChar = '.'; // default background (or space?)

                // Try to find a match in renderList
                // But we want the match that corresponds to the "highest" layer content?
                // Or just the first match in our priority list?

                // Let's trying matching.
                // Problem: 'Background' is in every cell usually. '.' matches Background.
                // If we have Player on Background, both '.' and 'P' match.
                // We want 'P'.
                // So we really want the match that involves the HIGHEST Z-index sprite.

                // Let's search for the highest Z-index sprite in the cell that has a mapping?

                const cellSprites = cell.getSprites(); // Reversed (Front to Back likely)
                // Actually let's verify Z ordering.
                // In engine.js: return sprites.reverse(); // reversed so we render sprites properly
                // This implies Index 0 is the one to draw (Top).

                let found = false;

                // Strategy: Loop through sprites in the cell (Top to Bottom).
                // For each sprite, see if there is a Legend Char that maps preferentially to it?
                // This is hard because Legends are tiles (sets).

                // Alternative Strategy:
                // Check all matching legends.
                // Pick the one that "contains" the highest z-index sprite present in the cell?

                const matchingLegends = this.renderList.filter(item => item.tile.matchesCell(cell));

                if (matchingLegends.length > 0) {
                    // Sort matches by the max collision layer of their constituent sprites?
                    // GameLegendTile.getCollisionLayer() exists but might be unreliable for mixed.
                    // Let's look at the sprites in the match.

                    // We want the legend that represents the visible top-most thing.
                    // cellSprites[0] is the top-most sprite.

                    // Find a legend that includes cellSprites[0]
                    const topSprite = cellSprites[0];
                    if (topSprite) {
                        const directMatch = matchingLegends.find(item => {
                            // Does this legend tile include this sprite?
                            // item.tile.getSprites() returns list of sprites in the legend
                            return item.tile.getSprites().includes(topSprite);
                        });
                        if (directMatch) {
                            bestChar = directMatch.key;
                            found = true;
                        }
                    }

                    if (!found) {
                        // Fallback: just pick the first one (maybe an OR covering something else)
                        // Or maybe the one with highest declared order?
                        bestChar = matchingLegends[0].key;

                        // Special case: Background usually '.'
                        // If we have something else, show it.
                        // If matchingLegends has non-background, pick it.
                        const nonBg = matchingLegends.find(m => m.key !== '.');
                        if (nonBg) bestChar = nonBg.key;
                    }
                }

                line += bestChar;
            }
            output += line + '\n';
        }
        return output;
    }
}

app.post('/init', (req, res) => {
    try {
        const { gameSource } = req.body;
        const { data } = Parser.parse(gameSource);

        const sessionId = Date.now().toString();
        const session = new Session(sessionId, data);
        gameSessions.set(sessionId, session);

        // Construct display legend for client
        const displayLegend = {};
        for (const [k, v] of Object.entries(data.legend)) {
            if (k.length === 1) displayLegend[k] = v.getName ? v.getName() : "Object";
        }

        res.json({
            sessionId,
            board: session.render(),
            level: 1,
            legend: displayLegend,
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
                }

                ticks++;
            } while (session.engine.hasAgain() && ticks < maxTicks);
        }

        if (session.handler.messages.length > 0) {
            message = session.handler.messages.join(' | ');
        }

        if (session.handler.won) {
            status = 'game_complete';
            message = "YOU WIN THE GAME!";
        }

        res.json({
            board: session.render(),
            level: session.engine.currentLevelNum + 1,
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
            level: session.engine.currentLevelNum + 1
        });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(port, () => console.log(`PuzzleEngine (Official) running on ${port}`));
