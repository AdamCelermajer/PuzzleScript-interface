# Committee review of the M.Sc proposal (hostile but fair), 19 October 2026

Prepared for the Thursday 22 October 2026 presentation. Scope: `docs/proposal/main.tex` (commit 94086fe; `proposal-draft.pdf` is built from the same source, title and headings match, so no rebuild was needed), `refs.bib`, the research notes under `docs/research/`, and the Board cards under `docs/board/`.

Evidence status: `docs/research/board-claim-verification-20261019.md` appeared while this review was being written and was used. It checks 43 Board and scorecard claims against the raw run artifacts: the run outcomes (Max 4/4, Flash 1/4, 27B 2/4 under AVO; 1/4, 1/4, 0/4 under baseline+), the self-check counts, Max's 32/1,060 wrong counterfactual predictions and 27B's stale-frame parser and no-op counts are all CONFIRMED. Corrections that matter for the proposal: Flash's research planner held the exact *player-movement* rule but not the push rule; Flash's delivered solver re-learned that movement rule online by step 80 and still looped, so a missing rule is not the demonstrated cause of its 1/4; Max's wrong rule is too strict on grey (27 cases) and too permissive on target cells (5 cases), not simply "conservative"; **no Qwen run exists yet on the new OpenCode or bare harness** (the 15 October NanoGPT runs were baseline+ on the Codex harness with an open budget, where Flash reached 2/4); and all dollar costs are list-price estimates with no billing data. Everything comparative rests on n = 1.

Nothing here was applied to `main.tex`. Every edit below is a suggestion for Adam to accept or reject.

---

## 1. Format compliance

Measured from the PDF (12 PDF pages: title, contents, body pages 1–9, references on page 10). Section lengths are estimates from the page-by-page text, accurate to about ±0.2 page.

| Department requirement | Required | Proposal as of 19 Oct | Verdict |
|---|---|---|---|
| Title page in Hebrew + English | yes | Both languages: title, student name, department, university, date. Labels "Student"/"Supervisors"/"M.Sc. Research Proposal" are English only. | Pass, but see supervisor row |
| Supervisor on title page | the confirmed supervisor | **"Prof. Gal Kaminka, Prof. Yoav Goldberg"** are printed. Supervision is not confirmed. | **Flag.** Do not present a title page that names unconfirmed supervisors. Either confirm by Wednesday or print "Supervisor: to be confirmed". |
| Department name | official name | "Department of Computer Science and Artificial Intelligence" (and Hebrew equivalent) | Verify against the department's own letterhead; the name may be "Department of Computer Science". |
| Table of contents | yes | Present (page i) | Pass |
| Introduction | ~1 page | §1 ≈ 0.6 page, **but §2 "The Task" (≈1.6 pages) is not a department section**. A reader applying the template counts §1+§2 as a 2.2-page introduction. | **Over.** Fold §2 into Research Goal (edit E2). |
| Related Work | 2–3 pages | §3 ≈ **0.6 page**, 4 paragraphs, 9 references in total | **Fail.** Needs ~1.5 more pages and ~12 more references. Largest format defect. |
| Research Goal | 1–3 pages | §4 ≈ 0.9 page including hypotheses | Borderline pass; becomes a clean pass once §2's task definition and capability table move here (≈2.3 pages). |
| Hypotheses (optional) | ≤ 2/3 page | ≈ 0.4 page inside §4 | Pass |
| Initial Results (required) | 2–3 pages | §5 ≈ **3.3 pages**, of which ≈1.5 pages describe infrastructure rather than results | **Over, and thin on results** (see Q3). Cut infrastructure prose, add the Qwen family pilot. |
| Work Plan | 1–3 pages | §6 (≈2.0) + §7 (≈0.5) ≈ 2.5 pages | Pass on length. **No dates, durations, run counts or costs**, which the committee will read as "no plan". |
| Bibliography | yes | 9 entries, page 10 | Present, but too small for a 2–3 page Related Work. |
| ≤ 10 pages excluding bibliography | yes | 9 pages | Pass now; adding 1.5 pages of Related Work requires cutting ≈1.5 pages elsewhere. |
| Numbered pages | yes | roman for contents, arabic 1–10 for body | Pass |
| LaTeX / Overleaf | yes | XeLaTeX, Overleaf project exists | Pass |

Proposed page budget that satisfies the template at 10 pages: Introduction 1.0 · Related Work 2.0 · Research Goal (task + capabilities + objective + hypotheses) 2.3 · Initial Results 2.7 · Work Plan 2.0.

---

## 2. Committee questions, ranked by danger

Each entry: (a) why it is dangerous, (b) what the proposal currently says, (c) suggested answer or fix.

### Q1. "Harness, model size, pretraining: is that split identifiable with the experiments you designed?"

