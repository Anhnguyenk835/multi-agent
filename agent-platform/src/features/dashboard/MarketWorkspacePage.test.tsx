import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import MarketWorkspacePage from './MarketWorkspacePage'

describe('Market Workspace', () => {
  it('switches from Market Overview to its competitor analysis', () => {
    render(
      <MemoryRouter initialEntries={['/markets/habit-tracking-apps']}>
        <Routes>
          <Route path="/markets/:marketId" element={<MarketWorkspacePage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Habit Tracking Apps' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Scale and demand indicators' })).toBeInTheDocument()
    expect(screen.getByText('$80M–$110M')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /Competitors/ }))
    expect(screen.getByRole('heading', { name: 'Products shaping this market' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Open Habitica' }))
    expect(screen.getByLabelText('Habitica competitor profile')).toBeInTheDocument()
  })
})
