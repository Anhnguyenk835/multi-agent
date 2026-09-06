import { Bell, Bot, Boxes, Check, ChevronDown, ExternalLink, Filter, GitCompareArrows, Lightbulb, Menu, Plus, RefreshCw, X } from 'lucide-react'
import { Button, IconButton, SearchField } from '../../components/ui'
import '../../styles/dashboard.css'
import { analyses } from './data'
import { DashboardSidebar } from './components/DashboardSidebar'
import { EmptyState, StatusPill } from './components/DashboardPrimitives'
import { CompetitorTable, IdeaCard, MarketOverview, TopicRows } from './components/MarketOverview'
import { NewTopicModal } from './components/NewTopicModal'
import { useDashboard } from './hooks/useDashboard'
import { dashboardViewLabel } from './lib/navigation'
import type { IdeaStatus } from './types'

const ideaFilters: Array<'All' | IdeaStatus> = ['All', 'Shortlisted', 'Validating']

export default function DashboardPage() {
  const state = useDashboard()
  const viewTitle = dashboardViewLabel(state.activeView)
  const analyzeCompetitor = (name: string) => state.setNotice(`A new chat for ${name} would start here.`)
  const openIdea = (name: string) => state.setNotice(`Opening the saved workspace for ${name}.`)

  return (
    <div className="dashboard-shell">
      <DashboardSidebar activeView={state.activeView} mobileOpen={state.mobileNavOpen} onNavigate={state.navigate} onNotice={state.setNotice} />
      {state.mobileNavOpen && <button className="sidebar-scrim" onClick={() => state.setMobileNavOpen(false)} aria-label="Close navigation" />}

      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <div className="topbar-title"><IconButton className="icon-button mobile-menu" onClick={() => state.setMobileNavOpen(true)} label="Open navigation"><Menu size={19} /></IconButton><div><span>Dashboard</span><strong>{viewTitle}</strong></div></div>
          <SearchField className="global-search" value={state.searchQuery} onChange={(event) => state.setSearchQuery(event.target.value)} placeholder="Search workspace" label="Search workspace" shortcut="⌘ K" />
          <div className="topbar-actions"><IconButton className="icon-button notification-button" label="Notifications"><Bell size={18} /><i /></IconButton><Button className="primary-button" onClick={() => state.setShowNewTopic(true)}><Plus size={16} />New topic</Button></div>
        </header>

        <div className="dashboard-content">
          <div className="page-heading"><div><p>{state.activeView === 'overview' ? 'Market workspace' : 'Saved intelligence'}</p><h1>{state.activeView === 'overview' ? state.selectedTopic.name : viewTitle}</h1><span>{state.activeView === 'overview' ? state.selectedTopic.summary : `Review and organize your saved ${viewTitle.toLowerCase()}.`}</span></div><div className="heading-actions">{state.activeView === 'overview' && <label className="topic-select"><span className="ui-sr-only">Select topic</span><select value={state.selectedTopicId} onChange={(event) => state.selectTopic(event.target.value)}>{state.topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select><ChevronDown size={15} /></label>}<Button className="secondary-button" variant="secondary" onClick={() => state.setNotice('Latest market signals are already up to date.')}><RefreshCw size={15} />Refresh</Button></div></div>

          {state.activeView === 'overview' && <MarketOverview topic={state.selectedTopic} topics={state.topics.slice(0, 3)} ideas={state.ideas} competitors={state.filteredCompetitors.filter((item) => item.topicId === state.selectedTopic.id)} onSelectTopic={state.selectTopic} onToggleIdea={state.toggleIdea} onOpenIdea={openIdea} onNavigate={state.navigate} onAnalyze={analyzeCompetitor} />}
          {state.activeView === 'topics' && <section className="view-panel"><div className="view-toolbar"><span>{state.filteredTopics.length} saved topics</span><button className="filter-button" onClick={() => state.setNotice('All topic statuses are currently visible.')}><Filter size={15} />All statuses</button></div>{state.filteredTopics.length ? <TopicRows topics={state.filteredTopics} onSelect={state.selectTopic} /> : <EmptyState icon={Boxes} title="No matching topics" description="Try another workspace search." />}</section>}
          {state.activeView === 'ideas' && <section className="view-panel"><div className="view-toolbar"><span>{state.filteredIdeas.length} saved ideas</span><div className="segmented-control">{ideaFilters.map((filter) => <button key={filter} className={state.ideaFilter === filter ? 'active' : ''} onClick={() => state.setIdeaFilter(filter)}>{filter}</button>)}</div></div>{state.filteredIdeas.length ? <div className="idea-grid">{state.filteredIdeas.map((idea) => <IdeaCard key={idea.id} idea={idea} onToggle={state.toggleIdea} onOpen={openIdea} />)}</div> : <EmptyState icon={Lightbulb} title="No ideas in this view" description="Choose another filter or workspace search." />}</section>}
          {state.activeView === 'competitors' && <section className="view-panel"><div className="view-toolbar"><span>{state.filteredCompetitors.length} saved competitors</span><button className="filter-button" onClick={() => state.setNotice('Competitors from all topics are currently visible.')}><Filter size={15} />All topics</button></div>{state.filteredCompetitors.length ? <CompetitorTable rows={state.filteredCompetitors} onAnalyze={analyzeCompetitor} /> : <EmptyState icon={GitCompareArrows} title="No matching competitors" description="Try another workspace search." />}</section>}
          {state.activeView === 'analyses' && <section className="view-panel"><div className="view-toolbar"><span>{analyses.length} durable runs</span><StatusPill tone="green">System healthy</StatusPill></div><div className="analysis-list">{analyses.map((analysis) => <article key={analysis.id}><span className={`analysis-icon ${analysis.state === 'Partial' ? 'partial' : ''}`}><Bot size={17} /></span><div><strong>{analysis.type}</strong><small>{analysis.id} · {analysis.time}</small></div><span><strong>{analysis.sources}</strong><small>sources</small></span><span><strong>{analysis.duration}</strong><small>duration</small></span><StatusPill tone={analysis.state === 'Completed' ? 'green' : 'amber'}>{analysis.state}</StatusPill><IconButton className="icon-button" onClick={() => state.setNotice(`Opening durable run ${analysis.id}.`)} label={`Open ${analysis.type}`}><ExternalLink size={15} /></IconButton></article>)}</div></section>}
        </div>
      </main>

      {state.notice && <div className="dashboard-toast" role="status"><Check size={16} /><span>{state.notice}</span><button onClick={() => state.setNotice('')} aria-label="Dismiss notification"><X size={14} /></button></div>}
      {state.showNewTopic && <NewTopicModal onClose={() => state.setShowNewTopic(false)} onCreate={state.createTopic} />}
    </div>
  )
}