(a) This is the scientific core, and as designed it is not identifiable. The within-family comparison confounds three things at once. Qwen 3.8 Flash is a 125B mixture-of-experts model with 6B active parameters, 27B is dense, Max is closed and roughly 2T. They differ in architecture, post-training recipe and serving, not only in size. There is no condition that varies pretraining while holding size and harness fixed, and Qwen's training data is closed. A committee member will say: "You have three models that differ in everything; whatever you observe, you cannot attribute it."

(b) §6.1 concedes "Family differences do not isolate parameter count alone: training, architecture and serving conditions will be treated as additional possible explanations" but offers no design that resolves them. H4 still reads as a size-gradient claim. The research-direction note (`qwen-harness-direction.md`) had cross-family same-size controls and a pretraining probe; the proposal dropped both.

(c) Reframe honestly: the thesis **manipulates one factor, the harness, with the model fixed**. Size and pretraining are not identified; they are *bounded* with two cheap controls: (i) one dense open model of similar size from another family (a ~27–32B dense model) on the same harness, which separates "27B-sized dense models fail" from "Qwen 27B fails"; (ii) a zero-shot familiarity probe using the existing 21-game, 10-probe next-frame benchmark, which already exists in `benchmark/` and has never been run on any model. State in the proposal that pretraining exposure cannot be established and will not be claimed. Rewrite H4 (edit E7). In the talk, say the sentence yourself before they do.

### Q2. "Every number is a single run. Why should we believe any of it?"

(a) Every cell of every table is n = 1. The AVO rows are "best completed fresh evaluation from the campaign". The Modality level-1 win of 27B was accidental. Flash reached 3/4 in research and 1/4 with its solver in the same run. Decoding is stochastic. A committee will treat "best-of-N with N unreported" as not a result and may ask why a student who built a workbench for repeatable batches has no repeats.

(b) Table 3's caption admits "best completed fresh evaluation … not averages". §6.4 promises "repeated-attempt outcomes and uncertainty" later. Nothing states n anywhere.

(c) Label every table "single runs (n = 1)". Point to the variance already visible: Flash scored 1/4 in 100 direct-play actions on 13 October and 2/4 in 296 actions through NanoGPT on 15 October, on different providers and budgets. Commit to a sample size per cell in the Work Plan: 3 seeds minimum, 5 for the headline cells, reported as counts (k/n solved, median levels) rather than means. Show the cost that makes this affordable, labelled as list-price estimates (no billing data exists): baseline+ ≈ $1–2 per 27B/Flash run, ≈ $20 per Max run; AVO ≈ $1–10 per 27B/Flash campaign. Run nothing new before Thursday (budget), but present the planned run matrix with its cost (Q5). The verification note names the single most informative repeat for afterwards: one Flash AVO campaign on Modality on the current harness, the cheapest run with the widest plausible outcome range.

### Q3. "Your 'Initial Results' section has 3.3 pages. Where are the results on your model?"

(a) Initial Results is the required section and the one the committee uses to judge whether the student can do research. The current section contains: Table 3, frontier-model successes (not the thesis model); Table 4, the 27B failure (0/4, 0/6, 3/6); a goal-recognition corpus with "no accuracy claim"; a rule-prediction benchmark that has **never scored a model** (`benchmark/results/` holds three smoke-test entries on `ps_wall_shuffle-v1`, no agent identity); a historical Sokoban rule agent with "verified rules" but no numbers; a two-check JSON-schema diagnostic. Meanwhile the strongest evidence the project has is absent: the Qwen family Modality pilot (Max 4/4 under AVO), the native replay audit (3,700 actions, 0 mismatches), Max's rule errors (32 of 1,060 counterfactual moves wrong), 27B's stale-frame parser and 1,405 no-ops in 1,420 actions, Flash's research planner holding the exact player-movement rule without ever writing it down.

(b) §6.1 says "Flash and Max runs were initiated on 13 October 2026", which is stale; the results exist and have been audited.

(c) Add a subsection "Pilot: the Qwen 3.8 family on Modality" with the audited table and three verified behavioural findings, under explicit n = 1 and harness caveats (edit E4). Cut ≈1 page of infrastructure prose (edit E12). Lead the section with results, then one paragraph on the platform that produced them.

### Q4. "Nine references and half a page of related work. How is this different from WorldCoder, PoE-World, theory-based RL, or any ARC-AGI-3 agent?"

