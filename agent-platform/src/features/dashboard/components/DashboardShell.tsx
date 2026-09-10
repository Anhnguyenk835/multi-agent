import { Bell, Menu } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { IconButton, SearchField } from '../../../components/ui'
import type { MarketSummary } from '../types'
import { DashboardSidebar } from './DashboardSidebar'

interface DashboardShellProps {
  title: string
  section: string
  searchQuery: string
  onSearchChange: (value: string) => void
  action?: ReactNode
  markets: MarketSummary[]
  children: ReactNode
}

export function DashboardShell({
  title,
  section,
  searchQuery,
  onSearchChange,
  action,
  markets,
  children,
}: DashboardShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  return (
    <div className="flex min-h-screen w-full overflow-x-hidden bg-[#f4f6f9] text-slate-900">
      <DashboardSidebar markets={markets} mobileOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      {mobileNavOpen && (
        <button
          className="fixed inset-0 z-20 bg-slate-950/30 md:hidden"
          onClick={() => setMobileNavOpen(false)}
          aria-label="Close navigation"
        />
      )}
      <main className="ml-61 min-w-0 flex-1 overflow-hidden max-md:ml-0">
        <header className="sticky top-0 z-20 flex h-[68px] items-center gap-6 border-b border-slate-200 bg-white/95 px-8 backdrop-blur max-md:px-4">
          <div className="flex min-w-[190px] items-center gap-2 max-md:min-w-0">
            <IconButton className="hidden max-md:grid" onClick={() => setMobileNavOpen(true)} label="Open navigation">
              <Menu size={19} />
            </IconButton>
            <div className="flex items-baseline gap-2 max-sm:hidden">
              <span className="text-[11px] text-slate-400">{section}</span>
              <strong className="max-w-44 truncate text-xs">{title}</strong>
            </div>
          </div>
          <SearchField
            className="mx-auto w-[min(430px,42vw)] max-md:w-full"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search this workspace"
            label="Search workspace"
            shortcut="⌘ K"
          />
          <div className="flex items-center gap-2">
            <IconButton className="relative" label="Notifications">
              <Bell size={18} />
              <i className="absolute top-[7px] right-[7px] size-[5px] rounded-full border border-white bg-red-500" />
            </IconButton>
            {action}
          </div>
        </header>
        {children}
      </main>
    </div>
  )
}
