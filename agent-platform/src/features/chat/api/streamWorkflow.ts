import { env } from '../../../config/env'
import type { WorkflowEvent } from '../types'

export async function readSse(response: Response, onEvent: (event: WorkflowEvent) => void) {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('Streaming response is unavailable.')

  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = 'message'

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const frame of frames) {
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7)
        if (line.startsWith('data: ')) {
          const payload = JSON.parse(line.slice(6)) as Record<string, unknown>
          onEvent({
            ...payload,
            type: eventType,
            agent: payload.agent as WorkflowEvent['agent'],
            data: (payload.data || payload) as WorkflowEvent['data'],
          })
        }
      }
      eventType = 'message'
    }

    if (done) break
  }
}

interface StreamWorkflowOptions {
  query: string
  requestId: string
  onEvent: (event: WorkflowEvent) => void
  signal?: AbortSignal
}

export async function streamWorkflow({ query, requestId, onEvent, signal }: StreamWorkflowOptions) {
  const response = await fetch(`${env.orchestratorBaseUrl}/workflows/stream`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
    body: JSON.stringify({ request_id: requestId, trace_id: requestId, query }),
    signal,
  })

  if (!response.ok) throw new Error(`Workflow request failed (${response.status}).`)
  await readSse(response, onEvent)
}
