"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  buildIndistinguishablePlacementPdb,
  chainPushSuccessors,
} = require("./pattern_database");

test("chain-push relaxation moves a contiguous line by one cell", () => {
  const valid = new Set([0, 1, 2, 3, 4]);
  const successors = [...chainPushSuccessors([1, 2], 1, 5, valid)];
  assert.ok(successors.some((state) => state.join(",") === "2,3"));
  assert.ok(successors.some((state) => state.join(",") === "0,1"));
});

test("placement PDB returns exact relaxed chain-push distance", () => {
  const valid = new Set([0, 1, 2, 3, 4]);
  const pdb = buildIndistinguishablePlacementPdb({
    rows: 1,
    cols: 5,
    validCells: valid,
    objectCount: 2,
    requiredCells: new Set([3, 4]),
  });
  assert.equal(pdb.lookup([0, 1]), 3);
  assert.equal(pdb.lookup([3, 4]), 0);
});
