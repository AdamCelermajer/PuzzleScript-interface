import test from 'node:test'
import assert from 'node:assert/strict'
import { selectEvidenceFrame } from '../../website/avo-replay.js'

test('replay indexes actions independently of log sequence and keeps reset observations', () => {
  const observation = value => ({payload:{frame:[[[value]]]},status:'PLAYING'})
  const events = [
    {type:'episode_started',sequence:1,payload:{observation:observation(0),episode:1}},
    {type:'checkpoint_saved',sequence:2,payload:{}},
    {type:'transition',sequence:3,payload:{action:{id:'ACTION1'},after:observation(1),episode:1}},
    {type:'episode_started',sequence:4,payload:{observation:observation(4),episode:2}},
    {type:'transition',sequence:5,payload:{action:{id:'ACTION2'},after:observation(2),episode:2}},
  ]
  assert.equal(selectEvidenceFrame(events,0).observation.payload.frame[0][0][0],0)
  assert.equal(selectEvidenceFrame(events,1).transition.sequence,3)
  assert.equal(selectEvidenceFrame(events,2).transition.episode,2)
  assert.equal(selectEvidenceFrame(events).step,2)
  assert.equal(selectEvidenceFrame(events,1).total_actions,2)
  for (const step of [-1,3,1.2,'wrong']) assert.throws(() => selectEvidenceFrame(events,step))
})

test('older recordings can use the first before-state; empty traces fail clearly', () => {
  const before = {payload:{frame:[[[3]]]}}
  const event = {type:'transition',payload:{before,after:{payload:{frame:[[[4]]]}}}}
  assert.deepEqual(selectEvidenceFrame([event],0).observation,before)
  assert.throws(() => selectEvidenceFrame([],0), /No saved observation/)
})
