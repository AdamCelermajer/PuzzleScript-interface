// client.js - PuzzleScript Client
const axios = require('axios');
const readline = require('readline');
const fs = require('fs');
const path = require('path');

class PuzzleScriptClient {
    constructor(serverUrl = 'http://localhost:3000') {
        this.serverUrl = serverUrl;
        this.sessionId = null;
    }

    async init(gameName) {
        const response = await axios.post(`${this.serverUrl}/init`, {
            gameName: gameName
        });
        this.sessionId = response.data.sessionId;
        return response.data;
    }

    async action(action) {
        if (!this.sessionId) throw new Error("No active session");
        const response = await axios.post(`${this.serverUrl}/action`, {
            sessionId: this.sessionId,
            action: action.toLowerCase()
        });
        return response.data;
    }

    async observe() {
        if (!this.sessionId) throw new Error("No active session");
        // Using GET as requested/designed
        const response = await axios.get(`${this.serverUrl}/observe`, {
            params: { sessionId: this.sessionId }
        });
        return response.data;
    }

    displayBoard(result, legend = null, actionName = null) {
        // console.clear(); // Removed per request to show history

        if (legend) {
            this.displayLegend(legend);
        }

        // Print Action taken if known
        if (actionName) {
            console.log(`Action: ${actionName}`);
        }

        // Show Level banner only if level changed (or message implies change)
        if (this.lastLevel !== result.level) {
            console.log('\n' + '='.repeat(60));
            console.log(`📍 Level ${result.level}`);
            console.log('='.repeat(60));
            this.lastLevel = result.level;
        }

        if (result.message) {
            console.log(`📣 ${result.message}`);
        }

        // Always print the board
        console.log(result.board);
        console.log('='.repeat(60) + '\n');

        // Don't reprint controls every time to reduce clutter, or keep it minimal?
        console.log('Controls: WASD, R, Z, O, J (JSON), Q');
    }

    displayLegend(legend) {
        if (!legend || Object.keys(legend).length === 0) return;
        console.log('Legend:');
        for (const [key, value] of Object.entries(legend)) {
            console.log(`  ${key} = ${value}`);
        }
        console.log('='.repeat(60) + '\n');
    }
}

async function main() {
    const client = new PuzzleScriptClient();
    try {
        const gameName = process.argv[2] || 'sokoban-basic';
        console.log(`📤 Initializing game "${gameName}"...`);

        try {
            const initResult = await client.init(gameName);
            let currentLegend = initResult.legend; // Store legend

            // displayBoard automatically handles "New Level" banner logic if we reset lastLevel
            client.lastLevel = -1;

            // Show initial state
            client.displayBoard(initResult, currentLegend);

            // Start Loop
            startLoop(client, currentLegend);

        } catch (err) {
            console.error('❌ Init failed:', err.response ? err.response.data : err.message);
            process.exit(1);
        }

    } catch (error) {
        console.error('❌ Error:', error.message);
    }
}

function startLoop(client, currentLegend) {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    const loop = () => {
        rl.question('> ', async (ans) => { // Simpler prompt
            const cmd = ans.trim().toLowerCase();
            if (cmd === 'q' || cmd === 'quit') {
                console.log('Bye!');
                rl.close();
                process.exit(0);
            }

            if (cmd === 'o' || cmd === 'observe') {
                try {
                    const result = await client.observe();
                    // "first the legend then the board"
                    client.displayBoard(result, result.legend, "Observe");
                } catch (err) {
                    console.error('Observe failed:', err.message);
                }
            } else if (cmd === 'j' || cmd === 'json') {
                try {
                    const result = await client.observe();
                    console.log('JSON Output:');
                    console.log(JSON.stringify(result.boardJSON, null, 2));
                    console.log('='.repeat(60) + '\n');
                } catch (err) {
                    console.error('JSON fetch failed:', err.message);
                }
            } else if (['w', 'a', 's', 'd', 'up', 'down', 'left', 'right', 'r', 'reset', 'z', 'undo', 'x', ' '].includes(cmd)) {
                try {
                    const result = await client.action(cmd);
                    client.displayBoard(result, null, cmd); // Pass command name for history logic
                    if (result.status === 'game_complete') {
                        console.log('\n🎉 CONGRATULATIONS! YOU BEAT THE GAME! 🎉\n');
                        rl.close();
                        process.exit(0);
                    }
                } catch (err) {
                    console.error('Action failed:', err.message);
                }
            }

            loop();
        });
    };

    loop();
}

main();