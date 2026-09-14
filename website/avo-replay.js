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
