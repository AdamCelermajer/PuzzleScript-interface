# Harness² with one task per level: feasibility

21 Oct 2026. This is a read-only investigation: no code was changed and nothing was launched. The only live calls were throwaway ARC sessions on port 8000 (scorecards tagged `throwaway-level-probe`, then closed).

**Short answer:** yes, and the work is small. The game stack can already start at level k: the Node runtime and the ARC service both accept a start index. Only the Python client and the agent driver fail to pass it through. Upstream Harness² already has the per-level shape: tasks, a per-domain library, and a driver that runs tasks in order (`run_domain`). Our wrapper skips all of that today, because it treats the whole game as one task. Expect about 3 days of work, done in the order in section 6.

---

## 1. Starting at level k

### What exists

- **Node runtime.** `POST /init` takes `levelIndex` (`puzzlescript_interface/runtime/server.js:524-541`). The `Session` constructor calls `engine.setLevel(levelIndex)` and then `skipMessageLevels()` (`server.js:116-133`, `135-147`). `skipMessageLevels()` records `lastPlayableLevelIndex`, and RESET returns to that level (`server.js:457-461`). So a reset stays on level k.
- **ARC service.** `ResetRequest.level_index` (`puzzlescript_interface/api/app.py:69-73`) is forwarded on the first RESET, the one without a `guid` (`app.py:206-212`), to `PuzzleScriptClient.start_game(level_index=...)` (`puzzlescript_interface/api/client.py:51-57`). The workbench's manual play already uses it (`workbench/benchmarks.py:446-452`).
- **Agent driver.** `--start` is **not** a level. It names the Baseline start *folder* that gets copied into the agent's working folder (`frameworks/baseline/agent.py:383`, `frameworks/baseline/framework.py:9-10, 32-33`). `--stop-after-levels N` ends the game once `levels_completed >= N` and never shows the next level (`agent.py:141-146`, `223-234`).

### What is missing

1. **Client env.** `LocalArcEnvironmentWrapper.reset()` never sends `level_index` (`client/arc/arcade_env.py:94-99`), and `ArcadeEnv` has no parameter for it (`arcade_env.py:136-176`, `262`). The fix is one optional `level_index` that is sent only on the first RESET, before a guid exists. Later resets already stay on level k.
2. **Agent driver.** It needs a `--start-level k` flag that reaches `ArcadeEnv(...)` (`agent.py:398`). `GameServer.__init__` makes the first `env.reset()` call (`agent.py:125`), and every later `reset` command goes through the guid path.
3. **Raw index versus playable index.** `levelIndex` counts entries in `gameData.levels`, and message entries count too. Playable levels are counted only by `countPlayableLevels` / `countCompletedPlayableLevels` (`runtime/arc_projection.js:112-121`). Modality has no messages, so raw and playable indices agree there. In `ps_enclosed-v1`, raw indices 0 to 3 all open the same first playable level. Before the per-level run uses any other game, either the Node runtime should accept a playable index, or Python should map one to the other. The workbench manual-play check bounds `level` by the playable count but sends it as a raw index (`benchmarks.py:447-452`), so it has the same latent bug for games with messages.
4. **Out-of-range index.** It returns HTTP 500 `Cannot read properties of undefined (reading 'type')` instead of a 400. The cause is `skipMessageLevels` reading `levels[k].type` before its range check (`server.js:137-138`).

### Live test (throwaway sessions, ARC service on 8000)

| Probe | Result |
|---|---|
| Modality `level_index` 0/1/2/3 | grids 3×5, 5×5, 6×6, 9×11 (four different levels); `levels_completed` = 0/1/2/3; `win_levels` = 4 |
| Modality `level_index` 4, 5 | HTTP 500 (see point 4 above) |
| Start at level 3, ACTION7 (undo) right away | grid unchanged, still level 3: undo cannot reach level 2 |
| Same-guid RESET after moves | back to the level 3 start board |
| `ps_enclosed-v1` raw 0–3 | all the same first playable level (messages at raw 0–2) |
| Scorecard after the level 3 probe | `score: 2`: the skipped levels count as completed |

### What starting at level k reveals

Earlier boards are never shown: the start, undo and reset all stay on level k. The level's position and the total count are visible, though:

- `levels_completed` starts at k−1 and `win_levels` is the full count. The player sees `levels=2/4` on its first `look` (`agent.py:158-167`), `LEVEL COMPLETED (3/4)` (`agent.py:233-236`), and `levels {levels}/{total}` in the continue, restart and report prompts (`agent.py:89-105`, `338-339`).
- The prompts say "Complete as many levels as possible" (`agent.py:79`; adapter `task_prompt`, `frameworks/harness2/adapter.py:109-111`). `SOLVER_PROMPT` asks for a solver "from the very first level" (`agent.py:92-98`).
- The coach's trajectory begins "completed X of N levels" and lists absolute level numbers (`adapter.py:161-170`, `level_times` at `37-46`).

