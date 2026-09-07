export type Confidence = number
export type MarketView = 'overview' | 'competitors'
export type QualitativeLevel = 'low' | 'moderate' | 'high'
export type EvidenceClass = 'reported' | 'estimated' | 'derived' | 'proxy' | 'inferred'
export type MarketVerdict =
  'attractive' | 'selectively_attractive' | 'mature' | 'unattractive' | 'insufficient_evidence'

export interface MarketAnalysisResponse {
  schema_version: 'market-analysis.v1'
  market: MarketIdentity
  report: ReportMetadata
  overview: MarketOverview
  competitors: CompetitorAnalysis
  evidence: EvidenceSource[]
}

export interface MarketIdentity {
  id: string
  name: string
  definition: string
  scope: {
    geography: string[]
    platforms: string[]
    customer_type: 'B2C' | 'B2B' | 'prosumer' | 'mixed'
    included: string[]
    excluded: string[]
  }
}

export interface ReportMetadata {
  id: string
  version: number
  status: 'partial' | 'completed'
  generated_at: string
  data_period: string
  overall_confidence: Confidence
  freshness: 'current' | 'aging' | 'stale'
  warnings: string[]
}

export interface MarketOverview {
  verdict: {
    status: MarketVerdict
    summary: string
    strengths: string[]
    constraints: string[]
  }
  scorecard: {
    demand: number
    market_size: number
    momentum: number
    commercial_quality: number
    accessibility: number
    competitive_headroom: number
  }
  market_size: { metrics: MarketMetric[] }
  momentum: {
    direction: 'growing' | 'stable' | 'declining' | 'uncertain'
    strength: QualitativeLevel
    summary: string
    signals: TrendSignal[]
    series: TrendPoint[]
  }
  customer_segments: CustomerSegment[]
  commercial_dynamics: CommercialDynamics
  market_accessibility: MarketAccessibility
  risks: MarketRisk[]
  opportunity_gaps: OpportunityGap[]
}

export interface MarketMetric {
  id: string
  label: string
  value?: number | null
  range?: { min: number; max: number }
  unit: 'USD' | 'percent' | 'users' | 'downloads' | 'products' | 'index'
  period: string
  change?: { value: number; unit: 'percent' | 'percentage_points' | 'absolute'; period: 'MoM' | 'YoY' | 'CAGR' }
  evidence_class: EvidenceClass
  confidence: Confidence
  source_ids: string[]
  methodology?: string
}

export interface TrendSignal {
  label: string
  change: number
  unit: 'percent' | 'percentage_points' | 'absolute'
  period: 'MoM' | 'YoY' | 'CAGR'
  source_ids: string[]
}

export interface TrendPoint {
  period: string
  revenue?: number | null
  downloads?: number | null
  active_users?: number | null
  search_index?: number | null
  product_count?: number | null
}

export interface CustomerSegment {
  id: string
  name: string
  jobs: string[]
  pain_points: string[]
  willingness_to_pay: QualitativeLevel | 'unknown'
  confidence: Confidence
  source_ids: string[]
}

export interface CommercialDynamics {
  dominant_model: string
  typical_annual_price?: { min: number; max: number; unit: 'USD' }
  willingness_to_pay: QualitativeLevel | 'unknown'
  retention_pressure: QualitativeLevel | 'unknown'
  summary: string
  source_ids: string[]
}

export interface MarketAccessibility {
  level: QualitativeLevel | 'unknown'
  channels: string[]
  barriers: string[]
  summary: string
  confidence: Confidence
  source_ids: string[]
}

export interface MarketRisk {
  id: string
  category: string
  title: string
  probability: QualitativeLevel
  impact: QualitativeLevel
  summary: string
  source_ids: string[]
}

export interface OpportunityGap {
  id: string
  segment: string
  unmet_need: string
  competitor_coverage: QualitativeLevel | 'unknown'
  demand_strength: QualitativeLevel | 'unknown'
  commercial_signal: QualitativeLevel | 'unknown'
  confidence: Confidence
  source_ids: string[]
}

export interface CompetitorAnalysis {
  summary: {
    competition_level: QualitativeLevel | 'unknown'
    market_structure: 'concentrated' | 'fragmented' | 'mixed' | 'unknown'
    tracked_products: number
    top_10_revenue_concentration?: number | null
    feature_saturation: QualitativeLevel | 'unknown'
    switching_cost: QualitativeLevel | 'unknown'
    source_ids: string[]
  }
  items: Competitor[]
}

export interface Competitor {
  id: string
  name: string
  type: 'direct' | 'indirect' | 'substitute' | 'emerging'
  positioning: string
  platforms: string[]
  pricing: { model: string; annual_price?: number | null; currency?: string | null }
  strengths: string[]
  weaknesses: string[]
  confidence: Confidence
  source_ids: string[]
}

export interface EvidenceSource {
  id: string
  title: string
  publisher: string
  url: string
  published_at?: string | null
  retrieved_at: string
  evidence_class: EvidenceClass
}

export interface AnalysisHistoryItem {
  id: string
  market_id: string
  type: string
  status: 'completed' | 'partial'
  version: number
  source_count: number
  saved_at: string
}
