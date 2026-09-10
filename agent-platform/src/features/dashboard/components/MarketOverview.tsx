import {
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  CircleDollarSign,
  Compass,
  Database,
  Gauge,
  ShieldAlert,
  TrendingUp,
  Users,
} from 'lucide-react'
import { useState } from 'react'
import type { MarketAnalysisResponse, MarketMetric, QualitativeLevel, RevenueTrendPoint } from '../types'
import { StatusPill } from './DashboardPrimitives'

const sectionClass = 'mt-9'
const cardClass = 'min-w-0 rounded-lg border border-slate-200 bg-white'
const eyebrowClass = 'text-[14px] font-bold text-slate-400 uppercase'
const evidenceButtonClass =
  'inline-flex items-center gap-1.5 bg-transparent py-1 text-[13px] font-bold text-blue-700 hover:text-blue-600'

const scoreLabels: Record<keyof MarketAnalysisResponse['overview']['scorecard'], string> = {
  demand: 'Demand',
  market_size: 'Market size',
  momentum: 'Momentum',
  commercial_quality: 'Commercial quality',
  accessibility: 'Accessibility',
  competitive_headroom: 'Competitive headroom',
}

const levelTone = (value: QualitativeLevel | 'unknown') =>
  value === 'high' ? 'green' : value === 'moderate' ? 'amber' : 'neutral'

const titleCase = (value: string) =>
  value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')

const compactNumber = (value: number, unit: MarketMetric['unit']) => {
  if (unit === 'USD') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  }
  if (unit === 'percent') return `${value}%`
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

const metricValue = (metric: MarketMetric) => {
  if (metric.range) {
    return `${compactNumber(metric.range.min, metric.unit)}–${compactNumber(metric.range.max, metric.unit)}`
  }
  return metric.value == null ? 'Not available' : compactNumber(metric.value, metric.unit)
}

function EvidenceButton({ sourceIds, onOpen }: { sourceIds: string[]; onOpen: (sourceIds: string[]) => void }) {
  return (
    <button className={evidenceButtonClass} onClick={() => onOpen(sourceIds)}>
      <Database size={13} />
      {sourceIds.length} {sourceIds.length === 1 ? 'source' : 'sources'}
    </button>
  )
}

