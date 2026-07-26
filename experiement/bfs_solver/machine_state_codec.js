"use strict";

class OrderedCellCodec {
  constructor(rows, cols) {
    this.rows = rows;
    this.cols = cols;
    this.signatureToId = new Map();
    this.idToTokens = [];
  }

  encode(cells) {
    const encoded = new Uint16Array(this.rows * this.cols);
    let offset = 0;
    for (const row of cells) {
      for (const tokens of row) {
        const signature = tokens.join("\u0000");
        let id = this.signatureToId.get(signature);
        if (id === undefined) {
          id = this.idToTokens.length;
          if (id >= 0xffff) throw new Error("Ordered cell dictionary is too large");
          this.signatureToId.set(signature, id);
          this.idToTokens.push(tokens.slice());
        }
        encoded[offset++] = id;
      }
    }
    return encoded;
  }

  decode(encoded) {
    const cells = [];
    let offset = 0;
    for (let rowIndex = 0; rowIndex < this.rows; rowIndex += 1) {
      const row = [];
      for (let colIndex = 0; colIndex < this.cols; colIndex += 1) {
        row.push(this.idToTokens[encoded[offset++]].slice());
      }
      cells.push(row);
    }
    return cells;
  }
}

function encodeLengthPrefixed(groups) {
  const words = [];
  for (const group of groups) {
    if (group.length >= 0xffff) throw new Error("Machine-state group is too large");
    words.push(group.length);
    for (const value of group) {
      if (value < 0 || value >= 0xffff) {
        throw new Error(`Machine-state cell index is out of range: ${value}`);
      }
      words.push(value);
    }
  }
  return Uint16Array.from(words);
}

function decodeLengthPrefixed(words, groupCount) {
  const groups = [];
  let offset = 0;
  for (let groupIndex = 0; groupIndex < groupCount; groupIndex += 1) {
    const length = words[offset++];
    groups.push(Array.from(words.slice(offset, offset + length)));
    offset += length;
  }
  if (offset !== words.length) throw new Error("Trailing words in machine-state groups");
  return groups;
}

function encodeLinkages(linkageOrders) {
  const words = [];
  for (const linkage of linkageOrders) {
    if (linkage.length >= 0xffff) throw new Error("Too many linkage entries");
    words.push(linkage.length);
    for (const [beforeIndex, afterIndexes] of linkage) {
      if (beforeIndex >= 0xffff || afterIndexes.length >= 0xffff) {
        throw new Error("Linkage entry exceeds Uint16 capacity");
      }
      words.push(beforeIndex, afterIndexes.length, ...afterIndexes);
    }
  }
  return Uint16Array.from(words);
}

function decodeLinkages(words, linkageCount) {
  const linkages = [];
  let offset = 0;
  for (let linkageIndex = 0; linkageIndex < linkageCount; linkageIndex += 1) {
    const entryCount = words[offset++];
    const entries = [];
    for (let entryIndex = 0; entryIndex < entryCount; entryIndex += 1) {
      const beforeIndex = words[offset++];
      const afterCount = words[offset++];
      const afterIndexes = Array.from(words.slice(offset, offset + afterCount));
      offset += afterCount;
      entries.push([beforeIndex, afterIndexes]);
    }
    linkages.push(entries);
  }
  if (offset !== words.length) throw new Error("Trailing words in linkage state");
  return linkages;
}

function bytesKey(words) {
  return Buffer.from(words.buffer, words.byteOffset, words.byteLength).toString("base64");
}

class MachineStateCodec {
  constructor(initialState) {
    const rows = initialState.cells.length;
    const cols = initialState.cells[0]?.length ?? 0;
    this.cellCodec = new OrderedCellCodec(rows, cols);
    this.cacheCount = initialState.cacheOrders.length;
    this.linkageCount = initialState.linkageOrders.length;
  }

  encode(state) {
    if (state.cacheOrders.length !== this.cacheCount) {
      throw new Error("Machine-state cache count changed");
    }
    if (state.linkageOrders.length !== this.linkageCount) {
      throw new Error("Machine-state linkage count changed");
    }
    return {
      levelIndex: state.levelIndex,
      pendingInput: state.pendingInput,
      hasAgain: state.hasAgain,
      cells: this.cellCodec.encode(state.cells),
      caches: encodeLengthPrefixed(state.cacheOrders),
      linkages: encodeLinkages(state.linkageOrders),
    };
  }

  decode(encoded) {
    return {
      levelIndex: encoded.levelIndex,
      pendingInput: encoded.pendingInput,
      hasAgain: encoded.hasAgain,
      cells: this.cellCodec.decode(encoded.cells),
      cacheOrders: decodeLengthPrefixed(encoded.caches, this.cacheCount),
      linkageOrders: decodeLinkages(encoded.linkages, this.linkageCount),
    };
  }

  key(encoded) {
    return [
      encoded.levelIndex,
      encoded.pendingInput ?? "",
      encoded.hasAgain ? 1 : 0,
      bytesKey(encoded.cells),
      bytesKey(encoded.caches),
      bytesKey(encoded.linkages),
    ].join("|");
  }

  byteLength(encoded) {
    return encoded.cells.byteLength
      + encoded.caches.byteLength
      + encoded.linkages.byteLength;
  }
}

module.exports = {
  MachineStateCodec,
  decodeLengthPrefixed,
  decodeLinkages,
  encodeLengthPrefixed,
  encodeLinkages,
};
