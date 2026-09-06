import type { AgentId, ConversationSummary } from './types'

export const conversations: ConversationSummary[] = [
  { id: 'demo', title: 'AI meeting assistants', time: 'Now' },
  { id: 'onboarding', title: 'Refine onboarding email', time: 'Yesterday' },
  { id: 'q3-research', title: 'Q3 research synthesis', time: 'Yesterday' },
  { id: 'interviews', title: 'Customer interview notes', time: 'Aug 24' },
]

export const starterPrompts = [
  'Analyze AI meeting assistants for solo developers',
  'Research the market behind Screen Studio',
  'Find promising indie app opportunities',
]

export const agentLabels: Record<AgentId, string> = {
  researcher: 'Researcher',
  market: 'Market Agent',
  analyst: 'Analyst',
  writer: 'Writer',
}
