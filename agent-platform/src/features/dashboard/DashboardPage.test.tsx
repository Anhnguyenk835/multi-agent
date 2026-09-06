import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from './DashboardPage'

describe('Opportunity dashboard prototype', () => {
  it('shows the active market and lets the user shortlist an idea', () => {
    render(<MemoryRouter initialEntries={['/dashboard']}><DashboardPage /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: 'AI meeting assistants' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Shortlist Async stand-up synthesizer' }))

    expect(screen.getByRole('button', { name: 'Remove Async stand-up synthesizer from shortlist' })).toBeInTheDocument()
  })
})
