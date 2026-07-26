"use strict";

const { performance } = require("node:perf_hooks");
const {
  Parser,
  GameEngine,
  INPUT_BUTTON,
  EmptyGameEngineHandler,
} = require("puzzlescript");

const ACTIONS = Object.freeze([
  { name: "UP", button: INPUT_BUTTON.UP },
  { name: "DOWN", button: INPUT_BUTTON.DOWN },
  { name: "LEFT", button: INPUT_BUTTON.LEFT },
  { name: "RIGHT", button: INPUT_BUTTON.RIGHT },
  { name: "ACTION", button: INPUT_BUTTON.ACTION },
]);
const ACTION_BY_NAME = new Map(ACTIONS.map((action) => [action.name, action]));

function availableSearchActions(gameData) {
  return gameData?.metadata?.noAction
    ? ACTIONS.filter((action) => action.name !== "ACTION")
    : ACTIONS;
}

function normalizeSource(source) {
  return source.replace(/\r\n?/g, "\n");
}

function firstPlayableLevel(gameData) {
  return gameData.levels.findIndex((level) => level.type === "LEVEL_MAP");
}

function inspectGameSource(source) {
  const normalizedSource = normalizeSource(source);
  const parseStarted = performance.now();
  const { data } = Parser.parse(normalizedSource);
  const parseMs = performance.now() - parseStarted;
  const firstLevelIndex = firstPlayableLevel(data);
  const formalGoalCount = Array.isArray(data.winConditions)
    ? data.winConditions.length
    : 0;

  const unsupportedReasons = [];
  if (/(^|[\s\[|])random(?:dir)?(?=$|[\s\]|])/im.test(normalizedSource)) {
    unsupportedReasons.push("random_rules");
  }
  if (/^\s*realtime_interval\b/im.test(normalizedSource)) {
    unsupportedReasons.push("realtime");
  }
  if (/\bcheckpoint\b/i.test(normalizedSource)) {
    unsupportedReasons.push("checkpoint_hidden_state");
  }

  return {
    data,
    parseMs,
    formalGoalCount,
    firstLevelIndex,
    unsupportedReasons,
  };
}

class CompactStateCodec {
  constructor(rows, cols) {
    this.rows = rows;
    this.cols = cols;
    this.signatureToId = new Map();
    this.idToSprites = [];
  }

  _signature(sprites) {
    return [...new Set(sprites)].sort().join("\u0000");
  }

  _idForSprites(sprites) {
    const signature = this._signature(sprites);
    const existing = this.signatureToId.get(signature);
    if (existing !== undefined) {
      return existing;
    }

    const id = this.idToSprites.length;
    if (id > 0xffff) {
      throw new Error("Compact cell dictionary exceeded Uint16 capacity");
    }
    this.signatureToId.set(signature, id);
    this.idToSprites.push(signature === "" ? [] : signature.split("\u0000"));
    return id;
  }

  encode(snapshot) {
    if (snapshot.length !== this.rows) {
      throw new Error(`Snapshot row count changed: ${snapshot.length} != ${this.rows}`);
    }

    const encoded = new Uint16Array(this.rows * this.cols);
    let offset = 0;
    for (const row of snapshot) {
      if (row.length !== this.cols) {
        throw new Error(`Snapshot column count changed: ${row.length} != ${this.cols}`);
      }
      for (const sprites of row) {
        encoded[offset++] = this._idForSprites(sprites);
      }
    }
    return encoded;
  }

  decode(encoded) {
    const snapshot = [];
    let offset = 0;
    for (let rowIndex = 0; rowIndex < this.rows; rowIndex += 1) {
      const row = [];
      for (let colIndex = 0; colIndex < this.cols; colIndex += 1) {
        const sprites = this.idToSprites[encoded[offset++]];
        if (!sprites) {
          throw new Error("Compact state referenced an unknown cell signature");
        }
        row.push(sprites.slice());
      }
      snapshot.push(row);
    }
    return snapshot;
  }

  key(encoded) {
    return Buffer.from(
      encoded.buffer,
      encoded.byteOffset,
      encoded.byteLength,
    ).toString("base64");
  }

  get dictionarySize() {
    return this.idToSprites.length;
  }
}

function actionsToNode(nodes, nodeIndex) {
  const reversed = [];
  while (nodeIndex >= 0) {
    const node = nodes[nodeIndex];
    if (node.action !== null) {
      reversed.push(node.action);
    }
    nodeIndex = node.parent;
  }
  return reversed.reverse();
}

async function applyAction(engine, action, maxAgainTicks) {
  engine.press(action.button);
  let tickCount = 0;
  do {
    const tickResult = await engine.tick();
    tickCount += 1;
    if (tickResult.didLevelChange || tickResult.didWinGame) {
      return { won: true, tickCount, againLimit: false };
    }
    if (tickCount >= maxAgainTicks && engine.hasAgain()) {
      return { won: false, tickCount, againLimit: true };
    }
  } while (engine.hasAgain());
  return { won: false, tickCount, againLimit: false };
}

