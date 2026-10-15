// Curated investigation dossiers, moved verbatim from website/src/paper-investigation.js.
export interface DossierSection {
  label: string
  title: string
  tone: string
  paragraphs?: string[]
  bullets?: string[]
  locator: string
}

export interface ImpactItem {
  status: string
  title: string
  body: string
}

export interface CuratedPaper {
  label: string
  type: string
  title: string
  authors: string
  sourceUrl: string
  verdict: string
  verdictDetail: string
  dossier: DossierSection[]
  impact: ImpactItem[]
}

export const CURATED_PAPERS: Record<string, CuratedPaper> = {
  avo: {
    label: 'AVO',
    type: 'Preprint · 12 pages · submitted 25 Mar 2026',
    title: 'AVO: Agentic Variation Operators for Autonomous Evolutionary Search',
    authors: 'Terry Chen, Zhifan Ye, Bing Xu, Zihao Ye, and collaborators · NVIDIA',
    sourceUrl: 'https://arxiv.org/pdf/2603.24517',
    verdict: 'Threatens fixed search orchestration, not diagnostic evaluation.',
    verdictDetail: 'AVO is evidence that the agent itself can own variation, testing, repair, and strategy shifts. It does not test whether the resulting knowledge is correct, transferable, or diagnosable in unfamiliar interactive worlds.',
    dossier: [
      {
        label: 'Core move',
        title: 'The coding agent becomes the variation operator',
        tone: 'claim',
        paragraphs: [
          'Earlier LLM-evolution systems keep sampling and population logic outside the model: a fixed framework selects parents, asks for one generated candidate, evaluates it, and updates the archive. AVO moves that whole variation step inside a long-running coding-agent loop.',
          'Its formal change is from Vary(P) = Generate(Sample(P)) to Vary(P) = Agent(P, K, f): the agent can inspect the full committed lineage P, consult a domain knowledge base K, invoke the scoring function f, edit code, diagnose failures, and decide when a candidate is worth committing.',
        ],
        locator: 'Sections 2.1 and 3.1, pp. 3–4',
      },
      {
        label: 'Actual system',
        title: 'A monotonic single lineage plus a stagnation supervisor',
        tone: 'mechanism',
        paragraphs: [
          'The evaluated instantiation is not a population with crossover. It starts from one seed kernel and keeps a new version only when it passes correctness and matches or improves the best committed benchmark score.',
          'Unsuccessful edits remain inside the agent trajectory but outside the published lineage. A supervisor watches for stalls or repetitive non-improving work and redirects the main agent toward fresh optimization directions.',
        ],
        locator: 'Sections 3.2–3.3, p. 5',
      },
      {
        label: 'Evidence',
        title: 'Seven days, 40 commits, more than 500 attempted directions',
        tone: 'evidence',
        paragraphs: [
          'An internally developed general-purpose coding agent, powered by unspecified frontier LLMs, optimized forward-pass attention kernels on NVIDIA B200 hardware. The agent had editing, shell, documentation, profiling, and persistent conversation-memory tools.',
          'Across a seven-day MHA run it produced 40 committed versions while exploring more than 500 internal optimization directions. The paper reports causal MHA gains of 0.4–3.5% over cuDNN and 5.0–10.5% over FlashAttention-4 across four tested sequence lengths. Shorter non-causal cases were within measurement noise; longer cases gained 1.8–2.4% over cuDNN.',
        ],
        locator: 'Sections 4.1–4.4, pp. 5–8',
      },
      {
        label: 'Transfer test',
        title: 'MHA optimizations adapted to GQA in about 30 minutes',
        tone: 'evidence',
        paragraphs: [
          'The evolved MHA kernel was then adapted by the agent to two grouped-query attention layouts. The paper reports gains across all tested GQA configurations, reaching 7.0% over cuDNN and 9.3% over FlashAttention-4 in the best causal case.',
          'This is useful engineering transfer within the same kernel family and hardware stack. It is not evidence of cross-domain transfer, new-task learning, or retention across an ordered curriculum.',
        ],
        locator: 'Section 4.3, pp. 6–7',
      },
      {
        label: 'Mechanistic evidence',
        title: 'Three optimization steps received local ablations',
        tone: 'evidence',
        bullets: [
          'Branchless accumulator rescaling plus a lighter fence: +8.1% non-causal, +1.6% causal geomean from v19 to v20.',
          'Overlap correction work with the second matrix-multiply stage: +1.1% non-causal, +0.4% causal from v29 to v30.',
          'Move registers from softmax warps to spilling correction warps: +2.1% non-causal and about 0% causal from v32 to v33.',
        ],
        locator: 'Section 5 and Table 1, pp. 8–10',
      },
      {
        label: 'Missing controls',
        title: 'The paper does not isolate why AVO wins',
        tone: 'limitation',
        bullets: [
          'No matched comparison against the same model in a fixed single-turn or fixed-workflow search harness.',
          'No ablation of full-lineage access, documentation access, persistent memory, testing tools, or the stagnation supervisor.',
          'The internal agent, model mixture, prompts, compute cost, complete failed trajectory, and evolved kernel code are not specified or released in the paper.',
          'One seven-day trajectory, one kernel family, one GPU generation, forward pass only, and a narrow BF16/head-dimension benchmark do not establish domain generality.',
          'The same benchmark suite guides evolution and final reporting, so the GQA adaptation is the stronger—but still nearby—generalization check.',
        ],
        locator: 'Critical reading of Sections 3–6',
      },
    ],
    impact: [
      {
        status: 'survives',
        title: 'Your benchmark contribution survives',
        body: 'PuzzleScript-World is an evaluation protocol: independent solving, goal-recognition, transition-prediction, and warm/cold transfer scores. AVO proposes a search operator and does not supply those diagnostics.',
      },
      {
        status: 'change',
        title: 'The agent architecture should become less prescriptive',
        body: 'Do not make periodic rule induction or a fixed orchestration loop part of the scientific claim. Treat agent-owned timing, tool use, repair, and strategy shifts as one harness condition.',
      },
      {
        status: 'baseline',
        title: 'AVO becomes a strong harness baseline',
        body: 'Compare a fixed rule-learning loop with a persistent agentic loop under the same model, observation, game, and budget. Score both on completion, exact next-state prediction, transfer, actions, tokens, time, and cost.',
      },
      {
        status: 'caution',
        title: 'Do not call the local client an AVO reproduction',
        body: 'The public paper omits the internal agent configuration. Your implementation can faithfully test AVO-inspired principles, but it cannot claim to reproduce NVIDIA’s unpublished system.',
      },
    ],
  },
  vista: {
    label: 'VISTA',
    type: 'Official project report · published 5 Aug 2026 · no paper released',
    title: 'VISTA: A Visual Harness for Reasoning in an Interactive World',
    authors: 'Qiushi Han, Keya Hu, Linlu Qiu, Cathy Wu, and Kaiming He · MIT',
    sourceUrl: 'https://vista-research.github.io/',
    verdict: 'Directly challenges necessity, not usefulness, of executable rules.',
    verdictDetail: 'VISTA shows that a strong multimodal model with lossless frame recall and free-form notes can solve all 25 public ARC-AGI-3 games without synthesizing an executable world model. It does not show what the agent learned, which harness component caused the gain, or whether the result generalizes to private games.',
    dossier: [
      {
        label: 'Publication status',
        title: 'There is no paper yet',
        tone: 'limitation',
        paragraphs: [
          'The authoritative source is an MIT project webpage dated 5 August 2026. It includes the method description, exact short prompt, per-game scores, and public replays, but it is not a peer-reviewed or arXiv paper.',
        ],
        locator: 'Official VISTA project report',
      },
      {
        label: 'Core move',
        title: 'Use fuzzy language reasoning instead of an executable program',
        tone: 'claim',
        paragraphs: [
          'VISTA gives a general-purpose multimodal model the rendered PNG observation, available actions, status, and progress. The model reasons in unrestricted natural language and records a compact, revisable game model in GUIDE.md, with WORKING.md as a level scratchpad.',
          'The authors explicitly contrast this with program-based agents that reconstruct state, transitions, and goals as executable code. Their claim is not that programs are impossible; it is that an implicit natural-language model can be sufficient for action selection on these games.',
        ],
        locator: 'Section 2, “Language reasoning”',
      },
      {
        label: 'Memory mechanism',
        title: 'Every returned frame remains available at full fidelity',
        tone: 'mechanism',
        paragraphs: [
          'The harness stores every environment frame with its turn and frame index. The agent can use inspect to revisit complete frames, intermediate animation frames, or cropped regions, and read_pixels to obtain exact colors.',
          'This is an external, lossless visual store—not ordinary context-window memory. The model chooses what old evidence to retrieve. Across context compaction, the frames, action history, and notes remain available.',
        ],
        locator: 'Section 2, “Lossless visual memory,” and Section 3',
      },
      {
        label: 'Prompt and loop',
        title: 'One short prompt, predict before play, revise after observation',
        tone: 'mechanism',
        paragraphs: [
          'The prompt asks the agent to complete the game with few actions, maintain a compact revisable model, state the expected visual result before each play call, describe all visible changes afterward, and keep durable versus working notes separate.',
          'One agent continues from the first observation to game completion. Looking back is optional and selected by the model rather than forced at a fixed point in the loop.',
        ],
        locator: 'Section 3, “The Complete Pipeline”',
      },
      {
        label: 'Evidence',
        title: 'Perfect completion with Opus; near-perfect RHAE with Sol',
        tone: 'evidence',
        paragraphs: [
          'The same prompt, tools, model, and reasoning effort were used across all 25 public games within each backend. Opus 5.0 at xhigh reports 100.00 RHAE. GPT-5.6 Sol at max reports 98.27, completes 25/25 games, and has 22 perfect game scores.',
          'RHAE charges environment actions but treats reasoning, read-only inspection, tokens, time, and tool calls as free. VISTA therefore demonstrates action efficiency, not total compute or economic efficiency.',
        ],
        locator: 'Section 4, “VISTA Results on ARC-AGI-3”',
      },
      {
        label: 'Missing controls',
        title: 'The result does not identify the causal ingredient',
        tone: 'limitation',
        bullets: [
          'No matched ablation removes lossless visual memory, notes, prediction-before-action, context continuation, or the coding-agent shell one at a time.',
          'System-level comparisons use different harnesses, models, efforts, and sometimes fallback procedures; they are rankings, not causal ablations.',
          'The representation check covers only Level 1 of two games in independent trajectories, so it does not establish broad invariance across text, 2D, and 3D inputs.',
          'All results are on public games. The authors explicitly say newer models may have seen them during training and that the private set is the real generalization test.',
          'Without an executable model, high task score alone cannot reveal whether the internal mechanics or goal hypothesis was correct, incomplete, or merely sufficient for the chosen actions.',
        ],
        locator: 'Critical reading of Sections 4–5',
      },
    ],
    impact: [
      {
        status: 'threat',
        title: 'A necessity claim is no longer defensible',
        body: 'You cannot claim that explicit executable rule learning is required to solve unfamiliar public ARC-AGI-3 games efficiently. VISTA is a direct counterexample at the system level.',
      },
      {
        status: 'survives',
        title: 'Your central diagnostic question becomes stronger',
        body: 'VISTA’s score cannot tell whether its natural-language model is faithful, which component helped, why a failure occurred, or what transferred. Those are exactly the gaps your separated protocol measures.',
      },
      {
        status: 'change',
        title: 'Explicit rules should be a treatment, not the thesis',
        body: 'Position verified executable rules as one architectural intervention to test against free-form notes, visual memory, and hybrids—not as the assumed correct representation.',
      },
      {
        status: 'experiment',
        title: 'The decisive experiment is now obvious',
        body: 'Use the same model and action budget across: minimal agent, VISTA-style notes plus visual recall, executable rules plus verification, and a hybrid. Measure actions, prediction fidelity, belief revision, transfer, tokens, time, and cost.',
      },
    ],
  },
}
