# Grading instructions: what does the player believe about the game's rules, and how did it get there?

An AI model played a grid puzzle game it did not know, for up to 800 moves. It learned the rules only by playing. It
kept files of its own (its notebook: `notes.md`, plans, scripts, a final `world_model.md`) and it thought out loud
(its thinking trace). You do two things: grade, at a series of checkpoints, which of the game's true rules the model
believes and how well; then explain its reasoning and how it played.

## Your folder: `run-X`, with segments `seg-0`, `seg-1`, ... in order

- `rules.json`: the game's true rules (id + text).
- `start.json` (from the second segment on): the labels at the checkpoint just before this segment, with the last
  evidence note per rule. `handoff.md`: a short summary of the model's beliefs and its own vocabulary at that point,
  which you wrote at the end of the previous segment.
- `cp-NNN.md`: the checkpoints, in order. Each holds the notebook (or says it is unchanged) and all the thinking the
  model wrote since the previous checkpoint. "[after N moves]" tells how many game moves had been played when a
  thought was written. A checkpoint may say that the model's conversation restarted: see Persistence.

Before each segment after the first, run `uv run python docs/research/rule-learning-vast-20261105/grade/ready.py run-X`
from the repository root. It writes that segment's `start.json` and `handoff.md`. Read the checkpoints in order and
grade each one before moving to the next. Read every checkpoint file in full (use offset/limit for long files); do
not skim by keyword. Keep the method the same from the first segment to the last.

## Labels, per rule, at each checkpoint

- `correct`: the model states the rule as its belief, with the essential content right. Its own words are fine (it
  names objects by colour, number or its own terms such as "door", "ring", "wall"); map them by the behaviour
  described, not by the name.
- `partial`: it believes part of the rule, or the right observable effect with a missing or wrong account of when it
  applies (e.g. it knows some steps are refused but gives the wrong cause, or it knows only one case).
- `wrong`: its belief contradicts the rule (it predicts different behaviour in the cases the rule covers), and it
  holds no substantial correct part.
- `absent`: no belief about this rule.

What counts as a belief:
- A statement of fact or conclusion ("So X", "This confirms X", "X blocks Y"), a working assumption the model adopts
  and acts on, or an entry in the notebook stated as a rule, fact or the single leading hypothesis.
- NOT a belief: "maybe", "what if", "let me test whether", questions, open items, or several alternatives listed side
  by side with none adopted.

Persistence: a belief, once stated (in the notebook or the thinking), holds until the model contradicts it, replaces
it, or says it was wrong. Silence, or a notebook rewrite that leaves it out, does not remove it. Passing doubt ("hmm,
not sure") without adopting something else does not remove it. Start each checkpoint from the previous checkpoint's
labels and change a label only when the new text gives a reason. One exception, which the earlier study did not have:
when a checkpoint says the conversation restarted, what the model only thought before that point is gone from its
mind. From there on, a belief holds only if its files still state it or it states it again.

Order in time: when the notebook is a NEW VERSION at a checkpoint, it was written at the end of that window, after the
thinking shown. When it is unchanged, it is older than the thinking shown. If notebook and thinking disagree, the
newer one wins. If they agree but one is more complete, use the more complete one.

## Mistakes earlier graders made on this kind of text

A hand check of 23 labels from the earlier study found three errors. Avoid them:
- Mapping an object to the wrong rule when an early object looks like a later one: walls of early levels described as
  "pit" or "rimmed dark blockers" were read as water. Decide what an object is from the behaviour described.
- A decorative or "does nothing" reading of something the rule does not concern is `absent` for that rule, not
  `wrong`, unless it predicts different behaviour in the cases the rule covers.
- Being too strict on `correct` when the model states the rule from another angle ("a level ends when no bright rings
  remain" states the win rule from the other side).
Also: a rule's description of an ordinary case does not override another rule's exception. Read the rules together.

## Fields per rule

- `belief`: the combined label (notebook + thinking, with persistence), as above.
- `source`: which current evidence supports `belief`: `notebook` (the current notebook alone gives this label),
  `thinking` (only the thinking gives it, in this window or carried from earlier thinking), `both`, or `none` (for
  `absent`).
- `notebook`: the label the current notebook text ALONE earns, with no persistence and no thinking (`absent` if there
  is no notebook yet).
- `note`: required whenever `belief` differs from the previous checkpoint (and for every rule at your first
  checkpoint): a word-for-word quote of at most 20 words that justifies it, prefixed by `N:` (notebook) or `T:`
  (thinking). Otherwise omit it or leave it empty.

## Output per segment

Write `labels.json` in the segment's folder: a JSON list, one object per checkpoint, in order:

```json
[{"cp": 12, "labels": {"M1": {"belief": "correct", "source": "both", "notebook": "correct", "note": "T: ..."}, "...": {}}}]
```

Every checkpoint in the folder, every rule in `rules.json`. Save after each checkpoint so no work is lost. Then write
`handoff.md`: 5–12 lines on what the model believes at the last checkpoint, in its own words (what it calls things),
and which wrong beliefs it holds. Then run, from the repository root:
`uv run python docs/research/rule-learning-20261028/grade/check.py <segment folder>` and fix anything it reports.
Your context may be compacted during this long job: the files you saved are what counts, so work from them.

## Report: `run-X/report.md`, after the last segment

Plain prose and small tables, grounded in the text, with word-for-word quotes and move numbers. No praise for its own
sake and no invented numbers; say so where the text does not settle something.

1. **Result**: the rule table at the end of play (rule, final belief, source, the move where it first became correct).
   Score: correct = 1, partial = 0.5, as a percentage of the rules, at about moves 25, 100, 200, 400 and the end.
2. **How it reasoned**: how it went about learning (what it tested, what it inferred from what), its typical
   reasoning moves, and how it used its notes and scripts.
3. **The turning points**: the moments a key rule was understood or a level won, and what led to each.
4. **Where it went wrong**: each wrong belief that mattered: where it came from, how long it lasted, what it cost in
   moves, and what finally corrected it, if anything. Say whether it failed from a wrong rule, from a planning or
   search failure with the rules right, or from giving up on an idea too early or too late.
5. **Stuck stretches**: long stretches with no progress: what it kept doing and why.
6. **Effect of its memory**: whether what it lost at compactions or restarts cost it anything visible. Compaction
   summaries are not in your files as such; judge from what it knows afterwards.
7. **Method notes**: anything in the text that made a label hard, and the labels you are least sure of.

Grade only from the text in your folder. Do not look at other runs' folders, `output/`, the game's source or any other
file in the repository, apart from this file and the two scripts named here. Do not play the game, start or stop any
run or service, and do not commit. Write only inside your own `run-X` folder.
