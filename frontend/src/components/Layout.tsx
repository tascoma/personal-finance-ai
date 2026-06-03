import type { ReactNode } from 'react'
import Sidebar from './Sidebar'
import AppHeader from './AppHeader'
import type { Period } from '../types'

interface Props {
  children: ReactNode
  activePeriod?: Period | null
}

export default function Layout({ children, activePeriod }: Props) {
  return (
    <div className="app">
      <AppHeader activePeriod={activePeriod} />
      <Sidebar />
      <main className="main">
        {children}
      </main>
    </div>
  )
}
