import { Bot, Check, ExternalLink, X } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useParams, useSearchParams } from 'react-router-dom'
import { IconButton } from '../../components/ui'
import { DashboardShell } from './components/DashboardShell'
import { SectionHeader, StatusPill } from './components/DashboardPrimitives'
import { MarketCompetitors } from './components/MarketCompetitors'
import { MarketOverview } from './components/MarketOverview'
import { analysisHistory, marketAnalysisReports } from './data'
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
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [selectedCompetitor, setSelectedCompetitor] = useState<Competitor | null>(null)
  const response = marketAnalysisReports.find((item) => item.market.id === marketId)

  if (!response) return <Navigate replace to="/dashboard" />

  const { market, report, competitors, evidence } = response
  const view: MarketView = searchParams.get('view') === 'competitors' ? 'competitors' : 'overview'
  const history = analysisHistory.filter((item) => item.market_id === market.id)
  const changeView = (next: MarketView) => setSearchParams(next === 'overview' ? {} : { view: next })
  const openEvidence = (sourceIds: string[]) => {
    const publishers = evidence
      .filter((source) => sourceIds.includes(source.id))
      .map((source) => source.publisher)
      .join(', ')
    setNotice(`${sourceIds.length} evidence ${sourceIds.length === 1 ? 'source' : 'sources'}: ${publishers}`)
  }

  return (
    <DashboardShell title={market.name} section="Market" searchQuery={query} onSearchChange={setQuery}>
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
              <span>Report v{report.version}</span>
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
          <small className="ml-auto text-slate-400 max-sm:ml-0 max-sm:w-full">Schema {response.schema_version}</small>
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
          <>
            <MarketOverview report={response} onOpenEvidence={openEvidence} />
            <section className="mt-9" id="analysis-history">
              <SectionHeader eyebrow="Version history" title="Saved market reports" />
              <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                {history.map((item) => (
                  <article
                    className="grid grid-cols-[36px_minmax(0,1fr)_80px_80px_auto_32px] items-center gap-3 border-b border-slate-100 p-3 last:border-b-0 max-sm:grid-cols-[36px_minmax(0,1fr)_auto_32px]"
                    key={item.id}
                  >
                    <span
                      className={`grid size-9 place-items-center rounded-md ${item.status === 'partial' ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-blue-600'}`}
                    >
                      <Bot size={17} />
                    </span>
                    <div className="flex min-w-0 flex-col">
                      <strong className="text-xs text-slate-800">{item.type}</strong>
                      <small className="mt-1 truncate text-[10px] text-slate-400">
                        {item.id} · {item.saved_at}
                      </small>
                    </div>
                    <span className="flex flex-col max-sm:hidden">
                      <strong className="text-xs text-slate-700">v{item.version}</strong>
                      <small className="text-[10px] text-slate-400">report</small>
                    </span>
                    <span className="flex flex-col max-sm:hidden">
                      <strong className="text-xs text-slate-700">{item.source_count}</strong>
                      <small className="text-[10px] text-slate-400">sources</small>
                    </span>
                    <StatusPill tone={item.status === 'completed' ? 'green' : 'amber'}>
                      {titleCase(item.status)}
                    </StatusPill>
                    <IconButton
                      onClick={() => setNotice(`Opening saved report ${item.id}.`)}
                      label={`Open ${item.type}`}
                    >
                      <ExternalLink size={15} />
                    </IconButton>
                  </article>
                ))}
              </div>
            </section>
          </>
        ) : (
          <MarketCompetitors
            analysis={competitors}
            query={query}
            onOpen={setSelectedCompetitor}
            onOpenEvidence={openEvidence}
          />
        )}
      </div>

      {notice && (
        <div
          className="fixed right-6 bottom-6 z-50 flex max-w-[420px] items-center gap-2.5 rounded-lg bg-slate-900 px-4 py-3 text-xs text-white shadow-xl max-sm:right-4 max-sm:bottom-4 max-sm:left-4"
          role="status"
        >
          <Check className="shrink-0 text-emerald-400" size={16} />
          <span className="min-w-0 flex-1">{notice}</span>
          <button
            className="grid size-6 place-items-center rounded text-slate-300 hover:bg-white/10 hover:text-white"
            onClick={() => setNotice('')}
            aria-label="Dismiss notification"
          >
            <X size={14} />
          </button>
        </div>
      )}
      {selectedCompetitor && (
        <CompetitorDrawer competitor={selectedCompetitor} onClose={() => setSelectedCompetitor(null)} />
      )}
    </DashboardShell>
  )
}
