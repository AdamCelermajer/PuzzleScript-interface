# Project Notes

## Main Demo

- Workbench settings and control
- Live agent play
- Replay of the promising Sokoban run
- Editable architecture pseudocode

## Rule Induction

The main change is that the LLM no longer creates trusted rules directly.

Rule learning is now a controlled process:

```text
Observe a transition
    -> propose a natural-language rule
    -> compile it into a logical rule
    -> verify it against real evidence
    -> use it for prediction and planning
```

### Major Points

- Natural-language rules explain the learned mechanic.
- Logical rules are executable and are used by the agent.
- A rule is stored only after deterministic verification.
- Failed rules never reach prediction or planning.
- Contradicted rules are deactivated and revised.
- Rule-learning attempts and failures are saved and visible in the Workbench.
- Retries are bounded so the agent cannot loop forever.

## Main Message

The LLM proposes an explanation, but the system decides whether that explanation
is trustworthy. Only rules supported by the real game history become part of
the agent's model of the environment.

## Demo Flow

- Show the Workbench controls.
- Run or replay the promising Sokoban game.
- Show the agent's actions, plans, predictions, and learned rules.
- Open one rule-learning attempt to show the verification process.
- Finish with the editable pseudocode view.
