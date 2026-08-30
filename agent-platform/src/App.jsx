import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'

// "label — publisher"; split on the last separator in case label has one too.
function splitCitationTitle(title) {
  if (!title) return { label: '', publisher: '' }
  const parts = title.split(' — ')
  if (parts.length < 2) return { label: title, publisher: '' }
  return { label: parts.slice(0, -1).join(' — '), publisher: parts[parts.length - 1] }
}

function CitationLink({ href, title, children }) {
  const [open, setOpen] = useState(false)
  const { label, publisher } = splitCitationTitle(title)

  return (
    <span className="relative inline-block">
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="ml-0.5 inline-block rounded bg-stone-100 px-1 align-super text-[10px] font-medium leading-4 text-stone-500 no-underline transition hover:bg-stone-200 hover:text-stone-800"
      >
        {children}
      </a>
      {open && (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2 rounded-xl border border-stone-200 bg-white p-3 text-left text-xs leading-5 text-stone-600 shadow-lg"
        >
          <span className="line-clamp-2 block font-medium text-stone-800">{label || href}</span>
          {publisher && <span className="mt-1 block truncate text-[11px] text-stone-400">{publisher}</span>}
          <span className="absolute left-1/2 top-full -mt-px h-2 w-2 -translate-x-1/2 rotate-45 border-b border-r border-stone-200 bg-white" />
        </span>
      )}
    </span>
  )
}

const markdownComponents = {
  p: (props) => <p className="mt-2 first:mt-0" {...props} />,
  h1: (props) => <p className="font-semibold text-stone-800" {...props} />,
  h2: (props) => <p className="mt-3 font-semibold text-stone-800" {...props} />,
  h3: (props) => <p className="mt-2 font-semibold text-stone-800" {...props} />,
  ul: (props) => <ul className="mt-2 list-disc space-y-0.5 pl-5" {...props} />,
  ol: (props) => <ol className="mt-2 list-decimal space-y-0.5 pl-5" {...props} />,
  strong: (props) => <strong className="font-semibold text-stone-800" {...props} />,
  a: ({ href, title, children }) => (
    <CitationLink href={href} title={title}>
      {children}
    </CitationLink>
  ),
}

function Markdown({ children }) {
  return <ReactMarkdown components={markdownComponents}>{children}</ReactMarkdown>
}

function SourcesList({ citations }) {
  if (!citations?.length) return null
  return (
    <div className="mt-3 border-t border-stone-200 pt-2 text-xs text-stone-500">
      <p className="mb-1 font-semibold uppercase tracking-[0.08em] text-stone-400">Sources</p>
      {citations.map((citation, index) => (
        <a key={citation.url} href={citation.url} target="_blank" rel="noreferrer" className="block truncate hover:text-stone-800">
          [{index + 1}] {citation.title} · {citation.publisher}
        </a>
      ))}
    </div>
  )
}

const conversations = [
  { title: 'Launch plan for Atlas', time: 'Now', active: true },
  { title: 'Refine onboarding email', time: 'Yesterday' },
  { title: 'Q3 research synthesis', time: 'Yesterday' },
  { title: 'Customer interview notes', time: 'Aug 24' },
]

const starterPrompts = [
  'Turn these notes into a project brief',
  'Plan my next product launch',
  'Summarize a research document',
]

const agentLabels = {
  researcher: 'Researcher',
  market: 'Market Agent',
  analyst: 'Analyst',
  writer: 'Writer',
}

const orchestratorBaseUrl = (import.meta.env.VITE_ORCHESTRATOR_BASE_URL || '/api').replace(/\/$/, '')

function applyStreamEvent(event, messageId, setMessages) {
  setMessages((current) => current.map((message) => {
    if (message.id !== messageId) return message
    const data = event.data || {}
    if (event.type === 'writer.delta') return { ...message, content: `${message.content}${data.text || ''}` }
    if (event.type === 'research.source_found') {
      const sources = message.sources.some((source) => source.url === data.url) ? message.sources : [...message.sources, data]
      return { ...message, sources }
    }
    if (event.type === 'workflow.completed') {
      // data.response is the full WorkflowResponse; the rendered brief (with
      // citation links already resolved) is nested under final_brief.
      return { ...message, streaming: false, finalBrief: data.response.final_brief ?? null, error: null }
    }
    if (event.type === 'workflow.failed') {
      return { ...message, streaming: false, error: data.response?.error || data.error || { message: 'Workflow failed.' } }
    }
    if (event.agent) {
      const activities = { ...message.activities, [event.agent]: { type: event.type, data } }
      return { ...message, activities }
    }
    return message
  }))
}

async function readSse(response, onEvent) {
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
          const payload = JSON.parse(line.slice(6))
          onEvent({ ...payload, type: eventType, data: payload.data || payload })
        }
      }
      eventType = 'message'
    }
    if (done) break
  }
}