async function solveSource({
  source,
  gameId,
  levelIndex = null,
  maxStates = 100_000,
  timeoutMs = 10_000,
  maxAgainTicks = 100,
}) {
  const totalStarted = performance.now();
  const inspection = inspectGameSource(source);
  const { data, parseMs, formalGoalCount, unsupportedReasons } = inspection;
  const selectedLevel = levelIndex ?? inspection.firstLevelIndex;
  const searchActions = availableSearchActions(data);

  if (formalGoalCount === 0) {
    return {
      gameId,
      levelIndex: selectedLevel,
      status: "ineligible",
      reason: "no_formal_win_condition",
      parseMs,
    };
  }
  if (selectedLevel < 0 || data.levels[selectedLevel]?.type !== "LEVEL_MAP") {
    return {
      gameId,
      levelIndex: selectedLevel,
      status: "ineligible",
      reason: "no_playable_level",
      parseMs,
    };
  }
  if (unsupportedReasons.length > 0) {
    return {
      gameId,
      levelIndex: selectedLevel,
      status: "unsupported",
      reason: unsupportedReasons.join(","),
      parseMs,
    };
  }

  const initStarted = performance.now();
  const engine = new GameEngine(data, new EmptyGameEngineHandler());
  engine.setLevel(selectedLevel, null);
  const initialSnapshot = engine.levelEngine.toSnapshot();
  const rows = initialSnapshot.length;
  const cols = initialSnapshot[0]?.length ?? 0;
  const codec = new CompactStateCodec(rows, cols);
  const initialCells = codec.encode(initialSnapshot);
  const initialKey = codec.key(initialCells);
  const initMs = performance.now() - initStarted;

  const nodes = [{
    cells: initialCells,
    key: initialKey,
    parent: -1,
    action: null,
    depth: 0,
  }];
  const visited = new Map([[initialKey, 0]]);
  let head = 0;
  let transitions = 0;
  let engineActions = 0;
  let replayedActions = 0;
  let ticks = 0;
  let duplicates = 0;
  let unchanged = 0;
  let engineMs = 0;
  let codecMs = 0;
  let peakHeapBytes = process.memoryUsage().heapUsed;
  const searchStarted = performance.now();
  let status = "exhausted";
  let solutionActions = null;
  let solutionDepth = null;

  searchLoop:
  while (head < nodes.length) {
    const elapsed = performance.now() - searchStarted;
    if (elapsed >= timeoutMs) {
      status = "time_limit";
      break;
    }
    if (visited.size >= maxStates) {
      status = "state_limit";
      break;
    }

    const parentIndex = head;
    const parent = nodes[head++];
    const parentActions = actionsToNode(nodes, parentIndex);

    for (const action of searchActions) {
      if (performance.now() - searchStarted >= timeoutMs) {
        status = "time_limit";
        break searchLoop;
      }

      const engineStarted = performance.now();
      const branchEngine = new GameEngine(data, new EmptyGameEngineHandler());
      branchEngine.setLevel(selectedLevel, null);

      for (const replayActionName of parentActions) {
        const replayResult = await applyAction(
          branchEngine,
          ACTION_BY_NAME.get(replayActionName),
          maxAgainTicks,
        );
        engineActions += 1;
        replayedActions += 1;
        ticks += replayResult.tickCount;
        if (replayResult.againLimit) {
          status = "again_limit";
          engineMs += performance.now() - engineStarted;
          break searchLoop;
        }
        if (replayResult.won) {
          throw new Error("A queued BFS node replays past a winning transition");
        }
      }

      const transitionResult = await applyAction(branchEngine, action, maxAgainTicks);
      transitions += 1;
      engineActions += 1;
      ticks += transitionResult.tickCount;

      if (transitionResult.againLimit) {
        status = "again_limit";
        engineMs += performance.now() - engineStarted;
        break searchLoop;
      }

      if (transitionResult.won) {
        engineMs += performance.now() - engineStarted;
        status = "solved";
        solutionActions = [...parentActions, action.name];
        solutionDepth = solutionActions.length;
        break searchLoop;
      }

      const nextSnapshot = branchEngine.levelEngine.toSnapshot();
      engineMs += performance.now() - engineStarted;
      const codecStarted = performance.now();
      const nextCells = codec.encode(nextSnapshot);
      const nextKey = codec.key(nextCells);
      codecMs += performance.now() - codecStarted;

      if (nextKey === parent.key) {
        unchanged += 1;
        continue;
      }
      if (visited.has(nextKey)) {
        duplicates += 1;
        continue;
      }

      const nodeIndex = nodes.length;
      visited.set(nextKey, nodeIndex);
      nodes.push({
        cells: nextCells,
        key: nextKey,
        parent: parentIndex,
        action: action.name,
        depth: parent.depth + 1,
      });

      if (visited.size >= maxStates) {
        status = "state_limit";
        break searchLoop;
      }
    }

    if (transitions % 5_000 === 0) {
      peakHeapBytes = Math.max(peakHeapBytes, process.memoryUsage().heapUsed);
    }
  }

  peakHeapBytes = Math.max(peakHeapBytes, process.memoryUsage().heapUsed);
  const searchMs = performance.now() - searchStarted;
  const totalMs = performance.now() - totalStarted;

  return {
    gameId,
    levelIndex: selectedLevel,
    board: { rows, cols, cells: rows * cols },
    status,
    solved: status === "solved",
    optimalityProven: status === "solved",
    solutionDepth,
    solutionActions,
    expandedStates: head,
    uniqueStates: visited.size,
    frontierStates: nodes.length - head,
    transitions,
    engineActions,
    replayedActions,
    ticks,
    duplicates,
    unchanged,
    compactBytesPerState: initialCells.byteLength,
    cellDictionarySize: codec.dictionarySize,
    parseMs,
    initMs,
    searchMs,
    engineMs,
    codecMs,
    totalMs,
    searchTransitionsPerSecond: searchMs > 0 ? transitions / (searchMs / 1000) : 0,
    engineActionsPerSecond: engineMs > 0 ? engineActions / (engineMs / 1000) : 0,
    engineTicksPerSecond: engineMs > 0 ? ticks / (engineMs / 1000) : 0,
    peakHeapBytes,
    limits: { maxStates, timeoutMs, maxAgainTicks },
  };
}

module.exports = {
  ACTIONS,
  CompactStateCodec,
  availableSearchActions,
  firstPlayableLevel,
  inspectGameSource,
  normalizeSource,
  solveSource,
};
