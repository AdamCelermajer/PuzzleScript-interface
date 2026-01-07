# PuzzleScript Server-Client

A modular architecture for running [PuzzleScript](https://www.puzzlescript.net/) games, separating the game logic (server) from the user interface (client).

## Overview

This project provides a **Node.js Express server** that acts as a game engine for PuzzleScript. It handles:
- Parsing PuzzleScript source files.
- Managing game sessions.
- Enforcing rules, movement, and collision detection.
- Checking win conditions.

A **reference client** (`client.js`) is included to demonstrate how to interact with the server via the command line.

## Prerequisites

- Node.js (v14 or higher recommended)
- npm

## Installation

1. Clone the repository (if applicable) or download the source.
2. Install dependencies:

```bash
npm install
```

## Running the Project

### 1. Start the Server

Start the backend server which listens for game sessions on port 3000.

```bash
npm start
# OR for development with auto-restart:
npm run dev
```

The server runs on `http://localhost:3000`.

### 2. Start the Client

Open a new terminal window and run the client script. By default, it loads `sokoban-basic.txt`.

```bash
npm run client
```

## How to Play

Once the client is running, you will see an ASCII representation of the game board.

**Controls:**
- **W / Up Arrow**: Move Up
- **S / Down Arrow**: Move Down
- **A / Left Arrow**: Move Left
- **D / Right Arrow**: Move Right
- **R**: Restart Level
- **Z / Undo**: Undo last move
- **Space / X**: Action (if applicable)
- **O**: Observe (refresh view)
- **Q**: Quit

## API Documentation

The server exposes a simple REST API for custom clients.

### `POST /init`
Initialize a new game session.
- **Body**: `{ "gameSource": "STRING_CONTENT_OF_PUZZLESCRIPT_FILE" }`
- **Response**: `{ "sessionId": "ID", "board": "ASCII_BOARD", "legend": { ... } }`

### `POST /action`
Perform an action in an active session.
- **Body**: `{ "sessionId": "ID", "action": "up|down|left|right|undo|restart|action" }`
- **Response**: `{ "board": "...", "status": "playing|game_complete", "message": "..." }`

### `GET /observe`
Get the current state of a session.
- **Query Params**: `?sessionId=ID`
- **Response**: `{ "board": "...", "level": 1 }`

## Project Structure

- **`server.js`**: Main Express server application.
- **`client.js`**: Command-line client for playing games.
- **`sokoban-basic.txt`**: Sample PuzzleScript game file.
- **`midas.txt`**: Another sample game file.

## License
MIT
