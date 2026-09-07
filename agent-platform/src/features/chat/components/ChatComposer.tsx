import { ArrowUp, Paperclip } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { IconButton } from '../../../components/ui'

interface ChatComposerProps {
  initialDraft?: string
  isStreaming: boolean
  onSend: (message: string) => Promise<void>
}

export function ChatComposer({ initialDraft = '', isStreaming, onSend }: ChatComposerProps) {
  const [draft, setDraft] = useState(initialDraft)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const message = draft.trim()
    if (!message || isStreaming) return
    setDraft('')
    await onSend(message)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) void submit(event)
  }

  return (
    <footer className="px-5 pb-5 pt-2 sm:px-10 sm:pb-7">
      <form onSubmit={submit} className="mx-auto max-w-[760px]">
        <div className="rounded-lg border border-slate-200 bg-white p-2 shadow-sm transition focus-within:border-blue-300 focus-within:ring-4 focus-within:ring-blue-50">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder="Message Aster..."
            className="block w-full resize-none bg-transparent px-2.5 py-2 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400"
            aria-label="Message Aster"
          />
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-1">
              <IconButton label="Add attachment">
                <Paperclip size={16} />
              </IconButton>
              <button
                type="button"
                className="rounded-md px-2 py-1.5 text-[11px] font-medium text-slate-500 hover:bg-slate-100"
              >
                Research
              </button>
            </div>
            <IconButton
              className="chat-send-button"
              type="submit"
              disabled={!draft.trim() || isStreaming}
              label="Send message"
            >
              <ArrowUp size={17} />
            </IconButton>
          </div>
        </div>
        <p className="mt-3 text-center text-[10px] text-slate-400">Aster can make mistakes. Check important details.</p>
      </form>
    </footer>
  )
}
