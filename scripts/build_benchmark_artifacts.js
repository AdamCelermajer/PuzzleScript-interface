const fs = require("fs");
const path = require("path");
const { Parser, INPUT_BUTTON } = require("puzzlescript");
const { Session } = require("../puzzlescript_interface/runtime/server");

const ROOT = path.resolve(__dirname, "..");
const CATALOG_PATH = path.join(ROOT, "benchmark", "reference-source.json");
const GAMES_ROOT = path.join(ROOT, "benchmark", "games");

const ACTIONS = {
  UP: { arc: "ACTION1", button: INPUT_BUTTON.UP },
  DOWN: { arc: "ACTION2", button: INPUT_BUTTON.DOWN },
  LEFT: { arc: "ACTION3", button: INPUT_BUTTON.LEFT },
  RIGHT: { arc: "ACTION4", button: INPUT_BUTTON.RIGHT },
  ACTION: { arc: "ACTION5", button: INPUT_BUTTON.ACTION },
};

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function frameKey(frame) {
  return JSON.stringify(frame);
}

function sourceLine(source, offset) {
  if (!Number.isInteger(offset) || offset < 0) return null;
  return source.slice(0, offset).split(/\r?\n/).length;
}

function leafRules(rule, output = []) {
  const children = typeof rule.getChildRules === "function"
    ? rule.getChildRules()
    : [];
  if (!children || children.length === 0) {
    if (typeof rule.evaluate === "function") output.push(rule);
    return output;
  }
  for (const child of children) leafRules(child, output);
  return output;
}

function instrumentRules(gameData, source) {
  let active = null;
  const rules = [];
  for (const rootRule of gameData.rules || []) leafRules(rootRule, rules);
  const seen = new Set();
  for (const rule of rules) {
    if (seen.has(rule)) continue;
    seen.add(rule);
    const offset = rule.__source?.sourceOffset;
    const line = sourceLine(source, offset);
    const id = line ? `rule-line-${line}` : `rule-offset-${offset ?? "unknown"}`;
    const original = rule.evaluate.bind(rule);
    rule.evaluate = (...args) => {
      const result = original(...args);
      if (active && Array.isArray(result) && result.length > 0) {
        active.add(id);
      }
      return result;
    };
  }
  return {
    begin() {
      active = new Set();
    },
    end() {
      const result = [...(active || [])].sort();
      active = null;
      return result;
    },
  };
}

async function applyAction(session, action, instrumentation) {
  instrumentation.begin();
  session.engine.press(action.button);
  let won = false;
  let ticks = 0;
  do {
    const tick = await session.engine.tick();
    ticks += 1;
    if (tick.didLevelChange || tick.didWinGame) {
      won = true;
      break;
    }
    if (ticks >= 100 && session.engine.hasAgain()) {
      throw new Error("AGAIN tick limit reached");
    }
  } while (session.engine.hasAgain());
  return {
    won,
    ticks,
    firedRuleIds: instrumentation.end(),
  };
}

function chooseProbes(candidates, limit = 10) {
  const remaining = [...candidates];
  const chosen = [];
  const covered = new Set();
  while (remaining.length > 0 && chosen.length < limit) {
    remaining.sort((left, right) => {
      const leftNew = left.fired_rule_ids.filter((id) => !covered.has(id)).length;
      const rightNew = right.fired_rule_ids.filter((id) => !covered.has(id)).length;
      if (rightNew !== leftNew) return rightNew - leftNew;
      if (right.solution_relevant !== left.solution_relevant) {
        return Number(right.solution_relevant) - Number(left.solution_relevant);
      }
      if (right.fired_rule_ids.length !== left.fired_rule_ids.length) {
        return right.fired_rule_ids.length - left.fired_rule_ids.length;
      }
      return left.selection_order - right.selection_order;
    });
    const candidate = remaining.shift();
    chosen.push(candidate);
    for (const id of candidate.fired_rule_ids) covered.add(id);
  }
  return chosen;
}

function sameSequence(left, right) {
  return left.length === right.length
    && left.every((value, index) => value === right[index]);
}

