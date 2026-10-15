import fs from 'fs'
import { promises as fsp } from 'fs'
import { dirname, extname, isAbsolute, resolve, sep } from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import { gameLibraryPlugin } from './game-library-server.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(__dirname, '..')
const goalRecognitionSource = resolve(repoRoot, 'studies/goal_recognition/website')
const thinkingComparisonSource = resolve(repoRoot, 'thinking-comparison')
const pseudocodeSource = resolve(repoRoot, 'docs/pseudocode')
const notesSource = resolve(repoRoot, 'docs/notes')
const architectureSource = resolve(repoRoot, 'docs/architecture')
const workbenchApiPort = process.env.WORKBENCH_API_PORT || '8010'
// Any hostname (Tailscale, LAN) may open the workbench.
const allowedHosts = true

const sourceRoutes = [
  {
    route: '/experiments/goal-recognition/assets/',
    source: resolve(goalRecognitionSource, 'assets'),
    buildTarget: 'experiments/goal-recognition/assets',
  },
  {
    route: '/experiments/thinking-comparison/',
    source: thinkingComparisonSource,
    buildTarget: 'experiments/thinking-comparison',
  },
  {
    route: '/docs/pseudocode/',
    source: pseudocodeSource,
    buildTarget: 'docs/pseudocode',
  },
  {
    route: '/docs/notes/',
    source: notesSource,
    buildTarget: 'docs/notes',
  },
  {
    route: '/docs/architecture-assets/',
    source: architectureSource,
    buildTarget: 'docs/architecture-assets',
  },
]

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jsonl': 'application/jsonlines; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.png': 'image/png',
  '.txt': 'text/plain; charset=utf-8',
}

function safeResolve(base, requestPath) {
  const relativePath = decodeURIComponent(requestPath).replace(/^\/+/, '')
  const target = resolve(base, relativePath)
  if (target !== base && !target.startsWith(base + sep)) return null
  return target
}

async function copySourceRoutes(outDir) {
  await Promise.all(
    sourceRoutes.map(async ({ source, buildTarget }) => {
      const target = resolve(outDir, buildTarget)
      await fsp.rm(target, { recursive: true, force: true })
      await fsp.mkdir(dirname(target), { recursive: true })
      await fsp.cp(source, target, { recursive: true })
    }),
  )
}

function experimentSourceRoutes() {
  let outDir = ''
  let command = 'serve'

  return {
    name: 'experiment-source-routes',
    configResolved(config) {
      outDir = isAbsolute(config.build.outDir)
        ? config.build.outDir
        : resolve(config.root, config.build.outDir)
      command = config.command
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = (req.url || '').split('?')[0]

        const mapping = sourceRoutes.find(({ route }) => pathname.startsWith(route))
        if (!mapping) {
          next()
          return
        }

        const suffix = pathname.slice(mapping.route.length)
        const filePath = safeResolve(mapping.source, suffix)
        if (!filePath) {
          res.statusCode = 403
          res.end('Forbidden')
          return
        }

        fs.stat(filePath, (error, stat) => {
          if (error || !stat.isFile()) {
            res.statusCode = 404
            res.end('Not found')
            return
          }
          res.setHeader(
            'Content-Type',
            contentTypes[extname(filePath).toLowerCase()] || 'application/octet-stream',
          )
          fs.createReadStream(filePath).pipe(res)
        })
      })
    },
    async closeBundle() {
      if (command === 'build') {
        await copySourceRoutes(outDir)
      }
    },
  }
}

export default defineConfig({
  root: 'website',
  plugins: [experimentSourceRoutes(), gameLibraryPlugin(repoRoot)],
  resolve: {
    alias: {
      '@goal-recognition': goalRecognitionSource,
    },
  },
  server: {
    allowedHosts,
    proxy: {
      '/api/workbench': `http://127.0.0.1:${workbenchApiPort}`,
      '/api/optimal-path': `http://127.0.0.1:${workbenchApiPort}`,
      // Former Vite-only routes now served by FastAPI; kept until the UI calls the new paths.
      '/__avo': {
        target: `http://127.0.0.1:${workbenchApiPort}`,
        rewrite: (path) => path.replace(/^\/__avo/, '/api/workbench/avo'),
      },
      '/__notes/save': {
        target: `http://127.0.0.1:${workbenchApiPort}`,
        rewrite: (path) => path.replace(/^\/__notes\/save/, '/api/workbench/notes'),
      },
      '/__pseudocode/save': {
        target: `http://127.0.0.1:${workbenchApiPort}`,
        rewrite: (path) => path.replace(/^\/__pseudocode\/save/, '/api/workbench/pseudocode'),
      },
    },
    fs: {
      allow: [repoRoot],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        newCampaign: resolve(__dirname, 'runs/new.html'),
        comparison: resolve(__dirname, 'runs/compare.html'),
        submission: resolve(__dirname, 'runs/submission.html'),
        avoLaunch: resolve(__dirname, 'runs/avo.html'),
        codexLaunch: resolve(__dirname, 'runs/codex.html'),
        results: resolve(__dirname, 'runs/results.html'),
        mechanics: resolve(__dirname, 'runs/mechanics.html'),
        runDetail: resolve(__dirname, 'runs/detail.html'),
        ruleAgent: resolve(__dirname, 'experiments/rule-agent.html'),
        oldContinuation: resolve(__dirname, 'experiments/avo-three-live.html'),
        notes: resolve(__dirname, 'notes.html'),
        experiments: resolve(__dirname, 'experiments/index.html'),
        goalRecognition: resolve(__dirname, 'experiments/goal-recognition.html'),
        goalRecognitionViewer: resolve(__dirname, 'experiments/goal-recognition/index.html'),
        thinkingComparison: resolve(__dirname, 'experiments/thinking-comparison.html'),
        liveFramework: resolve(__dirname, 'experiments/live-framework.html'),
        avoLab: resolve(__dirname, 'experiments/avo-lab.html'),
        paperInvestigation: resolve(__dirname, 'experiments/paper-investigation.html'),
        optimalPath: resolve(__dirname, 'experiments/optimal-path.html'),
        games: resolve(__dirname, 'games/index.html'),
        sokobanBasic: resolve(__dirname, 'games/sokoban-basic.html'),
        architecture: resolve(__dirname, 'docs/architecture.html'),
        api: resolve(__dirname, 'docs/api.html'),
      },
    },
  },
})
