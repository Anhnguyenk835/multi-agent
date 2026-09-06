import { useMemo, useState } from 'react'
import { competitors, initialIdeas, initialTopics } from '../data'
import type { DashboardView, Idea, Topic } from '../types'

export function useDashboard() {
  const [activeView, setActiveView] = useState<DashboardView>('overview')
  const [topics, setTopics] = useState<Topic[]>(initialTopics)
  const [ideas, setIdeas] = useState<Idea[]>(initialIdeas)
  const [selectedTopicId, setSelectedTopicId] = useState(initialTopics[0].id)
  const [searchQuery, setSearchQuery] = useState('')
  const [showNewTopic, setShowNewTopic] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const [ideaFilter, setIdeaFilter] = useState<'All' | Idea['status']>('All')

  const selectedTopic = topics.find((topic) => topic.id === selectedTopicId) || topics[0]
  const normalizedQuery = searchQuery.trim().toLowerCase()
  const filteredTopics = useMemo(() => topics.filter((topic) => `${topic.name} ${topic.summary}`.toLowerCase().includes(normalizedQuery)), [topics, normalizedQuery])
  const filteredIdeas = useMemo(() => ideas.filter((idea) => `${idea.title} ${idea.description} ${idea.audience}`.toLowerCase().includes(normalizedQuery) && (ideaFilter === 'All' || idea.status === ideaFilter)), [ideas, normalizedQuery, ideaFilter])
  const filteredCompetitors = useMemo(() => competitors.filter((competitor) => `${competitor.name} ${competitor.category}`.toLowerCase().includes(normalizedQuery)), [normalizedQuery])

  const navigate = (view: DashboardView) => {
    setActiveView(view)
    setMobileNavOpen(false)
    window.scrollTo?.({ top: 0, behavior: 'smooth' })
  }

  const selectTopic = (topicId: string) => {
    setSelectedTopicId(topicId)
    setActiveView('overview')
    setNotice(`Workspace changed to ${topics.find((topic) => topic.id === topicId)?.name}.`)
  }

  const toggleIdea = (ideaId: string) => setIdeas((current) => current.map((idea) => idea.id === ideaId ? { ...idea, status: idea.status === 'Shortlisted' ? 'New' : 'Shortlisted' } : idea))

  const createTopic = (name: string) => {
    const topic: Topic = { id: `topic-${Date.now()}`, name, summary: 'Ready for a new market analysis from chat.', status: 'Review', updated: 'Now', momentum: 0, competitors: 0, ideas: 0, color: '#7558c9' }
    setTopics((current) => [topic, ...current])
    setSelectedTopicId(topic.id)
    setShowNewTopic(false)
    setActiveView('topics')
    setNotice(`${name} was added to your workspace.`)
  }

  return { activeView, topics, ideas, selectedTopicId, selectedTopic, searchQuery, showNewTopic, mobileNavOpen, notice, ideaFilter, filteredTopics, filteredIdeas, filteredCompetitors, navigate, selectTopic, toggleIdea, createTopic, setSearchQuery, setShowNewTopic, setMobileNavOpen, setNotice, setIdeaFilter }
}
