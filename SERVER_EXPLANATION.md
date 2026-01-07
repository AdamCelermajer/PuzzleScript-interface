# Server.js Explanation

`server.js` is a Node.js Express application that acts as a generic backend engine for running PuzzleScript games. It handles parsing game files, managing game sessions, enforcing rules (movement, collision, win conditions), and rendering the game state.

## Core Responsibilities

1.  **Game Parsing**: Reads PuzzleScript source text and converts it into structured data (objects, legends, levels, rules).
2.  **Session Management**: Maintains state for multiple concurrent game sessions using a memory-based map.
3.  **Simulation Engine**: Implements the core logic of PuzzleScript, including:
    *   Movement and collision detection.
    *   Object interaction (pushing mechanics).
    *   Win condition verification.
    *   Level progression.
4.  **API Interface**: Provides HTTP endpoints for clients to initialize games and send actions.

## Key Components

### Classes
*   **Game**: Stores static game data (metadata, objects, rules, levels).
*   **Session**: Stores dynamic state for a specific player's run (current level, grid state, dimensions).

### Simulation Functions
*   **`parseGame(source)`**: Parses the raw PuzzleScript text file into a `Game` object. Supports sections like `OBJECTS`, `LEGEND`, `COLLISIONLAYERS`, `WINCONDITIONS`, and `LEVELS`.
*   **`initLevel(game, levelIndex)`**: Creates a `Session` for a specific level, populating the grid based on the level map and legend.
*   **`move(session, action)`**: Processes player input (arrows, WASD). Identifies player objects and attempts to move them.
*   **`tryPush(session, x, y, dx, dy, pusherObj)`**:Recursive function that handles movement physics. It checks if an object can move into a target cell, potentially pushing other objects out of the way (sokoban-style mechanics). *Note: Currently implements rigid body physics but implies a place for more complex Rule implementation.*
*   **`checkWin(session)`**: Evaluates if the current state meets the win conditions (e.g., "All Crate on Target").
*   **`render(session)`**: Converts the internal grid state back into an ASCII/text representation for the client to display.

## API Endpoints

### `POST /init`
Initializes a new game session.
*   **Input**: JSON body with `gameSource` (string content of the PuzzleScript file).
*   **Output**: JSON with `sessionId`, `board` (ASCII render), `level` number, and `legend`.

### `POST /action`
Performs a move in an active session.
*   **Input**: JSON body with `sessionId` and `action` (e.g., "up", "down", "reset").
*   **Output**: JSON with updated `board`, `status` ("playing", "level_complete", "game_complete"), and system messages.
*   **Logic**:
    *   Applies the move.
    *   Checks for win conditions.
    *   Auto-advances to the next level if a level is won.
    *   Handles "Message" levels by skipping them.

### `GET /observe`
Retrieves the current state of a session without modifying it.
*   **Input**: Query parameter `sessionId`.
*   **Output**: JSON with current `board` and `level`.

## Usage
The server runs on port **3000** by default. It is designed to be paired with a lightweight client (like `client.js`) that handles user input and visual output, while offloading all game logic to this server.