(a) Thin related work signals that the student does not know the field, and the novelty claim is then unanswerable. Direct neighbours that are missing: theory-based RL (Tsividis et al. 2021, learns game theories from interaction, the closest cognitive-science ancestor); PoE-World (Piriyakulkij et al. 2025, programmatic world models for Atari-like games from few demonstrations); Code World Models (Dainese et al. 2024); Hypothesis Search (Wang et al. 2024) and "Phenomenal yet Puzzling" (Qiu et al. 2024) on LLM hypothesis refinement, which is exactly the failure 27B shows; Baba Is AI (Cloos et al. 2024) on rule manipulation; BALROG (Paglieri et al. 2025) and SmartPlay (Wu et al. 2024) on LLM game agents; WorldTest (Warrier et al. 2026) on world-model learning queries; VISTA (Han et al. 2026) as a visual harness; RSIAgent (Zhu et al. 2026); NVIDIA's AVO-on-ARC-AGI-3 report; Voyager and Reflexion for memory and self-revision; Tam et al. 2024 on format restrictions, which directly explains the JSON-schema finding; Sclar et al. 2024 on prompt-format sensitivity; Kapoor et al. 2024 on cost-controlled agent evaluation; Golchin & Surdeanu 2024 and WIMBD on contamination. Most of these were in the 13 October bibliography (`tmp/pdfs/proposal-before-rule-framing-20261013T162421/refs.bib`) and were cut.

(b) §3 has four paragraphs: ARC-AGI-3/PuzzleJAX, ReAct/SWE-agent, WorldCoder/AVO, human priors.

(c) Expand to ≈2 pages in five paragraphs (edit E3) and end with a one-paragraph positioning: the contribution is not another world-model agent but (i) a capability-level diagnosis of *why* a fixed small open model fails, with rule accuracy audited against the game source by counterfactual replay, (ii) controlled interventions that supply ground truth as diagnostics, and (iii) evaluation that separates rule accuracy from winning.

### Q5. "Is this feasible in an M.Sc? There is no timeline."

(a) The Work Plan has five milestones and no months. Counting what §6 promises: family comparison 3 models × 3 games × 2 conditions × 3 repeats = 54 runs; interventions ≥ 3 families × 2 models × 3 repeats × controls ≈ 60–100 runs; component ablations; held-out evaluation on several games × repeats; plus annotating 700 goal-recognition predictions, a human agreement study, and a thesis. AVO campaigns take about 3 hours each. That is roughly two theses of work.

(b) Table 5 lists milestones with "completion evidence" but no dates, counts or budget.

(c) Add a timeline table with months, run counts and dollar cost (edit E9), and cut scope: the goal-recognition annotation becomes a bounded two-week task on one condition or moves to "if time permits" (Q11); human annotation becomes one second annotator on 30 traces (Q12). Pre-register the held-out set now (Q9).

### Q6. "Max, Flash and 27B were run on a harness that no longer exists. Is the planned comparison even runnable?"

(a) All three Modality runs used the old Codex harness routed through OpenRouter to Alibaba (confirmed from `job.json`). That route has been removed and Codex is now OpenAI-only, so future Qwen runs must go through OpenCode or bare, and **no Qwen run on either exists yet**. The 27B baseline+ run is from 8 October, the Max and Flash runs from 13 October, with harness code changes in between (action parser, tool guard). The 15 October NanoGPT runs (baseline+ on the Codex harness with an open budget: 27B 1/4 in 386 actions, Flash 2/4 in 296, both stopped by hand) used a different provider and budget and are not comparable. A committee will ask whether the pilot compares models or harness versions, and whether the next comparison will be comparable with this one at all.

(b) §6.1 promises "the same direct-player condition: Codex baseline+, Alibaba, high effort". **As written, this experiment cannot be run.**

(c) Say plainly: the October pilot is one run per model on a since-retired harness, with the three baseline+ runs matched on provider, effort, budget and observation format. The confirmatory comparison will be re-run on one fixed harness (OpenCode or bare, chosen and frozen before the family comparison) with ≥3 repeats, and the harness version is recorded as a factor. Fix §6.1 (edit E5).

### Q7. "Max won with a wrong rule. Does winning measure rule learning at all?"

(a) The thesis is *rule learning*, but the primary metric in §6.4 is levels completed. Max's model treats grey as a global phase toggle; the native counterfactual audit finds 32 wrong predictions among 1,060 alternatives at its own decision states; it still won 4/4 because its plan avoided those states. Level 4 was visible during research and the self-check played all four levels, so "transfer" is not held-out. If winning is the criterion, the thesis rewards lucky plans.

(b) §5.5 says "we audited the discovered mechanics" but the proposal reports no accuracy; §6.4 lists rule-prediction accuracy as one of many measures.

