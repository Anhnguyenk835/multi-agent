import { LayoutDashboard, Menu, MoreHorizontal, Plus } from 'lucide-react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { BrandMark, IconButton } from '../../../components/ui'
import { conversations } from '../data'

interface ChatSidebarProps {
  mobileOpen: boolean
  onClose: () => void
}

export function ChatSidebar({ mobileOpen, onClose }: ChatSidebarProps) {
  const navigate = useNavigate()

  return (
    <aside
      className={`${mobileOpen ? 'fixed inset-y-0 left-0 z-50 flex shadow-xl' : 'hidden'} w-[270px] shrink-0 flex-col border-r border-slate-200 bg-slate-50 p-4 lg:static lg:z-auto lg:flex lg:shadow-none`}
    >
      <div className="flex items-center justify-between px-1 py-1.5">
        <Link to="/chat/demo" className="flex items-center gap-2.5">
          <BrandMark className="chat-brand-mark" />
          <span className="text-sm font-semibold text-slate-900">Aster</span>
        </Link>
        <IconButton label="Close sidebar" onClick={onClose}>
          <Menu size={17} />
        </IconButton>
      </div>

      <button
        className="mt-6 flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3.5 py-3 text-left text-sm font-medium shadow-sm transition hover:border-slate-300"
        onClick={() => {
          onClose()
          navigate(`/chat/${crypto.randomUUID()}`)
        }}
      >
        <span className="flex items-center gap-2 text-slate-700">
          <Plus size={17} />
          New conversation
        </span>
        <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-400">⌘ K</kbd>
      </button>

      <nav className="mt-7" aria-label="Conversation history">
        <p className="px-2 text-[10px] font-semibold uppercase text-slate-400">Recent</p>
        <div className="mt-2 space-y-1">
          {conversations.map((conversation) => (
            <NavLink
              className={({ isActive }) =>
                `group flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 transition ${isActive ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`
              }
              key={conversation.id}
              to={`/chat/${conversation.id}`}
              onClick={onClose}
            >
              {({ isActive }) => (
                <>
                  <span className={`size-1.5 rounded-full ${isActive ? 'bg-blue-600' : 'bg-slate-300'}`} />
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{conversation.title}</span>
                  <span className="text-[10px] text-slate-400">{conversation.time}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      <Link
        to="/dashboard"
        onClick={onClose}
        className="mt-5 flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[13px] font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
      >
        <LayoutDashboard size={16} />
        Dashboard
      </Link>

      <div className="mt-auto border-t border-slate-200 pt-3">
        <button className="flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition hover:bg-slate-100">
          <span className="grid size-8 place-items-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
            TN
          </span>
          <span className="min-w-0 flex-1">
            <strong className="block truncate text-xs text-slate-700">Tuan Nguyen</strong>
            <small className="block text-[11px] text-slate-400">Personal workspace</small>
          </span>
          <MoreHorizontal size={17} className="text-slate-400" />
        </button>
      </div>
    </aside>
  )
}
