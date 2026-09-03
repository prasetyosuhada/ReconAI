import React, { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'
import type { NavTab } from './Sidebar'

interface MainLayoutProps {
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

const routeToTab = (pathname: string): NavTab => {
  if (pathname.startsWith('/documents')) return 'documents'
  if (pathname.startsWith('/review')) return 'review'
  if (pathname.startsWith('/ledger')) return 'ledger'
  if (pathname.startsWith('/reconciliation')) return 'reconciliation'
  if (pathname.startsWith('/audit')) return 'audit'
  return 'dashboard'
}

export const MainLayout: React.FC<MainLayoutProps> = ({ pendingReviewCount = 0 }) => {
  const [collapsed, setCollapsed] = useState(false)
  const activeTab = routeToTab(useLocation().pathname)

  return (
    <div className="min-h-screen bg-slate-950 flex font-sans antialiased text-slate-100 selection:bg-indigo-500 selection:text-white">
      {/* Sidebar */}
      <Sidebar
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
          <Outlet />
        </main>
      </div>
    </div>
  )
}
