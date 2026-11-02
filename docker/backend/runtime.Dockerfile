FROM node:22-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY puzzlescript_interface/runtime/ ./puzzlescript_interface/runtime/
RUN mkdir -p puzzlescript_interface/.runtime puzzlescript_interface/games \
    && chown -R node:node /app
USER node
CMD ["node", "puzzlescript_interface/runtime/server.js"]
