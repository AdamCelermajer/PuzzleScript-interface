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

    async init(gameSource) {
        const response = await axios.post(`${this.serverUrl}/init`, {
            gameSource: gameSource
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

    displayBoard(result, legend = null) {
        console.clear();
        if (legend) {
            this.displayLegend(legend);
        }
        console.log('\n' + '='.repeat(60));
        console.log(`📍 Level ${result.level}`);
        if (result.message) {
            console.log(`📣 ${result.message}`);
        }
        console.log('='.repeat(60));
        console.log('\n' + result.board + '\n');
        console.log('='.repeat(60) + '\n');
        console.log('Controls: WASD to move, R to reset, O to observe, Q to quit');
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
        console.log('Reading sokoban-basic.txt...');
        const gameSource = fs.readFileSync(path.join(__dirname, 'sokoban-basic.txt'), 'utf8');

        console.log('📤 Initializing game...');
        const initResult = await client.init(gameSource);
        let currentLegend = initResult.legend; // Store legend

        client.displayBoard(initResult);
        client.displayLegend(currentLegend);

        const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout
        });

        const loop = () => {
            rl.question('Action (WASD, O to observe): ', async (ans) => {
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
                        client.displayBoard(result, result.legend);
                    } catch (err) {
                        console.error('Observe failed:', err.message);
                    }
                } else if (['w', 'a', 's', 'd', 'r', 'reset', 'z', 'undo', 'x', ' '].includes(cmd)) {
                    try {
                        const result = await client.action(cmd);
                        client.displayBoard(result);
                        // client.displayLegend(currentLegend); // Removed per request

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

    } catch (error) {
        console.error('❌ Error:', error.message);
    }
}

main();