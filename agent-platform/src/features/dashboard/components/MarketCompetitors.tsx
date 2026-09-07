import { ArrowRight, Database, Filter } from 'lucide-react'
import { useState } from 'react'
import { IconButton } from '../../../components/ui'
import type { Competitor, CompetitorAnalysis } from '../types'
import { StatusPill } from './DashboardPrimitives'

const eyebrowClass = 'text-[11px] font-bold text-slate-400 uppercase'

const titleCase = (value: string) =>
  value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')

const formatPricing = (competitor: Competitor) => {
  const { model, annual_price: annualPrice, currency } = competitor.pricing
  return annualPrice == null ? model : `${currency ?? 'USD'} ${annualPrice}/year`
}

function CompetitorTable({ rows, onOpen }: { rows: Competitor[]; onOpen: (competitor: Competitor) => void }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-[1120px] w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-bold text-slate-500 uppercase">
            <th className="w-[15%] px-4 py-3">Product</th>
            <th className="w-[19%] px-4 py-3">Type & positioning</th>
            <th className="w-[10%] px-4 py-3">Platforms</th>
            <th className="w-[11%] px-4 py-3">Pricing</th>
            <th className="w-[16%] px-4 py-3">Strengths</th>
            <th className="w-[16%] px-4 py-3">Weaknesses</th>
            <th className="px-4 py-3">Evidence</th>
            <th className="px-4 py-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((competitor) => (
            <tr className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/70" key={competitor.id}>
              <td className="px-4 py-3.5">
                <span className="flex items-center gap-2.5">
                  <span className="grid size-8 shrink-0 place-items-center rounded-md bg-blue-50 font-bold text-blue-700">
                    {competitor.name[0]}
                  </span>
                  <span className="flex flex-col">
                    <strong className="text-slate-800">{competitor.name}</strong>
                    <small className="mt-0.5 text-[10px] text-slate-400">{competitor.confidence}% confidence</small>
                  </span>
                </span>
              </td>
              <td className="px-4 py-3.5">
                <span className="flex flex-col items-start gap-1.5">
                  <StatusPill tone={competitor.type === 'direct' ? 'blue' : 'neutral'}>
                    {titleCase(competitor.type)}
                  </StatusPill>
                  <small className="leading-relaxed text-slate-500">{competitor.positioning}</small>
                </span>
              </td>
              <td className="px-4 py-3.5 text-slate-600">{competitor.platforms.join(', ')}</td>
              <td className="px-4 py-3.5 text-slate-600">{formatPricing(competitor)}</td>
              <td className="px-4 py-3.5">
                <span className="flex min-w-[130px] flex-col gap-1 text-slate-500">
                  {competitor.strengths.map((item) => (
                    <small className="before:mr-1 before:text-slate-300 before:content-['·']" key={item}>
                      {item}
                    </small>
                  ))}
                </span>
              </td>
              <td className="px-4 py-3.5">
                <span className="flex min-w-[130px] flex-col gap-1 text-slate-500">
                  {competitor.weaknesses.map((item) => (
                    <small className="before:mr-1 before:text-slate-300 before:content-['·']" key={item}>
                      {item}
                    </small>
                  ))}
                </span>
              </td>
              <td className="px-4 py-3.5">
                <span className="inline-flex items-center gap-1.5 text-[10px] text-slate-600">
                  <Database size={13} />
                  {competitor.source_ids.length}
                </span>
              </td>
              <td className="px-4 py-3.5">
                <IconButton onClick={() => onOpen(competitor)} label={`Open ${competitor.name}`}>
                  <ArrowRight size={16} />
                </IconButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function MarketCompetitors({
  analysis,
  query,
  onOpen,
  onOpenEvidence,
}: {
  analysis: CompetitorAnalysis
  query: string
  onOpen: (competitor: Competitor) => void
  onOpenEvidence: (sourceIds: string[]) => void
}) {
  const [directOnly, setDirectOnly] = useState(false)
  const normalized = query.trim().toLowerCase()
  const rows = analysis.items.filter(
    (item) =>
      `${item.name} ${item.positioning} ${item.platforms.join(' ')}`.toLowerCase().includes(normalized) &&
      (!directOnly || item.type === 'direct'),
  )
  const summary = analysis.summary

  return (
    <>
      <section className="mt-[18px] grid grid-cols-4 overflow-hidden rounded-lg border border-slate-200 bg-white max-sm:grid-cols-2">
        <div className="flex flex-col border-r border-slate-200 p-4 max-sm:border-b">
          <span className={eyebrowClass}>Competition</span>
          <strong className="mt-2 text-lg capitalize text-slate-800">{titleCase(summary.competition_level)}</strong>
          <small className="mt-1 text-[11px] text-slate-400">market pressure</small>
        </div>
        <div className="flex flex-col border-r border-slate-200 p-4 max-sm:border-b max-sm:border-r-0">
          <span className={eyebrowClass}>Structure</span>
          <strong className="mt-2 text-lg capitalize text-slate-800">{titleCase(summary.market_structure)}</strong>
          <small className="mt-1 text-[11px] text-slate-400">{summary.tracked_products} tracked products</small>
        </div>
        <div className="flex flex-col border-r border-slate-200 p-4">
          <span className={eyebrowClass}>Concentration</span>
          <strong className="mt-2 text-lg text-slate-800">{summary.top_10_revenue_concentration ?? 'N/A'}%</strong>
          <small className="mt-1 text-[11px] text-slate-400">top 10 revenue share</small>
        </div>
        <div className="flex flex-col p-4">
          <span className={eyebrowClass}>Feature saturation</span>
          <strong className="mt-2 text-lg capitalize text-slate-800">{titleCase(summary.feature_saturation)}</strong>
          <small className="mt-1 text-[11px] text-slate-400">{titleCase(summary.switching_cost)} switching cost</small>
        </div>
      </section>

      <section className="mt-9">
        <div className="mb-4 flex items-end justify-between gap-5 max-sm:items-start max-sm:flex-col">
          <div>
            <p className={eyebrowClass}>Market landscape</p>
            <h2 className="mt-1 text-base font-medium text-slate-800">Products shaping this market</h2>
          </div>
          <div className="flex items-center gap-3 max-sm:w-full max-sm:justify-between">
            <button
              className="inline-flex items-center gap-1.5 py-1 text-[13px] font-bold text-blue-700 hover:text-blue-600"
              onClick={() => onOpenEvidence(summary.source_ids)}
            >
              <Database size={13} />
              Evidence
            </button>
            <button
              className="inline-flex min-h-[34px] items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-[11px] font-semibold text-slate-600 hover:border-slate-300 hover:text-slate-900"
              onClick={() => setDirectOnly((current) => !current)}
            >
              <Filter size={14} />
              {directOnly ? 'Direct only' : 'All competitor types'}
            </button>
          </div>
        </div>
        <CompetitorTable rows={rows} onOpen={onOpen} />
        {rows.length === 0 && <p className="mt-5 text-[11px] text-slate-500">No competitors match this search.</p>}
      </section>
    </>
  )
}
