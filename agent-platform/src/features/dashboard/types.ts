export type DashboardView = 'overview' | 'topics' | 'ideas' | 'competitors' | 'analyses'
export type TopicStatus = 'Active' | 'Tracking' | 'Review'
export type IdeaStatus = 'Shortlisted' | 'Validating' | 'New'
export type AnalysisState = 'Completed' | 'Partial'

export interface Topic {
  id: string
  name: string
  summary: string
  status: TopicStatus
  updated: string
  momentum: number
  competitors: number
  ideas: number
  color: string
}

export interface Idea {
  id: string
  topicId: string
  title: string
  description: string
  audience: string
  model: string
  score: number
  evidence: number
  status: IdeaStatus
}

export interface Competitor {
  id: string
  topicId: string
  name: string
  category: string
  pricing: string
  revenue: 'Reported' | 'Estimated' | 'Unknown'
  confidence: number
  signal: string
  updated: string
}

export interface Analysis {
  id: string
  topicId: string
  type: string
  state: AnalysisState
  sources: number
  duration: string
  time: string
}
