import type { PropsWithChildren } from 'react'

type BadgeProps = PropsWithChildren<{
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger'
  className?: string
}>

export default function Badge({ children, tone = 'neutral', className = '' }: BadgeProps) {
  return <span className={`ui-badge ui-badge--${tone} ${className}`.trim()}>{children}</span>
}
