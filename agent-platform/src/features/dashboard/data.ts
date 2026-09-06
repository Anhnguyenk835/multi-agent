import type { Analysis, Competitor, Idea, Topic } from './types'

export const initialTopics: Topic[] = [
  { id: 'ai-meeting', name: 'AI meeting assistants', summary: 'Focused tools are moving from transcription toward workflow completion.', status: 'Active', updated: '18 min ago', momentum: 82, competitors: 12, ideas: 6, color: '#1463ff' },
  { id: 'finance-ops', name: 'Finance automation for SMBs', summary: 'Reconciliation and cash-flow forecasting show consistent buyer intent.', status: 'Tracking', updated: 'Yesterday', momentum: 71, competitors: 9, ideas: 4, color: '#0b9b78' },
  { id: 'creator-tools', name: 'Creator workflow tools', summary: 'Video repurposing is crowded; review and approval workflows remain fragmented.', status: 'Review', updated: 'Sep 3', momentum: 64, competitors: 15, ideas: 8, color: '#d77716' },
]

export const initialIdeas: Idea[] = [
  { id: 'idea-1', topicId: 'ai-meeting', title: 'Decision ledger for client calls', description: 'Turn meeting decisions into an auditable approval queue for small agencies.', audience: 'Client-service teams', model: '$19 / workspace', score: 86, evidence: 11, status: 'Shortlisted' },
  { id: 'idea-2', topicId: 'ai-meeting', title: 'Async stand-up synthesizer', description: 'Merge voice notes, Slack updates, and blockers into one daily team brief.', audience: 'Remote product teams', model: '$8 / user', score: 79, evidence: 8, status: 'New' },
  { id: 'idea-3', topicId: 'finance-ops', title: 'Invoice anomaly inbox', description: 'A focused review queue for duplicate, late, and unusual supplier invoices.', audience: 'SMB finance leads', model: '$49 / month', score: 74, evidence: 9, status: 'Validating' },
  { id: 'idea-4', topicId: 'creator-tools', title: 'Sponsor content workspace', description: 'Collect briefs, drafts, approvals, and usage rights for solo creators.', audience: 'Newsletter creators', model: '$15 / month', score: 68, evidence: 6, status: 'New' },
]

export const competitors: Competitor[] = [
  { id: 'granola', topicId: 'ai-meeting', name: 'Granola', category: 'AI meeting notes', pricing: '$18 / user', revenue: 'Estimated', confidence: 84, signal: '+22%', updated: 'Today' },
  { id: 'fathom', topicId: 'ai-meeting', name: 'Fathom', category: 'Call intelligence', pricing: 'Freemium', revenue: 'Reported', confidence: 92, signal: '+18%', updated: 'Today' },
  { id: 'limitless', topicId: 'ai-meeting', name: 'Limitless', category: 'Personal memory', pricing: '$19 / month', revenue: 'Unknown', confidence: 61, signal: '+14%', updated: 'Yesterday' },
  { id: 'ramp', topicId: 'finance-ops', name: 'Ramp', category: 'Finance operations', pricing: 'Custom', revenue: 'Reported', confidence: 95, signal: '+17%', updated: 'Sep 4' },
  { id: 'descript', topicId: 'creator-tools', name: 'Descript', category: 'Creator editing', pricing: '$24 / month', revenue: 'Estimated', confidence: 81, signal: '+9%', updated: 'Sep 2' },
]

export const analyses: Analysis[] = [
  { id: 'run-1042', topicId: 'ai-meeting', type: 'Market analysis', state: 'Completed', sources: 28, duration: '4m 18s', time: 'Today, 10:42' },
  { id: 'run-1038', topicId: 'ai-meeting', type: 'Competitor · Granola', state: 'Completed', sources: 19, duration: '3m 06s', time: 'Today, 09:16' },
  { id: 'run-1017', topicId: 'finance-ops', type: 'Market analysis', state: 'Partial', sources: 24, duration: '5m 41s', time: 'Yesterday' },
  { id: 'run-996', topicId: 'creator-tools', type: 'Competitor · Descript', state: 'Completed', sources: 17, duration: '2m 48s', time: 'Sep 3' },
]
