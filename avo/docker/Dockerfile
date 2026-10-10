FROM avo-jericho:local AS dependencies
FROM node:22-alpine AS codex_cli
RUN npm install -g @openai/codex@0.156.1
FROM python:3.12.14-slim-bookworm
COPY --from=dependencies /opt/venv /opt/venv
COPY --from=codex_cli /usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex /usr/local/bin/codex
RUN ln -s /usr/local/bin/codex /usr/local/bin/codex-linux-sandbox
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap && rm -rf /var/lib/apt/lists/*
RUN /opt/venv/bin/python -m ensurepip && /opt/venv/bin/python -m pip install --no-cache-dir arc-agi fastapi uvicorn python-dotenv backports.zstd
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" HOME="/home/controller" PYTHONDONTWRITEBYTECODE=1
WORKDIR /controller
ENTRYPOINT ["/opt/venv/bin/python"]
