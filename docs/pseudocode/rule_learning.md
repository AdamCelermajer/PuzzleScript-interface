# Rule Learning

## Card Title

**File role** Learn persistent natural-language rules and separately verified executable rules

## Pseudocode

```text
MAX_LOGIC_ATTEMPTS <- 3
ALLOWED_EXHAUSTED_HYPOTHESES <- 3
exhausted_hypothesis_count <- 0 # owned by RuleLearner for this process

learn_from_memory(game_id, memory):
    transition <- memory.latest_transition()
    if transition does not exist then return
    (events, images) <- memory.latest_visual_context()

    previous_NL_rules <- natural_rule_library.all()
    NL_result <- natural_rule_inducer.infer(transition, events, images, general_NL_rule_schema, previous_NL_rules)
    if NL_result failed then log_failure(natural_induction, NL_result.reason); return learning_failed

    NL_updates <- natural_rule_library.merge(NL_result.hypotheses) # persist independently of logic rules
    if NL_updates are empty then return no_new_rules

    all_NL_rules <- natural_rule_library.all()
    for all NL_hypothesis in NL_updates do
        (logical_rule, failure) <- compile_and_verify(NL_hypothesis, transition, all_NL_rules, images, memory)
        if logical_rule exists then
            logical_rulebook.merge(logical_rule)
            natural_rule_library.mark_compiled(NL_hypothesis, logical_rule)
        else
            natural_rule_library.archive(NL_hypothesis, failure)
            exhausted_hypothesis_count <- exhausted_hypothesis_count + 1
            if exhausted_hypothesis_count > ALLOWED_EXHAUSTED_HYPOTHESES then
                log_failure(process_stopped, repeated_rule_learning_failure)
                return stop_required

    return learning_complete

compile_and_verify(NL_hypothesis, transition, all_NL_rules, images, memory):
    previous_failure <- none
    for attempt from 1 to MAX_LOGIC_ATTEMPTS do
        candidate <- logic_rule_compiler.compile_one(transition, NL_hypothesis, all_NL_rules, logical_rulebook.all(), executable_rule_schema, images, previous_failure)
        if candidate exists then
            verification <- verifier.verify(candidate, memory)
            if verification.accepted then return candidate, no_failure
            previous_failure <- verification.reason
        else
            previous_failure <- candidate.failure_reason
        log_failure(NL_hypothesis, attempt, previous_failure) # one compact log entry for every failure
    return no_rule, previous_failure
```
