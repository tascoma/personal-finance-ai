import { useState, type ReactNode } from 'react'

interface ConfirmDialogProps {
  title: string
  message: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Style the confirm button as destructive (red). */
  danger?: boolean
  /** When set, the user must type this exact string to enable the confirm button. */
  confirmText?: string
  /** Disables the confirm button and shows a busy label while the action runs. */
  pending?: boolean
  pendingLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

/**
 * Reusable confirmation modal. Replaces ad-hoc `window.confirm` calls and the
 * inline delete modals; reuses the existing `.modal*` styles.
 */
export default function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  confirmText,
  pending = false,
  pendingLabel = 'Working…',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('')
  const matches = confirmText == null || typed === confirmText
  const canConfirm = matches && !pending

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-hd">
          <div className="modal-title">{title}</div>
        </div>
        <div className="modal-bd">
          <div className="modal-confirm-label">{message}</div>
          {confirmText != null && (
            <input
              className="inp"
              style={{ width: '100%' }}
              placeholder={confirmText}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && canConfirm) onConfirm() }}
              autoFocus
            />
          )}
        </div>
        <div className="modal-ft">
          <button className="btn btn-ghost btn-sm" onClick={onCancel}>{cancelLabel}</button>
          <button
            className={`btn btn-sm ${danger ? 'btn-danger' : 'btn-primary'}`}
            disabled={!canConfirm}
            onClick={onConfirm}
          >
            {pending ? pendingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
