# Rule Learning

## Card Title

**File role** Learn persistent natural-language rules and separately verified executable rules

## Pseudocode

```text
MAX_LOGIC_ATTEMPTS <- 3
ALLOWED_EXHAUSTED_HYPOTHESES <- 3
exhausted_hypothesis_count <- 0 # owned by RuleLearner for this process

learn_from_memory(game_id, legend, memory):
    transition <- memory.latest_transition()
    if transition does not exist then return
    (events, images) <- memory.latest_visual_context()

    previous_NL_rules <- natural_rule_library.all()
    candidate <- natural_rule_inducer.infer_at_most_one(transition, events, images, legend, previous_NL_rules)
    if candidate failed then log_failure(natural_induction, candidate.reason); return learning_failed
    if candidate does not exist then return no_new_rules

    (logical_rule, failure) <- compile_and_verify(candidate, transition, previous_NL_rules, legend, images, memory)
    if logical_rule exists then
        stored_G_rule <- logical_rulebook.add_or_reuse(logical_rule)
        natural_rule_library.promote_or_reuse(candidate, stored_G_rule) # visible only after verification
        exhausted_hypothesis_count <- 0
    else
        rule_attempt_log.keeps(candidate, failure) # rejected candidates never enter the NL library
        exhausted_hypothesis_count <- exhausted_hypothesis_count + 1
        if exhausted_hypothesis_count > ALLOWED_EXHAUSTED_HYPOTHESES then
            log_failure(process_stopped, repeated_rule_learning_failure)
            return stop_required

    return learning_complete

compile_and_verify(NL_hypothesis, transition, all_NL_rules, legend, images, memory):
    previous_failure <- none
    for attempt from 1 to MAX_LOGIC_ATTEMPTS do
        (raw_response, candidate) <- logic_rule_compiler.compile_one(transition, NL_hypothesis, all_NL_rules, logical_rulebook.all(), legend, executable_rule_schema, images, previous_failure)
        verification <- not_run
        if candidate exists then
            verification <- verifier.verify(candidate, memory)
            if verification.accepted then
                rule_attempt_log.append(NL_hypothesis, transition, attempt, raw_response, candidate, verification)
                return candidate, no_failure
            previous_failure <- verification.reason
        else
            previous_failure <- candidate.failure_reason
        rule_attempt_log.append(NL_hypothesis, transition, attempt, raw_response, candidate, verification)
        log_failure(NL_hypothesis, attempt, previous_failure) # one compact log entry for every failure
    return no_rule, previous_failure

revise(contradicted_G_rules, linked_NL_rules, transition, memory):
    revision <- rule_reviser.revise(contradicted_G_rules, linked_NL_rules, transition, memory)
    if verifier.accepts_old_evidence_and_new_transition(revision) then
        supersede old N/G and activate revised N/G plus optional new case
```
