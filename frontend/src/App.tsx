import { useState } from 'react'
import { MainLayout } from './components/layout/MainLayout'
import type { NavTab } from './components/layout/Sidebar'
import { DocumentIntakeView } from './components/documents/DocumentIntakeView'
import { ReviewQueueView } from './components/review/ReviewQueueView'
import { GeneralLedgerView } from './components/ledger/GeneralLedgerView'
import { ReconciliationView } from './components/reconciliation/ReconciliationView'
import { CheckCircle2, FileText, History, ShieldCheck, Sparkles, UserCheck } from 'lucide-react'

function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard')

  return (
    <MainLayout activeTab={activeTab} onSelectTab={setActiveTab} pendingReviewCount={3}>
      {activeTab === 'dashboard' && (
        <div className="space-y-6">
          <div className="p-6 rounded-2xl bg-gradient-to-r from-indigo-900/40 via-slate-900 to-slate-900 border border-indigo-500/20 shadow-xl backdrop-blur-sm relative overflow-hidden">
            <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-indigo-500/10 to-transparent pointer-events-none" />
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-3">
              <Sparkles className="w-3.5 h-3.5" /> ReconAI Agent Platform
            </div>
            <h2 className="text-3xl font-extrabold text-white">
              AI-Powered Bookkeeping & Reconciliation
            </h2>
            <p className="text-slate-400 text-sm max-w-2xl mt-2 leading-relaxed">
              Multi-agent accounting automation framework. Autonomous OCR intake, LLM journal entry
              suggestions with deterministic double-entry guardrails, and human-in-the-loop
              verification.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <div className="p-5 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-2">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-medium">Processed Documents</span>
                <FileText className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-2xl font-bold text-white">128</div>
              <p className="text-[11px] text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> 100% Validated
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-2">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-medium">Human Review Queue</span>
                <UserCheck className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-2xl font-bold text-white">3 Pending</div>
              <p className="text-[11px] text-amber-400 font-medium">
                Low confidence / sensitive accounts
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-2">
              <div className="flex items-center justify-between text-slate-400">
                <span className="text-xs font-medium">Trial Balance Status</span>
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold text-emerald-400">BALANCED</div>
              <p className="text-[11px] text-slate-400">Debits: 45,200,000 | Credits: 45,200,000</p>
            </div>
          </div>
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

      {activeTab === 'audit' && (
        <div className="p-8 rounded-2xl bg-slate-800/40 border border-slate-700/50 text-center space-y-4">
          <History className="w-12 h-12 text-indigo-400 mx-auto" />
          <h3 className="text-xl font-bold text-white">Audit Log & Traceability</h3>
          <p className="text-slate-400 text-sm max-w-md mx-auto">
            Trace document extractions, LLM rationale, and human approval audit history.
          </p>
        </div>
      )}
    </MainLayout>
  )
}

export default App
