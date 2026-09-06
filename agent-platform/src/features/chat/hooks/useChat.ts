import { useEffect, useRef, useState } from 'react'
import { streamWorkflow } from '../api/streamWorkflow'
import { updateAssistantMessage } from '../lib/chatState'
import type { ChatMessage } from '../types'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => () => activeRequest.current?.abort(), [])

  const sendMessage = async (query: string) => {
    const text = query.trim()
    if (!text || isStreaming) return

    const messageId = crypto.randomUUID()
    const requestId = crypto.randomUUID()
    const controller = new AbortController()
    activeRequest.current = controller

    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: text },
      { id: messageId, role: 'assistant', content: '', activities: {}, sources: [], streaming: true },
    ])
    setIsStreaming(true)

    try {
      await streamWorkflow({
        query: text,
        requestId,
        signal: controller.signal,
        onEvent: (event) => updateAssistantMessage(setMessages, messageId, event),
      })
    } catch (error) {
      if (controller.signal.aborted) return
      const message = error instanceof Error ? error.message : 'Workflow request failed.'
      updateAssistantMessage(setMessages, messageId, {
        type: 'workflow.failed',
        data: { error: { message } },
      })
    } finally {
      if (!controller.signal.aborted) setIsStreaming(false)
      if (activeRequest.current === controller) activeRequest.current = null
    }
  }

  return { messages, isStreaming, sendMessage }
}
