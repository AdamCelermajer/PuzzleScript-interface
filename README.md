# PuzzleScript Server Project

This repository contains a Node.js implementation of a server-client architecture for running PuzzleScript games. It allows for game logic to be executed on a server with clients connecting to play.

## Project Structure

- `puzzlescript-server/`: Main application directory containing the server, client, and game definitions.

## Getting Started

### Prerequisites

- Node.js (v14 or higher recommended)
- npm

### Installation

1. Navigate to the server directory:
   ```bash
   cd puzzlescript-server
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

## Usage

### Running the Server

Start the game server:

```bash
npm start
```

### Running the Client

In a separate terminal, run the client to connect to the server:

```bash
npm run client
```

## Available Games

The project includes several PuzzleScript game files (e.g., `midas.txt`, `sokoban-basic.txt`, `match3.txt`) located in the server directory.
