import { useCallback, useEffect, useState } from 'react'
import { getMarket, getMarkets } from '../api/dashboardApi'
import type { MarketAnalysisResponse, MarketSummary } from '../types'

interface AsyncState<T> {
  data: T | null
  error: string
  requestKey: string | null
}

const initialState = <T>(): AsyncState<T> => ({ data: null, error: '', requestKey: null })

export function useMarketList() {
  const [state, setState] = useState<AsyncState<MarketSummary[]>>(initialState)
  const [request, setRequest] = useState(0)
  const requestKey = String(request)

  useEffect(() => {
    const controller = new AbortController()
    getMarkets(controller.signal)
      .then((data) => setState({ data, error: '', requestKey }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            data: null,
            error: error instanceof Error ? error.message : 'Dashboard data is unavailable.',
            requestKey,
          })
        }
      })
    return () => controller.abort()
  }, [requestKey])

  const settled = state.requestKey === requestKey
  return {
    data: settled ? state.data : null,
    error: settled ? state.error : '',
    loading: !settled,
    retry: useCallback(() => setRequest((value) => value + 1), []),
  }
}

interface MarketWorkspaceData {
  markets: MarketSummary[]
  report: MarketAnalysisResponse
}

export function useMarketWorkspace(marketId: string | undefined) {
  const [state, setState] = useState<AsyncState<MarketWorkspaceData>>(initialState)
  const [request, setRequest] = useState(0)
  const requestKey = `${marketId ?? 'missing'}:${request}`

  useEffect(() => {
    if (!marketId) {
      return
    }

    const controller = new AbortController()
    Promise.all([getMarkets(controller.signal), getMarket(marketId, controller.signal)])
      .then(([markets, report]) => setState({ data: { markets, report }, error: '', requestKey }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            data: null,
            error: error instanceof Error ? error.message : 'Dashboard data is unavailable.',
            requestKey,
          })
        }
      })
    return () => controller.abort()
  }, [marketId, requestKey])

  const settled = state.requestKey === requestKey
  return {
    data: settled ? state.data : null,
    error: marketId ? (settled ? state.error : '') : 'Market not found.',
    loading: Boolean(marketId) && !settled,
    retry: useCallback(() => setRequest((value) => value + 1), []),
  }
}
