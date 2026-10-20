# AVO isolation

Superseded on 2026-10-15. AVO campaigns (optimizer, players and fresh solver
evaluations) now run inside one plain Docker container per campaign, started by
`python -m harnesses.launch --framework avo`. The former Codex sandbox profile,
request proxy/guard, Windows ACL handling and isolation preflight were removed.

See [../../harnesses/README.md](../../harnesses/README.md) for the container, the
credentials each harness receives and the accepted limits. Runs recorded before
this change carry `isolation_version: 1` in `evolution_config.json`; new runs
carry `2`.
