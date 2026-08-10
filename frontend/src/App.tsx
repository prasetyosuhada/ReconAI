function App() {
  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl text-center space-y-6 bg-slate-800/50 p-8 rounded-2xl border border-slate-700/50 shadow-xl backdrop-blur-sm">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold uppercase tracking-wider">
          ReconAI Platform
        </div>
        <h1 className="text-4xl font-bold bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">
          Agentic AI Accounting Automation
        </h1>
        <p className="text-slate-400 text-base leading-relaxed">
          Intelligent bookkeeping pipeline powered by LangGraph, deterministic accounting guardrails, and human-in-the-loop review.
        </p>
        <div className="pt-4 flex items-center justify-center gap-4">
          <a
            href="/api/v1/health"
            target="_blank"
            className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm transition-all shadow-lg shadow-indigo-600/20"
          >
            Backend Health Status
          </a>
        </div>
      </div>
    </div>
  )
}

export default App
