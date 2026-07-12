import fs from 'fs'
import { promises as fsp } from 'fs'
import { dirname, extname, isAbsolute, resolve, sep } from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'

const __dirname = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(__dirname, '..')
const goalRecognitionSource = resolve(repoRoot, 'studies/goal_recognition/website')
const thinkingComparisonSource = resolve(repoRoot, 'thinking-comparison')
const pseudocodeSource = resolve(repoRoot, 'docs/pseudocode')

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
  plugins: [experimentSourceRoutes()],
  resolve: {
    alias: {
      '@goal-recognition': goalRecognitionSource,
    },
  },
  server: {
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
        experiments: resolve(__dirname, 'experiments/index.html'),
        goalRecognition: resolve(__dirname, 'experiments/goal-recognition.html'),
        goalRecognitionViewer: resolve(__dirname, 'experiments/goal-recognition/index.html'),
        thinkingComparison: resolve(__dirname, 'experiments/thinking-comparison.html'),
        liveFramework: resolve(__dirname, 'experiments/live-framework.html'),
        games: resolve(__dirname, 'games/index.html'),
        sokobanBasic: resolve(__dirname, 'games/sokoban-basic.html'),
        architecture: resolve(__dirname, 'docs/architecture.html'),
        api: resolve(__dirname, 'docs/api.html'),
      },
    },
  },
})
