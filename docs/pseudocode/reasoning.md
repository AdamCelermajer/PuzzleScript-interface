# Reasoning Pseudocode

## Responsibility

Use transition evidence to infer rules, compress duplicates, and verify which beliefs should update the active context.

## Inputs

- selected transition evidence
- active task context
- persistent prior knowledge

## Outputs

- legend updates
- candidate rules
- validated rules
- compressed abstractions
- remaining hypotheses

## Pseudocode

```python
def reason_about_transitions(evidence, active_context, persistent_store):
    prior_rules = persistent_store.retrieve_rules(active_context.game_id)

    legend_updates = infer_symbol_roles(
        evidence=evidence,
        current_legend=active_context.inferred_legend,
        prior_symbol_roles=prior_rules.symbol_roles,
    )

    candidate_rules = induce_rules(
        evidence=evidence,
        known_rules=active_context.known_rules,
        legend={**active_context.inferred_legend, **legend_updates},
    )

    compressed_rules = compress_rules(
        candidate_rules=candidate_rules,
        existing_rules=active_context.known_rules,
    )

    verified_rules = verify_rules_against_evidence(
        rules=compressed_rules,
        evidence=evidence,
    )

    hypotheses = build_or_update_hypotheses(
        evidence=evidence,
        verified_rules=verified_rules,
        unresolved_questions=active_context.unresolved_questions(),
    )

    return ReasoningUpdate(
        legend_updates=legend_updates,
        candidate_rules=candidate_rules,
        validated_rules=verified_rules,
        compressed_abstractions=compressed_rules.abstractions,
        remaining_hypotheses=hypotheses,
        final_goal=infer_goal_if_supported(evidence, active_context),
    )
```

## Notes

The reasoning mechanism is intentionally open. It may be an LLM call, a symbolic search process, a rule engine, a learned dynamics model, or a hybrid.