Does it matter? It doesn't leak content. It does tell the player "you are on level 3 of 4, there were earlier levels", and the coach sees N. For a clean per-level task, the game server should report levels relative to the start (`levels=0/1`), and the per-level prompts should drop "as many levels". The scorecard's inflated score isn't used by our runs (results come from `result.json`), but don't read it for per-level runs.

## 2. Ending a level and its budget

- **Already works:** `--stop-after-levels` is absolute. Starting at level k (`levels_completed = k−1`) with `stop_after_levels = k` ends the run exactly when level k is won, and level k+1 is withheld (`agent.py:141-146`, `184-191`). `--max-steps` is the action budget and ends with `step_budget_exhausted` (`agent.py:146-156`). The Harness² adapter already passes both (`adapter.py:146-152`).
- **A per-level task needs:**
  - **A budget per level.** The shortest solutions for Modality are computed by `studies/thursday/modality.py:134` (`optimum_moves()`, 6/33/66/158). Other games would need the BFS results in `experiement/bfs_solver/*results*.json` (`levelIndex` there should be checked as raw or playable), or a hand-written list. `Option` supports only `int | str | bool` (`frameworks/base.py:14`), so the cleanest launch option is an int `level_budget_multiple` plus a per-game optimum table, or a str such as `"18,99,198,474"`.
  - **A "solved" flag that means "this level".** `solved` in `result.json` means the whole game (`agent.py:132-134`). Per level, the score is `levels_completed >= k` (equivalently `reason == level_target_reached`), then action count.
  - **A decision on the end-of-rollout turns.** Every rollout ends with a world-model report turn and a `solver.py` turn (`agent.py:342-345`). With 5 rollouts per level, both turns cost tokens 5× per level. The report feeds the coach (`adapter.py:179-187`). The solver turn could be skipped per level.

## 3. Upstream Harness² multi-task support

How it works (`.venv/Lib/site-packages/harness2/core/`):

- **Tasks.** The adapter lists `tasks()` and maps each one to a `domain_of()` (`spec.py:201-247`). `schedule.task_stream` groups tasks by domain and orders them (`schedule.py:736-777`, `stream_order` `130-163`).
- **One task.** `schedule.run_task` (`schedule.py:566-666`) rolls k base rollouts with the adapter's **fixed** base harness (`617`), runs the recursion mode with `library_dir` (`499-511`), selects a final, then calls `selection.reflect_adoption` (`529-538`). That is one extra coach session, which writes `cue/lesson/evidence` (`selection.py:402-451`, `_distil` `454+`). Only then does it call `Library.add` (`555-563`).
- **Library.** `Library` lives at `<root>/<domain>/` with `INDEX.md` and `harnesses/<task>/{harness/, EXPERIENCE.md}` (`library.py:189-313`). `add()` **writes nothing** unless the experience has `cue`, `lesson` and `evidence` (`library.py:252-253`). `context_dir()` returns the library only once some entry exists (`211-213`). `context.build` copies it into each coach's `context/library/` (`context.py:161-165`).
- **Tasks in order.** `run_domain` (`schedule.py:669-733`) runs tasks in order, calls `lib.retain(task_ids[:i-1])` so a task sees only earlier tasks (`700-701`), and catches each task's exception so the next task still runs (`727-729`).
- **"Sequential" means two different things.** Our option `recursion: sequential` is upstream's **depth** mode (k nested passes on one task, `recursion.py:452-566`). Levels in order are a separate idea: upstream's task stream / `run_domain`.

Is a domain with several tasks supported as is? Yes. One game is one domain, each level is one task, and `run_domain` threads the library forward. Three things stop us from calling `run_domain` / `run_task` directly:
- `_write_summary` uses `fcntl` (`schedule.py:294`). That works in our Linux container but not on the Windows host.
- `run_task` uses upstream's run-id namespace and directory scheme (`Namespace`, `schedule.py:84-108`), which our workbench doesn't read.
- At k=1 it adopts the k final (`agg1`/`c1`) via `trivial_selection`, not by our score rank (`frameworks/harness2/run.py:274-283`). Our wrapper's adoption across all rollouts, including base, would be lost.

