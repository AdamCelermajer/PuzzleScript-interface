# PuzzleScript backend in Docker

The Compose project `puzzlescript-backend` owns two services: the Node game
runtime and its Python ARC-compatible API. The workbench, website and campaign
launcher stay local. Campaign agent runs already have their own temporary Docker
containers; they are not part of this stack.

## Everyday use

Start Docker Desktop, then from the repository root:

```powershell
npm run local                  # start backend, wait for health, return
scripts/backend.ps1 status     # both services and ports
scripts/backend.ps1 logs       # follow both logs; Ctrl+C exits log view
scripts/backend.ps1 stop       # stop both backend services
npm run workbench              # start/reuse backend, run local workbench
```

Equivalent direct commands: `docker compose up -d --wait`, `docker compose ps`,
`docker compose logs -f`, `docker compose stop`.

The stack has no automatic restart policy. It starts on explicit `up` or a new
workbench launch, not simply because Docker starts. The workbench checks backend
health but does not restart a backend you explicitly stopped while it is running.
Closing the workbench leaves the shared backend running. No Windows startup
settings are changed by this migration.

## Connections and files

- Host API: `http://127.0.0.1:8000`; agent containers:
  `http://host.docker.internal:8000` (unchanged). The API publishes on all host
  interfaces, matching the original API and allowing Docker Desktop's host gateway.
- Internal runtime address for the API: `http://runtime:3543`.
  Host runtime diagnostics: `http://127.0.0.1:3543/health`.
- Host overrides: `ARC_PROXY_PORT` (8000) and `PORT` (3543). Set the same values
  in the shell launching the workbench and Compose. Compose also reads `.env`.
- Games are bind-mounted read-only from `puzzlescript_interface/games` into both
  containers. Editing an existing script requires no image rebuild; catalog
  additions require `docker compose up -d --no-deps --force-recreate api` because
  the API discovers games at startup (do this between campaigns).
- History stays in the existing host `puzzlescript_interface/.runtime` directory.
  Campaign output and reports remain in their existing host directories.
- Active game sessions, snapshots and API scorecards remain in memory, as before.
  Stopping/recreating the backend loses these; stop campaigns first. Saved campaign
  results and game history are not removed by `stop` or `down`.
- Build contexts allow only the required backend sources and package manifests.
  No provider credentials, workbench code or campaign outputs go into the images.
  Container logs rotate at 10 MB, three files per service.

## Change backend code / debug locally

```powershell
scripts/backend.ps1 build
scripts/backend.ps1 up         # recreate only when the image/config changed
```

For host debugging, first stop the Docker backend, then:

```powershell
scripts/start-workbench.ps1 -LocalBackend
```

This preserves the original host Node/Python startup behavior. Do not run both
backends on the same ports. `npm start` remains the host-only Node debugging entry.

## Offline verification

```powershell
.venv/Scripts/python.exe scripts/check-backend.py
Get-Content -Raw scripts/check-backend.py | docker run --rm -i --init --add-host host.docker.internal:host-gateway --entrypoint /opt/venv/bin/python puzzlescript-agents:local - http://host.docker.internal:8000
```

The second check uses the existing agent image and its normal host gateway,
without starting an agent or making paid API calls. Both checks exercise catalog,
reset, action, snapshot restore and scorecard close.
