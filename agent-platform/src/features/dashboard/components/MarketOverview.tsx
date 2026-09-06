import { ArrowRight, Bookmark, Check, CircleDollarSign, Lightbulb, Network, Sparkles, TrendingUp, Users } from 'lucide-react'
import { Button, IconButton } from '../../../components/ui'
import type { Competitor, DashboardView, Idea, Topic } from '../types'
import { Metric, SectionHeader, StatusPill } from './DashboardPrimitives'

const trendPoints = '0,116 52,108 104,111 156,91 208,95 260,72 312,81 364,52 416,57 468,31 520,40 572,18 624,23 676,8'

function MarketChart() {
  return <div className="market-chart" aria-label="Market momentum rose from 42 to 82 over twelve weeks"><div className="chart-y-labels" aria-hidden="true"><span>90</span><span>60</span><span>30</span><span>0</span></div><div className="chart-plot"><div className="chart-grid" aria-hidden="true" /><svg viewBox="0 0 676 128" preserveAspectRatio="none" role="img"><title>Market momentum over twelve weeks</title><polyline points={trendPoints} fill="none" stroke="#1463ff" strokeWidth="3" vectorEffect="non-scaling-stroke" /><circle cx="676" cy="8" r="5" fill="#ffffff" stroke="#1463ff" strokeWidth="3" vectorEffect="non-scaling-stroke" /></svg><div className="chart-x-labels" aria-hidden="true"><span>Jun 17</span><span>Jul 08</span><span>Jul 29</span><span>Aug 19</span><span>Sep 06</span></div></div></div>
}

function CoverageMap() {
  return <div className="coverage-map" aria-label="Research coverage network: 28 sources, 43 claims, and 5 categories"><span className="coverage-node node-main"><Network size={19} /></span><span className="coverage-node node-one">28</span><span className="coverage-node node-two">43</span><span className="coverage-node node-three">5</span><span className="coverage-node node-four"><Check size={14} /></span><i className="link-one" /><i className="link-two" /><i className="link-three" /><i className="link-four" /></div>
}

export function TopicRows({ topics, onSelect }: { topics: Topic[]; onSelect: (id: string) => void }) {
  return <div className="topic-rows">{topics.map((topic) => <button className="topic-row" key={topic.id} onClick={() => onSelect(topic.id)}><span className="topic-dot" style={{ backgroundColor: topic.color }} /><span className="topic-copy"><strong>{topic.name}</strong><span>{topic.summary}</span></span><span className="topic-stat"><strong>{topic.momentum}</strong><small>momentum</small></span><span className="topic-stat"><strong>{topic.competitors}</strong><small>competitors</small></span><span className="topic-stat"><strong>{topic.ideas}</strong><small>ideas</small></span><StatusPill tone={topic.status === 'Active' ? 'blue' : topic.status === 'Tracking' ? 'green' : 'amber'}>{topic.status}</StatusPill><ArrowRight className="row-arrow" size={17} /></button>)}</div>
}

export function IdeaCard({ idea, onToggle, onOpen }: { idea: Idea; onToggle: (id: string) => void; onOpen: (name: string) => void }) {
  const isShortlisted = idea.status === 'Shortlisted'
  return <article className="idea-card"><div className="idea-topline"><StatusPill tone={isShortlisted ? 'blue' : idea.status === 'Validating' ? 'green' : 'neutral'}>{idea.status}</StatusPill><IconButton className="icon-button" active={isShortlisted} onClick={() => onToggle(idea.id)} label={isShortlisted ? `Remove ${idea.title} from shortlist` : `Shortlist ${idea.title}`}><Bookmark size={16} fill={isShortlisted ? 'currentColor' : 'none'} /></IconButton></div><h3>{idea.title}</h3><p>{idea.description}</p><dl><div><dt>Audience</dt><dd>{idea.audience}</dd></div><div><dt>Model</dt><dd>{idea.model}</dd></div></dl><div className="idea-footer"><span className="score-ring" style={{ '--score': `${idea.score * 3.6}deg` } as React.CSSProperties}>{idea.score}</span><span><strong>{idea.evidence} signals</strong><small>Evidence linked</small></span><button className="text-button" onClick={() => onOpen(idea.title)}>Open <ArrowRight size={14} /></button></div></article>
}

