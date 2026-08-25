"use strict";

const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");
const { inspectGameSource } = require("../solver");
const { PuzzleScriptMachineAdapter } = require("../machine_state_adapter");
const { compileProfile } = require("./compiled_profiles");

function profileFor(gameId) {
  const source = fs.readFileSync(path.join(
    __dirname,
    "..",
    "..",
    "..",
    "puzzlescript_interface",
    "games",
    gameId,
    "script.txt",
  ), "utf8");
  const inspection = inspectGameSource(source);
  const adapter = new PuzzleScriptMachineAdapter({
    source,
    levelIndex: inspection.firstLevelIndex,
  });
  return compileProfile({
    source,
    gameId,
    gameData: adapter.gameData,
    initialState: adapter.initialState,
  });
}

test("Art of Storage compiles only its rule-relevant state", () => {
  const profile = profileFor("ps_the_art_of_storage-v1");
  assert.equal(profile.name, "compiled_art_of_storage");
  assert.equal(profile.metadata.targetCount, 9);
  assert.equal(profile.heuristic(profile.initial), 12);
});

test("Infected compiles crate infection as an irreversible type change", () => {
  const profile = profileFor("ps_infected-v1");
  assert.equal(profile.name, "compiled_infected");
  const apply = (state, action) => profile.successors(state)
    .find((successor) => successor.action === action).state;
  const pushed = apply(apply(apply(profile.initial, "UP"), "UP"), "RIGHT");
  assert.notEqual(profile.key(pushed), profile.key(profile.initial));
  assert.notEqual(pushed.infected, 0n);
});

test("Self Alteration level one compiles to its single relevant crate", () => {
  const profile = profileFor("ps_self_alteration-v1");
  assert.equal(profile.name, "compiled_self_alteration_level_one");
  assert.equal(profile.metadata.targetCount, 1);
  assert.ok(profile.heuristic(profile.initial) > 0);
});

test("Fire in Winter compiles its movable portal endpoint", () => {
  const profile = profileFor("ps_fire_in_winter-v1");
  assert.equal(profile.name, "compiled_fire_in_winter_level_one");
  assert.equal(profile.metadata.crateCount, 3);
  assert.ok(profile.heuristic(profile.initial) > 0);
});

test("Fuse to Green compiles sliding primary crates and fused crate3", () => {
  const profile = profileFor("ps_fuse_to_green-v1");
  assert.equal(profile.name, "compiled_fuse_to_green_level_one");
  assert.equal(profile.metadata.targetCount, 1);
  assert.equal(profile.heuristic(profile.initial), 1);
});

test("Dark Pellets compiles its two-stage pellet objective", () => {
  const profile = profileFor("ps_dark_pellets-v1");
  assert.equal(profile.name, "compiled_dark_pellets_level_one");
  assert.equal(profile.heuristic(profile.initial), 2);
});

test("Side Painting compiles wall1 paint as shared crate-side state", () => {
  const profile = profileFor("ps_side_painting-v1");
  assert.equal(profile.name, "compiled_side_painting_level_one");
  assert.equal(profile.metadata.targetCount, 2);
  assert.ok(profile.heuristic(profile.initial) > 0);
});
