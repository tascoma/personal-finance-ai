import { useState, type ReactNode } from 'react'
import ConfirmDialog from '../components/ConfirmDialog'

interface ConfirmOptions {
  title: string
  message: ReactNode
  confirmLabel?: string
  danger?: boolean
  confirmText?: string
  onConfirm: () => void
}

/**
 * Imperative confirmation prompt backed by `ConfirmDialog`. Replaces `window.confirm`:
 * call `ask({ ... })` from a click handler and render `confirmDialog` once in the tree.
 */
export function useConfirm() {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null)

  const ask = (options: ConfirmOptions) => setOpts(options)

  const confirmDialog = opts ? (
    <ConfirmDialog
      title={opts.title}
      message={opts.message}
      confirmLabel={opts.confirmLabel}
      danger={opts.danger}
      confirmText={opts.confirmText}
      onConfirm={() => { const fn = opts.onConfirm; setOpts(null); fn() }}
      onCancel={() => setOpts(null)}
    />
  ) : null

  return { ask, confirmDialog }
}
