# Goal Recognition Study

This folder owns the active goal-recognition study: collection code, prompts, model outputs, review tools, docs, and the static results website.

## Layout

- `experiment/` - current 3-shot/openrouter goal-recognition experiment code and prompt builders.
- `review/` - manual review and reporting utilities for prediction outputs.
- `website/` - static result viewer and bundled viewer data.
- `dataset/` - curated game-pool definition for the study.
- `docs/` - study-specific design notes and historical plans.

## Commands

Prepare or inspect experiment artifacts:

```bash
python -m studies.goal_recognition.experiment.run_collect --help
python -m studies.goal_recognition.experiment.prepare_artifacts --help
python -m studies.goal_recognition.experiment.build_prompts --help
```

Build the static result viewer data:

```bash
node scripts/build-goal-recognition-results-viewer.js
```

Preview the website locally:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory studies/goal_recognition
```

Then open `http://127.0.0.1:8765/website/`.
