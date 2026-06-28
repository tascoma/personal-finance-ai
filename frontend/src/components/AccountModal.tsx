import { useState } from 'react'
import type { Account, AccountCreate, AccountUpdate } from '../types'

const ACCOUNT_TYPES = ['Asset', 'Liability', 'Equity', 'Income', 'Expense', 'Memo Asset*']

const NORMAL_BALANCE_BY_TYPE: Record<string, string> = {
  Asset: 'debit',
  Expense: 'debit',
  'Memo Asset*': 'debit',
  Liability: 'credit',
  Equity: 'credit',
  Income: 'credit',
}

interface AccountModalProps {
  mode: 'add' | 'edit'
  /** Prefilled account when editing. */
  initial?: Account
  /** Existing codes, used to block duplicates when adding. */
  existingCodes: number[]
  /** Sub-categories already in use, keyed by account type, for datalist suggestions. */
  subCategoriesByType: Record<string, string[]>
  /** Suggests the next available code for the given type (add mode only). */
  suggestCode?: (type: string) => number | null
  pending: boolean
  error: string | null
  onSubmit: (payload: AccountCreate | AccountUpdate) => void
  onClose: () => void
}

/**
 * Create or edit a chart-of-accounts entry. Reuses the shared `.modal*` styles.
 * Account code is immutable once created (it's the primary key referenced by
 * journal lines), so it's read-only in edit mode.
 */
export default function AccountModal({
  mode,
  initial,
  existingCodes,
  subCategoriesByType,
  suggestCode,
  pending,
  error,
  onSubmit,
  onClose,
}: AccountModalProps) {
  const [code, setCode] = useState(() => {
    if (initial) return String(initial.account_code)
    const suggested = mode === 'add' ? suggestCode?.('Asset') : null
    return suggested == null ? '' : String(suggested)
  })
  const [codeEdited, setCodeEdited] = useState(false)
  const [name, setName] = useState(initial?.account_name ?? '')
  const [type, setType] = useState(initial?.account_type ?? 'Asset')
  const [subCat, setSubCat] = useState(initial?.sub_category ?? '')
  const [normalBalance, setNormalBalance] = useState(initial?.normal_balance ?? 'debit')
  const [isMemo, setIsMemo] = useState(initial?.is_memo ?? false)
  const [paystub, setPaystub] = useState(initial?.paystub_mapping ?? '')

  function handleTypeChange(next: string) {
    setType(next)
    setNormalBalance(NORMAL_BALANCE_BY_TYPE[next] ?? 'debit')
    setIsMemo(next === 'Memo Asset*')
    // Re-suggest the code unless the user has typed their own.
    if (mode === 'add' && !codeEdited) {
      const suggested = suggestCode?.(next)
      setCode(suggested == null ? '' : String(suggested))
    }
  }

  const codeNum = Number(code)
  const codeWellFormed = Number.isInteger(codeNum) && codeNum > 0
  const codeDuplicate = mode === 'add' && codeWellFormed && existingCodes.includes(codeNum)
  const codeValid = mode === 'edit' || (codeWellFormed && !codeDuplicate)
  const canSubmit = codeValid && name.trim() !== '' && subCat.trim() !== '' && !pending

  // Sub-category suggestions for the selected type, falling back to all types
  // when the chosen type has none yet.
  const allSubCats = [...new Set(Object.values(subCategoriesByType).flat())]
  const typeSubCats = subCategoriesByType[type] ?? []
  const subCatOptions = typeSubCats.length ? typeSubCats : allSubCats

  function handleSubmit() {
    if (!canSubmit) return
    const common = {
      account_name: name.trim(),
      account_type: type,
      sub_category: subCat.trim(),
      normal_balance: normalBalance,
      is_memo: isMemo,
      paystub_mapping: paystub.trim() || null,
    }
    onSubmit(mode === 'add' ? { account_code: codeNum, ...common } : common)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-hd">
          <div className="modal-title">{mode === 'add' ? 'Add Account' : `Edit Account ${initial?.account_code}`}</div>
          <div className="modal-sub">
            {mode === 'add'
              ? 'Define a new chart-of-accounts entry.'
              : 'Update this account. The code cannot be changed.'}
          </div>
        </div>

        <div className="modal-bd" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="form-row">
            <div className="field-group" style={{ width: 120 }}>
              <label className="field-label">Code</label>
              <input
                type="number"
                className="inp mono"
                style={{ width: '100%' }}
                placeholder="100101"
                value={code}
                disabled={mode === 'edit'}
                onChange={(e) => { setCode(e.target.value); setCodeEdited(true) }}
                autoFocus={mode === 'add'}
              />
            </div>
            <div className="field-group" style={{ flex: 1, minWidth: 200 }}>
              <label className="field-label">Account Name</label>
              <input
                type="text"
                className="inp"
                style={{ width: '100%' }}
                placeholder="e.g. Primary Checking"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus={mode === 'edit'}
              />
            </div>
          </div>

          {codeDuplicate && <p className="color-red" style={{ fontSize: 12, margin: 0 }}>Code {codeNum} is already in use.</p>}

          <div className="form-row">
            <div className="field-group" style={{ flex: 1, minWidth: 160 }}>
              <label className="field-label">Type</label>
              <select className="inp" style={{ width: '100%' }} value={type} onChange={(e) => handleTypeChange(e.target.value)}>
                {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="field-group" style={{ width: 150 }}>
              <label className="field-label">Normal Balance</label>
              <select className="inp" style={{ width: '100%' }} value={normalBalance} onChange={(e) => setNormalBalance(e.target.value)}>
                <option value="debit">Debit</option>
                <option value="credit">Credit</option>
              </select>
            </div>
          </div>

          <div className="field-group">
            <label className="field-label">Sub-Category</label>
            <input
              type="text"
              className="inp"
              style={{ width: '100%' }}
              placeholder="e.g. Cash"
              list="account-subcategories"
              value={subCat}
              onChange={(e) => setSubCat(e.target.value)}
            />
            <datalist id="account-subcategories">
              {subCatOptions.map((s) => <option key={s} value={s} />)}
            </datalist>
          </div>

          <div className="field-group">
            <label className="field-label">Paystub Mapping <span className="muted">(optional)</span></label>
            <input
              type="text"
              className="inp"
              style={{ width: '100%' }}
              placeholder="Paystub line label this account maps to"
              value={paystub}
              onChange={(e) => setPaystub(e.target.value)}
            />
          </div>

          <label className="row gap-2" style={{ alignItems: 'center', cursor: 'pointer', fontSize: 13, color: 'var(--text-2)' }}>
            <input type="checkbox" checked={isMemo} onChange={(e) => setIsMemo(e.target.checked)} />
            Memo (off-balance-sheet) account
          </label>

          {error && <p className="color-red" style={{ fontSize: 12, margin: 0 }}>{error}</p>}
        </div>

        <div className="modal-ft">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary btn-sm" disabled={!canSubmit} onClick={handleSubmit}>
            {pending ? 'Saving…' : mode === 'add' ? 'Add Account' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
