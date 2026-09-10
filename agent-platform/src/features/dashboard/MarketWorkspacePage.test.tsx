import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { marketAnalysisReports } from './__fixtures__/marketAnalysis'
import { getMarket, getMarkets } from './api/dashboardApi'
import MarketWorkspacePage from './MarketWorkspacePage'

vi.mock('./api/dashboardApi', () => ({
  getMarket: vi.fn(),
  getMarkets: vi.fn(),
}))

describe('Market Workspace', () => {
  beforeEach(() => {
    vi.mocked(getMarkets).mockResolvedValue([
      {
        id: 'habit-tracking-apps',
        name: 'Habit Tracking Apps',
        definition: 'Consumer apps that help individuals build and maintain recurring habits.',
        momentum_score: 64,
      },
    ])
    vi.mocked(getMarket).mockResolvedValue(marketAnalysisReports[0]!)
  })

  it('loads API data and switches from Market Overview to competitor analysis', async () => {
    render(
      <MemoryRouter initialEntries={['/markets/habit-tracking-apps']}>
        <Routes>
          <Route path="/markets/:marketId" element={<MarketWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Habit Tracking Apps' })).toBeInTheDocument()
    expect(getMarket).toHaveBeenCalledWith('habit-tracking-apps', expect.any(AbortSignal))
    expect(screen.getByRole('heading', { name: 'Scale and demand indicators' })).toBeInTheDocument()
    expect(screen.getByText('$80M–$110M')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Estimated annual revenue' })).toBeInTheDocument()
    expect(screen.getByText('$72M')).toBeInTheDocument()
    expect(screen.getByText('$95M')).toBeInTheDocument()
    expect(screen.getByText('$108M')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Market growth' }))
    expect(screen.getByRole('heading', { name: 'Annual market growth' })).toBeInTheDocument()
    expect(screen.getByText('+31.9%')).toBeInTheDocument()
    expect(screen.getByText('+13.7%')).toBeInTheDocument()
    expect(screen.queryByText(/Report v/)).not.toBeInTheDocument()
    expect(screen.queryByText('Saved market reports')).not.toBeInTheDocument()
    expect(screen.queryByText(/Schema market-analysis/)).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: '2 sources' })[0]!)
    expect(screen.getByRole('dialog', { name: 'Evidence sources' })).toBeInTheDocument()
    expect(screen.getByText('Consumer spending estimate')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close evidence' }))

    fireEvent.click(screen.getByRole('tab', { name: /Competitors/ }))
    expect(screen.getByRole('heading', { name: 'Products shaping this market' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Open Habitica' }))
    expect(screen.getByLabelText('Habitica competitor profile')).toBeInTheDocument()
  })
})
