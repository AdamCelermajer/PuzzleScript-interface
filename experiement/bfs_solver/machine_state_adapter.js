"use strict";

const {
  Parser,
  GameEngine,
  EmptyGameEngineHandler,
} = require("puzzlescript");

function normalizeSource(source) {
  return source.replace(/\r\n?/g, "\n");
}

function parseSavedSprite(savedSprite) {
  const separator = savedSprite.indexOf(" ");
  if (separator < 1) {
    throw new Error(`Invalid saved sprite state: ${savedSprite}`);
  }
  return {
    wantsToMove: savedSprite.slice(0, separator),
    spriteName: savedSprite.slice(separator + 1),
  };
}

function cloneCells(cells) {
  return cells.map((row) => row.map((cell) => cell.slice()));
}

function findOrderedCellCaches(root) {
  const caches = [];
  const seenObjects = new WeakSet();
  const seenCaches = new WeakSet();
  const cachePropertyNames = new Set(["trickleCells", "firstCells"]);

  function visit(value) {
    if (value === null || (typeof value !== "object" && typeof value !== "function")) {
      return;
    }
    if (seenObjects.has(value)) return;
    seenObjects.add(value);

    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (value instanceof Map) {
      for (const [key, item] of value) {
        visit(key);
        visit(item);
      }
      return;
    }
    if (value instanceof Set) {
      for (const item of value) visit(item);
      return;
    }

    for (const key of Object.keys(value)) {
      const child = value[key];
      if (cachePropertyNames.has(key) && child instanceof Set) {
        if (!seenCaches.has(child)) {
          seenCaches.add(child);
          caches.push(child);
        }
        continue;
      }
      visit(child);
    }
  }

  visit(root);
  return caches;
}

function findCellLinkageCaches(root) {
  const caches = [];
  const seenObjects = new WeakSet();

  function visit(value) {
    if (value === null || (typeof value !== "object" && typeof value !== "function")) return;
    if (seenObjects.has(value)) return;
    seenObjects.add(value);
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (value instanceof Map) {
      for (const [key, item] of value) {
        visit(key);
        visit(item);
      }
      return;
    }
    if (value instanceof Set) {
      for (const item of value) visit(item);
      return;
    }
    for (const key of Object.keys(value)) {
      const child = value[key];
      if (key === "linkages" && child?.map instanceof Map) {
        caches.push(child);
        continue;
      }
      if (key === "trickleCells" || key === "firstCells") continue;
      visit(child);
    }
  }

  visit(root);
  return caches;
}

function captureMachineState(engine, orderedCellCaches, cellLinkageCaches = []) {
  const levelEngine = engine.levelEngine;
  const cols = levelEngine.getCurrentLevel().getCells()[0].length;
  const cellIndex = (cell) => (cell.rowIndex * cols) + cell.colIndex;
  return {
    levelIndex: engine.currentLevelNum,
    cells: cloneCells(levelEngine.toSnapshot()),
    pendingInput: levelEngine.pendingPlayerWantsToMove,
    hasAgain: levelEngine.hasAgainThatNeedsToRun,
    cacheOrders: orderedCellCaches.map((cache) => (
      [...cache].map(cellIndex)
    )),
    linkageOrders: cellLinkageCaches.map((cache) => (
      [...cache.map].map(([before, afterSet]) => [
        cellIndex(before),
        [...afterSet].map(cellIndex),
      ])
    )),
  };
}

class PuzzleScriptMachineAdapter {
  constructor({ source, levelIndex }) {
    const parsed = Parser.parse(normalizeSource(source));
    this.gameData = parsed.data;
    this.levelIndex = levelIndex;
    this.engine = new GameEngine(this.gameData, new EmptyGameEngineHandler());
    this.engine.setLevel(levelIndex, null);

    const levelEngine = this.engine.levelEngine;
    if (
      typeof levelEngine._setLevel !== "function"
      || typeof this.gameData.clearCaches !== "function"
    ) {
      throw new Error(
        "Installed PuzzleScript internals are incompatible with the experiment adapter",
      );
    }

    this.initialRestartSnapshot = levelEngine.undoStack[0];
    this.orderedCellCaches = findOrderedCellCaches(this.gameData);
    this.cellLinkageCaches = findCellLinkageCaches(this.gameData);
    this.initialState = this.exportState();
  }

