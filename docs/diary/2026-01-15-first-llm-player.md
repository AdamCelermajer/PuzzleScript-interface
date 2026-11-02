---
date: 2026-01-15
title: First LLM player, learning and solving modes
threads: [rule-agent]
runs: []
commits: [b57d430, 6030496, 9fa06f0, 7327d27, def02d4]
docs: []
reconstructed: true
brief: true
---
## Did
- Jan 15: moved rendering to the server and added `llm_client.py`, an autonomous player on the OpenAI GPT-5 series (reasoning low) that sends the full game history.
- Jan 17: migrated the client to Gemini Flash-Lite and added a learning mode.
- Jan 20: simplified the LLM client to stop hallucinated output.
- Jan 22: added separate learning and solving modes, with hand-written rule files for Midas and Sokoban (`rules/`).
## Found
- —
## Decided
- Split the agent into a learn phase (infer rules from play) and a solve phase (use the rules).
## Next
- Generalise the agent beyond hand-written rule files.
