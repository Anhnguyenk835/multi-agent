import { ArrowRight, MoreHorizontal, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { BrandMark, Button, IconButton } from '../../../components/ui'
import type { DashboardView } from '../types'
import { dashboardNavItems } from '../lib/navigation'

interface DashboardSidebarProps {
  activeView: DashboardView
  mobileOpen: boolean
  onNavigate: (view: DashboardView) => void
  onNotice: (message: string) => void
}

export function DashboardSidebar({ activeView, mobileOpen, onNavigate, onNotice }: DashboardSidebarProps) {
  return (
    <aside className={`dashboard-sidebar ${mobileOpen ? 'is-open' : ''}`}>
      <Link to="/dashboard" className="dashboard-brand"><BrandMark className="dash-brand-mark" /><span><strong>Indie Lab</strong><small>Opportunity intelligence</small></span></Link>
      <Button className="primary-button new-analysis" block onClick={() => onNotice('A new analysis conversation would start here.')}><Plus size={16} />New analysis</Button>
      <nav className="dashboard-nav" aria-label="Dashboard navigation">
        <p>Workspace</p>
        {dashboardNavItems.map(({ id, label, icon: Icon }) => <button key={id} className={activeView === id ? 'active' : ''} onClick={() => onNavigate(id)}><Icon size={17} /><span>{label}</span>{id === 'ideas' && <small>18</small>}</button>)}
      </nav>
      <div className="sidebar-research">
        <div className="research-status"><span className="pulse-dot" /><div><strong>Research active</strong><small>4 of 6 tasks complete</small></div></div>
        <div className="progress-track"><i /></div>
        <button onClick={() => onNotice('Opening the active analysis conversation.')}>View conversation <ArrowRight size={13} /></button>
      </div>
      <div className="sidebar-profile"><span className="avatar">TN</span><span><strong>Tuan Nguyen</strong><small>Personal workspace</small></span><IconButton className="icon-button" label="Account options"><MoreHorizontal size={17} /></IconButton></div>
    </aside>
  )
}
