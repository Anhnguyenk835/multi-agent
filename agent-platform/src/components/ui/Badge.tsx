import type { PropsWithChildren } from 'react'

type BadgeProps = PropsWithChildren<{
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger'
  className?: string
}>

export default function Badge({ children, tone = 'neutral', className = '' }: BadgeProps) {
  const toneClass = {
    neutral: 'bg-slate-100 text-slate-500',
    primary: 'bg-blue-100 text-blue-700',
    success: 'bg-emerald-50 text-emerald-700',
    warning: 'bg-amber-50 text-amber-700',
    danger: 'bg-red-50 text-red-700',
  }[tone]

  return (
    <span
      className={`inline-flex w-fit items-center justify-center rounded-full px-2 py-1 text-[10px] font-bold whitespace-nowrap ${toneClass} ${className}`}
    >
      {children}
    </span>
  )
}
