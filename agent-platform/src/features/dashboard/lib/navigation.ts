import { Boxes, FileSearch, GitCompareArrows, LayoutDashboard, Lightbulb } from 'lucide-react'
import type { DashboardView } from '../types'

export const dashboardNavItems = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'topics', label: 'Topics', icon: Boxes },
  { id: 'ideas', label: 'Ideas', icon: Lightbulb },
  { id: 'competitors', label: 'Competitors', icon: GitCompareArrows },
  { id: 'analyses', label: 'Analyses', icon: FileSearch },
] satisfies Array<{ id: DashboardView; label: string; icon: typeof LayoutDashboard }>

export const dashboardViewLabel = (view: DashboardView) => dashboardNavItems.find((item) => item.id === view)?.label || 'Overview'
