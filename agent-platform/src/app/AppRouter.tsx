import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'

const ChatPage = lazy(() => import('../features/chat/ChatPage'))
const DashboardPage = lazy(() => import('../features/dashboard/DashboardPage'))

function ChatRoute() {
  const { conversationId = 'demo' } = useParams()
  return <ChatPage key={conversationId} />
}

export default function AppRouter() {
  return (
    <Suspense fallback={<div className="grid min-h-screen place-items-center text-sm text-slate-500">Loading workspace...</div>}>
      <Routes>
        <Route path="/chat/:conversationId" element={<ChatRoute />} />
        <Route path="/dashboard/*" element={<DashboardPage />} />
        <Route path="/" element={<Navigate replace to="/chat/demo" />} />
        <Route path="*" element={<Navigate replace to="/chat/demo" />} />
      </Routes>
    </Suspense>
  )
}