**Recommended:** keep our `run.py` and add a level loop that reuses the upstream pieces: `Library`, `recursion.run_mode(..., library_dir=...)` and `selection.reflect_adoption`. Our `run()` already calls `recursion.run_mode` but never passes `library_dir` (`run.py:306-307`). `run_parallel` and `run_sequential` both accept it (`recursion.py:353`, `462`).

### Passing a level's adopted harness on: two choices

- **(A) Upstream semantics.** Every level starts from the same empty base. Earlier levels' adopted harnesses and lessons are only *visible* to coaches in `context/library/`. This is what `run_task` does (`schedule.py:617`). It needs a `reflect_adoption` session per level; without a lesson, nothing enters the library.
- **(B) Carry forward.** Level k's base harness is level k−1's adopted tree, written into `levels/Lk/base` before the level's adapter starts. `adapter.base_harness()` returns `root/"base"` (`adapter.py:116-117`), so the base rollout, the coach fallbacks and the diffs then all start from the carried harness. The library can be kept as well.

The plan below works with either choice; the choice decides what `levels/Lk/base` holds.

### Where to skip rollouts whose harness is unchanged

Every rollout goes through `recursion._roll` → `adapter.execute(task_id, harness_dir, run_id)` (`recursion.py:260-300`, `303-340`). A stage that **fell back** gets `tree = dict(fallback)` (`recursion.py:242-251`). A stage the coach left **unchanged** is flagged `kept_base` (`119-120`). In parallel mode both are identical to the base tree. In sequential mode both are identical to the previous `c{t-1}`.

**The skip point is `PuzzleScriptAdapter.execute`** (`adapter.py:127-156`). Fingerprint the harness tree (`harness_tree.read_tree` of `harness_dir`, or the base when it is None). If a rollout with the same fingerprint already completed in this level, write `rollouts/<label>/reused.json` (`{"same_as": "base1"}`) and return that earlier run directory.
- The ledger stays valid: it counts labels, not runs (`ledger.py:89-113`).
- Adoption ties go to the base label (`run.py:281`).
- Resume stays safe if `reused.json` is checked before the "retry from fresh" branch (`adapter.py:131-136`).
- `_roll_many` runs inv/dom in parallel threads (`recursion.py:328-336`), so the fingerprint map needs a lock.
- **Don't skip `final`**: it is the independent measurement of the adopted harness (`run.py:317`). That can become an option later.

## 4. Control

- **Stop and resume.** Harness² already restarts with `restart="resume"` (`frameworks/harness2/framework.py:239`, `check_restart` `214-225`). On resume:
  - Completed rollouts are reused (`adapter.py:131-132`).
  - A rollout killed mid-play is deleted and rerun fresh (`adapter.py:135-136`).
  - Coach sessions are served from the proposer cache. Its key includes the label, the mission and the context contents (`core/proposer.py:143-147`).

  Per level, the loop skips levels whose `levels/Lk/result.json` exists. The library on disk carries over. Write the library entry *before* the level's `result.json`, so that a stop between the two steps leaves nothing half-written.
- **Per-level results.** Each `levels/Lk/` gets today's files (`adoption.json`, `recursion.json`, `result.json`, `run.py:308-324`). A top-level `result.json` lists, for each level: solved, actions, the adopted label, and which rollouts were reused. For the run list, put `levels_completed` = the number of levels solved.
- **A level never solved.** The next level still runs, because each level starts directly via `level_index` and doesn't depend on the previous one being won. The library still gets the level's adopted harness and lesson, from a failure. What does stop a level today is an error: `run()` raises if no base rollout completes (`run.py:304-305`) or if the final rollout fails (`run.py:319-320`). The loop must catch that per level, record `status: error`, and go on, as `run_domain` does (`schedule.py:727-729`). Optionally add a `stop_on_unsolved` option.

## 5. Workbench

- **Layout.** If each level runs in `levels/Lk/` with today's per-run layout (`rollouts/`, `improver/`, `harnesses/`, `adoption.json`), the existing views work unchanged on a sub-path:
  - `/record` already accepts nested ids; the rollout view uses `${runId}/rollouts/${label}` (`website/app/src/views/Harness2Detail.tsx:84`).
  - `coach_sessions`, `harness_edits` and `harness_diffs` read `improver/` and `harnesses/` under whatever path they get (`workbench/harness2_view.py:29-89`).
  - The coach-session endpoint resolves `run_path(run)/improver/...` (`workbench/experiments.py:708-717`).

  A shared `improver/` folder would mix the levels: `harness_edits` keys by `folder.name.split(".")[0]` (`harness2_view.py:67`), so `inv1` from L1 and from L2 would collide.
