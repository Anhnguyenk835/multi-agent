import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from './ChatPage'

const encoder = new TextEncoder()

function sseFrame(eventType: string, data: unknown) {
  return `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`
}

function sse(frames: string[]) {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(frames.join('')))
      controller.close()
    },
  })
}

describe('Agent Platform streaming chat', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders agent activity, selected sources, writer text, and the final brief', async () => {
    const finalBrief = {
      content: '# Final brief\n\nValidated summary [1](https://example.com/source "Primary source — Example")',
      citations: [{ title: 'Primary source', url: 'https://example.com/source', publisher: 'Example' }],
      status: 'success',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: sse([
          sseFrame('agent.activity', { agent: 'market_analyst', data: { message: 'Searching public sources' } }),
          sseFrame('research.source_found', {
            agent: 'market_analyst',
            data: { title: 'Primary source', publisher: 'Example', url: 'https://example.com/source' },
          }),
          sseFrame('writer.delta', { agent: 'writer', data: { text: 'Drafting summary' } }),
          // Mirrors the real backend shape: WorkflowResponse nests the brief
          // under final_brief, not at the top level of data.response.
          sseFrame('workflow.completed', { data: { response: { final_brief: finalBrief } } }),
        ]),
      }),
    )

    render(
      <MemoryRouter initialEntries={['/chat/demo']}>
        <ChatPage />
      </MemoryRouter>,
    )
    fireEvent.change(screen.getByLabelText('Message Aster'), { target: { value: 'Research this' } })
    fireEvent.click(screen.getByLabelText('Send message'))

    // The whole SSE stream arrives in one flush here, so by the time this
    // resolves workflow.completed has already landed and the raw streamed
    // delta ("Drafting summary") has been replaced by the completed brief —
    // that replacement is exactly the behavior under test.
    await waitFor(() => expect(screen.getByText(/↗ Primary source/)).toBeInTheDocument())
    expect(screen.queryByText('Drafting summary')).not.toBeInTheDocument()
    expect(screen.getByText('Final brief')).toBeInTheDocument()
    expect(screen.getByText(/Validated summary/)).toBeInTheDocument()

    const citationChip = screen.getByRole('link', { name: '1' })
    expect(citationChip).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.mouseEnter(citationChip)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent('Primary source')
    expect(tooltip).toHaveTextContent('Example')

    fireEvent.mouseLeave(citationChip)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    expect(screen.getByText(/\[1\] Primary source/)).toBeInTheDocument()
  })
})
