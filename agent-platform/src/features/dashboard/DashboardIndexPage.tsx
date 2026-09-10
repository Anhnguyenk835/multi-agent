import { Navigate } from 'react-router-dom'
import { Button } from '../../components/ui'
import { useMarketList } from './hooks/useDashboardData'

export default function DashboardIndexPage() {
  const { data: markets, error, loading, retry } = useMarketList()

  if (loading) {
    return <div className="grid min-h-screen place-items-center text-sm text-slate-500">Loading markets...</div>
  }
  if (error) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 p-6 text-center">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Dashboard unavailable</h1>
          <p className="mt-2 text-sm text-slate-500">{error}</p>
          <Button className="mt-4" onClick={retry}>
            Retry
          </Button>
        </div>
      </main>
    )
  }
  if (!markets?.length) {
    return <div className="grid min-h-screen place-items-center text-sm text-slate-500">No saved markets yet.</div>
  }
  return <Navigate replace to={`/markets/${markets[0]!.id}`} />
}
