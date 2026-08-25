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
const pseudocodeManifest = resolve(pseudocodeSource, 'manifest.json')
const pseudocodeSaveRoute = '/__pseudocode/save'
const notesSource = resolve(repoRoot, 'docs/notes')
const allowedNotesFiles = new Set(['workbench-notes.md', 'todo.md', 'benchmark-positioning.md'])
const notesSaveRoute = '/__notes/save'
const maxPseudocodeBytes = 1024 * 1024
const workbenchApiPort = process.env.WORKBENCH_API_PORT || '8010'
const allowedHosts = (process.env.WORKBENCH_ALLOWED_HOSTS || '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean)

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

function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(JSON.stringify(payload))
}

function readJsonBody(req) {
  return new Promise((resolveBody, rejectBody) => {
    let body = ''
    let byteLength = 0
    let tooLarge = false

    req.setEncoding('utf8')
    req.on('data', (chunk) => {
      byteLength += Buffer.byteLength(chunk, 'utf8')
      if (byteLength > maxPseudocodeBytes) {
        tooLarge = true
        return
      }
      body += chunk
    })
    req.on('end', () => {
      if (tooLarge) {
        rejectBody(Object.assign(new Error('Markdown exceeds the 1 MB limit'), { statusCode: 413 }))
        return
      }
      try {
        resolveBody(JSON.parse(body))
      } catch {
        rejectBody(Object.assign(new Error('Request body must be valid JSON'), { statusCode: 400 }))
      }
    })
    req.on('error', rejectBody)
  })
}

async function savePseudocodeMarkdown(payload) {
  const file = payload?.file
  const markdown = payload?.markdown
  if (typeof file !== 'string' || typeof markdown !== 'string') {
    throw Object.assign(new Error('Both file and markdown are required'), { statusCode: 400 })
  }

  const manifest = JSON.parse(await fsp.readFile(pseudocodeManifest, 'utf8'))
  if (!manifest.some((item) => item.file === file)) {
    throw Object.assign(new Error('Only pseudocode files listed in the manifest can be saved'), { statusCode: 403 })
  }

  const filePath = safeResolve(pseudocodeSource, file)
  if (!filePath || extname(filePath).toLowerCase() !== '.md') {
    throw Object.assign(new Error('Invalid pseudocode Markdown path'), { statusCode: 400 })
  }

  await fsp.writeFile(filePath, markdown, 'utf8')
}

async function saveNotesMarkdown(payload) {
  const file = payload?.file
  const markdown = payload?.markdown
  if (typeof file !== 'string' || typeof markdown !== 'string') {
    throw Object.assign(new Error('Both file and markdown are required'), { statusCode: 400 })
  }
  if (!allowedNotesFiles.has(file)) {
    throw Object.assign(new Error('Only notebook files listed by the Notes page can be saved'), { statusCode: 403 })
  }
  const filePath = safeResolve(notesSource, file)
  if (!filePath || extname(filePath).toLowerCase() !== '.md') {
    throw Object.assign(new Error('Invalid notes Markdown path'), { statusCode: 400 })
  }
  await fsp.writeFile(filePath, markdown, 'utf8')
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

        if (pathname === pseudocodeSaveRoute) {
          if (req.method !== 'POST') {
            res.setHeader('Allow', 'POST')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }

          readJsonBody(req)
            .then(async (payload) => {
              await savePseudocodeMarkdown(payload)
              sendJson(res, 200, { saved: true, file: payload.file })
            })
            .catch((error) => {
              sendJson(res, error.statusCode || 500, { error: error.message || 'Could not save Markdown' })
            })
          return
        }

        if (pathname === notesSaveRoute) {
          if (req.method !== 'POST') {
            res.setHeader('Allow', 'POST')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }

          readJsonBody(req)
            .then(async (payload) => {
              await saveNotesMarkdown(payload)
              sendJson(res, 200, { saved: true })
            })
            .catch((error) => {
              sendJson(res, error.statusCode || 500, { error: error.message || 'Could not save notes' })
            })
          return
        }

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
    allowedHosts,
    proxy: {
      '/api/workbench': `http://127.0.0.1:${workbenchApiPort}`,
      '/api/optimal-path': `http://127.0.0.1:${workbenchApiPort}`,
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
