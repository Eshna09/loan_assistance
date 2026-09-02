import React, { useCallback, useEffect, useState } from 'react'
import { getHealth } from '../services/api'
import Section from './ui/Section'

const POLL_MS = 15_000

// Presentation metadata for each service. Live values come from GET /health.
const SERVICE_META = {
  'app-service': {
    label: 'Application Service',
    port: 8000,
    owns: 'Orchestration + public API',
  },
  'retrieval-service': {
    label: 'Retrieval / RAG Service',
    port: 8001,
    owns: 'MiniLM embeddings + FAISS index',
  },
  'llm-service': {
    label: 'LLM Service',
    port: 8002,
    owns: 'Ollama / Code Llama inference',
  },
  'data-service': {
    label: 'Data Service',
    port: 8003,
    owns: 'Documents, chunking, uploads',
  },
}

const ORDER = ['app-service', 'retrieval-service', 'llm-service', 'data-service']

function statusStyle(status) {
  if (status === 'ok') return { dot: 'bg-[#34d399]', text: 'text-[#34d399]', label: 'healthy' }
  if (status === 'degraded') return { dot: 'bg-[#fbbf24]', text: 'text-[#fbbf24]', label: 'degraded' }
  if (status === 'unreachable') return { dot: 'bg-[#f87171]', text: 'text-[#f87171]', label: 'down' }
  return { dot: 'bg-white/20', text: 'text-[#6b7683]', label: 'unknown' }
}

/** The one detail worth surfacing per service, drawn from its own health payload. */
function serviceDetail(name, info) {
  if (name === 'retrieval-service' && info.vectors !== undefined) {
    return `${info.vectors} vectors · ${info.dimension}-dim · ${info.index_type}`
  }
  if (name === 'llm-service') {
    if (info.ollama_reachable === false) return 'Ollama unreachable'
    if (info.model) return `${info.model}${info.model_available === false ? ' (not pulled)' : ''}`
  }
  if (name === 'data-service' && info.documents !== undefined) {
    return `${info.documents} documents · ${info.uploaded} uploaded`
  }
  if (name === 'app-service') return 'Sequences the other three'
  return info.error ? String(info.error).slice(0, 60) : '—'
}

function ServiceCard({ name, info }) {
  const meta = SERVICE_META[name] || { label: name, owns: '' }
  const s = statusStyle(info?.status)

  return (
    <div className="panel p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[12.5px] font-medium text-[#f1f5f9] truncate">{meta.label}</p>
          <p className="text-[10.5px] text-[#6b7683] font-mono tabular">:{meta.port}</p>
        </div>
        <span className="flex items-center gap-1.5 shrink-0" title={s.label}>
          <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
          <span className={`text-[10.5px] ${s.text}`}>{s.label}</span>
        </span>
      </div>

      <p className="text-[11.5px] text-[#a5b0bd] mt-2.5 leading-relaxed">{meta.owns}</p>
      <p className="text-[10.5px] text-[#6b7683] font-mono mt-1 break-words">
        {info ? serviceDetail(name, info) : '—'}
      </p>
      {info?.latency_ms !== undefined && (
        <p className="text-[10.5px] text-[#6b7683] mt-1 tabular">health {info.latency_ms} ms</p>
      )}
    </div>
  )
}

function CallGraph() {
  return (
    <pre className="code-block text-[10.5px]">
{`  Browser
     │  POST /api/ask/debug
     ▼
  ┌──────────────────────┐
  │  Application Service │  :8000   orchestrates, owns no model or data
  └──────────┬───────────┘
             │ 1. POST /embed      ┐
             │ 2. POST /retrieve   ├──► Retrieval Service :8001 ──► Data Service :8003
             │                     ┘        MiniLM + FAISS             documents, chunks
             │ 3. build RAG prompt  (local)
             │ 4. POST /generate   ──────► LLM Service :8002 ──────► Ollama :11434
             ▼                                                        Code Llama
          Response`}
    </pre>
  )
}

function TraceTable({ trace }) {
  const total = trace.reduce((sum, s) => sum + s.duration_ms, 0)
  const max = Math.max(...trace.map((s) => s.duration_ms), 1)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <p className="eyebrow">Last request · measured hops</p>
        <p className="text-[11px] text-[#a5b0bd] font-mono tabular">{total.toFixed(1)} ms total</p>
      </div>
      <div className="space-y-1.5">
        {trace.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-[11px]">
            <span className="w-4 text-[#6b7683] shrink-0 tabular">{i + 1}</span>
            <span className="w-[92px] font-mono text-[#f1f5f9] truncate shrink-0">{s.step}</span>
            <span className="w-36 text-[#6b7683] truncate shrink-0 hidden sm:block">{s.service}</span>
            <div className="flex-1 h-1.5 bg-white/[0.06] rounded-full overflow-hidden min-w-[40px]">
              <div
                className={`h-full rounded-full ${s.status === 'ok' ? 'bg-[#6366f1]' : 'bg-[#f87171]'}`}
                style={{ width: `${Math.max((s.duration_ms / max) * 100, 2)}%` }}
              />
            </div>
            <span className="w-[74px] text-right font-mono tabular text-[#a5b0bd] shrink-0">
              {s.duration_ms} ms
            </span>
            <span
              className={`w-[70px] text-right shrink-0 ${s.status === 'ok' ? 'text-[#34d399]' : 'text-[#f87171]'}`}
            >
              {s.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ServiceArchitecture({ trace }) {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  const check = useCallback(async () => {
    try {
      setHealth(await getHealth())
      setError(null)
    } catch (err) {
      setHealth(null)
      setError(err.message || 'Health check failed')
    }
  }, [])

  useEffect(() => {
    check()
    const timer = setInterval(check, POLL_MS)
    return () => clearInterval(timer)
  }, [check])

  const services = health?.services || {}
  const overall = health?.status

  return (
    <Section
      id="service-architecture"
      eyebrow="Live system"
      title="Service architecture"
      description="Four independent services, each owning one concern and talking over HTTP."
      aside={
        overall ? (
          <span className={overall === 'ok' ? 'chip chip-ok' : 'chip'}>
            {overall === 'ok' ? 'All healthy' : `System ${overall}`}
          </span>
        ) : null
      }
    >
      {error && (
        <p className="text-[12px] text-[#fbbf24] mb-4">
          Live health unavailable ({error}) — start the stack to see real service status.
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {ORDER.map((name) => (
          <ServiceCard key={name} name={name} info={services[name]} />
        ))}
      </div>

      <div className="mt-5 pt-5 border-t border-white/[0.07]">
        <p className="eyebrow mb-2.5">Orchestration of one request</p>
        <CallGraph />
      </div>

      <div className="mt-5 pt-5 border-t border-white/[0.07]">
        {trace && trace.length > 0 ? (
          <TraceTable trace={trace} />
        ) : (
          <p className="text-[12.5px] text-[#6b7683]">
            Ask a question above and the measured timing of each service hop appears here.
          </p>
        )}
      </div>
    </Section>
  )
}