- **Catalog.** `harness2_rollouts` globs `rollouts/*` and sets `total = 4k+1` (`workbench/catalog.py:286-295`, used at `425`). For a per-level run, glob `levels/*/rollouts/*`, set total = levels × (4k+1), count `reused.json` as done, and show the current level.
- **Record API.** `/record` returns `rollouts`, `adoption` and the coach views from the run root (`experiments.py:689-706`). For a per-level run, add `levels: [{level, budget, solved, actions, adopted, reused}]` from `levels/*/result.json`.
- **Run page.** `RunDetail.tsx:34` picks `Harness2Detail` by framework. Add a level strip on top: L1…Ln, each with solved/actions/adopted. Picking a level renders the existing `Harness2Detail` with `runId = ${runId}/levels/Lk`. Mark reused rollouts ("same harness as base1, not rerun"). Show the library (`library/<mode>/<game>/INDEX.md`, `EXPERIENCE.md`) as one more card.
- **Launch.** Options come from `Framework.options` through `GET /api/workbench/frameworks` (`frameworks/base.py:101-104`; `website/app/src/lib/launch.ts:49`), so new options appear in the launch form with no UI work:
  - `per_level: bool`
  - `level_budget_multiple: int`
  - `carry_harness: bool` (choice A or B)
  - `skip_unchanged: bool`

  Add them in `frameworks/harness2/framework.py:232-238` and in the argv of `run.py:main`.

## 6. Plan (smallest changes, in order)

| # | Change | Files | Effort |
|---|---|---|---|
| 1 | `level_index` in the client env (first RESET only) | `client/arc/arcade_env.py` | 1 h |
| 2 | `--start-level k` in the agent driver; levels reported relative to the start (`0/1`), per-level prompt wording, optional skip of the solver turn | `frameworks/baseline/agent.py` | 3 h |
| 3 | Playable→raw level mapping, and 400 for an out-of-range index (Modality works without this) | `runtime/server.js` (or Python mapping) | 2 h |
| 4 | Per-level adapter: task ids `L1..Ln`, `execute` passes start level, `stop_after_levels=k`, budget k; per-level task prompt and yardstick; trajectory says "solved / not solved in A of B actions"; adoption ranks on solved-this-level | `frameworks/harness2/adapter.py`, `run.py` (`adopt`) | 4 h |
| 5 | Skip unchanged / fell-back rollouts in `execute` (fingerprint + lock + `reused.json`) | `frameworks/harness2/adapter.py` | 3 h |
| 6 | Level loop in `run.py`: `levels/Lk/` per level, `Library` + `library_dir`, `reflect_adoption` per level, choice A or B, per-level error handling, top-level result, resume by level | `frameworks/harness2/run.py`, `framework.py` | 1 day |
| 7 | Workbench: catalog progress over levels, `levels` in `/record`, level strip + library card, reused marker | `workbench/catalog.py`, `workbench/experiments.py`, `Harness2Detail.tsx`, `api/types.ts` | 0.5–1 day |
| 8 | Tests: fake-player runs of the loop (resume mid-level, unsolved level, all stages fell back), env level start | `frameworks/harness2/tests/`, `tests/workbench/` | in each step |

About 3 days in total. Steps 1–2 can be checked alone by running one Baseline-agent rollout from level 3, and steps 4–6 by a fake-player test before any paid run.

### Risks

- **Empty library.** `Library.add` silently stores nothing when `reflect_adoption` returns no lesson (`library.py:252-253`), and later coaches then see no library. Log it per level; choice B still carries the harness itself.
- **Cost.** Per level: 4k+1 rollouts, 3k coach sessions, plus one reflect session. At k=1 over 4 Modality levels that is up to 20 rollouts and 16 coach sessions, against 5 + 3 today. Skipping unchanged stages and dropping the solver turn win part of it back. Level 1's budget is tiny (6 × multiple), so its rollouts are short.
- **Small budgets.** With a 3× multiple, L1 gives 18 actions. The base player may spend them all on exploration, leaving the coach thin evidence.
- **The position is still visible** unless step 2 makes levels relative. Today's prompts say "as many levels as possible" and show `2/4`.
- **Message levels.** Any game other than Modality needs step 3 first; check by grid size, as in the `ps_enclosed-v1` probe.
- **Reused rollouts as evidence.** A reused rollout appears in the agg/compose pool under the stage's label, with the base's trajectory. That is correct, because the harness is identical, but it isn't an independent sample. The stage's decision note already says it fell back.
- **Upstream drift.** The plan uses `recursion.run_mode`, `Library` and `selection.reflect_adoption` at the pinned commit (`run.py:256`). `_roll` is private, and our `run.py` already calls it (`run.py:302`).
