import { BrandMark } from '../../../components/ui'
import { agentLabels } from '../data'
import type { ChatMessage } from '../types'
import { MarkdownContent, SourcesList } from './MarkdownContent'

export function EmptyConversation() {
  return (
    <>
      <div className="mb-10 flex items-center gap-3">
        <BrandMark className="chat-brand-mark" />
        <div>
          <p className="text-sm font-semibold text-slate-900">Aster</p>
          <p className="mt-0.5 text-xs text-slate-400">Market intelligence workspace</p>
        </div>
      </div>
      <article className="max-w-[690px] text-[15px] leading-7 text-slate-600">
        <p className="font-medium text-slate-900">Good morning, Tuan.</p>
        <p className="mt-2">
          Explore an app market, investigate a competitor, or turn evidence into a shortlist of opportunities.
        </p>
      </article>
    </>
  )
}

function ActivityPanel({ message }: { message: ChatMessage }) {
  if (!message.activities || Object.keys(message.activities).length === 0) return null

  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
      {Object.entries(agentLabels).map(([agent, label]) => {
        const activity = message.activities?.[agent as keyof typeof agentLabels]
        if (!activity) return null
        const state = activity.type.replace('agent.', '').replace('workflow.', '')
        return (
          <p key={agent} className="flex gap-2 py-0.5">
            <span className="text-blue-600">●</span>
            <span className="font-medium text-slate-700">{label}</span>
            <span className="text-slate-500">{activity.data.message || state}</span>
          </p>
        )
      })}
      {!!message.sources?.length && (
        <div className="mt-2 border-t border-slate-200 pt-2 text-slate-500">
          {message.sources.map((source) => (
            <a
              key={source.url}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="block truncate hover:text-slate-900"
            >
              ↗ {source.title} · {source.publisher}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className={`space-y-7 ${messages.length ? '' : 'mt-7'}`}>
      {messages.map((message) => (
        <article
          key={message.id}
          className={
            message.role === 'user'
              ? 'ml-auto max-w-[560px] rounded-lg bg-blue-50 px-4 py-3 text-[14px] leading-6 text-slate-700'
              : 'max-w-[690px] text-[15px] leading-7 text-slate-600'
          }
        >
          {message.role === 'assistant' && (
            <p className="mb-2 text-xs font-semibold text-slate-900">
              Aster {message.streaming && <span className="font-normal text-slate-400">is working...</span>}
            </p>
          )}
          {message.role === 'assistant' && <ActivityPanel message={message} />}
          {message.finalBrief ? (
            <div className="mt-3">
              <MarkdownContent>{message.finalBrief.content}</MarkdownContent>
              <SourcesList citations={message.finalBrief.citations} />
            </div>
          ) : message.content ? (
            <MarkdownContent>{message.content}</MarkdownContent>
          ) : null}
          {message.error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{message.error.message}</p>
          )}
        </article>
      ))}
    </div>
  )
}
