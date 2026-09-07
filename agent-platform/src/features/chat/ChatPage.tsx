import { Menu, MoreHorizontal } from 'lucide-react'
import { useState } from 'react'
import { IconButton } from '../../components/ui'
import '../../styles/chat.css'
import { ChatComposer } from './components/ChatComposer'
import { ChatSidebar } from './components/ChatSidebar'
import { EmptyConversation, MessageList } from './components/MessageList'
import { starterPrompts } from './data'
import { useChat } from './hooks/useChat'

export default function ChatPage() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const { messages, isStreaming, sendMessage } = useChat()

  return (
    <main className="min-h-screen bg-white text-slate-900">
      <div className="flex min-h-screen overflow-hidden bg-white">
        <ChatSidebar mobileOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
        {mobileNavOpen && (
          <button
            className="fixed inset-0 z-40 bg-slate-950/20 lg:hidden"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close navigation"
          />
        )}
        <section className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 items-center justify-between border-b border-slate-200 px-5 sm:px-7">
            <div className="flex min-w-0 items-center gap-3">
              <IconButton className="lg:hidden" label="Open sidebar" onClick={() => setMobileNavOpen(true)}>
                <Menu size={19} />
              </IconButton>
              <div className="min-w-0">
                <h1 className="truncate text-sm font-semibold text-slate-900">Market opportunity analysis</h1>
                <p className="mt-0.5 text-[11px] text-slate-400">Active conversation</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button className="rounded-md px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100">
                Share
              </button>
              <IconButton label="More options">
                <MoreHorizontal size={18} />
              </IconButton>
            </div>
          </header>

          <div className="flex flex-1 flex-col overflow-y-auto px-5 py-8 sm:px-10 sm:py-12">
            <div className="mx-auto w-full max-w-[760px]">
              {!messages.length && <EmptyConversation />}
              <MessageList messages={messages} />
              {!messages.length && (
                <div className="mt-9 grid gap-2 sm:grid-cols-3">
                  {starterPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => void sendMessage(prompt)}
                      className="rounded-lg border border-slate-200 bg-white px-3.5 py-3 text-left text-xs leading-5 text-slate-500 transition hover:border-blue-300 hover:bg-blue-50 hover:text-slate-800"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <ChatComposer isStreaming={isStreaming} onSend={sendMessage} />
        </section>
      </div>
    </main>
  )
}
