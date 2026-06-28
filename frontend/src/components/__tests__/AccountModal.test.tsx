import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AccountModal from '../AccountModal'
import type { Account } from '../../types'

describe('AccountModal', () => {
  it('keeps submit disabled until required fields are filled, then submits an AccountCreate', () => {
    const onSubmit = vi.fn()
    render(
      <AccountModal mode="add" existingCodes={[]} subCategoriesByType={{}} pending={false} error={null} onSubmit={onSubmit} onClose={vi.fn()} />,
    )
    const submit = screen.getByRole('button', { name: 'Add Account' })
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('100101'), { target: { value: '100200' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. Primary Checking'), { target: { value: 'Savings' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. Cash'), { target: { value: 'Cash' } })

    expect(submit).not.toBeDisabled()
    fireEvent.click(submit)
    expect(onSubmit).toHaveBeenCalledWith({
      account_code: 100200,
      account_name: 'Savings',
      account_type: 'Asset',
      sub_category: 'Cash',
      normal_balance: 'debit',
      is_memo: false,
      paystub_mapping: null,
    })
  })

  it('blocks submit when the code already exists', () => {
    render(
      <AccountModal mode="add" existingCodes={[100101]} subCategoriesByType={{}} pending={false} error={null} onSubmit={vi.fn()} onClose={vi.fn()} />,
    )
    fireEvent.change(screen.getByPlaceholderText('100101'), { target: { value: '100101' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. Primary Checking'), { target: { value: 'Dup' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. Cash'), { target: { value: 'Cash' } })

    expect(screen.getByText('Code 100101 is already in use.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Add Account' })).toBeDisabled()
  })

  it('defaults normal balance from the selected type', () => {
    render(
      <AccountModal mode="add" existingCodes={[]} subCategoriesByType={{}} pending={false} error={null} onSubmit={vi.fn()} onClose={vi.fn()} />,
    )
    expect(screen.getByDisplayValue('Debit')).toBeTruthy()
    fireEvent.change(screen.getByDisplayValue('Asset'), { target: { value: 'Income' } })
    expect(screen.getByDisplayValue('Credit')).toBeTruthy()
  })

  it('edits an existing account without sending the immutable code', () => {
    const onSubmit = vi.fn()
    const account: Account = {
      account_code: 400101,
      account_name: 'Salary',
      account_type: 'Income',
      sub_category: 'Earned',
      normal_balance: 'credit',
      paystub_mapping: null,
      is_memo: false,
      is_active: true,
    }
    render(
      <AccountModal mode="edit" initial={account} existingCodes={[400101]} subCategoriesByType={{ Income: ['Earned'] }} pending={false} error={null} onSubmit={onSubmit} onClose={vi.fn()} />,
    )
    expect(screen.getByDisplayValue('400101')).toBeDisabled()

    fireEvent.change(screen.getByDisplayValue('Salary'), { target: { value: 'Base Salary' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }))

    expect(onSubmit).toHaveBeenCalledWith({
      account_name: 'Base Salary',
      account_type: 'Income',
      sub_category: 'Earned',
      normal_balance: 'credit',
      is_memo: false,
      paystub_mapping: null,
    })
  })

  it('pre-fills the suggested code and updates it when the type changes', () => {
    const suggestCode = (type: string) => (type === 'Income' ? 410104 : 120102)
    render(
      <AccountModal mode="add" existingCodes={[]} subCategoriesByType={{}} suggestCode={suggestCode} pending={false} error={null} onSubmit={vi.fn()} onClose={vi.fn()} />,
    )
    expect(screen.getByDisplayValue('120102')).toBeTruthy() // default type Asset
    fireEvent.change(screen.getByDisplayValue('Asset'), { target: { value: 'Income' } })
    expect(screen.getByDisplayValue('410104')).toBeTruthy()
  })

  it('does not overwrite a manually entered code when the type changes', () => {
    const suggestCode = (type: string) => (type === 'Income' ? 410104 : 120102)
    render(
      <AccountModal mode="add" existingCodes={[]} subCategoriesByType={{}} suggestCode={suggestCode} pending={false} error={null} onSubmit={vi.fn()} onClose={vi.fn()} />,
    )
    fireEvent.change(screen.getByDisplayValue('120102'), { target: { value: '199999' } })
    fireEvent.change(screen.getByDisplayValue('Asset'), { target: { value: 'Income' } })
    expect(screen.getByDisplayValue('199999')).toBeTruthy()
  })
})
