# Rule Learning

## Card Title

**File role** Turn fresh transitions into accepted executable rules

## Pseudocode

```text
records <- memory.recent_transitions(1)
if records is empty then return
(events, images) <- memory.latest_visual_context()
H <- llm.call_json(natural_rule_prompt(events, rulebook.known_rules_text()), images) # plain language only
if H is empty then return
response <- llm.call_json(schema_prompt(events, H), images)
candidates <- parse_rule_candidates(response)
for all c in candidates do
    if verifier.verify(c).accepted then
        rulebook.add_generalized_rule(c)
    else log rejected candidate
```
