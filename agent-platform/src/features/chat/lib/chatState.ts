import type { Dispatch, SetStateAction } from 'react'
import type { ChatMessage, Citation, WorkflowEvent } from '../types'

export function applyWorkflowEvent(message: ChatMessage, event: WorkflowEvent): ChatMessage {
  const data = event.data || {}

  if (event.type === 'writer.delta') {
    return { ...message, content: `${message.content}${data.text || ''}` }
  }

  if (event.type === 'research.source_found') {
    const sources = message.sources || []
    const citation = data as unknown as Citation
    const exists = sources.some((source) => source.url === citation.url)
    return { ...message, sources: exists ? sources : [...sources, citation] }
  }

  if (event.type === 'workflow.completed') {
    return {
      ...message,
      streaming: false,
      finalBrief: data.response?.final_brief ?? null,
      error: null,
    }
  }

  if (event.type === 'workflow.failed') {
    return {
      ...message,
      streaming: false,
      error: data.response?.error || data.error || { message: 'Workflow failed.' },
    }
  }

  if (event.agent) {
    return {
      ...message,
      activities: {
        ...message.activities,
        [event.agent]: { type: event.type, data },
      },
    }
  }

  return message
}

export function updateAssistantMessage(
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>,
  messageId: string,
  event: WorkflowEvent,
) {
  setMessages((current) => current.map((message) => (
    message.id === messageId ? applyWorkflowEvent(message, event) : message
  )))
}
