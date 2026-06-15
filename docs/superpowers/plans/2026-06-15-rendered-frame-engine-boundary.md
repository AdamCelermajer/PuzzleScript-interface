# Rendered Frame Engine Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional real PuzzleScript rendered PNG observations end-to-end while moving environment transport and action execution out of the engine boundary.

**Architecture:** PuzzleScript emits `frame` plus optional `rendered_frame`; the ARC adapter passes that extension through unchanged; client `FrameData` carries it as optional data. The runtime runner owns reset/step/dashboard I/O, while `client/engine/` remains focused on perception, memory, rulebook, induction, planning, and action decisions.

**Tech Stack:** Node.js built-ins (`zlib`, `Buffer`) for PNG encoding, PuzzleScript `BaseUI`/sprite pixel APIs, FastAPI adapter, Python dataclasses, pytest/unittest, node:test.

---

## File Structure

- Create `puzzlescript_interface/runtime/rendered_frame.js`: headless PuzzleScript sprite-to-PNG renderer.
- Modify `puzzlescript_interface/runtime/server.js`: include `rendered_frame` in `/init`, `/action`, and `/observe`.
- Modify `puzzlescript_interface/api/app.py`: pass `rendered_frame` through `_frame_response` when present.
- Create `client/arc/types.py`: canonical ARC-shaped client types, including `RenderedFrame`.
- Modify `client/engine/types.py`: compatibility re-export of `client.arc.types`.
- Create `client/arc/base_env.py` and `client/arc/arcade_env.py`: move backend environment adapter outside engine.
- Modify `client/engine/base_env.py` and `client/engine/arcade_env.py`: compatibility shims.
- Create `client/runtime/runner.py`: reset/step orchestration and action execution outside engine.
- Modify `client/engine/actions.py`: keep decision data only; remove environment stepping responsibility.
- Modify `client/engine/loop.py` and `client/engine/agent.py`: compatibility wrappers around runtime runner.
- Modify `client/run_arc_agent.py`: import adapter/runner from non-engine packages.
- Add/modify focused tests in `tests/puzzlescript_interface/` and `tests/client/`.

## Task 1: Add Real PuzzleScript PNG Renderer

**Files:**
- Create: `puzzlescript_interface/runtime/rendered_frame.js`
- Modify: `puzzlescript_interface/runtime/server.js`
- Test: `tests/puzzlescript_interface/server-api.test.js`

- [ ] **Step 1: Write failing server API test**

Add this test to `tests/puzzlescript_interface/server-api.test.js`:

