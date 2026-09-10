import { Database, ExternalLink, X } from 'lucide-react'
import { useEffect } from 'react'
import { IconButton } from '../../../components/ui'
import type { EvidenceSource } from '../types'

const formatDate = (value: string | null | undefined) => {
  if (!value) return 'Not reported'
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium' }).format(new Date(value))
}

export function EvidenceDrawer({ sources, onClose }: { sources: EvidenceSource[]; onClose: () => void }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return (
    <>
      <button className="fixed inset-0 z-40 bg-slate-950/25" onClick={onClose} aria-label="Dismiss evidence panel" />
      <aside
        className="fixed inset-y-0 right-0 z-50 w-[min(480px,100vw)] overflow-y-auto border-l border-slate-200 bg-slate-50 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
      >
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-5">
          <span className="grid size-10 shrink-0 place-items-center rounded-md bg-blue-50 text-blue-600">
            <Database size={19} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold text-slate-400 uppercase">Research evidence</p>
            <h2 id="evidence-drawer-title" className="mt-1 text-lg font-semibold text-slate-900">
              Evidence sources
            </h2>
          </div>
          <IconButton label="Close evidence" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </header>

        <div className="p-6">
          <p className="mb-4 text-sm leading-relaxed text-slate-500">
            {sources.length} {sources.length === 1 ? 'source supports' : 'sources support'} this market insight.
          </p>
          <div className="space-y-3">
            {sources.map((source, index) => (
              <article className="rounded-lg border border-slate-200 bg-white p-4" key={source.id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <span className="text-[10px] font-bold text-blue-600 uppercase">
                      Source {index + 1} · {source.evidence_class}
                    </span>
                    <h3 className="mt-1.5 text-sm leading-snug font-semibold text-slate-800">{source.title}</h3>
                    <p className="mt-1 text-xs text-slate-500">{source.publisher}</p>
                  </div>
                  <a
                    className="grid size-8 shrink-0 place-items-center rounded-md text-slate-400 hover:bg-blue-50 hover:text-blue-600 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-blue-500/15"
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`Open source: ${source.title}`}
                    title="Open source"
                  >
                    <ExternalLink size={15} />
                  </a>
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-3">
                  <div>
                    <dt className="text-[10px] text-slate-400 uppercase">Published</dt>
                    <dd className="mt-1 text-xs font-medium text-slate-700">{formatDate(source.published_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] text-slate-400 uppercase">Retrieved</dt>
                    <dd className="mt-1 text-xs font-medium text-slate-700">{formatDate(source.retrieved_at)}</dd>
                  </div>
                </dl>
                <p className="mt-3 truncate text-[11px] text-slate-400" title={source.url}>
                  {source.url}
                </p>
              </article>
            ))}
          </div>
        </div>
      </aside>
    </>
  )
}
