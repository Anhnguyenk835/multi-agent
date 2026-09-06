export type AgentId = 'researcher' | 'market' | 'analyst' | 'writer'

export interface Citation {
  title: string
  url: string
  publisher: string
}

export interface FinalBrief {
  content: string
  citations: Citation[]
  status: string
}

export interface WorkflowError {
  message: string
  code?: string
  retryable?: boolean
}

export interface WorkflowEventData {
  text?: string
  title?: string
  url?: string
  publisher?: string
  message?: string
  response?: { final_brief?: FinalBrief | null; error?: WorkflowError }
  error?: WorkflowError
  [key: string]: unknown
}

export interface WorkflowEvent {
  type: string
  agent?: AgentId
  data: WorkflowEventData
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  activities?: Partial<Record<AgentId, { type: string; data: WorkflowEventData }>>
  sources?: Citation[]
  streaming?: boolean
  finalBrief?: FinalBrief | null
  error?: WorkflowError | null
}

export interface ConversationSummary {
  id: string
  title: string
  time: string
}