```javascript
test('init and action include real rendered PNG data URLs', async () => {
    const server = startServer();

    try {
        await waitForServer(`${SERVER_URL}/observe?sessionId=missing`);

        const initResponse = await fetch(`${SERVER_URL}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gameName: 'ps_sokoban_basic-v1' }),
        });
        const initBody = await initResponse.json();

        assert.equal(initBody.rendered_frame.mime_type, 'image/png');
        assert.match(initBody.rendered_frame.data_url, /^data:image\/png;base64,/);
        assert.equal(Buffer.from(initBody.rendered_frame.data_url.split(',')[1], 'base64').subarray(1, 4).toString('ascii'), 'PNG');

        const actionResponse = await fetch(`${SERVER_URL}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: initBody.sessionId, action: 'ACTION4' }),
        });
        const actionBody = await actionResponse.json();

        assert.equal(actionBody.rendered_frame.mime_type, 'image/png');
        assert.match(actionBody.rendered_frame.data_url, /^data:image\/png;base64,/);
    } finally {
        server.kill();
    }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
node --test tests/puzzlescript_interface/server-api.test.js
```

Expected: FAIL because `rendered_frame` is undefined.

- [ ] **Step 3: Implement renderer and server fields**

Create `puzzlescript_interface/runtime/rendered_frame.js` with:

```javascript
const zlib = require('zlib');
const { BaseUI } = require('puzzlescript');

class HeadlessPixelUI extends BaseUI {
    renderLevelScreen() {}
    setPixel() {}
    checkIfCellCanBeDrawnOnScreen() { return true; }
    getMaxSize() { return { columns: Number.MAX_SAFE_INTEGER, rows: Number.MAX_SAFE_INTEGER }; }
    drawCellsAfterRecentering() {}
    clearScreen() {}
}

function makeCrcTable() {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) {
            c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
        }
        table[n] = c >>> 0;
    }
    return table;
}

const CRC_TABLE = makeCrcTable();

function crc32(buffer) {
    let crc = 0xffffffff;
    for (const byte of buffer) {
        crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
    const typeBuffer = Buffer.from(type, 'ascii');
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length, 0);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
    return Buffer.concat([length, typeBuffer, data, crc]);
}

function rgbaFromColor(color) {
    if (!color || color.isTransparent()) {
        return [0, 0, 0, 0];
    }
    const { r, g, b, a } = color.toRgb();
    return [r, g, b, a === null ? 255 : Math.round(a * 255)];
}

function encodePng(width, height, rgba) {
    const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const ihdr = Buffer.alloc(13);
    ihdr.writeUInt32BE(width, 0);
    ihdr.writeUInt32BE(height, 4);
    ihdr[8] = 8;
    ihdr[9] = 6;
    ihdr[10] = 0;
    ihdr[11] = 0;
    ihdr[12] = 0;

    const stride = width * 4;
    const raw = Buffer.alloc((stride + 1) * height);
    for (let y = 0; y < height; y++) {
        raw[y * (stride + 1)] = 0;
        rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
    }

    return Buffer.concat([
        signature,
        pngChunk('IHDR', ihdr),
        pngChunk('IDAT', zlib.deflateSync(raw)),
        pngChunk('IEND', Buffer.alloc(0)),
    ]);
}

function renderSessionFrame(session) {
    let cells;
    try {
        cells = session.engine.getCurrentLevelCells();
    } catch (e) {
        return null;
    }
    if (!cells || cells.length === 0 || !cells[0] || cells[0].length === 0) {
        return null;
    }

    const ui = new HeadlessPixelUI();
    ui.onGameChange(session.gameData);
    const spriteHeight = ui.SPRITE_HEIGHT;
    const spriteWidth = ui.SPRITE_WIDTH;
    const rows = cells.length;
    const cols = cells[0].length;
    const width = cols * spriteWidth;
    const height = rows * spriteHeight;
    const rgba = Buffer.alloc(width * height * 4);

    for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
            const pixels = ui.getPixelsForCell(cells[row][col]);
            for (let py = 0; py < spriteHeight; py++) {
                for (let px = 0; px < spriteWidth; px++) {
                    const [r, g, b, a] = rgbaFromColor(pixels[py][px]);
                    const index = ((row * spriteHeight + py) * width + (col * spriteWidth + px)) * 4;
                    rgba[index] = r;
                    rgba[index + 1] = g;
                    rgba[index + 2] = b;
                    rgba[index + 3] = a;
                }
            }
        }
    }

    const png = encodePng(width, height, rgba);
    return {
        mime_type: 'image/png',
        data_url: `data:image/png;base64,${png.toString('base64')}`,
        width,
        height,
    };
}

module.exports = { renderSessionFrame, encodePng };
```

Modify `server.js` to import `renderSessionFrame`, and add `rendered_frame: renderSessionFrame(session)` to the JSON returned by `/init`, `/action`, and `/observe`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
node --test tests/puzzlescript_interface/server-api.test.js
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add puzzlescript_interface/runtime/rendered_frame.js puzzlescript_interface/runtime/server.js tests/puzzlescript_interface/server-api.test.js
git commit -m "feat: render puzzlescript frames as png"
```

## Task 2: Forward Rendered Frame Through ARC Adapter

**Files:**
- Modify: `puzzlescript_interface/api/app.py`
- Test: `tests/puzzlescript_interface/test_arc_app.py`

- [ ] **Step 1: Write failing adapter test**

Update `FakePuzzleScriptClient.start_game()` in `tests/puzzlescript_interface/test_arc_app.py` to include:

```python
"rendered_frame": {
    "mime_type": "image/png",
    "data_url": "data:image/png;base64,iVBORw0KGgo=",
    "width": 10,
    "height": 10,
},
```

Add this assertion in `test_scorecard_lifecycle_tracks_reset_and_actions` after `reset_body` is assigned:

```python
self.assertEqual(reset_body["rendered_frame"]["mime_type"], "image/png")
self.assertTrue(reset_body["rendered_frame"]["data_url"].startswith("data:image/png;base64,"))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/puzzlescript_interface/test_arc_app.py::PuzzleScriptArcAppTests::test_scorecard_lifecycle_tracks_reset_and_actions -q
```

Expected: FAIL with missing `rendered_frame`.

- [ ] **Step 3: Implement passthrough**

In `_frame_response`, build the existing response dict first, then add:

```python
rendered_frame = payload.get("rendered_frame")
if rendered_frame:
    response["rendered_frame"] = rendered_frame
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/puzzlescript_interface/test_arc_app.py::PuzzleScriptArcAppTests::test_scorecard_lifecycle_tracks_reset_and_actions -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add puzzlescript_interface/api/app.py tests/puzzlescript_interface/test_arc_app.py
git commit -m "feat: forward rendered frame through arc adapter"
```

## Task 3: Add Client ARC Types And Optional Image Conversion

**Files:**
- Create: `client/arc/__init__.py`
- Create: `client/arc/types.py`
- Modify: `client/engine/types.py`
- Modify: `client/engine/arcade_env.py`
- Test: `tests/client/test_arcade_env.py`

- [ ] **Step 1: Write failing client conversion test**

Create or update `tests/client/test_arcade_env.py` with:

```python
from types import SimpleNamespace

from arcengine import GameState as ArcGameState

from client.engine.arcade_env import ArcadeEnv


def test_arcade_env_preserves_optional_rendered_frame() -> None:
    env = ArcadeEnv.__new__(ArcadeEnv)
    env.game_id = "ps_sokoban_basic-v1"
    rendered = {
        "mime_type": "image/png",
        "data_url": "data:image/png;base64,iVBORw0KGgo=",
        "width": 10,
        "height": 10,
    }
    raw = SimpleNamespace(
        frame=[[[0]]],
        state=ArcGameState.NOT_FINISHED,
        levels_completed=0,
        win_levels=1,
        guid="guid-1",
        full_reset=True,
        available_actions=[1],
        action_input=SimpleNamespace(id=0, data={}),
        projection={},
        rendered_frame=rendered,
    )

    converted = env._convert_frame(raw)

    assert converted.rendered_frame is not None
    assert converted.rendered_frame.mime_type == "image/png"
    assert converted.rendered_frame.data_url.startswith("data:image/png;base64,")
    assert converted.rendered_frame.width == 10
    assert converted.rendered_frame.height == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/client/test_arcade_env.py::test_arcade_env_preserves_optional_rendered_frame -q
```

Expected: FAIL because `FrameData` has no `rendered_frame`.

- [ ] **Step 3: Implement types and conversion**

Move type definitions into `client/arc/types.py`, including:

```python
@dataclass(frozen=True)
class RenderedFrame:
    mime_type: str
    data_url: str
    width: int | None = None
    height: int | None = None
```

Add `rendered_frame: RenderedFrame | None = None` to `FrameData`.

Make `client/engine/types.py` re-export:

```python
from client.arc.types import ActionInput, FrameData, GameAction, GameState, RenderedFrame
```

Update `_convert_frame` to read either object or dict `rendered_frame` and construct `RenderedFrame`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/client/test_arcade_env.py::test_arcade_env_preserves_optional_rendered_frame -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add client/arc/__init__.py client/arc/types.py client/engine/types.py client/engine/arcade_env.py tests/client/test_arcade_env.py
git commit -m "feat: carry rendered frame in client observations"
```

## Task 4: Move Environment Adapter Outside Engine With Shims

**Files:**
- Create: `client/arc/base_env.py`
- Create: `client/arc/arcade_env.py`
- Modify: `client/engine/base_env.py`
- Modify: `client/engine/arcade_env.py`
- Test: `tests/client/test_entrypoints.py`

- [ ] **Step 1: Write failing import expectation**

In `tests/client/test_entrypoints.py`, add:

```python
def test_arcade_env_canonical_import_lives_outside_engine(self) -> None:
    from client.arc.arcade_env import ArcadeEnv
    from client.engine.arcade_env import ArcadeEnv as EngineArcadeEnv

    self.assertIs(EngineArcadeEnv, ArcadeEnv)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/client/test_entrypoints.py::ClientEntrypointTests::test_arcade_env_canonical_import_lives_outside_engine -q
```

Expected: FAIL because `client.arc.arcade_env` does not exist.

- [ ] **Step 3: Move adapter implementation**

Copy the implementation from `client/engine/base_env.py` to `client/arc/base_env.py`.
Copy the implementation from `client/engine/arcade_env.py` to `client/arc/arcade_env.py`, updating imports to `client.arc.base_env` and `client.arc.types`.

Replace `client/engine/base_env.py` with:

```python
from client.arc.base_env import BaseEnv

__all__ = ["BaseEnv"]
```

Replace `client/engine/arcade_env.py` with:

```python
from client.arc.arcade_env import ArcadeEnv

__all__ = ["ArcadeEnv"]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/client/test_entrypoints.py::ClientEntrypointTests::test_arcade_env_canonical_import_lives_outside_engine -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add client/arc/base_env.py client/arc/arcade_env.py client/engine/base_env.py client/engine/arcade_env.py tests/client/test_entrypoints.py
git commit -m "refactor: move arc environment adapter outside engine"
```

## Task 5: Move Action Execution To Runtime Runner

**Files:**
- Create: `client/runtime/__init__.py`
- Create: `client/runtime/runner.py`
- Modify: `client/engine/actions.py`
- Modify: `client/engine/loop.py`
- Test: `tests/client/test_modular_engine_loop.py`

- [ ] **Step 1: Write failing runtime runner test**

In `tests/client/test_modular_engine_loop.py`, add:

```python
def test_runtime_runner_executes_engine_decisions_outside_engine(self) -> None:
    from client.runtime.runner import ActionExecutor

    before_frame = _frame([[2, 0]])
    after_frame = _frame([[0, 2]], action=GameAction.ACTION4)
    before_state = Perceiver().perceive(before_frame)
    env = FakeEnv(before_frame, [after_frame])
    decision = PlanDecision(GameAction.ACTION4, "test", [GameAction.ACTION4])

    outcome = ActionExecutor(env, Perceiver()).execute(before_frame, before_state, decision)

    self.assertEqual(env.step_actions, [GameAction.ACTION4])
    self.assertEqual(outcome.action, GameAction.ACTION4)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/client/test_modular_engine_loop.py::ModularEngineLoopTests::test_runtime_runner_executes_engine_decisions_outside_engine -q
```

Expected: FAIL because `client.runtime.runner` does not exist.

- [ ] **Step 3: Implement runner and engine shim**

Create `client/runtime/runner.py` with `StepOutcome`, `ActionExecutor`, and `RuleReasoningLoop` moved from `client/engine/actions.py` and `client/engine/loop.py`.

Change `client/engine/actions.py` so it only re-exports `PlanDecision` as the engine action decision compatibility surface:

```python
from client.engine.planner import PlanDecision as ActionDecision

__all__ = ["ActionDecision"]
```

Change `client/engine/loop.py` to:

```python
from client.runtime.runner import RuleReasoningLoop

__all__ = ["RuleReasoningLoop"]
```

Keep any compatibility imports that existing tests still need by importing `ActionExecutor` and `StepOutcome` from `client.runtime.runner` until call sites are migrated.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest tests/client/test_modular_engine_loop.py tests/client/test_agent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add client/runtime/__init__.py client/runtime/runner.py client/engine/actions.py client/engine/loop.py tests/client/test_modular_engine_loop.py
git commit -m "refactor: move action execution to runtime runner"
```

## Task 6: Wire Entrypoint To Runtime And Keep Terminal Fallback

**Files:**
- Modify: `client/run_arc_agent.py`
- Test: `tests/client/test_entrypoints.py`

- [ ] **Step 1: Write failing entrypoint import test**

Update `test_run_arc_agent_defaults_to_public_sokoban_id` so it patches:

```python
patch.object(run_arc_agent, "ArcadeEnv", FakeArcadeEnv)
patch.object(run_arc_agent, "RuleReasoningLoop", FakeLoop)
```

after `run_arc_agent.py` imports those names from `client.arc.arcade_env` and `client.runtime.runner`.

- [ ] **Step 2: Run test to verify current import path fails the new expectation**

Run:

```powershell
python -m pytest tests/client/test_entrypoints.py::ClientEntrypointTests::test_run_arc_agent_defaults_to_public_sokoban_id -q
```

Expected: FAIL if `run_arc_agent.py` still imports from engine modules.

- [ ] **Step 3: Update imports**

Change `client/run_arc_agent.py` imports to:

```python
from client.arc.arcade_env import ArcadeEnv
from client.runtime.runner import RuleReasoningLoop
```

Use `ScreenDashboard` as the engine-run dashboard.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/client/test_entrypoints.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add client/run_arc_agent.py tests/client/test_entrypoints.py
git commit -m "refactor: run agent through client runtime boundary"
```

## Final Verification

- [ ] Run JavaScript runtime tests:

```powershell
node --test tests/puzzlescript_interface/*.test.js
```

Expected: all JavaScript tests pass.

- [ ] Run Python PuzzleScript adapter tests:

```powershell
python -m pytest tests/puzzlescript_interface -q
```

Expected: all Python PuzzleScript tests pass.

- [ ] Run client tests:

```powershell
python -m pytest tests/client -q
```

Expected: all client tests pass.

- [ ] Check git status:

```powershell
git status --short --branch
```

Expected: clean worktree, branch ahead of origin by the new commits.
