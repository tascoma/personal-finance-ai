import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ConfirmDialog from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('calls onConfirm when the confirm button is clicked', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog title="Delete?" message="Sure?" confirmLabel="Delete" onConfirm={onConfirm} onCancel={vi.fn()} />,
    )
    fireEvent.click(screen.getByText('Delete'))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onCancel when the cancel button is clicked', () => {
    const onCancel = vi.fn()
    render(<ConfirmDialog title="Delete?" message="Sure?" onConfirm={vi.fn()} onCancel={onCancel} />)
    fireEvent.click(screen.getByText('Cancel'))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('disables confirm until the required text is typed', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        title="Delete period"
        message="Type to confirm"
        confirmText="Jan 2026"
        confirmLabel="Delete"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    )
    const button = screen.getByText('Delete')
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText('Jan 2026'), { target: { value: 'Jan 2026' } })
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('shows the pending label and disables confirm while pending', () => {
    render(
      <ConfirmDialog title="Delete?" message="Sure?" pending pendingLabel="Deleting…" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    )
    expect(screen.getByText('Deleting…')).toBeDisabled()
  })
})
