# Adapting PuzzleScript-Interface to ARC-AGI-3 — Full Research & Plan

## Context

The project at `PuzzleScript-interface/` is a system where an LLM agent plays PuzzleScript games to learn their rules. It currently uses:
- A **Node.js Express HTTP server** ([src/server.js](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/server.js)) wrapping the [`puzzlescript` npm package](https://www.npmjs.com/package/puzzlescript) (v6.0.0-alpha.2)
- A **Python LLM client** ([src/llm_client.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/llm_client.py), [src/learning_mode.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/learning_mode.py), [src/prompts.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/prompts.py)) that calls the server via REST and uses `litellm` to query Gemini models

The goal: **fully adapt this to match ARC-AGI-3's communication protocol** so the bot interacts with PuzzleScript games the same way ARC-AGI-3 agents interact with ARC environments.

---

## Part 1: How ARC-AGI-3 Works (from docs + source code)

### SDK & Package
- Python package: `arc-agi` (install via `pip install arc-agi`)
- Engine package: `arcengine`
- Agents repo: https://github.com/arcprize/ARC-AGI-3-Agents

### Core Loop
```python
import arc_agi
from arcengine import GameAction

arc = arc_agi.Arcade()
env = arc.make("ls20", render_mode="terminal")
obs = env.step(GameAction.ACTION1)
print(arc.get_scorecard())
```

### GameAction Enum
```python
class GameAction:
    RESET    # Start/restart game
    ACTION1  # Up / W
    ACTION2  # Down / S  
    ACTION3  # Left / A
    ACTION4  # Right / D
    ACTION5  # Enter / Spacebar / Delete
    ACTION6  # Click/Point (complex action with x,y coordinates)
```

Actions have:
- `action.reasoning` — free-form field for storing LLM reasoning
- `action.is_simple()` / `action.is_complex()` — ACTION6 is "complex" (needs x,y coords)
- `action.set_data({"x": int, "y": int})` — for ACTION6 only
- `GameAction.from_name("ACTION1")` — string→enum conversion

### GameState Enum
```python
class GameState:
    NOT_PLAYED  # Game hasn't started
    PLAYING     # Game is active
    WIN         # Player won
    GAME_OVER   # Player lost
```

### FrameData (observation returned after each step)
```python
@dataclass
class FrameData:
    frame: list[list[list[int]]]  # 3D: list of 2D grids, each grid is list[list[int]]
    state: GameState              # Current game state
    levels_completed: int         # How many levels beaten
    game_id: str                  # Which game
    win_levels: int               # Levels needed to win
    guid: str                     # Session GUID
    full_reset: bool              # Whether this was a full reset
    available_actions: list       # Available actions
    action_input: ActionInput     # The action that produced this frame
```

Key detail: `frame` is a **3D array** — a list of 2D grids. Each grid is `list[list[int]]` where values are integers 0-15. One action can produce multiple sequential grids (animation frames). Each grid can be up to 64×64.

### Agent Base Class (from `agents/agent.py`)
```python
class Agent(ABC):
    MAX_ACTIONS: int = 80
    frames: list[FrameData]
    action_counter: int = 0

    def main(self):
        """The main agent loop."""
        while not self.is_done(self.frames, self.frames[-1]) \
              and self.action_counter <= self.MAX_ACTIONS:
            action = self.choose_action(self.frames, self.frames[-1])
            frame = self.take_action(action)
            self.append_frame(frame)
            self.action_counter += 1
        self.cleanup()

    @abstractmethod
    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        raise NotImplementedError

    @abstractmethod
    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        raise NotImplementedError
```

### LLM Agent (from `agents/templates/llm_agents.py`)

The LLM agent uses **OpenAI function calling** to select actions:

```python
class LLM(Agent):
    MAX_ACTIONS = 80
    DO_OBSERVATION = True
    MODEL = "gpt-4o-mini"
    MESSAGE_LIMIT = 10  # Rolling FIFO message history

    def choose_action(self, frames, latest_frame):
        # 1. On first call: send user prompt + auto-call RESET
        # 2. On subsequent calls:
        #    a. Send the function response (observation) from previous action
        #    b. If DO_OBSERVATION: ask LLM for strategy observation (plain text)
        #    c. Send user prompt asking for next action
        #    d. LLM calls one of the action functions via function_call
        # 3. Parse function call → GameAction
```

**Prompts used by the LLM agent:**

Function response prompt (observation):
```
# State:
{state}           # e.g. "PLAYING"

# Score:
{score}           # levels_completed

# Frame:
Grid 0:
  [0, 0, 8, 8, 8, ...]
  [0, 0, 10, 10, 10, ...]
  ...

# TURN:
Reply with a few sentences of plain-text strategy observation about the frame.
```

User prompt:
```
# CONTEXT:
You are an agent playing a dynamic game. Your objective is to
WIN and avoid GAME_OVER while minimizing actions.

One action produces one Frame. One Frame is made of one or more sequential
Grids. Each Grid is a matrix size INT<0,63> by INT<0,63> filled with
INT<0,15> values.

# TURN:
Call exactly one action.
```

**Functions exposed to the LLM:**
```python
functions = [
    {"name": "RESET",   "description": "Start or restart a game..."},
    {"name": "ACTION1", "description": "Send this simple input action (1, W, Up)."},
    {"name": "ACTION2", "description": "Send this simple input action (2, S, Down)."},
    {"name": "ACTION3", "description": "Send this simple input action (3, A, Left)."},
    {"name": "ACTION4", "description": "Send this simple input action (4, D, Right)."},
    {"name": "ACTION5", "description": "Send this simple input action (5, Enter, Spacebar, Delete)."},
    {"name": "ACTION6", "description": "Send this complex input action (6, Click, Point).",
     "parameters": {"x": "Coordinate X 0-63", "y": "Coordinate Y 0-63"}},
]
```

**GuidedLLM agent** — includes game-specific rules directly in the prompt (example for LockSmith game):
```
* RESET: start over, ACTION1: move up, ACTION2: move down, ACTION3: move left, ACTION4: move right
* walls are made of INT<10>, walkable floor is INT<8>
* the player is a 4x4 square: [[X,X,X,X],[0,0,0,X],[4,4,4,X],[4,4,4,X]]
```

---

## Part 2: How PuzzleScript NPM Terminal Works (from source code)

### The `puzzlescript` NPM Package
- GitHub: https://github.com/philschatz/puzzlescript
- Description: "Play PuzzleScript games in your terminal!"
- Has full terminal rendering with ANSI colors
- Exports: `Parser`, [GameEngine](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/engine.ts#947-1100), [Cell](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/engine.ts#70-326), `INPUT_BUTTON`, `EmptyGameEngineHandler`, [BaseUI](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/ui/base.ts#121-564)

### GameEngine API (from [src/engine.ts](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/engine.ts))
```typescript
class GameEngine {
    press(button: INPUT_BUTTON): void    // Queue an action
    tick(): ITickResult                  // Process the action, return result
    setLevel(num: number): Cell[][]      // Load a level
    getCurrentLevelCells(): Cell[][]     // Get current board state
    hasAgain(): boolean                  // Check for AGAIN rules
}
```

### INPUT_BUTTON Enum (from `src/util.ts`)
```typescript
enum INPUT_BUTTON {
    UP,
    DOWN,
    LEFT,
    RIGHT,
    ACTION,   // Space/X
    UNDO,     // Z
    RESTART   // R
}
```

### ITickResult (from [src/engine.ts](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/engine.ts))
```typescript
interface ITickResult {
    changedCells: Set<Cell>
    didWinGame: boolean
    didLevelChange: boolean
    wasAgainTick: boolean
}
```

### Cell (from [src/engine.ts](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/engine.ts))
```typescript
class Cell {
    rowIndex: number
    colIndex: number
    getSprites(): GameSprite[]           // Named sprites in this cell
    hasSprite(sprite: GameSprite): boolean
    // Sprites have .getName() returning strings like "Player", "Wall", "Crate", etc.
}
```

### Terminal Rendering (from [src/ui/base.ts](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/ui/base.ts))
- [BaseUI](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/ui/base.ts#121-564) abstract class with pixel-level rendering
- Each cell's sprites are collapsed to colored pixels
- Uses ANSI terminal colors
- Supports flickscreen and zoomscreen
- Each sprite is 5×5 pixels by default, rendered with 2-char-wide terminal pixels

### Your Current Server ([src/server.js](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/server.js))
Uses the puzzlescript npm package to:
1. Parse game source → [GameData](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/node_modules/puzzlescript/src/engine.ts#960-963)
2. Create sessions with `new GameEngine(data, handler)`
3. Expose HTTP endpoints:
   - `POST /init` → `{sessionId, board (ASCII), boardJSON, level, legend, totalLevels}`
   - `POST /action` → `{board, boardJSON, level, message, status}`
   - `GET /observe` → `{board, boardJSON, level, legend}`
4. Render ASCII boards by mapping `Cell.getSprites()` → single legend characters
5. [renderJSON()](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/server.js#238-262) gives per-cell sprite name lists: `[{x, y, content: ["Player", "Background"]}]`

### Your Current Python Client ([src/llm_client.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/llm_client.py))
```python
class Server:
    def init(self, game: str) -> dict      # POST /init
    def action(self, session, action) -> dict  # POST /action

class LlmClient:
    def _call(self, system, prompt, model_type="flash") -> str  # litellm completion

class Config:
    server_url = "http://localhost:3000"
    flash_model = "gemini-3-flash-preview"
    pro_model = "gemini-3.1-pro-preview"
    game, mode, max_steps, show_legend, api_key, rules_dir
```

### Your Current Agent Loop ([src/learning_mode.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/learning_mode.py))
```python
class Agent:
    history: list[tuple[str, str, str]]  # (prev_board_ascii, action_letter, next_board_ascii)
    known_rules: dict[str, list[str]]    # category → list of rule strings
    inferred_legend: dict[str, str]      # symbol → role name

    # Methods:
    infer_legend(history)               # Guess what each ASCII symbol means
    deduce_rules_from_history(history)  # Extract IF/THEN rules from transitions
    compress_rules()                    # Merge direction-specific rules
    refine_and_complete_rules_and_legend()  # Final audit pass
    plan_subgoal(board, history)        # Plan next experiment
    act(board, local, subgoal)          # Pick action letter (W/A/S/D/X/R)

def run_learning_mode(cfg):
    srv = Server(cfg.server_url)
    agent = Agent(cfg, llm_client)
    data = srv.init(cfg.game)
    while True:
        action = agent.act(state.board, state.local, subgoal)  # returns "W"/"A"/etc.
        response = srv.action(state.session_id, action)
        # ... track history, periodic analysis every 5 steps, etc.
```

---

## Part 3: Side-by-Side Comparison

| Aspect | ARC-AGI-3 | PuzzleScript (current) | Similarity |
|---|---|---|---|
| **Transport** | In-process Python SDK (`env.step()`) | HTTP REST (`POST /action`) | Different mechanism, same concept |
| **Action input** | `GameAction` enum: `RESET, ACTION1-6` | String: `"up"/"down"/"left"/"right"/"action"/"r"` | Same 6 actions, different naming |
| **PuzzleScript engine** | N/A | `engine.press(INPUT_BUTTON)` + `engine.tick()` | — |
| **Board observation** | `FrameData.frame`: 3D int array (values 0-15, up to 64×64) | ASCII string + `boardJSON` (sprite name lists) | Different format, equivalent info |
| **Game state** | `GameState` enum: `NOT_PLAYED/PLAYING/WIN/GAME_OVER` | `status` string: `"playing"/"game_complete"` | Same concept, simpler in PS |
| **Agent pattern** | ABC with `is_done()` + `choose_action()` | Procedural `while True` loop | Different structure |
| **LLM integration** | OpenAI function calling (actions as callable tools) | litellm text completion (output single char) | Very different approach |
| **History** | `frames: list[FrameData]` + rolling 10-msg chat history | `list[tuple[str, str, str]]` of (board, action, board) | Different shape |
| **Terminal render** | `render_mode="terminal"` (colored int grid) | Custom ASCII from sprite legend | Both terminal |

### Action Mapping Table
| ARC-AGI-3 | PuzzleScript `INPUT_BUTTON` | Current string | Meaning |
|---|---|---|---|
| `RESET` | `RESTART` | `"r"` | Reset/restart level |
| `ACTION1` | `UP` | `"up"` / `"w"` | Move up |
| `ACTION2` | `DOWN` | `"down"` / `"s"` | Move down |
| `ACTION3` | `LEFT` | `"left"` / `"a"` | Move left |
| `ACTION4` | `RIGHT` | `"right"` / `"d"` | Move right |
| `ACTION5` | `ACTION` | `"action"` / `"x"` | Action/Space |
| `ACTION6` | *(no equivalent)* | *(no equivalent)* | Click with x,y |
| *(no equivalent)* | `UNDO` | `"z"` | Undo last move |

---

## Part 4: Implementation Plan

### Goal
Make the PuzzleScript agent speak ARC-AGI-3 protocol end-to-end:
- **Actions**: `GameAction` enum (`RESET, ACTION1-5`)
- **Observations**: `FrameData` with `frame` as 2D int grid (0-15), [state](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/learning_mode.py#83-111) as `GameState` enum
- **Agent pattern**: `is_done(frames, latest_frame)` + `choose_action(frames, latest_frame)`
- **Board in prompts**: Integer grid format (like ARC-AGI-3 shows `Grid 0: [0, 0, 8, ...]`)
- **LLM action selection**: Function calling (actions exposed as callable tools) — or at minimum, output `ACTION1`/`ACTION2`/etc. instead of `W`/`A`/`S`/`D`

### Architecture

```
┌─────────────────────────────────────┐
│         LLM Agent (Python)          │
│  is_done() / choose_action()        │
│  Uses GameAction enum               │
│  Receives FrameData (int grids)     │
│  Rule deduction pipeline preserved  │
└─────────────┬───────────────────────┘
              │ ARC-AGI-3 interface
              ▼
┌─────────────────────────────────────┐
│    PuzzleScriptEnv Adapter (Python) │
│  step(GameAction) → FrameData       │
│  Maps ACTION1-4 → up/down/left/right│
│  Converts ASCII board → int grid    │
│  Wraps HTTP calls to server.js      │
└─────────────┬───────────────────────┘
              │ HTTP
              ▼
┌─────────────────────────────────────┐
│     Node.js server.js (unchanged)   │
│     (puzzlescript npm package)      │
└─────────────────────────────────────┘
```

### Files to Create/Modify

1. **[NEW] [src/env_adapter.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/env_adapter.py)** — The adapter layer:
   - `GameAction` enum (RESET, ACTION1-5)
   - `GameState` enum (NOT_PLAYED, PLAYING, WIN, GAME_OVER)
   - `FrameData` dataclass (frame=2D int grid, state, levels_completed, legend)
   - `PuzzleScriptEnv` class with `reset()→FrameData` and `step(GameAction)→FrameData`
   - ASCII char→int mapping (legend chars get assigned stable IDs 0-15)
   - Terminal rendering that prints int grid

2. **[MODIFY] [src/learning_mode.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/learning_mode.py)** — Refactor agent:
   - Agent gets `is_done(frames, latest_frame)` and `choose_action(frames, latest_frame)`
   - Main loop follows ARC-AGI-3 pattern: `while not done: action = choose(); frame = env.step(action)`
   - Board transitions stored as int grids instead of ASCII strings
   - Rule deduction pipeline stays but works with int grid format

3. **[MODIFY] [src/llm_client.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/llm_client.py)** — Update client:
   - Move [Server](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/llm_client.py#33-57) class to adapter (or keep as internal detail)
   - Config supports both modes

4. **[MODIFY] [src/prompts.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/prompts.py)** — Update prompts:
   - Action vocabulary: `ACTION1/ACTION2/ACTION3/ACTION4/ACTION5/RESET`
   - Board format: integer grids `[0, 0, 3, 3, 1, ...]` per row
   - Rule format: reference int IDs instead of ASCII symbols

5. **[MODIFY] [src/solving_mode.py](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/solving_mode.py)** — Same changes as learning_mode

### Key Design Decisions Needed

1. **Board conversion**: Each ASCII legend character (e.g. `#`=Wall, `@`=Player, `.`=Background) gets a stable integer ID 0-15. The server already returns a [legend](file:///c:/Users/adamc/Desktop/uni/adam_project/PuzzleScript-interface/src/learning_mode.py#64-82) dict mapping chars to descriptions.

2. **Rule deduction with int grids**: The prompts for rule deduction currently reference ASCII symbols like `#`, `@`, `O`. With int grids, the LLM will see `[0, 0, 3, 1, ...]`. The int→description legend should be included in prompts so the LLM can still reason about "Player" and "Wall".

3. **Function calling vs text output for actions**: ARC-AGI-3 uses OpenAI function calling. Your project uses litellm text completion. You could either:
   - Switch to function calling (more ARC-AGI-3 faithful)
   - Keep text completion but output `ACTION1`/`RESET` instead of `W`/`R` (simpler change)

---

## Current Project File Structure

```
PuzzleScript-interface/
├── src/
│   ├── server.js          # Node.js PuzzleScript engine server (430 lines)
│   ├── client.js          # Node.js terminal client for manual play (94 lines)
│   ├── llm_client.py      # Config, Server HTTP client, LlmClient (106 lines)
│   ├── learning_mode.py   # Agent + learning loop (484 lines)
│   ├── solving_mode.py    # Solving agent + loop (81 lines)
│   ├── prompts.py         # All LLM prompts (244 lines)
│   ├── utils.py           # add_coordinates helper (19 lines)
│   └── rules/             # Persisted inferred rules per game
├── games/                 # PuzzleScript game source files
├── package.json           # Node deps: puzzlescript, express, axios
└── requirements.txt       # Python deps
```