function AssistantMark() {
  return <div className="grid size-8 shrink-0 place-items-center rounded-xl bg-stone-800 text-xs font-semibold text-stone-50">A</div>
}

function App() {
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)

  const sendMessage = async (event) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text) return

    const messageId = crypto.randomUUID()
    const requestId = crypto.randomUUID()
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: text },
      {
        id: messageId,
        role: 'assistant',
        content: '',
        activities: {},
        sources: [],
        streaming: true,
      },
    ])
    setDraft('')
    setIsStreaming(true)
    try {
      const response = await fetch(`${orchestratorBaseUrl}/workflows/stream`, {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, trace_id: requestId, query: text }),
      })
      if (!response.ok) throw new Error(`Workflow request failed (${response.status}).`)
      await readSse(response, (streamEvent) => applyStreamEvent(streamEvent, messageId, setMessages))
    } catch (error) {
      applyStreamEvent({ type: 'workflow.failed', data: { error: { message: error.message } } }, messageId, setMessages)
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <main className="min-h-screen bg-[#fcfbf8] text-stone-800">
      <div className="flex min-h-screen overflow-hidden bg-[#fcfbf8]">
        <aside className="hidden w-[270px] shrink-0 flex-col border-r border-stone-200/80 bg-[#f8f6f1] p-4 lg:flex">
          <div className="flex items-center justify-between px-1 py-1.5">
            <div className="flex items-center gap-2.5">
              <AssistantMark />
              <span className="text-sm font-semibold tracking-[-0.02em]">Aster</span>
            </div>
            <button className="grid size-8 place-items-center rounded-lg text-lg text-stone-500 transition hover:bg-stone-200/70 hover:text-stone-800" aria-label="Toggle sidebar">☰</button>
          </div>

          <button className="mt-6 flex items-center justify-between rounded-xl border border-stone-200 bg-[#fffefa] px-3.5 py-3 text-left text-sm font-medium shadow-sm transition hover:border-stone-300 hover:bg-white">
            <span className="flex items-center gap-2 text-stone-700"><span className="text-lg leading-none">＋</span> New conversation</span>
            <kbd className="rounded border border-stone-200 bg-stone-50 px-1.5 py-0.5 text-[10px] font-medium text-stone-400">⌘ K</kbd>
          </button>

          <nav className="mt-7" aria-label="Conversation history">
            <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-stone-400">Recent</p>
            <div className="mt-2 space-y-1">
              {conversations.map((conversation) => (
                <button
                  className={`group flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-left transition ${conversation.active ? 'bg-stone-200/70 text-stone-900' : 'text-stone-600 hover:bg-stone-200/45 hover:text-stone-800'}`}
                  key={conversation.title}
                >
                  <span className={`size-1.5 rounded-full ${conversation.active ? 'bg-amber-600' : 'bg-stone-300'}`} />
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{conversation.title}</span>
                  <span className="text-[10px] text-stone-400">{conversation.time}</span>
                </button>
              ))}
            </div>
          </nav>

          <div className="mt-auto border-t border-stone-200/80 pt-3">
            <button className="flex w-full items-center gap-2.5 rounded-xl p-2 text-left transition hover:bg-stone-200/60">
              <div className="grid size-8 place-items-center rounded-full bg-[#d8c8b8] text-xs font-semibold text-[#705d4e]">TN</div>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-semibold text-stone-700">Tuan Nguyen</span>
                <span className="block text-[11px] text-stone-400">Personal workspace</span>
              </span>
              <span className="text-stone-400">···</span>
            </button>
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 items-center justify-between border-b border-stone-200/80 px-5 sm:px-7">
            <div className="flex min-w-0 items-center gap-3">
              <button className="grid size-8 place-items-center rounded-lg text-lg text-stone-500 hover:bg-stone-100 lg:hidden" aria-label="Open sidebar">☰</button>
              <div className="min-w-0">
                <h1 className="truncate text-sm font-semibold tracking-[-0.02em] text-stone-800">Launch plan for Atlas</h1>
                <p className="mt-0.5 text-[11px] text-stone-400">Today, 10:42 AM</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-stone-500 transition hover:bg-stone-100 hover:text-stone-800">Share</button>
              <button className="grid size-8 place-items-center rounded-lg text-base text-stone-500 transition hover:bg-stone-100" aria-label="More options">•••</button>
            </div>
          </header>

          <div className="flex flex-1 flex-col overflow-y-auto px-5 py-8 sm:px-10 sm:py-12">
            <div className="mx-auto w-full max-w-[760px]">
              {messages.length === 0 && (
                <>
                  <div className="mb-10 flex items-center gap-3">
                    <AssistantMark />
                    <div>
                      <p className="text-sm font-semibold tracking-[-0.02em] text-stone-800">Aster</p>
                      <p className="mt-0.5 text-xs text-stone-400">Your thoughtful work partner</p>
                    </div>
                  </div>
                  <article className="max-w-[690px] text-[15px] leading-7 text-stone-600">
                    <p className="font-medium text-stone-800">Good morning, Tuan.</p>
                    <p className="mt-2">What would you like to make progress on today? I can help you think through a plan, shape an idea, or turn scattered notes into something useful.</p>
                  </article>
                </>
              )}

              <div className={`space-y-7 ${messages.length > 0 ? '' : 'mt-7'}`}>
                {messages.map((message, index) => (
                  <article key={`${message.role}-${index}`} className={message.role === 'user' ? 'ml-auto max-w-[560px] rounded-2xl rounded-br-md bg-[#e9e2d7] px-4 py-3 text-[14px] leading-6 text-stone-700' : 'max-w-[690px] text-[15px] leading-7 text-stone-600'}>
                    {message.role === 'assistant' && <p className="mb-2 text-xs font-semibold text-stone-800">Aster {message.streaming && <span className="font-normal text-stone-400">is working…</span>}</p>}
                    {message.role === 'assistant' && Object.keys(message.activities || {}).length > 0 && (
                      <div className="mb-4 rounded-xl border border-stone-200 bg-stone-50/80 p-3 text-xs">
                        {Object.entries(agentLabels).map(([agent, label]) => {
                          const activity = message.activities[agent]
                          if (!activity) return null
                          const state = activity.type.replace('agent.', '').replace('workflow.', '')
                          return <p key={agent} className="flex gap-2 py-0.5"><span className="text-amber-700">●</span><span className="font-medium text-stone-700">{label}</span><span className="text-stone-500">{activity.data.message || state}</span></p>
                        })}
                        {message.sources?.length > 0 && <div className="mt-2 border-t border-stone-200 pt-2 text-stone-500">{message.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="block truncate hover:text-stone-800">↗ {source.title} · {source.publisher}</a>)}</div>}
                      </div>
                    )}
                    {message.finalBrief ? (
                      // Prefer the completed brief: citation markers are only
                      // resolved into real links on the full text, once
                      // streaming is done — the raw streamed deltas below
                      // still have unresolved `[N]` markers.
                      <div className="mt-3">
                        <Markdown>{message.finalBrief.content}</Markdown>
                        <SourcesList citations={message.finalBrief.citations} />
                      </div>
                    ) : (
                      message.content && <Markdown>{message.content}</Markdown>
                    )}
                    {message.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{message.error.message}</p>}
                  </article>
                ))}
              </div>

              {messages.length === 0 && (
                <div className="mt-9 grid gap-2 sm:grid-cols-3">
                  {starterPrompts.map((prompt) => (
                    <button key={prompt} onClick={() => setDraft(prompt)} className="rounded-xl border border-stone-200 bg-[#fffefa] px-3.5 py-3 text-left text-xs leading-5 text-stone-500 transition hover:border-stone-300 hover:bg-white hover:text-stone-700">
                      {prompt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <footer className="px-5 pb-5 pt-2 sm:px-10 sm:pb-7">
            <form onSubmit={sendMessage} className="mx-auto max-w-[760px]">
              <div className="rounded-2xl border border-stone-200 bg-[#fffefa] p-2 shadow-[0_8px_24px_rgba(82,68,51,0.05)] transition focus-within:border-stone-300 focus-within:shadow-[0_8px_28px_rgba(82,68,51,0.09)]">
                <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) sendMessage(event) }} rows="2" placeholder="Message Aster..." className="block w-full resize-none bg-transparent px-2.5 py-2 text-sm leading-6 text-stone-700 outline-none placeholder:text-stone-400" aria-label="Message Aster" />
                <div className="flex items-center justify-between px-1">
                  <div className="flex items-center gap-1">
                    <button type="button" className="grid size-8 place-items-center rounded-lg text-lg text-stone-400 transition hover:bg-stone-100 hover:text-stone-600" aria-label="Add attachment">＋</button>
                    <button type="button" className="rounded-lg px-2 py-1.5 text-[11px] font-medium text-stone-400 transition hover:bg-stone-100 hover:text-stone-600">Research</button>
                  </div>
                  <button type="submit" disabled={!draft.trim() || isStreaming} className="grid size-8 place-items-center rounded-lg bg-stone-800 text-sm text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-400" aria-label="Send message">↑</button>
                </div>
              </div>
              <p className="mt-3 text-center text-[10px] text-stone-400">Aster can make mistakes. Check important details.</p>
            </form>
          </footer>
        </section>
      </div>
    </main>
  )
}

export default App
