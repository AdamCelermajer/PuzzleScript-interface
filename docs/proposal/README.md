# M.Sc proposal (Overleaf draft)

Live project (created and compiled with XeLaTeX on 2026-10-13): https://www.overleaf.com/project/6ace1aad76649cafbf02bf40 . Local files and Overleaf are separate copies; edits are not automatically synchronised.

1. Zip this folder (`main.tex`, `refs.bib`, `latexmkrc`, `figures/`) and upload it to Overleaf (New Project → Upload Project). `proposal-draft.pdf` is a local Tectonic (XeTeX) build for preview.
2. Set **Settings → Compiler → XeLaTeX** and **TeX Live version → 2025** (`latexmkrc` already selects XeLaTeX). The 2026 distribution produced a `UseMathForPositioningText` compatibility error in the Hebrew/table packages. The Hebrew text uses the Culmus font "David CLM" and falls back to other fonts if it is missing.
3. The revised body (Introduction through Work Plan and Deliverables) is 9 pages. The page limit is 10, not counting the bibliography. The title page and contents are separate.
4. The proposal centers on rule learning: a small model will infer game dynamics from images, integer grids and state transitions, then use the learned rules to solve puzzles. Main game-playing conditions provide both image and grid observations. Text-only conditions in the separate goal-recognition study remain explicitly identified.
5. Student: Adam Celermajer / אדם סלרמאג'ר. Supervisors: Prof. Gal Kaminka and Prof. Yoav Goldberg. Completed work is organized by contribution and evidence, without historical month labels.
6. The experimental order is the Qwen family comparison, AVO follow-ups, bottleneck interventions, construction and ablation of the small-model rule-learning harness, then held-out validation. Planned experiments and correctness annotation are research stages, not missing editorial sections.
7. The bibliography contains the nine sources cited in the proposal. Unused entries and their old verification notes have been removed; the earlier bibliography is preserved with the previous revision under `tmp/pdfs/`.