function uniqueTransitionCandidates(candidates) {
  const unique = [];
  const seen = new Set();
  for (const candidate of candidates) {
    const key = `${frameKey(candidate.before_frame)}|${candidate.action}|${frameKey(candidate.expected_frame)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(candidate);
  }
  return unique;
}

async function replaySequence(gameData, gameId, levelIndex, sequence, instrumentation) {
  const session = new Session(
    `${gameId}-probe-${sequence.join("-") || "start"}`,
    gameData,
    levelIndex,
  );
  for (const actionName of sequence) {
    const result = await applyAction(session, ACTIONS[actionName], instrumentation);
    if (result.won) return { session, won: true };
  }
  return { session, won: false };
}

async function exploreTransitions(
  game,
  gameData,
  levelIndex,
  reference,
  instrumentation,
  solutionStateKeys,
) {
  const queue = [[]];
  const visitedStates = new Set();
  const candidates = [];
  const seenTransitions = new Set();
  const maxDepth = 4;
  let order = 100000;

  while (queue.length > 0 && candidates.length < 80) {
    const sequence = queue.shift();
    const replay = await replaySequence(
      gameData,
      game.game_id,
      levelIndex,
      sequence,
      instrumentation,
    );
    if (replay.won) continue;
    const before = replay.session.renderIntGrid();
    const beforeKey = frameKey(before);
    if (visitedStates.has(beforeKey)) continue;
    visitedStates.add(beforeKey);

    for (const [actionName, action] of Object.entries(ACTIONS)) {
      const branch = await replaySequence(
        gameData,
        game.game_id,
        levelIndex,
        sequence,
        instrumentation,
      );
      const result = await applyAction(branch.session, action, instrumentation);
      if (result.won) continue;
      const after = branch.session.renderIntGrid();
      if (
        before.length !== after.length
        || !before.every((row, rowIndex) => row.length === after[rowIndex].length)
      ) {
        continue;
      }
      const transitionKey = `${beforeKey}|${action.arc}|${frameKey(after)}`;
      if (seenTransitions.has(transitionKey)) continue;
      seenTransitions.add(transitionKey);
      const expectedAction = reference.path[sequence.length];
      const solutionRelevant = sameSequence(
        sequence,
        reference.path.slice(0, sequence.length),
      ) && actionName === expectedAction;
      candidates.push({
        probe_id: `level-${levelIndex}-explore-${candidates.length + 1}`,
        level_index: levelIndex,
        solution_step: solutionRelevant ? sequence.length + 1 : null,
        before_frame: before,
        action: action.arc,
        action_name: actionName,
        expected_frame: after,
        fired_rule_ids: result.firedRuleIds.length > 0
          ? result.firedRuleIds
          : [frameKey(before) === frameKey(after) ? "engine-noop" : "engine-movement"],
        solution_relevant: solutionRelevant,
        source_state_on_solution_trace: solutionStateKeys.has(beforeKey),
        selection_order: order,
      });
      order += 1;
      if (
        sequence.length + 1 < maxDepth
        && frameKey(before) !== frameKey(after)
      ) {
        queue.push([...sequence, actionName]);
      }
    }
  }
  return candidates;
}

async function buildLevelArtifact(game, source, levelIndex, reference) {
  const normalizedSource = source.replace(/\r\n?/g, "\n");
  const parsed = Parser.parse(normalizedSource);
  if (parsed.errors && parsed.errors.length > 0) {
    throw new Error(parsed.errors.map((error) => error.message).join("; "));
  }
  const instrumentation = instrumentRules(parsed.data, normalizedSource);
  const session = new Session(
    `${game.game_id}-artifact-${levelIndex}`,
    parsed.data,
    levelIndex,
  );
  const initialFrame = session.renderIntGrid();
  const depth = reference.path.length;
  const trace = [{
    step: 0,
    frame: initialFrame,
    frame_key: frameKey(initialFrame),
    remaining_actions: depth,
    closeness: depth === 0 ? 1 : 0,
  }];
  const candidates = [];
  let replayVerified = false;

  for (const [index, actionName] of reference.path.entries()) {
    const action = ACTIONS[actionName];
    if (!action) throw new Error(`Unsupported saved action: ${actionName}`);
    const before = session.renderIntGrid();
    const result = await applyAction(session, action, instrumentation);
    const after = session.renderIntGrid();
    const step = index + 1;

    if (!result.won) {
      trace.push({
        step,
        frame: after,
        frame_key: frameKey(after),
        remaining_actions: depth - step,
        closeness: depth === 0 ? 1 : Number((step / depth).toFixed(6)),
      });
    }

    if (
      !result.won
      && frameKey(before) !== frameKey(after)
      && before.length === after.length
      && before.every((row, rowIndex) => row.length === after[rowIndex].length)
    ) {
      candidates.push({
        probe_id: `level-${levelIndex}-step-${step}`,
        level_index: levelIndex,
        solution_step: step,
        before_frame: before,
        action: action.arc,
        action_name: actionName,
        expected_frame: after,
        fired_rule_ids: result.firedRuleIds.length > 0
          ? result.firedRuleIds
          : ["engine-movement"],
        solution_relevant: true,
        source_state_on_solution_trace: true,
        selection_order: step,
      });
    }

    if (result.won) {
      replayVerified = step === depth;
      break;
    }
  }

  const solutionStateKeys = new Set(trace.map((item) => item.frame_key));
  const explored = await exploreTransitions(
    game,
    parsed.data,
    levelIndex,
    reference,
    instrumentation,
    solutionStateKeys,
  );
  const candidatePool = [...candidates, ...explored];
  let preview = chooseProbes(uniqueTransitionCandidates(candidatePool));
  if (preview.length < 10) {
    for (
      let otherLevel = 0;
      otherLevel < parsed.data.levels.length && preview.length < 10;
      otherLevel += 1
    ) {
      if (
        otherLevel === levelIndex
        || parsed.data.levels[otherLevel].type !== "LEVEL_MAP"
      ) {
        continue;
      }
      const otherLevelCandidates = await exploreTransitions(
        game,
        parsed.data,
        otherLevel,
        { path: [] },
        instrumentation,
        new Set(),
      );
      candidatePool.push(...otherLevelCandidates);
      preview = chooseProbes(uniqueTransitionCandidates(candidatePool));
    }
  }
  const mergedCandidates = uniqueTransitionCandidates(candidatePool);
  const probes = chooseProbes(mergedCandidates);
  const eligibleRules = [...new Set(
    mergedCandidates.flatMap((candidate) => candidate.fired_rule_ids),
  )].sort();
  const coveredRules = [...new Set(
    probes.flatMap((probe) => probe.fired_rule_ids),
  )].sort();
  const coverageLevels = [...new Set(
    probes.map((probe) => probe.level_index),
  )].sort((left, right) => left - right);

  return {
    solution: {
      schema_version: 1,
      game_id: game.game_id,
      level_index: levelIndex,
      method: reference.method,
      claim: reference.claim,
      replay_verified: replayVerified,
      action_count: depth,
      actions: reference.path,
    },
    ruleProbes: {
      schema_version: 1,
      game_id: game.game_id,
      level_index: levelIndex,
      selection: "verified_solution_then_bounded_rule_coverage",
      requested_probes: 10,
      available_probes: probes.length,
      coverage_levels: coverageLevels,
      eligible_rule_families: eligibleRules,
      covered_rule_families: coveredRules,
      probes,
    },
    closeness: {
      schema_version: 1,
      game_id: game.game_id,
      level_index: levelIndex,
      mode: "replay_verified_solution_trace",
      exact_for: "states matching this saved shortest solution trace",
      unavailable_for: "off-trace states",
      initial_distance: depth,
      replay_verified: replayVerified,
      trace,
    },
  };
}

async function main() {
  const catalog = JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8"));
  const index = {
    benchmark_id: "puzzlescript-world",
    version: "0.4.0",
    generated_from: path.relative(ROOT, CATALOG_PATH).replaceAll("\\", "/"),
    game_count: catalog.games.length,
    tracks: ["rule_learning", "closeness"],
    games: [],
  };

  for (const game of catalog.games) {
    const sourcePath = path.join(
      ROOT,
      "puzzlescript_interface",
      "games",
      game.game_id,
      "script.txt",
    );
    const source = fs.readFileSync(sourcePath, "utf8");
    const levelIndex = Number(game.reference.level_index);
    const artifacts = await buildLevelArtifact(
      game,
      source,
      levelIndex,
      game.reference,
    );
    const gameRoot = path.join(GAMES_ROOT, game.game_id);
    const levelRoot = path.join(
      gameRoot,
      "levels",
      `level-${String(levelIndex).padStart(3, "0")}`,
    );

    writeJson(path.join(gameRoot, "game.json"), {
      schema_version: 1,
      game_id: game.game_id,
      source_game: path.relative(ROOT, sourcePath).replaceAll("\\", "/"),
      max_actions: game.max_actions,
      artifact_status: artifacts.solution.replay_verified
        ? "replay_verified"
        : "invalid",
      level_artifacts: [{
        level_index: levelIndex,
        directory: `levels/level-${String(levelIndex).padStart(3, "0")}`,
        solution_actions: artifacts.solution.action_count,
        replay_verified: artifacts.solution.replay_verified,
        rule_probes: artifacts.ruleProbes.available_probes,
        requested_rule_probes: artifacts.ruleProbes.requested_probes,
        closeness_mode: artifacts.closeness.mode,
      }],
    });
    writeJson(path.join(levelRoot, "solution.json"), artifacts.solution);
    writeJson(path.join(levelRoot, "rule-probes.json"), artifacts.ruleProbes);
    writeJson(path.join(levelRoot, "closeness.json"), artifacts.closeness);
    index.games.push({
      game_id: game.game_id,
      directory: game.game_id,
      artifact_status: artifacts.solution.replay_verified
        ? "replay_verified"
        : "invalid",
      levels: 1,
      rule_probes: artifacts.ruleProbes.available_probes,
    });
  }

  writeJson(path.join(GAMES_ROOT, "index.json"), index);
  process.stdout.write(
    `Built ${index.game_count} benchmark game artifact folders.\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
