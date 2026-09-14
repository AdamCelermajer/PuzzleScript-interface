import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import { join } from 'node:path'
import { resolveAvoRun } from '../../website/run-paths.js'

test('AVO paths support old links and nested campaigns, reject arbitrary files and traversal', () => {
  const root = fs.mkdtempSync(join(os.tmpdir(), 'workbench-paths-'))
  try {
    for (const id of ['avo/output/evolution/old', 'output/batch/repairs/game/campaign']) {
      fs.mkdirSync(join(root,id), {recursive:true})
      fs.writeFileSync(join(root,id,'evolution_config.json'), '{}')
      assert.equal(resolveAvoRun(root,id), join(root,id))
    }
    assert.equal(resolveAvoRun(root,'old'),join(root,'avo/output/evolution/old'))
    for (const id of ['output/../.env','../private','/output/a','output/batch','output//batch','output/./batch']) assert.equal(resolveAvoRun(root,id), null)
  } finally { fs.rmSync(root,{recursive:true,force:true}) }
})
