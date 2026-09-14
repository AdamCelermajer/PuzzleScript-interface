// Read-only compatibility for saved experiments from the retired OpenCode runner.
// Keep the original event for inspection; never mix duplicate final snapshots in.
export function openCodeConversation(events) {
  const parts = new Map()
  const roles = new Map()
  for (const event of events) {
    const info = event.payload?.info
    if (info?.id && info.role) roles.set(info.id, info.role)
    const part = event.payload?.part
    if (part?.id && ['tool', 'text', 'reasoning'].includes(part.type)) {
      parts.set(part.id, {event, part: {...part}})
    } else if (event.method === 'message.part.delta') {
      const entry = parts.get(event.payload?.partID)
      if (entry && event.payload.field === 'text') {
        entry.part.text = (entry.part.text || '') + (event.payload.delta || '')
        entry.event = event
      }
    }
  }
  return [...parts.values()].filter(({part}) => roles.get(part.messageID) !== 'user').map(({event, part}) => {
    const common = {recorded_at: event.recorded_at, turn: event.turn, role: 'assistant', native: event}
    if (part.type !== 'tool') return {...common, type: part.type, content: part.text || '', item: part}
    const state = part.state || {}
    return {...common, role: 'tool', type: 'commandExecution', item: {
      command: part.tool === 'bash' ? state.input?.command || 'bash' : `${part.tool} ${JSON.stringify(state.input || {})}`,
      aggregatedOutput: state.output || state.error || '', status: state.status,
      durationMs: state.time?.end && state.time?.start ? state.time.end - state.time.start : null,
    }}
  })
}
