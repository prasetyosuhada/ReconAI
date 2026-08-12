import { useState } from 'react'
import { MainLayout } from './components/layout/MainLayout'
import type { NavTab } from './components/layout/Sidebar'
import { DocumentIntakeView } from './components/documents/DocumentIntakeView'
import { ReviewQueueView } from './components/review/ReviewQueueView'
import { GeneralLedgerView } from './components/ledger/GeneralLedgerView'
import { ReconciliationView } from './components/reconciliation/ReconciliationView'
import { AuditTraceabilityView } from './components/audit/AuditTraceabilityView'
import { useDashboardStats } from './hooks/useDashboardStats'
import type { DashboardStats as DashboardStatsType } from './services/api'
import {
  CheckCircle2,
  FileText,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from 'lucide-react'

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'decimal',
    maximumFractionDigits: 0,
  }).format(value)
}

interface DashboardStatsProps {
  stats: DashboardStatsType | null
  loading: boolean
  error: string | null
  onRefresh: () => void
}

function DashboardStatsCards({ stats, loading, error, onRefresh }: DashboardStatsProps) {
  const isBalanced = stats?.trialBalance?.status === 'balanced'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
          Overview Statistics
        </h3>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700/80 text-slate-200 hover:text-white text-xs font-medium transition-all shadow-sm active:scale-95 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-indigo-400 ${loading ? 'animate-spin' : ''}`} />
          <span>{loading ? 'Refreshing...' : 'Refresh Data'}</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Processed Documents */}
        <div className="p-5 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-2">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Processed Documents</span>
            <FileText className="w-4 h-4 text-indigo-400" />
          </div>
          {loading && !stats ? (
            <div className="flex items-center gap-2 text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading…</span>
            </div>
          ) : error && !stats ? (
            <div className="text-2xl font-bold text-slate-500">—</div>
          ) : (
            <div className="text-2xl font-bold text-white flex items-center justify-between">
              <span>{stats?.totalDocuments.toLocaleString() ?? '0'}</span>
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />}
            </div>
          )}
          <p className="text-[11px] text-emerald-400 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Total uploaded &amp; processed
          </p>
        </div>

        {/* Human Review Queue */}
        <div className="p-5 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-2">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Human Review Queue</span>
            <UserCheck className="w-4 h-4 text-amber-400" />
          </div>
          {loading && !stats ? (
            <div className="flex items-center gap-2 text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading…</span>
            </div>
          ) : error && !stats ? (
            <div className="text-2xl font-bold text-slate-500">—</div>
          ) : (
            <div className="text-2xl font-bold text-white flex items-center justify-between">
              <div>
                {stats?.pendingReviewCount ?? 0}{' '}
                <span className="text-base font-medium text-amber-400">Pending</span>
              </div>
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />}
            </div>
          )}
          <p className="text-[11px] text-amber-400 font-medium">
            Low confidence / sensitive accounts
          </p>
        </div>

        {/* Trial Balance Status */}
        <div className="p-5 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-2">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Trial Balance Status</span>
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
            ) : isBalanced ? (
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
            ) : (
              <ShieldAlert className="w-4 h-4 text-red-400" />
            )}
          </div>
          {loading && !stats ? (
            <div className="flex items-center gap-2 text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading…</span>
            </div>
          ) : error || !stats?.trialBalance ? (
            <div className="text-2xl font-bold text-slate-500">N/A</div>
          ) : (
            <div
              className={`text-2xl font-bold ${isBalanced ? 'text-emerald-400' : 'text-red-400'}`}
            >
              {isBalanced ? 'BALANCED' : 'UNBALANCED'}
            </div>
          )}
          {stats?.trialBalance && (
            <p className="text-[11px] text-slate-400">
              Debits: {formatCurrency(stats.trialBalance.total_debits)} | Credits:{' '}
              {formatCurrency(stats.trialBalance.total_credits)}
            </p>
          )}
          {!stats?.trialBalance && !loading && !error && (
            <p className="text-[11px] text-slate-500">No posted entries yet</p>
          )}
        </div>

        {/* Error / Refresh row */}
        {error && (
          <div className="col-span-3 flex items-center justify-between p-3 rounded-lg bg-red-900/20 border border-red-500/30 text-red-400 text-xs">
            <span>⚠ Failed to load stats: {error}</span>
            <button
              onClick={onRefresh}
              className="flex items-center gap-1 px-2 py-1 rounded bg-red-500/10 hover:bg-red-500/20 transition-colors"
            >
              <RefreshCw className="w-3 h-3" /> Retry
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard')
  const { stats, loading, error, refresh } = useDashboardStats()

  return (
    <MainLayout
      activeTab={activeTab}
      onSelectTab={setActiveTab}
      pendingReviewCount={stats?.pendingReviewCount ?? 0}
    >
      {activeTab === 'dashboard' && (
        <div className="space-y-6">
          <div className="p-6 rounded-2xl bg-gradient-to-r from-indigo-900/40 via-slate-900 to-slate-900 border border-indigo-500/20 shadow-xl backdrop-blur-sm relative overflow-hidden">
            <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-indigo-500/10 to-transparent pointer-events-none" />
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-3">
              <Sparkles className="w-3.5 h-3.5" /> ReconAI Agent Platform
            </div>
            <h2 className="text-3xl font-extrabold text-white">
              AI-Powered Bookkeeping &amp; Reconciliation
            </h2>
            <p className="text-slate-400 text-sm max-w-2xl mt-2 leading-relaxed">
              Multi-agent accounting automation framework. Autonomous OCR intake, LLM journal entry
              suggestions with deterministic double-entry guardrails, and human-in-the-loop
              verification.
            </p>
          </div>

          <DashboardStatsCards
            stats={stats}
            loading={loading}
            error={error}
            onRefresh={refresh}
          />
        </div>
      )}

      {activeTab === 'documents' && (
        <DocumentIntakeView
          onSelectDocument={(docId) => {
            console.log('Selected document:', docId)
            setActiveTab('audit')
          }}
        />
      )}

      {activeTab === 'review' && (
        <ReviewQueueView
          onInspectItem={(item) => {
            console.log('Inspect review item:', item)
          }}
        />
      )}

      {activeTab === 'ledger' && <GeneralLedgerView />}

      {activeTab === 'reconciliation' && <ReconciliationView />}

      {activeTab === 'audit' && <AuditTraceabilityView />}
    </MainLayout>
  )
}

export default App
