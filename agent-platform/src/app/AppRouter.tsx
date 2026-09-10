import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'

const ChatPage = lazy(() => import('../features/chat/ChatPage'))
const DashboardIndexPage = lazy(() => import('../features/dashboard/DashboardIndexPage'))
const MarketWorkspacePage = lazy(() => import('../features/dashboard/MarketWorkspacePage'))

function ChatRoute() {
  const { conversationId = 'demo' } = useParams()
  return <ChatPage key={conversationId} />
}

export default function AppRouter() {
  return (
    <Suspense
      fallback={<div className="grid min-h-screen place-items-center text-sm text-slate-500">Loading workspace...</div>}
    >
      <Routes>
        <Route path="/chat/:conversationId" element={<ChatRoute />} />
        <Route path="/dashboard/*" element={<DashboardIndexPage />} />
        <Route path="/markets/:marketId" element={<MarketWorkspacePage />} />
        <Route path="/" element={<Navigate replace to="/chat/demo" />} />
        <Route path="*" element={<Navigate replace to="/chat/demo" />} />
      </Routes>
    </Suspense>
  )
}
