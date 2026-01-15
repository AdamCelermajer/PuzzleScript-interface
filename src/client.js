// client.js - PuzzleScript Thin Client
const axios = require('axios');
const readline = require('readline');

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
}

async function main() {
    const client = new PuzzleScriptClient();
    try {
        const gameName = process.argv[2] || 'sokoban-basic';
        console.log(`📤 Initializing game "${gameName}"...`);

        try {
            const initResult = await client.init(gameName);
            console.log("✅ Game Initialized. Check Server Console for Board.");
            console.log("Controls: WASD, R (Reset), Z (Undo), Q (Quit)");

            startLoop(client);

        } catch (err) {
            console.error('❌ Init failed:', err.response ? err.response.data : err.message);
            process.exit(1);
        }

    } catch (error) {
        console.error('❌ Error:', error.message);
    }
}

function startLoop(client) {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    const loop = () => {
        rl.question('> ', async (ans) => {
            const cmd = ans.trim().toLowerCase();
            if (cmd === 'q' || cmd === 'quit') {
                console.log('Bye!');
                rl.close();
                process.exit(0);
            }

            if (['w', 'a', 's', 'd', 'up', 'down', 'left', 'right', 'r', 'reset', 'z', 'undo', 'x', ' '].includes(cmd)) {
                try {
                    const result = await client.action(cmd);

                    if (result.message) {
                        console.log(`📣 ${result.message}`);
                    }
                    if (result.status === 'game_complete') {
                        console.log('\n🎉 GAME COMPLETE! 🎉\n');
                        rl.close();
                        process.exit(0);
                    }

                } catch (err) {
                    console.error('Action failed:', err.message);
                }
            } else {
                console.log("Unknown command.");
            }

            loop();
        });
    };

    loop();
}

main();