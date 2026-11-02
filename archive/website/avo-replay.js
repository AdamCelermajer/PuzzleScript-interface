// Replay recorded observations, indexed by game actions rather than log events.
export function selectEvidenceFrame(events, requestedStep = null) {
  const transitions = events.filter(event => event.type === 'transition')
  const total = transitions.length
  const step = requestedStep === null ? total : Number(requestedStep)
  if (!Number.isInteger(step) || step < 0 || step > total) {
    throw Object.assign(new Error('Replay step is outside the saved action history'), { statusCode: 400 })
  }
  const event = step ? transitions[step - 1] : events.find(item => item.type === 'episode_started')
  const observation = step ? event?.payload?.after : event?.payload?.observation || transitions[0]?.payload?.before
  if (!observation) throw Object.assign(new Error('No saved observation for this step'), { statusCode: 404 })
  return { step, total_actions: total, observation, transition: {
    sequence: event?.sequence, recorded_at: event?.recorded_at,
    action: step ? event?.payload?.action : null, status: observation.status || '',
    progress: observation.progress || {}, episode: event?.payload?.episode ?? null,
  } }
}

function reasoningText(value) {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(reasoningText).filter(Boolean).join('\n')
  if (value && typeof value === 'object') return reasoningText(value.text ?? value.content ?? value.summary)
  return ''
}

// Timestamps establish proximity, not a one-to-one cause: one tool call may play many actions.
export function reasoningAtAction(evidence, conversation, requestedStep, phase) {
  const { step, transition } = selectEvidenceFrame(evidence, requestedStep)
  if (!step) return { status: 'initial' }
  if (phase === 'evaluation') return { status: 'offline_solver' }
  const actionTime = Date.parse(transition.recorded_at)
  if (!Number.isFinite(actionTime)) return { status: 'unavailable' }
  const transitions = evidence.filter(event => event.type === 'transition')
  const previousTime = step > 1 ? Date.parse(transitions[step - 2]?.recorded_at) : -Infinity
  const matching = conversation.filter(event => event.type === 'reasoning' || event.role === 'assistant_reasoning')
    .map(event => ({ event, time: Date.parse(event.recorded_at), text: reasoningText(event.item?.content ?? event.item?.summary ?? event.content) }))
    .filter(entry => Number.isFinite(entry.time) && entry.time <= actionTime && entry.text.trim())
    .sort((left, right) => left.time - right.time)
  const latest = matching.at(-1)
  if (!latest) return { status: 'unavailable' }
  return {
    status: 'captured', text: latest.text, recorded_at: latest.event.recorded_at,
    turn: latest.event.turn ?? null, new_since_previous_action: latest.time > previousTime,
  }
}
