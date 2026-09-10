import { env } from '../../../config/env'
import type { MarketAnalysisResponse, MarketSummary } from '../types'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${env.backendBaseUrl}${path}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) {
    throw new Error(response.status === 404 ? 'Market not found.' : 'Dashboard data is unavailable.')
  }
  return (await response.json()) as T
}

export const getMarkets = (signal?: AbortSignal) => getJson<MarketSummary[]>('/markets', signal)

export const getMarket = (marketId: string, signal?: AbortSignal) =>
  getJson<MarketAnalysisResponse>(`/markets/${encodeURIComponent(marketId)}`, signal)
