import { MoreHorizontal } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'
import { BrandMark, IconButton } from '../../../components/ui'
import type { MarketAnalysisResponse } from '../types'

export function DashboardSidebar({
  reports,
  mobileOpen,
  onClose,
}: {
  reports: MarketAnalysisResponse[]
  mobileOpen: boolean
  onClose: () => void
}) {
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-30 flex w-61 flex-col border-r border-slate-200 bg-slate-50 px-4 pt-[22px] pb-4 transition-transform max-md:-translate-x-full ${mobileOpen ? 'max-md:translate-x-0' : ''}`}
    >
      <Link to="/dashboard" onClick={onClose} className="flex items-center gap-3 px-2">
        <BrandMark />
        <span className="flex min-w-0 flex-col">
          <strong className="text-[15px] leading-[18px] text-slate-900">Indie Lab</strong>
          <small className="mt-0.5 text-[10px] text-slate-400">Opportunity intelligence</small>
        </span>
      </Link>
      <nav className="mt-7" aria-label="Dashboard navigation">
        <p className="mx-2 mb-2 text-[10px] font-bold text-slate-400 uppercase">Markets</p>
        {reports.map(({ market, overview }) => (
          <NavLink key={market.id} to={`/markets/${market.id}`} onClick={onClose}>
            {({ isActive }) => (
              <span
                className={`flex h-10 items-center gap-2.5 rounded-md px-2.5 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-900 ${isActive ? 'bg-blue-50 font-bold text-blue-700 hover:bg-blue-50 hover:text-blue-700' : ''}`}
              >
                <i className={`size-2 rounded-full ${isActive ? 'bg-blue-600' : 'bg-slate-300'}`} />
                <span className="min-w-0 flex-1 truncate">{market.name}</span>
                <small
                  className={`min-w-6 rounded-full px-1.5 py-0.5 text-center text-[9px] ${isActive ? 'bg-blue-100 text-blue-700' : 'bg-slate-200 text-slate-500'}`}
                >
                  {overview.scorecard.momentum}
                </small>
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto flex items-center gap-2 border-t border-slate-200 px-1 pt-2.5">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-800 text-[10px] font-bold text-white">
          TN
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <strong className="truncate text-[11px] text-slate-800">Tuan Nguyen</strong>
          <small className="mt-0.5 text-[10px] text-slate-400">Personal workspace</small>
        </span>
        <IconButton label="Account options">
          <MoreHorizontal size={17} />
        </IconButton>
      </div>
    </aside>
  )
}
