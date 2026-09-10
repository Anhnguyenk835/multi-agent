import { X } from 'lucide-react'
import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Button, IconButton } from '../../components/ui'
import { DashboardShell } from './components/DashboardShell'
import { EvidenceDrawer } from './components/EvidenceDrawer'
import { StatusPill } from './components/DashboardPrimitives'
import { MarketCompetitors } from './components/MarketCompetitors'
import { MarketOverview } from './components/MarketOverview'
import { useMarketWorkspace } from './hooks/useDashboardData'
import type { Competitor, MarketView } from './types'

const titleCase = (value: string) =>
  value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')

const eyebrowClass = 'text-[11px] font-bold text-slate-400 uppercase'
const drawerFactClass = 'border-l-2 border-slate-200 pl-2'

function CompetitorDrawer({ competitor, onClose }: { competitor: Competitor; onClose: () => void }) {
  const annualPrice = competitor.pricing.annual_price
  return (
    <>
      <button className="fixed inset-0 z-40 bg-slate-950/25" onClick={onClose} aria-label="Close competitor detail" />
      <aside
        className="fixed inset-y-0 right-0 z-50 w-[min(460px,100vw)] overflow-y-auto border-l border-slate-200 bg-white p-6 shadow-2xl"
        aria-label={`${competitor.name} competitor profile`}
      >
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-md bg-blue-50 font-bold text-blue-700">
            {competitor.name[0]}
          </span>
          <div className="min-w-0 flex-1">
            <span className={eyebrowClass}>Competitor profile</span>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">{competitor.name}</h2>
          </div>
          <IconButton label="Close competitor detail" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-slate-600">{competitor.positioning}</p>
        <dl className="mt-6 grid grid-cols-2 gap-4">
          <div className={drawerFactClass}>
            <dt className="text-[10px] text-slate-400 uppercase">Type</dt>
            <dd className="mt-1 text-sm font-semibold text-slate-700">{titleCase(competitor.type)}</dd>
          </div>
          <div className={drawerFactClass}>
            <dt className="text-[10px] text-slate-400 uppercase">Platforms</dt>
            <dd className="mt-1 text-sm font-semibold text-slate-700">{competitor.platforms.join(', ')}</dd>
          </div>
          <div className={drawerFactClass}>
            <dt className="text-[10px] text-slate-400 uppercase">Pricing model</dt>
            <dd className="mt-1 text-sm font-semibold text-slate-700">{competitor.pricing.model}</dd>
          </div>
          <div className={drawerFactClass}>
            <dt className="text-[10px] text-slate-400 uppercase">Annual price</dt>
            <dd className="mt-1 text-sm font-semibold text-slate-700">
              {annualPrice == null ? 'Not reported' : `${competitor.pricing.currency ?? 'USD'} ${annualPrice}`}
            </dd>
          </div>
          <div className={drawerFactClass}>
            <dt className="text-[10px] text-slate-400 uppercase">Evidence</dt>
            <dd className="mt-1 text-sm font-semibold text-slate-700">{competitor.source_ids.length} sources</dd>
          </div>
          <div className={drawerFactClass}>
            <dt className="text-[10px] text-slate-400 uppercase">Confidence</dt>
            <dd className="mt-1 text-sm font-semibold text-slate-700">{competitor.confidence}%</dd>
          </div>
        </dl>
        <section className="mt-8 border-t border-slate-200 pt-6">
          <span className={eyebrowClass}>Observed strengths</span>
          <h3 className="mt-1 text-base font-semibold text-slate-800">What supports its position</h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-600">
            {competitor.strengths.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        <section className="mt-8 border-t border-slate-200 pt-6">
          <span className={eyebrowClass}>Observed weaknesses</span>
          <h3 className="mt-1 text-base font-semibold text-slate-800">Where customers face friction</h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-600">
            {competitor.weaknesses.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </aside>
    </>
  )
}

export default function MarketWorkspacePage() {
  const { marketId } = useParams()
  const { data, error, loading, retry } = useMarketWorkspace(marketId)
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [selectedCompetitor, setSelectedCompetitor] = useState<Competitor | null>(null)
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState<string[]>([])
  if (loading) {
    return <div className="grid min-h-screen place-items-center text-sm text-slate-500">Loading market analysis...</div>
  }
  if (error || !data) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 p-6 text-center">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Market analysis unavailable</h1>
          <p className="mt-2 text-sm text-slate-500">{error || 'Market not found.'}</p>
          <Button className="mt-4" onClick={retry}>
            Retry
          </Button>
        </div>
      </main>
    )
  }

  const { report: response, markets } = data
  const { market, report, competitors, evidence } = response
  const view: MarketView = searchParams.get('view') === 'competitors' ? 'competitors' : 'overview'
  const selectedEvidence = evidence.filter((source) => selectedEvidenceIds.includes(source.id))
  const changeView = (next: MarketView) => setSearchParams(next === 'overview' ? {} : { view: next })
  const openEvidence = (sourceIds: string[]) => {
    setSelectedCompetitor(null)
    setSelectedEvidenceIds(sourceIds)
  }

  return (
    <DashboardShell
      title={market.name}
      section="Market"
      searchQuery={query}
      onSearchChange={setQuery}
      markets={markets}
    >
      <div className="mx-auto w-full max-w-[1440px] px-[34px] pt-[34px] pb-[52px] max-md:px-5 max-sm:px-4 max-sm:pt-6">
        <div className="mb-7 flex min-h-16 items-start justify-between gap-6">
          <div className="min-w-0">
            <p className="mb-1 text-[10px] font-bold text-blue-600 uppercase">App Market</p>
            <h1 className="text-[34px] leading-tight font-bold text-slate-950 max-sm:text-2xl">{market.name}</h1>
            <span className="mt-2 block max-w-[680px] text-sm leading-relaxed text-slate-500">{market.definition}</span>
            <div className="mt-4 flex flex-wrap items-center gap-2.5 text-[11px] text-slate-500 [&>span:not(:first-child):not(:last-child)]:border-l [&>span:not(:first-child):not(:last-child)]:border-slate-300 [&>span:not(:first-child):not(:last-child)]:pl-2.5">
              <StatusPill tone={report.status === 'completed' ? 'green' : 'amber'}>
                {titleCase(report.status)}
              </StatusPill>
              <span>{report.data_period}</span>
              <span>{report.overall_confidence}% confidence</span>
              <StatusPill tone={report.freshness === 'current' ? 'blue' : 'amber'}>
                {titleCase(report.freshness)}
              </StatusPill>
            </div>
          </div>
        </div>

        <div
          className="-mt-2 mb-5 flex items-center gap-2 text-xs text-slate-500 max-sm:flex-wrap max-sm:items-start"
          aria-label="Market scope"
        >
          <span className="rounded-md border border-slate-200 bg-white px-2 py-1">{market.scope.customer_type}</span>
          <span className="rounded-md border border-slate-200 bg-white px-2 py-1">
            {market.scope.geography.join(', ')}
          </span>
          <span className="rounded-md border border-slate-200 bg-white px-2 py-1">
            {market.scope.platforms.join(' · ')}
          </span>
        </div>

        <div className="flex gap-7 border-b border-slate-200" role="tablist" aria-label="Market views">
          <button
            role="tab"
            aria-selected={view === 'overview'}
            className={`relative flex items-center gap-2 py-3 text-xs font-semibold after:absolute after:inset-x-0 after:bottom-[-1px] after:h-0.5 ${view === 'overview' ? 'text-blue-600 after:bg-blue-600' : 'text-slate-500 after:bg-transparent'}`}
            onClick={() => changeView('overview')}
          >
            Overview
          </button>
          <button
            role="tab"
            aria-selected={view === 'competitors'}
            className={`relative flex items-center gap-2 py-3 text-xs font-semibold after:absolute after:inset-x-0 after:bottom-[-1px] after:h-0.5 ${view === 'competitors' ? 'text-blue-600 after:bg-blue-600' : 'text-slate-500 after:bg-transparent'}`}
            onClick={() => changeView('competitors')}
          >
            Competitors
            <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[9px] text-slate-500">
              {competitors.summary.tracked_products}
            </span>
          </button>
        </div>

        {view === 'overview' ? (
          <MarketOverview report={response} onOpenEvidence={openEvidence} />
        ) : (
          <MarketCompetitors
            analysis={competitors}
            query={query}
            onOpen={setSelectedCompetitor}
            onOpenEvidence={openEvidence}
          />
        )}
      </div>
      {selectedCompetitor && (
        <CompetitorDrawer competitor={selectedCompetitor} onClose={() => setSelectedCompetitor(null)} />
      )}
      {selectedEvidence.length > 0 && (
        <EvidenceDrawer sources={selectedEvidence} onClose={() => setSelectedEvidenceIds([])} />
      )}
    </DashboardShell>
  )
}