(c) Make the counterfactual rule-accuracy audit (the `native_verify.cjs` procedure: restore each recorded state in the real engine, test all four moves, compare with the model's prediction) a **primary** metric alongside levels, and report both in every table. Add "held-out layouts" to the definition of transfer (edit E8). This is also the best answer to novelty: the project can score a learned rule against the game source, which ARC-AGI-3 cannot.

### Q8. "Why freeze the weights? The obvious way to make a 27B model solve these games is to fine-tune it on Max's trajectories."

(a) A Goldberg-style committee will push on this. Fixed weights plus harness engineering can look like prompt tuning. Distillation is the standard baseline for "make a small model do what a large one does".

(b) §4: "We will keep its weights fixed while developing the harness, so improvements can be attributed to the agent system." No fine-tuning control.

(c) Answer: the question is about inference-time support for a model you cannot retrain per game, and a harness is what generalises across games; but add a planned **distillation control** (LoRA on successful trajectories from Max or GPT-5.6) as a comparison arm at the end, or scope it out explicitly with the reason (edit E15). Either is defensible; silence is not.

### Q9. "Which games are held out, and when were they chosen?"

(a) The harness is developed on Modality, Knightoban and IceCrates, all Sokoban-like. Candidate interventions such as "name the genre" or "test for undo" are genre priors that may only help Sokoban-likes. "Select and freeze a held-out subset later" lets the student pick games after seeing what works.

(b) §6.4: "Before final evaluation, we will select and freeze a held-out subset from the curated collection."

(c) Pre-register now: a named list of 5–6 games from the 21-game benchmark set, never played by any Qwen model, covering ≥4 mechanic families, listed in the proposal (edit E10). This costs nothing and converts a weakness into a strength.

### Q10. "The title says 'from images'. Show me evidence that the image matters."

(a) The grid is lossless; the image adds pixels of the same tiles. No ablation exists. Whether the 27B endpoint used is a vision model should be stated; the DeepInfra 30-image cap shows images were sent, not that they were used. Flash decoded the PNG in research; 27B's failures were in the grid parser.

(b) §1–2 frame multimodality as central; no experiment tests it.

(c) Either add an observation-modality ablation (image+grid, grid only, image only) to §6.2 (edit E14) or soften the framing to "from grid observations and rendered images". Recommend both: keep images, test them.

### Q11. "The goal-recognition study: 700 predictions, 114 human responses, no result. Is it in the thesis or not?"

(a) It reads as a second thesis. Its own confound (glyph prompts in one condition, anonymous IDs in the other) was discovered after collection. Unannotated data invites "what have you learned from it?"

(b) §5.3 spends 0.7 page and a table on collection counts, then says no accuracy claim is made.

(c) Demote to one paragraph in Initial Results and one bounded deliverable in the Work Plan ("annotate the initial-frame condition, 50 games × 4 models, two weeks; report model vs human agreement"). If a result is wanted for Thursday, annotating one condition of one model is a few hours; otherwise present it as collected data only.

### Q12. "Who annotates the failure traces and the capability ratings, and what is the agreement?"

(a) The scorecard ratings come from one analyst's reading with no second annotator; the planned failure taxonomy uses "annotators" without saying who. The Tepper proposal, which is the format model here, validated its taxonomy with Cohen's κ.

(b) §6.2: "Independent human annotation of a sample will assess the reliability of the taxonomy."

(c) Specify: two human annotators (Adam plus one lab member), 30 traces, Cohen's κ reported; an LLM labeller is used at scale only if κ against humans is acceptable (edit E16).

### Q13. "These models are hosted APIs. Max is closed; `qwen3.8-max-0902` is a dated snapshot. How is any of this reproducible?"

(a) Serving precision and weights cannot be established from a model name; providers change. The audit itself says this.

(b) §5.6 mentions provider pinning and recorded request metadata.

(c) Say: all requests are recorded with model id, provider, effort and usage; the 27B is open-weights and can be served locally at bf16 for the final evaluation; Max is a diagnostic comparator only, never part of the deliverable. One sentence in §6.4.

### Q14. "What is the thesis if the 27B model never solves a held-out game?"

(a) §1 opens with "This thesis will enable a small language model to learn game rules". A proposal that only succeeds if the hypothesis is true worries a committee.

(b) No negative-result plan.

(c) State the fallback: a validated capability taxonomy with agreement statistics, a rule-prediction benchmark with scores for several models, and a set of interventions with measured null effects is a publishable negative result. Soften the first sentence (edit E13).

### Q15. "And the real-time, Jev, RoboCup direction we have heard about. Is it in this proposal?"

(a) It is not in `main.tex`, and it should stay out. The proposal already carries four hypotheses and three experimental stages. The real-time work needs runtime changes (a TICK action and clock driver), new metrics (latency percentiles, escalation precision), its own 80-entry prior-work map, and relies on vendor-reported Jev figures; its claimed gap is two weeks old (Code to Control, 30 Sep 2026). Mentioning it in the document invites "which thesis are you proposing?"

(b) Absent from the proposal; present on the Board (three cards) and in `realtime-llm-controllers-direction.md`.

(c) **Recommendation: keep it out of the proposal document entirely. In the talk, hold one reserve slide, "Beyond this thesis", shown only if asked or if a prospective supervisor's interest makes it useful, framed as a second-year extension that reuses the same harness and solver-evolution loop.** If the supervisor turns out to be Gal Kaminka and wants the real-time track, that becomes a revision of the proposal after Thursday, not a dilution before it.

---

## 3. Concrete edits to `main.tex`, prioritised

Not applied. "Current" quotes the source; "Proposed" is replacement text or a specification.

### E1 (must). Title page: supervisors

Lines 87–89. Current:
```latex
\emph{Supervisors:}\\
Prof.\ Gal Kaminka\\
Prof.\ Yoav Goldberg
```
Proposed, unless both have confirmed in writing before Thursday:
```latex
\emph{Supervisor:}\\
To be confirmed
```
Also add Hebrew labels next to the English ones (`\texthebrew{סטודנט:}`, `\texthebrew{מנחה:}`, and `\texthebrew{הצעת מחקר לתואר שני}` under "M.Sc. Research Proposal"), and verify the official department name.

### E2 (must). Restructure to the department template

Rename and move sections so the headings match the template exactly:

1. `\section{Introduction}`: §1 trimmed to 1 page; keep the ARC-AGI-3 motivation, the 27B gap and one sentence on the platform.
2. `\section{Related Work}`: expanded (E3).
3. `\section{Research Goal and Hypotheses}`: move §2.1–2.3 here as subsections "The task", "Example: Modality" (figure kept, text halved) and "Capabilities" (Table 1), followed by the current §4 text and hypotheses.
4. `\section{Initial Results}`: current §5, reordered: pilot results first (E4), platform last, infrastructure cut (E12).
5. `\section{Work Plan}`: current §6 + §7, with timeline (E9).
6. References.

### E3 (must). Related Work: expand to ≈2 pages

Keep the four current paragraphs and add these five. Entries marked † were in the 13 October bibliography and can be restored from `tmp/pdfs/proposal-before-rule-framing-20261013T162421/refs.bib`; verify the others (arXiv ids: Tsividis 2107.12544; PoE-World 2505.10819; Baba Is AI 2407.13729; Hypothesis Search ICLR 2024; Qiu et al. ICLR 2024; SmartPlay ICLR 2024; Dainese et al. NeurIPS 2024) before adding.

```latex
\paragraph{Learning game dynamics from interaction.}
Theory-based reinforcement learning shows that an agent which induces an
explicit theory of objects, rules and goals and plans with it reaches
human-like sample efficiency on novel video games \citep{tsividis2021theory}.
Program-synthesis world models extend this to language models:
WorldCoder \citep{tang2024worldcoder}, code world models guided by search
\citep{dainese2024codeworldmodels} and products of programmatic experts
\citep{piriyakulkij2025poeworld} learn executable dynamics from few
transitions. We share the executable-model representation but target a
fixed small model and ask which capability prevents it from learning.

\paragraph{Hypothesis formation and revision in language models.}
Language models propose and refine hypotheses well when the loop is
externally structured \citep{wang2024hypothesissearch} and poorly when
asked to find a rule and then apply it \citep{qiu2024phenomenal}. Our
27B traces show the second pattern: a wrong explanation of an accidental
win is retained across levels. The proposed experiment-and-revision
components target exactly this.

\paragraph{Benchmarks for agents in games.}
BALROG \citep{paglieri2025balrog}, SmartPlay \citep{wu2024smartplay},
Baba Is AI \citep{cloos2024baba} and WorldTest \citep{warrier2026worldtest}
evaluate language agents on games with known or manipulable rules;
PuzzleJAX \citep{earle2025puzzlejax} and ARC-AGI-3 supply unknown rules.
Unlike these, our platform scores a learned rule against the game source
by replaying counterfactual actions in the real engine, separating rule
accuracy from task success.

\paragraph{Harness effects and format sensitivity.}
Interface choices change what a model can do: enforced output formats
degrade reasoning \citep{tam2024letmespeak}, prompt formatting changes
scores by many points \citep{sclar2024quantifying}, and visual harnesses
alter agent behaviour \citep{han2026vista}. Agent evaluations must also
control cost \citep{kapoor2024agents}. Our JSON-schema diagnostic is an
instance of the first effect; our resource reporting follows the last.

\paragraph{Small open models and training exposure.}
Whether a model has seen similar environments cannot be read off its
behaviour; contamination studies \citep{golchin2024timetravel,elazar2024wimbd}
show how hard attribution is even with open corpora. We therefore treat
pretraining as a bounded, not identified, factor (Section~4).
```

† tsividis2021theory, paglieri2025balrog, warrier2026worldtest, tam2024letmespeak, sclar2024quantifying, han2026vista, kapoor2024agents, golchin2024timetravel, elazar2024wimbd, and also zhu2026rsiagent, nvidia2026avoarc, wang2023voyager, shinn2023reflexion, which fit the existing "Executable models and evolutionary improvement" and "Agent interfaces and persistent learning" paragraphs.

### E4 (must). Initial Results: add the audited Qwen family pilot

Insert as the first subsection of Initial Results, before the platform description:

```latex
\subsection{Pilot: the Qwen 3.8 family on Modality (single runs)}

Table~\ref{tab:family} reports one run per model and condition on Modality,
all with high reasoning effort and first-party Alibaba routing. Baseline+ is
direct play with note tools and a 100-action budget; AVO allows 300 research
actions, two real solver self-checks and a 1,500-action final evaluation of a
frozen solver. The conditions are not resource-matched and each cell is a
single run; the table motivates the comparisons in the Work Plan rather than
establishing a ranking. Every recorded action (3,700 across eight logs) was
replayed in the native PuzzleScript engine with no position or level mismatch.

\begin{table}[ht]
  \centering\small
  \begin{tabular}{lcccr}
    \toprule
    Model & Baseline+ (100 actions) & AVO research & AVO final solver & Solver actions \\
    \midrule
    Qwen 3.8 Max   & 1/4 & 3/4 (123 actions) & \textbf{4/4} & 265 \\
    Qwen 3.8 Flash & 1/4 & 3/4 (160 actions) & 1/4 & 1,500 \\
    Qwen 3.8-27B   & 0/4 & 1/4 (234 actions) & 2/4 & 1,500 \\
    \bottomrule
  \end{tabular}
  \caption{Modality, October 2026, $n=1$ per cell. The three baseline+ runs
  share harness, provider, effort, budget and observation format (the 27B run
  is five days older). Flash is a 125B mixture-of-experts model with 6B active
  parameters; 27B is dense. Level 4 was visible to Max during research, so the
  4/4 is not a held-out result. The harness used has since been retired
  (Section~\ref{sec:plan}).}
  \label{tab:family}
\end{table}

Three verified observations shape the proposal. First, winning did not
require a correct rule: Max's solver models the checkered tile as a global
phase toggle and exempts target cells from the terrain test, and
counterfactual replay in the real engine finds 32 wrong predictions among
1,060 alternative moves at its own decision states (27 too strict, 5 too
permissive); none of those situations arose on its 265-action path. Second,
Flash's research planner encoded the exact player-movement rule (no direct
move between white and black floor, though not the push rule) and used it
to clear levels 2--3, but never wrote it into its notes or world model; its
final solver relearned the same movement rule online within 80 actions and
still spent 1,490 actions oscillating on level 2, so the cause of its 1/4 is
open. Third, 27B's solver parsed the older of the two
frames in each observation, built delayed-action mechanics that fit its own
misreading, and chose a position no-op in 1,405 of its 1,420 level-3
actions; in direct play it read undo as a ``jump'' and declared a recoverable
deadlock permanent. These are recorded behaviours, not demonstrated causes;
isolating causes is the first stage of the Work Plan.
```

Then shorten §5.6 so it does not repeat the 27B story, keeping Table 4 with a harness/provider/date column.

### E5 (must). §6.1: replace stale and unrunnable text

Current (lines 557–561): "We will compare Qwen 3.8 Flash, 27B and Max on Modality with the same direct-player condition: Codex baseline+, Alibaba, high effort, image and grid observations, and a 100-action budget. Flash and Max runs were initiated on 13 October 2026."

Proposed: "The October pilot (Table~\ref{tab:family}) used a Codex-based harness routed through OpenRouter that has since been retired. The confirmatory comparison will fix one harness (the OpenCode or bare runner, chosen and frozen before the first run), Alibaba routing, high effort, image and grid observations, a 100-action direct-play budget and the AVO budgets above, with three independent runs per model and game. Harness version is recorded as an experimental factor and never changed mid-comparison."

### E6 (should). Table 3: state n and roles

Add a column "Runs" (number of campaigns the best was selected from) and change the caption's "representative best fresh evaluations" to "best fresh evaluation of $k$ campaigns ($k$ in the last column); no averages are available". If $k$ is unknown for a row, say so.

### E7 (must). H4: drop the implicit size claim

Current: "H4: Model-family differences. Under matched conditions, Qwen 3.8 Flash, 27B and Max differ in their ability to discover and revise the decisive rules. Their traces will identify concrete capabilities for the small-model harness to support."

Proposed: "H4: Capability gaps are localisable. Under one fixed harness, the Qwen 3.8 models fail at identifiable stages (observation parsing, action interpretation, rule consolidation, verification) rather than uniformly, and the stage at which 27B fails is the one whose support most improves it. We do not claim to separate parameter count from architecture, post-training or serving; a same-size dense model from another family and a zero-shot next-frame probe bound, but do not identify, those factors."

### E8 (must). §6.4: make rule accuracy a primary metric

Current first paragraph defines $L(m,h,g)$ and lists rule-prediction accuracy among many measures.

Proposed addition after the definition: "Two outcomes are primary: $L/n_g$ on held-out layouts, and counterfactual rule accuracy $A(m,h,g)$: for each recorded decision state the real engine is restored and all legal actions are executed; $A$ is the fraction the learned model predicts correctly. Every table reports both, so that a win obtained with a wrong model (as in the Max pilot) is visible."

### E9 (must). Work Plan: timeline with counts and cost

Add to Table 5 (or a new table) columns "Months", "Runs" and "Cost". Costs are list-price estimates (no billing data exists in the repository); say so in the caption. Suggested template (adjust dates to the actual thesis deadline):

| Stage | Months | Runs | Est. cost |
|---|---|---|---|
| Fix harness; family comparison, 3 models × 3 games × {baseline+, AVO} × 3 repeats | Nov–Dec 2026 | 54 | ≈ $700 (Max dominates) |
| Bottleneck interventions on 27B and Flash: supplied goal, supplied actions, latest-frame-only, enforced self-check, rival-hypothesis step; 3 repeats + controls | Jan–Mar 2027 | ≈ 90 | ≈ $400 |
| Build the small-model harness; ablations on development games | Apr–Jun 2027 | ≈ 60 | ≈ $300 |
| Held-out evaluation, 6 games × 3 repeats × {baseline, harness} | Jul–Aug 2027 | 36 | ≈ $200 |
| Thesis writing and release | Sep–Oct 2027 | — | — |

### E10 (should). Pre-register the held-out games

Current (§6.4): "Before final evaluation, we will select and freeze a held-out subset from the curated collection, covering different mechanics and level structures."

Proposed: "The held-out set is fixed now: six games from the 21-game benchmark set that no Qwen model has played (list them), covering at least four mechanic families (sliding, gravity, keys and doors, multi-object interaction, counting, mode switching). No prompt, note or component is tuned on them."

### E11 (should). Goal-recognition study: demote

Replace §5.3 (0.7 page + Table 2) with one paragraph: what was collected, the glyph-vs-ID representation confound, and the bounded deliverable; move the counts into the paragraph and delete the table. Saves ≈0.5 page.

### E12 (should). Cut infrastructure prose (≈1 page)

- §5.1 "Experiment infrastructure" paragraph → two sentences ("The workbench records settings, process ownership, frames, transitions, note revisions, model requests and solver files for every run, and replays any action with the reasoning that produced it.").
- §5.4 "AVO adaptation": keep the formula and the sentence on the trusted evaluator; cut the sandbox, controller and report-retention details to one sentence.
- §5.2: give one number (how many Sokoban rules verified against how many transitions) or cut to two sentences.

### E13 (should). Introduction first sentence

Current: "This thesis will enable a small language model to learn game rules from images, grid observations and interaction, and use those rules to solve interactive puzzles."

Proposed: "This thesis asks why a capable small open language model fails to learn the rules of unfamiliar puzzle games from interaction, and which inference-time support lets it succeed. Its deliverable is a diagnosed, ablated harness around a fixed Qwen 3.8-27B, evaluated by rule accuracy and whole-game success on held-out games." Also delete the repeated platform list in paragraph 3 if E2 moves it.

### E14 (should). §6.2: add the observation-modality intervention

Add item 4: "Observation modality: image and grid, grid only, image only. This measures whether the rendered image contributes to rule learning or only to goal recognition."

### E15 (should). Fine-tuning control

Add to §6.3 last paragraph: "As a reference point for the harness results, we will fine-tune the 27B model (LoRA) on successful trajectories from a larger model and report it as a separate arm; it is a comparison, not the contribution, because it does not transfer to unseen mechanics without new trajectories." Or scope it out with that reason.

### E16 (should). Annotation procedure

Current (§6.2): "Independent human annotation of a sample will assess the reliability of the taxonomy; we will report agreement and disagreements."

Proposed: "Two annotators will label 30 failure traces independently with the capability taxonomy; we report Cohen's $\kappa$. An LLM labeller is used at scale only if its agreement with the human labels is at least as high as the inter-annotator agreement."

### E17 (nice). Define "small"

Footnote at first use: "Small: dense, open-weight, at most ~30B parameters, servable on one GPU. Qwen 3.8 Flash (125B, 6B active) and DeepSeek V4.1 Flash are cheap to run but are not small in this sense."

### E18 (nice). Table 4: provenance column

Add "Harness / provider / date" to the 27B pilot rows (Codex-via-OpenRouter, Alibaba, 8 Oct 2026) and the two 13 Oct baseline+ rows for Max and Flash so the direct-play comparison is in one place.

### E19 (nice). Consistency checks

"GPT-6 Luna" (§5.5, Enqueue) vs "GPT-5.6 Luna" (Table 3): confirm which. Table 4 "Actions" shows budgets (100/120/120); the IceCrates run reached 3/6 after 99 actions; state "budget" in the header or report actions used.

---

## 4. Presentation outline for Thursday (11 slides + 1 reserve)

1. **Title.** Rule learning with small language models in interactive puzzle games. Student name; supervisor line as on the title page (to be confirmed if not). One sentence: "Why does a strong 27B open model fail to learn simple game rules from play, and what support fixes it?" No figure.
2. **The setting.** Unknown game, anonymous actions, image + integer grid, no legend, no stated goal; undo is just ACTION7. Figure: proposal Figure 1 (Modality level 1 image, the anonymous grid, a later layout).
3. **The gap that motivates the thesis.** Frontier and some cheap models solve whole games (Table 3: Modality 4/4, Knightoban 6/6, IceCrates 6/6; DeepSeek Flash too). Qwen 3.8-27B direct play: 0/4, 0/6, 3/6 (Table 4). Evidence on slide: both tables, condensed, with "single runs" printed.
4. **Research question and hypotheses.** H1 learning loop beats direct play; H2 goal/control bottlenecks; H3 externalised planning; H4 (rewritten) gaps are localisable. One line: "Manipulated: the harness. Fixed: the model. Reported, not identified: size and pretraining." Figure: capability table (Table 1) as a strip.
5. **Platform in one picture.** PuzzleScript engine → ARC-compatible service → agent; AVO loop strategy → research → solver → fresh evaluation by a trusted evaluator without LLM calls; workbench replay. Figure: the §5.4 formula as a diagram plus one workbench screenshot.
6. **Initial result 1: the Qwen family pilot on Modality.** The audited table (Max 1/4 → 4/4; Flash 1/4 → 1/4; 27B 0/4 → 2/4) with "n = 1, unmatched budgets, retired harness, 3,700 actions replayed with 0 mismatches". Evidence: `qwen-modality-claim-audit-20261015.md` table.
7. **Initial result 2: what 27B gets wrong.** Undo read as "jump", deadlock declared permanent; stale-frame parser; 1,405 no-ops in 1,420 actions; superstition from an accidental win. Contrast with the GPT-5.5 trace naming "Sokoban-like" and "undo" within minutes. Evidence: `qwen27b-modality-failure-analysis.md` table; scorecard rows, checked against raw traces in `board-claim-verification-20261019.md`.
8. **Initial result 3: winning is not understanding.** Max's grey-phase rule: 32/1,060 counterfactual moves wrong (27 too strict, 5 too permissive), still 4/4 because none arose on its path. Flash's planner had the exact movement rule, never wrote it down, and its solver re-learned it online and still looped, so the cause is open. Therefore rule accuracy is a primary metric. Evidence: native counterfactual audit numbers.
9. **From diagnosis to interventions.** Scorecard summary (Max strong on verification; Flash fails to consolidate; 27B fails at perception and action interpretation), then the top three ranked interventions with estimated cost: enforced self-check, latest-frame-only observation, rival-hypothesis step. Say "behaviours verified against the raw traces on 19 October, one run each; interventions are designs, none run". Evidence: `capability-scorecard-modality-20261015.md` table and ranking.
10. **Work plan and timeline.** The E9 table: stages, months, run counts, cost; the fixed harness; pre-registered held-out games; two primary metrics; repeats. Figure: timeline table.
11. **Risks and what counts as success.** n = 1 today → 3–5 repeats; non-identifiability of size/pretraining → bounded by controls; harness drift → frozen harness; overfitting to Sokoban-likes → held-out set; negative-result plan. Related-work positioning in three bullets (theory-based RL and code world models; game-agent benchmarks; harness and format effects).
12. **Reserve, show only if asked: beyond this thesis.** Real-time control: a slow coding agent compiling learned rules into fast controllers and typed decision calls; same harness, same games with a clock. One sentence that it is a second-year extension, not part of this proposal.

Speaking rule for every number: say "one run" out loud before the committee does.

---

## 5. Summary

Top three risks:

1. **The three-way attribution (harness / size / pretraining) is not identifiable as designed**, and H4 still reads as a size claim. Reframe to "harness manipulated, model fixed, size and pretraining bounded by controls".
2. **Initial Results does not show results on the thesis model**, and every number anywhere is n = 1 from a retired harness. The strongest audited evidence (family pilot, counterfactual rule audit, 27B behaviours) is missing from the document, and §6.1 describes an experiment that can no longer be run.
3. **Related Work is 0.6 page with nine references** against a 2–3 page requirement, so the novelty question cannot be answered on paper.

Single most important fix before Thursday: **rewrite Initial Results around the audited Qwen family pilot (E4) with every table labelled n = 1 and the harness caveat, and fix §6.1 (E5)**. The Related Work expansion (E3) is the most important format fix and can be done from the 13 October bibliography in an evening.
