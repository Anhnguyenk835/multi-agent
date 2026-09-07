import { Search } from 'lucide-react'
import type { InputHTMLAttributes } from 'react'

type SearchFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  className?: string
  label?: string
  shortcut?: string
}

export default function SearchField({ className = '', label = 'Search', shortcut, ...props }: SearchFieldProps) {
  return (
    <label
      className={`flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-2.5 text-slate-400 focus-within:border-blue-300 focus-within:bg-white focus-within:ring-3 focus-within:ring-blue-500/10 ${className}`}
    >
      <Search className="shrink-0" size={16} />
      <input
        className="min-w-0 flex-1 border-0 bg-transparent text-xs text-slate-900 outline-none placeholder:text-slate-400"
        aria-label={label}
        {...props}
      />
      {shortcut && (
        <kbd className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[9px] text-slate-400">
          {shortcut}
        </kbd>
      )}
    </label>
  )
}