function MarketMetricCard({ metric, onEvidence }: { metric: MarketMetric; onEvidence: (sourceIds: string[]) => void }) {
  return (
    <article className={`${cardClass} p-4`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-600">{metric.label}</span>
        <StatusPill tone="neutral">{metric.evidence_class}</StatusPill>
      </div>
      <strong className="mt-3.5 block text-[26px] leading-none text-slate-900 max-sm:text-[21px]">
        {metricValue(metric)}
      </strong>
      <div className="mt-2.5 flex items-center justify-between gap-2 text-[13px] text-slate-500">
        {metric.change ? (
          <span className={metric.change.value >= 0 ? 'font-bold text-emerald-700' : 'font-bold text-red-700'}>
            {metric.change.value >= 0 ? '+' : ''}
            {metric.change.value}% {metric.change.period}
          </span>
        ) : (
          <span>No comparison</span>
        )}
        <span>{metric.period}</span>
      </div>
      <div className="mt-4 flex items-center justify-between gap-2 border-t border-slate-100 pt-2.5 text-[13px] text-slate-500">
        <span>{metric.confidence}% confidence</span>
        <EvidenceButton sourceIds={metric.source_ids} onOpen={onEvidence} />
      </div>
      {metric.methodology && <p className="mt-2 text-[13px] leading-relaxed text-slate-400">{metric.methodology}</p>}
    </article>
  )
}

type TrendMode = 'revenue' | 'growth'

function formatGrowth(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

function MarketTrendChart({ points, mode }: { points: RevenueTrendPoint[]; mode: TrendMode }) {
  const chartPoints =
    mode === 'revenue'
      ? points
      : points.slice(1).map((point, index) => ({
          ...point,
          value: ((point.value - points[index]!.value) / points[index]!.value) * 100,
        }))
  const values = chartPoints.map((point) => point.value)
  const max = Math.max(...values, 1)
  const min = Math.min(...values)
  const range = Math.max(max - min, 1)
  const coordinates = values
    .map((value, index) => {
      const x = chartPoints.length === 1 ? 340 : (index / (chartPoints.length - 1)) * 680
      const y = 112 - ((value - min) / range) * 92
      return `${x},${y}`
    })
    .join(' ')

  return (
    <div
      className="mt-5"
      aria-label={
        mode === 'revenue' ? 'Estimated market revenue over the available years' : 'Market revenue growth rate'
      }
    >
      <div className="relative h-[150px] bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_41px,#edf0f4_42px)]">
        <svg
          className="relative z-1 h-32 w-full overflow-visible"
          viewBox="0 0 680 128"
          preserveAspectRatio="none"
          role="img"
        >
          <title>{mode === 'revenue' ? 'Estimated market revenue by year' : 'Market revenue growth by year'}</title>
          <polyline
            points={coordinates}
            fill="none"
            stroke="#1463ff"
            strokeWidth="3"
            vectorEffect="non-scaling-stroke"
          />
          {values.map((value, index) => {
            const x = chartPoints.length === 1 ? 340 : (index / (chartPoints.length - 1)) * 680
            const y = 112 - ((value - min) / range) * 92
            return (
              <circle
                key={chartPoints[index]?.period}
                cx={x}
                cy={y}
                r="4"
                fill="#fff"
                stroke="#1463ff"
                strokeWidth="3"
              />
            )
          })}
        </svg>
      </div>
      <div className="-mt-0.5 flex justify-between gap-2.5">
        {chartPoints.map((point, index) => (
          <span
            className={`flex flex-col text-[9px] text-slate-400 ${index === 1 ? 'items-center' : index === points.length - 1 ? 'items-end' : ''}`}
            key={point.period}
          >
            <strong className="text-xs text-slate-700">
              {mode === 'revenue' ? compactNumber(point.value, point.unit) : formatGrowth(point.value)}
            </strong>
            <small>{point.period}</small>
          </span>
        ))}
      </div>
    </div>
  )
}

export function MarketOverview({
  report,
  onOpenEvidence,
}: {
  report: MarketAnalysisResponse
  onOpenEvidence: (sourceIds: string[]) => void
}) {
  const { overview, competitors } = report
  const price = overview.commercial_dynamics.typical_annual_price
  const [trendMode, setTrendMode] = useState<TrendMode>('revenue')

  return (
    <>
      <section
        className={`${cardClass} mt-[18px] grid grid-cols-[minmax(0,1.35fr)_minmax(360px,1fr)] gap-7 border-l-[3px] border-l-blue-600 px-6 py-[22px] max-[1100px]:grid-cols-1 max-sm:p-[18px]`}
      >
        <div>
          <span className={eyebrowClass}>Executive market verdict</span>
          <div className="mt-2 flex items-center gap-3">
            <h2 className="text-[21px] font-medium text-slate-900">{titleCase(overview.verdict.status)}</h2>
            <StatusPill tone="blue">{report.report.overall_confidence}% confidence</StatusPill>
          </div>
          <p className="mt-2.5 max-w-[700px] text-sm leading-relaxed text-slate-600">{overview.verdict.summary}</p>
        </div>
        <div className="grid grid-cols-2 gap-[18px] border-l border-slate-200 pl-6 max-[1100px]:border-t max-[1100px]:border-l-0 max-[1100px]:pt-[18px] max-[1100px]:pl-0 max-sm:grid-cols-1">
          <div className="flex flex-col gap-2">
            <strong className="mb-0.5 text-xs text-slate-700">Market strengths</strong>
            {overview.verdict.strengths.map((strength) => (
              <span className="flex items-start gap-1.5 text-sm leading-snug text-slate-500" key={strength}>
                <TrendingUp className="shrink-0 text-emerald-600" size={13} /> {strength}
              </span>
            ))}
          </div>
          <div className="flex flex-col gap-2">
            <strong className="mb-0.5 text-xs text-slate-700">Structural constraints</strong>
            {overview.verdict.constraints.map((constraint) => (
              <span className="flex items-start gap-1.5 text-sm leading-snug text-slate-500" key={constraint}>
                <AlertTriangle className="shrink-0 text-amber-600" size={13} /> {constraint}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section
        className="mt-3.5 grid grid-cols-6 overflow-hidden rounded-lg border border-slate-200 bg-white max-[1100px]:grid-cols-3 max-sm:grid-cols-2"
        aria-label="Market scorecard"
      >
        {Object.entries(overview.scorecard).map(([key, score]) => (
          <article
            className="min-w-0 border-r border-b border-slate-200 p-3.5 even:max-sm:border-r-0 [&:nth-child(3)]:max-[1100px]:border-r-0 [&:nth-child(6)]:border-r-0 [&:nth-child(n+4)]:max-[1100px]:border-b-0 [&:nth-child(-n+4)]:max-sm:border-b"
            key={key}
          >
            <div className="flex items-baseline justify-between gap-1.5">
              <span className="truncate text-[11px] text-slate-500">
                {scoreLabels[key as keyof typeof scoreLabels]}
              </span>
              <strong className="text-lg text-slate-800">{score}</strong>
            </div>
            <span className="mt-2.5 block h-[3px] overflow-hidden rounded bg-slate-200">
              <i className="block h-full rounded bg-blue-600" style={{ width: `${score}%` }} />
            </span>
          </article>
        ))}
      </section>

      <section className={sectionClass}>
        <div className="mb-4 flex items-end justify-between gap-5 max-sm:items-start max-sm:flex-col">
          <div>
            <p className={eyebrowClass}>Measured market size</p>
            <h2 className="mt-1 text-base font-medium text-slate-800">Scale and demand indicators</h2>
          </div>
          <span className="text-[10px] text-slate-400">Data period · {report.report.data_period}</span>
        </div>
        <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
          {overview.market_size.metrics.map((metric) => (
            <MarketMetricCard key={metric.id} metric={metric} onEvidence={onOpenEvidence} />
          ))}
        </div>
      </section>

      <section className="mt-4 grid grid-cols-[minmax(0,1.7fr)_minmax(260px,.8fr)] gap-4 max-sm:grid-cols-1">
        <article className={`${cardClass} p-5`}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <span className={eyebrowClass}>Market revenue trend</span>
              <h2 className="mt-1 text-base font-medium text-slate-800">
                {trendMode === 'revenue' ? 'Estimated annual revenue' : 'Annual market growth'}
              </h2>
            </div>
            <div className="flex flex-col items-end gap-2 max-sm:items-start">
              <StatusPill tone="green">
                {titleCase(overview.momentum.direction)} · {overview.momentum.strength}
              </StatusPill>
              <div
                className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-0.5"
                role="group"
                aria-label="Market trend chart mode"
              >
                <button
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${trendMode === 'revenue' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                  onClick={() => setTrendMode('revenue')}
                  type="button"
                  aria-pressed={trendMode === 'revenue'}
                >
                  Revenue
                </button>
                <button
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${trendMode === 'growth' ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                  onClick={() => setTrendMode('growth')}
                  type="button"
                  aria-pressed={trendMode === 'growth'}
                >
                  Market growth
                </button>
              </div>
            </div>
          </div>
          <MarketTrendChart points={overview.market_size.revenue_history} mode={trendMode} />
          <p className="mt-3.5 border-t border-slate-100 pt-3 text-xs leading-relaxed text-slate-600">
            {trendMode === 'revenue'
              ? overview.momentum.summary
              : 'Growth is calculated from the estimated market revenue at consecutive yearly data points.'}
          </p>
        </article>
        <article className={`${cardClass} p-5`}>
          <span className={eyebrowClass}>Corroborating indicators</span>
          <h2 className="mt-1 mb-4 text-base font-medium text-slate-800">Momentum signals</h2>
          <div className="flex flex-col">
            {overview.momentum.signals.map((signal) => (
              <div
                className="grid grid-cols-[minmax(0,1fr)_auto_34px] items-center gap-2.5 border-t border-slate-100 py-3"
                key={signal.label}
              >
                <span className="flex min-w-0 flex-col">
                  <strong className="text-[13px] text-slate-800">{signal.label}</strong>
                  <small className="text-[9px] text-slate-400">{signal.source_ids.length} sources</small>
                </span>
                <strong className="text-[15px] text-emerald-700">
                  {signal.change >= 0 ? '+' : ''}
                  {signal.change}%
                </strong>
                <small className="text-[9px] text-slate-400">{signal.period}</small>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className={sectionClass}>
        <div className="mb-4">
          <div>
            <p className={eyebrowClass}>Customer structure</p>
            <h2 className="mt-1 text-base font-medium text-slate-800">Target Segments, jobs and pain points</h2>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 max-[1100px]:grid-cols-1">
          {overview.customer_segments.map((segment) => (
            <article className={`${cardClass} p-4`} key={segment.id}>
              <div className="flex items-center gap-2.5">
                <span className="grid size-9 shrink-0 place-items-center rounded-md bg-blue-50 text-blue-600">
                  <Users size={16} />
                </span>
                <div>
                  <h3 className="text-sm leading-snug text-slate-800">{segment.name}</h3>
                  <small className="text-[11px] text-slate-400">{segment.confidence}% confidence</small>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3.5 max-sm:grid-cols-1">
                <div className="flex flex-col gap-1.5">
                  <strong className="mb-0.5 text-[11px] text-slate-500 uppercase">Jobs</strong>
                  {segment.jobs.map((job) => (
                    <span className="text-[13px] leading-snug text-slate-600" key={job}>
                      {job}
                    </span>
                  ))}
                </div>
                <div className="flex flex-col gap-1.5">
                  <strong className="mb-0.5 text-[11px] text-slate-500 uppercase">Pain points</strong>
                  {segment.pain_points.map((pain) => (
                    <span className="text-[13px] leading-snug text-slate-600" key={pain}>
                      {pain}
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between gap-2 border-t border-slate-100 pt-2.5 text-[13px] text-slate-500">
                <span>
                  Willingness to pay ·{' '}
                  <strong className="text-slate-700 capitalize">{segment.willingness_to_pay}</strong>
                </span>
                <EvidenceButton sourceIds={segment.source_ids} onOpen={onOpenEvidence} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-4 grid grid-cols-2 gap-4 max-sm:grid-cols-1">
        <article className={`${cardClass} relative p-[18px]`}>
          <div className="absolute top-4 right-4 grid size-[34px] place-items-center rounded-md bg-blue-50 text-blue-600">
            <CircleDollarSign size={18} />
          </div>
          <span className={eyebrowClass}>Commercial dynamics</span>
          <h2 className="mt-1.5 mr-12 text-[17px] font-medium">{overview.commercial_dynamics.dominant_model}</h2>
          <p className="my-3 text-sm leading-relaxed text-slate-500">{overview.commercial_dynamics.summary}</p>
          <dl className="mb-3 grid grid-cols-3 gap-2 max-sm:grid-cols-1">
            <div className="border-l-2 border-slate-200 pl-2">
              <dt className="text-[10px] text-slate-400">Typical annual price</dt>
              <dd className="mt-1 text-sm font-bold text-slate-700">
                {price ? `$${price.min}–$${price.max}` : 'Unknown'}
              </dd>
            </div>
            <div className="border-l-2 border-slate-200 pl-2">
              <dt className="text-[10px] text-slate-400">Willingness to pay</dt>
              <dd className="mt-1 text-sm font-bold text-slate-700 capitalize">
                {overview.commercial_dynamics.willingness_to_pay}
              </dd>
            </div>
            <div className="border-l-2 border-slate-200 pl-2">
              <dt className="text-[10px] text-slate-400">Retention pressure</dt>
              <dd className="mt-1 text-sm font-bold text-slate-700 capitalize">
                {overview.commercial_dynamics.retention_pressure}
              </dd>
            </div>
          </dl>
          <EvidenceButton sourceIds={overview.commercial_dynamics.source_ids} onOpen={onOpenEvidence} />
        </article>
        <article className={`${cardClass} relative p-[18px]`}>
          <div className="absolute top-4 right-4 grid size-[34px] place-items-center rounded-md bg-emerald-50 text-emerald-700">
            <Compass size={18} />
          </div>
          <span className={eyebrowClass}>Market accessibility</span>
          <div className="flex items-baseline gap-2.5">
            <h2 className="mt-1.5 text-[17px] font-medium">{titleCase(overview.market_accessibility.level)}</h2>
            <span className="text-[11px] text-slate-400">{overview.market_accessibility.confidence}% confidence</span>
          </div>
          <p className="my-3 text-sm leading-relaxed text-slate-500">{overview.market_accessibility.summary}</p>
          <div className="mb-3 grid grid-cols-2 gap-[18px] max-sm:grid-cols-1">
            <div className="flex flex-col gap-1.5">
              <strong className="mb-0.5 text-[11px] text-slate-500 uppercase">Channels</strong>
              {overview.market_accessibility.channels.map((item) => (
                <span className="text-[13px] text-slate-600" key={item}>
                  {item}
                </span>
              ))}
            </div>
            <div className="flex flex-col gap-1.5">
              <strong className="mb-0.5 text-[11px] text-slate-500 uppercase">Barriers</strong>
              {overview.market_accessibility.barriers.map((item) => (
                <span className="text-[13px] text-slate-600" key={item}>
                  {item}
                </span>
              ))}
            </div>
          </div>
          <EvidenceButton sourceIds={overview.market_accessibility.source_ids} onOpen={onOpenEvidence} />
        </article>
      </section>

      <section className={sectionClass}>
        <div className="mb-4">
          <div>
            <p className={eyebrowClass}>Risk register</p>
            <h2 className="mt-1 text-base font-medium text-slate-800">Structural market risks</h2>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 max-[1100px]:grid-cols-1">
          {overview.risks.map((risk) => (
            <article className={`${cardClass} p-4`} key={risk.id}>
              <div className="mb-3 flex items-center gap-2 text-amber-700">
                <ShieldAlert size={17} />
                <span className="text-[11px] font-bold text-slate-500 uppercase">{risk.category}</span>
              </div>
              <h3 className="text-sm leading-snug text-slate-800">{risk.title}</h3>
              <p className="mt-2 min-h-12 text-sm leading-relaxed text-slate-500 max-[1100px]:min-h-0">
                {risk.summary}
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2.5 text-[13px] text-slate-500">
                <StatusPill tone={levelTone(risk.probability)}>Probability · {risk.probability}</StatusPill>
                <StatusPill tone={levelTone(risk.impact)}>Impact · {risk.impact}</StatusPill>
                <span className="ml-auto">
                  <EvidenceButton sourceIds={risk.source_ids} onOpen={onOpenEvidence} />
                </span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className={sectionClass}>
        <div className="mb-4 flex items-end justify-between gap-5">
          <div>
            <p className={eyebrowClass}>Opportunity map</p>
            <h2 className="mt-1 text-base font-medium text-slate-800">Evidence-backed unmet needs</h2>
          </div>
          <span className="text-[10px] text-slate-400">{overview.opportunity_gaps.length} identified gaps</span>
        </div>
        <div className="grid grid-cols-3 gap-3 max-[1100px]:grid-cols-1">
          {overview.opportunity_gaps.map((gap) => (
            <article className={`${cardClass} p-4`} key={gap.id}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold text-slate-500 uppercase">{gap.segment}</span>
                <strong className="text-[17px] text-blue-600">{gap.confidence}%</strong>
              </div>
              <h3 className="min-h-[52px] text-sm leading-snug text-slate-800 max-[1100px]:min-h-0">
                {gap.unmet_need}
              </h3>
              <dl className="mt-3.5 grid grid-cols-3 gap-1.5">
                <div className="min-w-0 border-l-2 border-slate-200 pl-2">
                  <dt className="text-[10px] text-slate-400">Demand</dt>
                  <dd className="mt-1 text-[13px] font-bold text-slate-700 capitalize">{gap.demand_strength}</dd>
                </div>
                <div className="min-w-0 border-l-2 border-slate-200 pl-2">
                  <dt className="text-[10px] text-slate-400">Competitor coverage</dt>
                  <dd className="mt-1 text-[13px] font-bold text-slate-700 capitalize">{gap.competitor_coverage}</dd>
                </div>
                <div className="min-w-0 border-l-2 border-slate-200 pl-2">
                  <dt className="text-[10px] text-slate-400">Commercial signal</dt>
                  <dd className="mt-1 text-[13px] font-bold text-slate-700 capitalize">{gap.commercial_signal}</dd>
                </div>
              </dl>
              <div className="mt-4 flex items-center justify-between gap-2 border-t border-slate-100 pt-2.5 text-[13px] text-slate-500">
                <span className="inline-flex items-center gap-1.5">
                  <Gauge size={14} /> Confidence
                </span>
                <EvidenceButton sourceIds={gap.source_ids} onOpen={onOpenEvidence} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section
        className="mt-[18px] flex items-center gap-[22px] border-t border-slate-200 px-0.5 pt-4 text-[13px] text-slate-500 max-sm:flex-col max-sm:items-start max-sm:gap-2"
        aria-label="Market facts"
      >
        <span className="inline-flex items-center gap-1.5">
          <BarChart3 size={15} /> {competitors.summary.tracked_products} tracked products
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ArrowUpRight size={15} /> {titleCase(competitors.summary.market_structure)} market
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Database size={15} /> {report.evidence.length} evidence sources
        </span>
      </section>
    </>
  )
}
