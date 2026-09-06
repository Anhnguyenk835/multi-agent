import type { ComponentType, ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Badge } from '../../../components/ui'

export type StatusTone = 'neutral' | 'blue' | 'green' | 'amber'

export function StatusPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: StatusTone }) {
  const designTone = tone === 'blue' ? 'primary' : tone === 'green' ? 'success' : tone === 'amber' ? 'warning' : 'neutral'
  return <Badge className={`status-pill status-${tone}`} tone={designTone}>{children}</Badge>
}

export function Metric({ icon: Icon, label, value, detail, tone }: { icon: ComponentType<{ size?: number; strokeWidth?: number }>; label: string; value: ReactNode; detail: string; tone: string }) {
  return <div className="metric-cell"><div className={`metric-icon metric-${tone}`}><Icon size={17} strokeWidth={1.9} /></div><div><p>{label}</p><strong>{value}</strong><span>{detail}</span></div></div>
}

export function SectionHeader({ eyebrow, title, action, onAction }: { eyebrow: string; title: string; action?: string; onAction?: () => void }) {
  return <div className="section-header"><div><p>{eyebrow}</p><h2>{title}</h2></div>{action && <button className="text-button" onClick={onAction}>{action}<ArrowRight size={14} /></button>}</div>
}

export function EmptyState({ icon: Icon, title, description }: { icon: ComponentType<{ size?: number }>; title: string; description: string }) {
  return <div className="empty-state"><Icon size={26} /><h3>{title}</h3><p>{description}</p></div>
}
