import { get, post, patch } from './client'
import type { Account, AccountCreate, AccountUpdate } from '../types'

export function fetchAccounts(includeInactive = false): Promise<Account[]> {
  return get<Account[]>(`/accounts${includeInactive ? '?include_inactive=true' : ''}`)
}

export function createAccount(body: AccountCreate): Promise<Account> {
  return post<Account>('/accounts', body)
}

export function updateAccount(code: number, body: AccountUpdate): Promise<Account> {
  return patch<Account>(`/accounts/${code}`, body)
}