export function CompetitorTable({ rows, onAnalyze }: { rows: Competitor[]; onAnalyze: (name: string) => void }) {
  return <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Company</th><th>Category</th><th>Pricing</th><th>Revenue evidence</th><th>Confidence</th><th>Signal</th><th><span className="ui-sr-only">Actions</span></th></tr></thead><tbody>{rows.map((competitor) => <tr key={competitor.id}><td><span className="company-avatar">{competitor.name[0]}</span><span><strong>{competitor.name}</strong><small>Updated {competitor.updated}</small></span></td><td>{competitor.category}</td><td>{competitor.pricing}</td><td><StatusPill tone={competitor.revenue === 'Reported' ? 'green' : competitor.revenue === 'Estimated' ? 'amber' : 'neutral'}>{competitor.revenue}</StatusPill></td><td><span className="confidence"><i style={{ width: `${competitor.confidence}%` }} /></span><small>{competitor.confidence}%</small></td><td className="positive">{competitor.signal}</td><td><IconButton className="icon-button" onClick={() => onAnalyze(competitor.name)} label={`Analyze ${competitor.name}`}><ArrowRight size={16} /></IconButton></td></tr>)}</tbody></table></div>
}

interface MarketOverviewProps {
  topic: Topic
  topics: Topic[]
  ideas: Idea[]
  competitors: Competitor[]
  onSelectTopic: (id: string) => void
  onToggleIdea: (id: string) => void
  onOpenIdea: (name: string) => void
  onNavigate: (view: DashboardView) => void
  onAnalyze: (name: string) => void
}

export function MarketOverview({ topic, topics, ideas, competitors, onSelectTopic, onToggleIdea, onOpenIdea, onNavigate, onAnalyze }: MarketOverviewProps) {
  const topicIdeas = ideas.filter((idea) => idea.topicId === topic.id).slice(0, 3)
  return <><section className="metric-band" aria-label="Topic metrics"><Metric icon={TrendingUp} label="Market momentum" value={`${topic.momentum}/100`} detail="Up 14 points" tone="blue" /><Metric icon={Users} label="Tracked competitors" value={topic.competitors} detail="3 added this month" tone="violet" /><Metric icon={Lightbulb} label="Saved ideas" value={topic.ideas} detail="2 shortlisted" tone="amber" /><Metric icon={CircleDollarSign} label="Pricing median" value="$18" detail="Per user / month" tone="green" /></section><section className="overview-grid"><article className="panel momentum-panel"><div className="panel-heading"><div><span className="panel-kicker">12-week signal</span><h2>Market momentum</h2></div><div className="legend"><i />Composite score</div></div><MarketChart /><div className="chart-note"><Sparkles size={15} /><span><strong>Acceleration detected.</strong> Launch activity and user discussion increased together over the last three weeks.</span></div></article><article className="panel coverage-panel"><div className="panel-heading"><div><span className="panel-kicker">Evidence graph</span><h2>Research coverage</h2></div><StatusPill tone="green">Strong</StatusPill></div><CoverageMap /><div className="coverage-legend"><span><i className="blue-dot" />28 sources</span><span><i className="green-dot" />43 claims</span><span><i className="amber-dot" />5 categories</span></div><Button className="secondary-button" variant="secondary" block onClick={() => onNavigate('analyses')}>Inspect latest analysis <ArrowRight size={14} /></Button></article></section><section className="content-section"><SectionHeader eyebrow="Workspace" title="Tracked markets" action="View all topics" onAction={() => onNavigate('topics')} /><TopicRows topics={topics} onSelect={onSelectTopic} /></section><section className="content-section"><SectionHeader eyebrow="Opportunity queue" title="Ideas worth testing" action="View all ideas" onAction={() => onNavigate('ideas')} /><div className="idea-grid">{topicIdeas.map((idea) => <IdeaCard key={idea.id} idea={idea} onToggle={onToggleIdea} onOpen={onOpenIdea} />)}</div></section><section className="content-section"><SectionHeader eyebrow="Landscape" title="Competitors gaining attention" action="Compare all" onAction={() => onNavigate('competitors')} /><CompetitorTable rows={competitors.slice(0, 4)} onAnalyze={onAnalyze} /></section></>
}