  exportState() {
    return captureMachineState(
      this.engine,
      this.orderedCellCaches,
      this.cellLinkageCaches,
    );
  }

  importState(state) {
    if (state.levelIndex !== this.levelIndex) {
      throw new Error(
        `Adapter cannot import level ${state.levelIndex}; expected ${this.levelIndex}`,
      );
    }

    const decoded = state.cells.map((row) => row.map((savedCell) => (
      savedCell.map(parseSavedSprite)
    )));
    const levelSprites = decoded.map((row) => row.map((savedCell) => {
      const sprites = savedCell.map(({ spriteName }) => {
        const sprite = this.gameData._getSpriteByName(spriteName);
        if (!sprite) {
          throw new Error(`Unknown sprite in machine state: ${spriteName}`);
        }
        return sprite;
      });
      return new Set(sprites);
    }));

    this.gameData.clearCaches();
    const levelEngine = this.engine.levelEngine;
    levelEngine._setLevel(levelSprites);
    this.engine.currentLevelNum = state.levelIndex;
    levelEngine.tempOldLevel = null;
    levelEngine.pendingPlayerWantsToMove = state.pendingInput;
    levelEngine.hasAgainThatNeedsToRun = state.hasAgain;
    levelEngine.undoStack = this.initialRestartSnapshot
      ? [this.initialRestartSnapshot]
      : [];

    const level = levelEngine.getCurrentLevel();
    decoded.forEach((row, rowIndex) => {
      row.forEach((savedCell, colIndex) => {
        const cell = level.getCell(rowIndex, colIndex);
        for (const { spriteName, wantsToMove } of savedCell) {
          const sprite = this.gameData._getSpriteByName(spriteName);
          cell.updateSprite(sprite, wantsToMove);
        }
      });
    });

    const rows = level.getCells();
    const cols = rows[0].length;
    if (state.cacheOrders.length !== this.orderedCellCaches.length) {
      throw new Error("Machine state cache layout does not match the adapter");
    }
    this.orderedCellCaches.forEach((cache, cacheIndex) => {
      const orderedIndexes = state.cacheOrders[cacheIndex];
      cache.clear();
      for (const index of orderedIndexes) {
        if (index < 0 || index >= rows.length * cols) {
          throw new Error(`Cache ${cacheIndex} contains invalid cell index ${index}`);
        }
        cache.add(rows[Math.floor(index / cols)][index % cols]);
      }
    });
    if (state.linkageOrders.length !== this.cellLinkageCaches.length) {
      throw new Error("Machine state linkage-cache layout does not match the adapter");
    }
    const cellAt = (index) => rows[Math.floor(index / cols)][index % cols];
    this.cellLinkageCaches.forEach((cache, cacheIndex) => {
      cache.clear();
      for (const [beforeIndex, afterIndexes] of state.linkageOrders[cacheIndex]) {
        for (const afterIndex of afterIndexes) {
          cache.add(cellAt(beforeIndex), cellAt(afterIndex));
        }
      }
    });
  }

  async transition(state, actionButton, maxAgainTicks = 100) {
    this.importState(state);
    this.engine.press(actionButton);

    let ticks = 0;
    do {
      const tickResult = await this.engine.tick();
      ticks += 1;
      if (tickResult.didLevelChange || tickResult.didWinGame) {
        return { state: null, won: true, ticks, againLimit: false };
      }
      if (ticks >= maxAgainTicks && this.engine.hasAgain()) {
        return {
          state: this.exportState(),
          won: false,
          ticks,
          againLimit: true,
        };
      }
    } while (this.engine.hasAgain());

    return {
      state: this.exportState(),
      won: false,
      ticks,
      againLimit: false,
    };
  }
}

module.exports = {
  PuzzleScriptMachineAdapter,
  captureMachineState,
  cloneCells,
  findCellLinkageCaches,
  findOrderedCellCaches,
  normalizeSource,
  parseSavedSprite,
};
