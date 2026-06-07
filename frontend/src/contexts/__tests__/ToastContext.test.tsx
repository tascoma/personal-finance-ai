import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ToastProvider, useToast } from '../ToastContext'

function Trigger() {
  const toast = useToast()
  return <button onClick={() => toast.success('Saved!')}>fire</button>
}

describe('ToastContext', () => {
  it('renders a toast when pushed and dismisses it on click', () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByText('fire'))
    const toast = screen.getByText('Saved!')
    expect(toast).toBeInTheDocument()

    // Click the toast to dismiss it.
    fireEvent.click(toast)
    expect(screen.queryByText('Saved!')).not.toBeInTheDocument()
  })

  it('auto-dismisses after the timeout', () => {
    vi.useFakeTimers()
    try {
      render(
        <ToastProvider>
          <Trigger />
        </ToastProvider>,
      )
      fireEvent.click(screen.getByText('fire'))
      expect(screen.getByText('Saved!')).toBeInTheDocument()
      act(() => { vi.advanceTimersByTime(4000) })
      expect(screen.queryByText('Saved!')).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})
