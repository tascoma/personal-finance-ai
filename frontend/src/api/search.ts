import { get } from './client'

export type SearchHitType =
  | 'account'
  | 'transaction'
  | 'journal_entry'
  | 'document'
  | 'period'

export interface SearchHit {
  type: SearchHitType
  id: string
  title: string
  subtitle: string | null
  period_id: string | null
}

export interface SearchResponse {
  query: string
  hits: SearchHit[]
}

export function searchGlobal(q: string): Promise<SearchResponse> {
  return get<SearchResponse>(`/search?q=${encodeURIComponent(q)}`)
}
