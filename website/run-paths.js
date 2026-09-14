import fs from 'node:fs'
import { resolve, relative, sep } from 'node:path'

export function resolveAvoRun(repoRoot, runId) {
  if (typeof runId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(runId)) return null
  if (runId.split('/').some(part => !part || part === '.' || part === '..')) return null
  const candidate = runId.includes('/') ? resolve(repoRoot, runId) : resolve(repoRoot, 'avo/output/evolution', runId)
  const roots = ['avo/output/evolution', 'output'].map(base => resolve(repoRoot, base))
  if (!roots.some(root => candidate.startsWith(root + sep))) return null
  try {
    // Reject junctions/symlinks at every component, including the approved roots.
    let cursor = repoRoot
    for (const part of relative(repoRoot, candidate).split(sep)) {
      cursor = resolve(cursor, part)
      if (fs.lstatSync(cursor).isSymbolicLink()) return null
    }
    if (fs.realpathSync(candidate).toLowerCase() !== candidate.toLowerCase()) return null
    if (!fs.statSync(resolve(candidate, 'evolution_config.json')).isFile()) return null
    return candidate
  } catch { return null }
}
