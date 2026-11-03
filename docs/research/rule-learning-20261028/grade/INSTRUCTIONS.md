# Grading instructions: what does the player believe about the game's rules?

An AI model played a grid puzzle game it did not know. It learned the rules only by playing. It kept a notebook
(`world_model.md`) and it thought out loud (its thinking trace). You grade, at a series of checkpoints, which of
the game's true rules the model believes, and how well.

## Your folder

- `rules.json`: the game's true rules (id + text).
- `start.json` (may be missing for the first segment): the labels at the checkpoint just before your segment,
  with the last evidence note per rule. `handoff.md` (may be missing): a short summary of the model's beliefs
  and its own vocabulary at that point, written by the previous grader.
- `cp-NNN.md`: your checkpoints, in order. Each holds the notebook (or says it is unchanged) and all the thinking
  the model wrote since the previous checkpoint. "[after N moves]" tells how many game moves had been played when
  a thought was written.

Read the checkpoints in order and grade each one before moving to the next. Read every checkpoint file in full
(use offset/limit for long files); do not skim by keyword.

## Labels, per rule, at each checkpoint

- `correct`: the model states the rule as its belief, with the essential content right. Its own words are fine
  (it names objects by colour, number or its own terms such as "door", "ring", "wall"); map them by the behaviour
  described, not by the name.
- `partial`: it believes part of the rule, or the right observable effect with a missing or wrong account of
  when it applies (e.g. it knows some steps are refused but gives the wrong cause, or it knows only one case).
- `wrong`: its belief contradicts the rule (it predicts different behaviour in the cases the rule covers), and it
  holds no substantial correct part.
- `absent`: no belief about this rule.

What counts as a belief:
- A statement of fact or conclusion ("So X", "This confirms X", "X blocks Y"), a working assumption the model
  adopts and acts on, or an entry in the notebook stated as a rule, fact or the single leading hypothesis.
- NOT a belief: "maybe", "what if", "let me test whether", questions, open items, or several alternatives listed
  side by side with none adopted.

Persistence: a belief, once stated (in the notebook or the thinking), holds until the model contradicts it,
replaces it, or says it was wrong. Silence, or a notebook rewrite that leaves it out, does not remove it. Passing
doubt ("hmm, not sure") without adopting something else does not remove it. Start each checkpoint from the
previous checkpoint's labels and change a label only when the new text gives a reason.

Order in time: when the notebook is a NEW VERSION at a checkpoint, it was written at the end of that window,
after the thinking shown. When it is unchanged, it is older than the thinking shown. If notebook and thinking
disagree, the newer one wins. If they agree but one is more complete, use the more complete one.

## Fields per rule

- `belief`: the combined label (notebook + thinking, with persistence), as above.
- `source`: which current evidence supports `belief`: `notebook` (the current notebook alone gives this label),
  `thinking` (only the thinking gives it, in this window or carried from earlier thinking), `both`, or `none`
  (for `absent`).
- `notebook`: the label the current notebook text ALONE earns, with no persistence and no thinking (`absent` if
  there is no notebook yet).
- `note`: required whenever `belief` differs from the previous checkpoint (and for every rule at your first
  checkpoint if there is no `start.json`): a quote of at most 20 words that justifies it, prefixed by `N:`
  (notebook) or `T:` (thinking). Otherwise omit it or leave it empty.

## Output

Write `labels.json` in your folder: a JSON list, one object per checkpoint, in order:

```json
[{"cp": 12, "labels": {"M1": {"belief": "correct", "source": "both", "notebook": "correct", "note": "T: ..."}, "...": {}}}]
```

Every checkpoint in your folder, every rule in `rules.json`. Save after each checkpoint so no work is lost.
When done, write `handoff.md`: 5–12 lines on what the model believes at your last checkpoint, in its own words
(what it calls things), and which wrong beliefs it holds. Then run, from the repository root:
`uv run python docs/research/rule-learning-20261028/grade/check.py <your folder>` and fix anything it reports.

Grade only from the text. Do not look at other folders, other runs or any other file in the repository.
