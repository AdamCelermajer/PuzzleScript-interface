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
    NL_result <- natural_rule_inducer.infer(
        transition,
        events,
        images,
        general_NL_rule_schema,
        previous_NL_rules
    )
    if NL_result failed then
        failure_log.append(stage = natural_induction, transition, NL_result.reason)
        return learning_failed

    NL_candidates <- NL_result.hypotheses
    NL_updates <- natural_rule_library.merge(NL_candidates) # persist independently of logic rules
    if NL_updates are empty then return no_new_rules

    all_NL_rules <- natural_rule_library.all()
    for all NL_hypothesis in NL_updates do
        accepted <- false
        previous_failure <- none

        for attempt from 1 to MAX_LOGIC_ATTEMPTS do
            compile_result <- logic_rule_compiler.compile_one(
                transition,
                NL_hypothesis,
                all_NL_rules,
                logical_rulebook.all(),
                executable_rule_schema,
                images,
                previous_failure
            )

            if compile_result failed then
                failure_log.append(
                    stage = logic_compilation,
                    NL_hypothesis,
                    attempt,
                    compile_result.reason,
                    transition
                )
                previous_failure <- compile_result.reason
                continue

            candidate <- compile_result.logical_rule
            verification <- verifier.verify(candidate, memory)
            if verification.accepted then
                logical_rulebook.merge(candidate)
                natural_rule_library.mark_compiled(NL_hypothesis, candidate)
                accepted <- true
                break

            failure_log.append(
                stage = logic_verification,
                NL_hypothesis,
                candidate,
                attempt,
                verification.reason,
                transition
            )
            previous_failure <- verification.reason

        if not accepted then
            natural_rule_library.archive(NL_hypothesis, previous_failure)
            exhausted_hypothesis_count <- exhausted_hypothesis_count + 1
            failure_log.append(event = hypothesis_archived, NL_hypothesis, previous_failure)

            if exhausted_hypothesis_count > ALLOWED_EXHAUSTED_HYPOTHESES then
                failure_log.append(event = process_stopped, reason = repeated_rule_learning_failure)
                return stop_required

    return learning_complete
```
