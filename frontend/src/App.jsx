import React, { useState, useCallback } from 'react'
import Header from './components/Header'
import PipelineOverview from './components/PipelineOverview'
import KnowledgeBase from './components/KnowledgeBase'
import ChunkingViewer from './components/ChunkingViewer'
import EmbeddingViewer from './components/EmbeddingViewer'
import VectorDatabase from './components/VectorDatabase'
import RAGDemo from './components/RAGDemo'
import ServiceArchitecture from './components/ServiceArchitecture'
import ApiArchitecture from './components/ApiArchitecture'
import DockerArchitecture from './components/DockerArchitecture'
import PipelineSummary from './components/PipelineSummary'
import QueryHistory from './components/QueryHistory'
import ModelPlayground from './components/ModelPlayground'
import EvaluationDashboard from './components/EvaluationDashboard'
import RAGAnalysis from './components/RAGAnalysis'
import RepositoryAnalysis from './components/RepositoryAnalysis'
import { useBackendStatus } from './hooks/useBackendStatus'

// ── Navigation config ──────────────────────────────────────────────────────
const PAGES = [
  { id: 'dashboard',   label: '🏠 Dashboard',          description: 'RAG demo + live system state' },
  { id: 'playground',  label: '🤖 Model Playground',    description: 'Demonstrate each LLM individually' },
  { id: 'evaluation',  label: '📊 LLM Evaluation',      description: 'Quantitative model comparison' },
  { id: 'rag-analysis',label: '🔍 RAG Analysis',        description: 'How retrieval affects generation' },
  { id: 'repo',        label: '💻 Repository Analysis', description: 'Multi-file codebase understanding' },
]

function GroupHeading({ label, hint }) {
  return (
    <div className="flex items-baseline gap-3 pt-4">
      <span className="eyebrow">{label}</span>
      <span className="h-px flex-1 bg-white/[0.07]" />
      {hint && <span className="text-[11.5px] text-[#6b7683]">{hint}</span>}
    </div>
  )
}

// ── Top navigation bar ─────────────────────────────────────────────────────
function PageNav({ current, onChange }) {
  return (
    <nav
      aria-label="Main pages"
      className="sticky top-16 z-40 border-b border-white/10 bg-[#0a0a0f]/90 backdrop-blur-md"
    >
      <div className="max-w-[1240px] mx-auto px-5 sm:px-8">
        <ul className="flex items-center gap-0.5 overflow-x-auto py-2 -mb-px" style={{ scrollbarWidth: 'none' }}>
          {PAGES.map(p => (
            <li key={p.id}>
              <button
                onClick={() => onChange(p.id)}
                title={p.description}
                className={`block whitespace-nowrap px-3 py-1.5 rounded-md text-[12.5px] font-medium transition-colors ${
                  current === p.id
                    ? 'bg-[rgba(99,102,241,0.12)] text-[#818cf8]'
                    : 'text-[#6b7683] hover:text-[#a5b0bd] hover:bg-white/[0.04]'
                }`}
              >
                {p.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}

// ── Dashboard page (original Week 3 content, preserved intact) ────────────
function DashboardPage({ status, kbInfo, applyKbInfo }) {
  const [queryHistory, setQueryHistory] = useState([])
  const [liveEmbedding, setLiveEmbedding] = useState(null)
  const [ragDemoKey, setRagDemoKey] = useState(0)
  const [rerunQuery, setRerunQuery] = useState(null)
  const [lastTrace, setLastTrace] = useState(null)

  const handleQueryComplete = useCallback((question, data) => {
    if (data.trace) setLastTrace(data.trace)
    setQueryHistory(prev => [
      ...prev,
      { question, answer: data.answer?.slice(0, 120) + (data.answer?.length > 120 ? '…' : '') },
    ])
  }, [])

  const handleEmbeddingReceived = useCallback(embedding => setLiveEmbedding(embedding), [])

  const handleRerun = useCallback(question => {
    setRerunQuery(question)
    setRagDemoKey(k => k + 1)
    document.getElementById('rag-demo')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  return (
    <>
      <div className="flex flex-col gap-6">
        <RAGDemo
          key={ragDemoKey}
          backendStatus={status}
          onQueryComplete={handleQueryComplete}
          onEmbeddingReceived={handleEmbeddingReceived}
          initialQuery={rerunQuery}
        />
        <QueryHistory history={queryHistory} onRerun={handleRerun} />
      </div>

      <GroupHeading label="Live system" hint="Reflects the running backend" />
      <div className="flex flex-col gap-6 mt-5">
        <KnowledgeBase kbInfo={kbInfo} backendStatus={status} onKbUpdate={applyKbInfo} />
        <ServiceArchitecture trace={lastTrace} />
      </div>

      <GroupHeading label="How it works" hint="Documents to answer, stage by stage" />
      <div className="flex flex-col gap-6 mt-5">
        <PipelineOverview />
        <div className="grid lg:grid-cols-2 gap-6 items-start">
          <ChunkingViewer kbInfo={kbInfo} />
          <div className="flex flex-col gap-6">
            <EmbeddingViewer backendStatus={status} liveEmbedding={liveEmbedding} />
            <VectorDatabase kbInfo={kbInfo} backendStatus={status} />
          </div>
        </div>
      </div>

      <GroupHeading label="Reference" hint="Architecture and deployment" />
      <div className="mt-5 grid lg:grid-cols-2 gap-6 items-start">
        <ApiArchitecture />
        <DockerArchitecture />
      </div>

      <div className="mt-6">
        <PipelineSummary backendStatus={status} />
      </div>
    </>
  )
}

// ── Root App ───────────────────────────────────────────────────────────────
export default function App() {
  const { status, kbInfo, applyKbInfo } = useBackendStatus()
  const [page, setPage] = useState('dashboard')

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-[#f1f5f9]">
      <Header status={status} />
      <PageNav current={page} onChange={setPage} />

      <main className="max-w-[1240px] mx-auto px-5 sm:px-8 py-8">
        {page === 'dashboard'    && <DashboardPage status={status} kbInfo={kbInfo} applyKbInfo={applyKbInfo} />}
        {page === 'playground'   && <ModelPlayground />}
        {page === 'evaluation'   && <EvaluationDashboard />}
        {page === 'rag-analysis' && <RAGAnalysis />}
        {page === 'repo'         && <RepositoryAnalysis />}
      </main>

      <footer className="border-t border-white/10 mt-16">
        <div className="max-w-[1240px] mx-auto px-5 sm:px-8 py-6 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11.5px] text-[#6b7683]">
            Loan Knowledge Assistance — Week 4 · RAG + Multi-Model Evaluation
          </p>
          <p className="text-[11.5px] text-[#6b7683] font-mono">
            all-MiniLM-L6-v2 · FAISS · Ollama · 4 models · 116 evaluations
          </p>
        </div>
      </footer>
    </div>
  )
}
