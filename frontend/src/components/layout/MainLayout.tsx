import React, { useState } from 'react'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'
import type { NavTab } from './Sidebar'

interface MainLayoutProps {
  children: React.ReactNode
  activeTab: NavTab
  onSelectTab: (tab: NavTab) => void
  pendingReviewCount?: number
}

const TAB_TITLES: Record<NavTab, string> = {
  dashboard: 'Executive Dashboard',
  documents: 'Document Intake & OCR Processing',
  review: 'Human-in-the-Loop Review Queue',
  ledger: 'General Ledger & Trial Balance',
  reconciliation: 'Bank Mutation Reconciliation',
  audit: 'Audit Log & Document Traceability',
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  children,
  activeTab,
  onSelectTab,
  pendingReviewCount = 0,
}) => {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="min-h-screen bg-slate-950 flex font-sans antialiased text-slate-100 selection:bg-indigo-500 selection:text-white">
      {/* Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={onSelectTab}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        pendingReviewCount={pendingReviewCount}
      />

      {/* Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-slate-900/50">
        {/* Navbar */}
        <Navbar activeTabTitle={TAB_TITLES[activeTab]} pendingReviewCount={pendingReviewCount} />

        {/* Main Content Container */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8 max-w-7xl w-full mx-auto space-y-6">
          {children}
        </main>
      </div>
    </div>
  )
}
