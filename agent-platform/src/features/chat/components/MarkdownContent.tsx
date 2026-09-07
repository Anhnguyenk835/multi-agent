import { useState, type AnchorHTMLAttributes } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import type { Citation } from '../types'

function splitCitationTitle(title?: string) {
  if (!title) return { label: '', publisher: '' }
  const parts = title.split(' — ')
  if (parts.length < 2) return { label: title, publisher: '' }
  return { label: parts.slice(0, -1).join(' — '), publisher: parts[parts.length - 1] }
}

function CitationLink({ href = '#', title, children }: AnchorHTMLAttributes<HTMLAnchorElement>) {
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
        className="ml-0.5 inline-block rounded bg-blue-50 px-1 align-super text-[10px] font-medium leading-4 text-blue-600 no-underline transition hover:bg-blue-100 hover:text-blue-800"
      >
        {children}
      </a>
      {open && (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-3 text-left text-xs leading-5 text-slate-600 shadow-lg"
        >
          <span className="line-clamp-2 block font-medium text-slate-800">{label || href}</span>
          {publisher && <span className="mt-1 block truncate text-[11px] text-slate-400">{publisher}</span>}
          <span className="absolute left-1/2 top-full -mt-px h-2 w-2 -translate-x-1/2 rotate-45 border-b border-r border-slate-200 bg-white" />
        </span>
      )}
    </span>
  )
}

const markdownComponents: Components = {
  p: (props) => <p className="mt-2 first:mt-0" {...props} />,
  h1: (props) => <p className="font-semibold text-slate-800" {...props} />,
  h2: (props) => <p className="mt-3 font-semibold text-slate-800" {...props} />,
  h3: (props) => <p className="mt-2 font-semibold text-slate-800" {...props} />,
  ul: (props) => <ul className="mt-2 list-disc space-y-0.5 pl-5" {...props} />,
  ol: (props) => <ol className="mt-2 list-decimal space-y-0.5 pl-5" {...props} />,
  strong: (props) => <strong className="font-semibold text-slate-800" {...props} />,
  a: ({ href, title, children }) => (
    <CitationLink href={href} title={title}>
      {children}
    </CitationLink>
  ),
}

export function MarkdownContent({ children }: { children: string }) {
  return <ReactMarkdown components={markdownComponents}>{children}</ReactMarkdown>
}

export function SourcesList({ citations }: { citations?: Citation[] }) {
  if (!citations?.length) return null

  return (
    <div className="mt-3 border-t border-slate-200 pt-2 text-xs text-slate-500">
      <p className="mb-1 font-semibold uppercase text-slate-400">Sources</p>
      {citations.map((citation, index) => (
        <a
          key={citation.url}
          href={citation.url}
          target="_blank"
          rel="noreferrer"
          className="block truncate hover:text-slate-800"
        >
          [{index + 1}] {citation.title} · {citation.publisher}
        </a>
      ))}
    </div>
  )
}
