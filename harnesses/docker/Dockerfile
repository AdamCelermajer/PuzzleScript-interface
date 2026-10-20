# One image for every harness: puzzlescript-agents:local
#   docker build -t puzzlescript-agents:local harnesses/docker
# Controller code is NOT copied in; harnesses.launch bind-mounts a staged copy
# read-only at /controller for each run.
FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git procps ripgrep less \
 && rm -rf /var/lib/apt/lists/*

# Python controller dependencies (subset of pyproject.toml actually used in the container).
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir requests arc-agi python-dotenv fastapi uvicorn backports.zstd pillow numpy

# Harness² method only; player and improver use the installed OpenCode binary below.
RUN /opt/venv/bin/pip install --no-cache-dir "harness2 @ git+https://github.com/google-research/harness2.git@1cfe254e8d25b15f37048c3730134686abe60335"

# CLI harnesses, pinned to the versions verified on 2026-10-15.
ARG CODEX_VERSION=0.162.1
ARG CLAUDE_VERSION=2.1.299
ARG OPENCODE_VERSION=1.14.19
RUN npm install -g --no-fund --no-audit \
      @openai/codex@${CODEX_VERSION} \
      @anthropic-ai/claude-code@${CLAUDE_VERSION} \
      opencode-ai@${OPENCODE_VERSION} \
 && npm cache clean --force
# Antigravity CLI (official bootstrapper; flat native binary).
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin \
 && /usr/local/bin/agy --version

# Claude Code refuses --dangerously-skip-permissions as root: everything runs as `agent`.
# ~/.config/antigravity points into the ~/.gemini volume so an agy login persists
# wherever the CLI keeps its file-based token store.
RUN useradd -m -u 1000 -s /bin/bash agent \
 && mkdir -p /results /home/agent/.gemini /home/agent/.config \
 && ln -s ../.gemini/xdg-antigravity /home/agent/.config/antigravity \
 && chown -R agent:agent /results /home/agent
USER agent
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    HOME="/home/agent" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    DISABLE_AUTOUPDATER=1 \
    OPENCODE_DISABLE_AUTOUPDATE=1 \
    AGY_CLI_DISABLE_AUTO_UPDATE=1
WORKDIR /controller
ENTRYPOINT ["/opt/venv/bin/python"]
