import type { ComponentType, ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Badge } from '../../../components/ui'

export type StatusTone = 'neutral' | 'blue' | 'green' | 'amber'

export function StatusPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: StatusTone }) {
  const designTone =
    tone === 'blue' ? 'primary' : tone === 'green' ? 'success' : tone === 'amber' ? 'warning' : 'neutral'
  return <Badge tone={designTone}>{children}</Badge>
}

export function Metric({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
  label: string
  value: ReactNode
  detail: string
  tone: string
}) {
  const toneClass: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-600',
    violet: 'bg-violet-50 text-violet-600',
    amber: 'bg-amber-50 text-amber-700',
    green: 'bg-emerald-50 text-emerald-700',
  }

  return (
    <div className="flex min-w-0 items-center gap-3 border-r border-slate-200 p-5 last:border-r-0">
      <div className={`grid size-9 shrink-0 place-items-center rounded-md ${toneClass[tone] ?? ''}`}>
        <Icon size={17} strokeWidth={1.9} />
      </div>
      <div className="flex min-w-0 flex-col">
        <p className="m-0 text-[10px] text-slate-500">{label}</p>
        <strong className="mt-1 text-lg text-slate-900">{value}</strong>
        <span className="mt-0.5 text-[10px] text-slate-400">{detail}</span>
      </div>
    </div>
  )
}

export function SectionHeader({
  eyebrow,
  title,
  action,
  onAction,
}: {
  eyebrow: string
  title: string
  action?: string
  onAction?: () => void
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-5 max-sm:items-start max-sm:flex-col">
      <div>
        <p className="mb-1 text-[11px] font-bold text-slate-400 uppercase">{eyebrow}</p>
        <h2 className="text-base font-medium text-slate-800">{title}</h2>
      </div>
      {action && (
        <button
          className="inline-flex items-center gap-2 bg-transparent py-1 text-[11px] font-semibold text-slate-600 hover:text-blue-600"
          onClick={onAction}
        >
          {action}
          <ArrowRight size={14} />
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: ComponentType<{ size?: number }>
  title: string
  description: string
}) {
  return (
    <div className="grid min-h-52 place-items-center rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-slate-400">
      <Icon size={26} />
      <h3 className="mt-3 text-sm font-semibold text-slate-700">{title}</h3>
      <p className="mt-1 text-xs">{description}</p>
    </div>
  )
}
