import test from 'node:test'
import assert from 'node:assert/strict'
import { openCodeConversation } from '../../website/history/opencode-events.js'

test('Archived OpenCode tools retain input and output with one row per part', () => {
  const event = state => ({method:'message.part.updated', turn:1, payload:{part:{id:'tool-1', type:'tool', tool:'bash', state}}})
  const rows = openCodeConversation([
    {method:'message.updated',payload:{info:{id:'user-1',role:'user'}}},
    {method:'message.part.updated',payload:{part:{id:'user-part',messageID:'user-1',type:'text',text:'User instruction already logged by AVO'}}},
    event({status:'running',input:{command:'python avo_tool.py observe'}}),
    event({status:'completed',input:{command:'python avo_tool.py observe'},output:'game state',time:{start:5,end:10}}),
    {method:'message.part.updated',payload:{part:{id:'text-1',type:'text',text:'Saved'}}},
    {method:'message.part.delta',payload:{partID:'text-1',field:'text',delta:' solver'}},
  ])
  assert.equal(rows.length,2)
  assert.equal(rows[0].type,'commandExecution')
  assert.equal(rows[0].item.command,'python avo_tool.py observe')
  assert.equal(rows[0].item.aggregatedOutput,'game state')
  assert.equal(rows[0].item.durationMs,5)
  assert.equal(rows[1].content,'Saved solver')
})
