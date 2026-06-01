import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBadge from '../StatusBadge'

describe('StatusBadge', () => {
  it('renders the human-readable label for a known status', () => {
    render(<StatusBadge status="pending_review" />)
    expect(screen.getByText('Review')).toBeInTheDocument()
  })

  it('applies the correct variant class for open status', () => {
    const { container } = render(<StatusBadge status="open" />)
    const badge = container.querySelector('.badge')
    expect(badge).toHaveClass('badge--green')
  })

  it('renders a closed badge with ghost variant', () => {
    const { container } = render(<StatusBadge status="closed" />)
    expect(screen.getByText('Closed')).toBeInTheDocument()
    const badge = container.querySelector('.badge')
    expect(badge).toHaveClass('badge--ghost')
  })
})
