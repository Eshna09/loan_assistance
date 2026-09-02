/**
 * ModelPlayground.jsx — Part A of Week 4
 *
 * Select one model → ask a question → see that model work through the
 * existing RAG pipeline.  Retrieval is ALWAYS MiniLM + FAISS regardless
 * of which model is chosen — only the LLM changes.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react'
import Section from './ui/Section'

const BASE = '/api'

async function apiGet(path) {
  const res = await fetch(`${BASE}${path}`, { signal: AbortSignal.timeout(10_000) })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function apiPost(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(360_000),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json()
}

// Human-readable display names keyed by Ollama tag prefix
const MODEL_DISPLAY = {
  'codellama': { label: 'Code Llama', icon: '🦙', color: 'text-red-300', border: 'border-red-500/30', bg: 'bg-red-500/10' },
  'llama3':    { label: 'Llama 3',    icon: '🦙', color: 'text-orange-300', border: 'border-orange-500/30', bg: 'bg-orange-500/10' },
  'llama3.2':  { label: 'Llama 3.2',  icon: '🦙', color: 'text-orange-300', border: 'border-orange-500/30', bg: 'bg-orange-500/10' },
  'gemma':     { label: 'Gemma',      icon: '💎', color: 'text-blue-300',   border: 'border-blue-500/30',   bg: 'bg-blue-500/10'  },
  'wizardlm':  { label: 'WizardLM',   icon: '🧙', color: 'text-purple-300', border: 'border-purple-500/30', bg: 'bg-purple-500/10'},
  'mistral':   { label: 'Mistral',    icon: '🌪',  color: 'text-cyan-300',   border: 'border-cyan-500/30',   bg: 'bg-cyan-500/10'  },
}

function getDisplay(name) {
  const prefix = Object.keys(MODEL_DISPLAY).find(k => name.toLowerCase().startsWith(k))
  return prefix ? MODEL_DISPLAY[prefix] : { label: name, icon: '🤖', color: 'text-slate-300', border: 'border-slate-500/30', bg: 'bg-slate-500/10' }
}

const SUGGESTED = [
  'What documents are required for a personal loan?',
  'What is the difference between a fixed and variable interest rate?',
  'What happens if I miss a loan repayment?',
  'What is a debt-to-income ratio?',
  'Should I buy Bitcoin?',
]

export default function ModelPlayground() {
  const [availableModels, setAvailableModels] = useState([])
  const [modelsError, setModelsError] = useState(null)
  const [selectedModel, setSelectedModel] = useState('')
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  // Use a ref so handleAsk always sees the latest values without stale closure issues
  const loadingRef = useRef(false)
  const selectedModelRef = useRef('')

  useEffect(() => {
    selectedModelRef.current = selectedModel
  }, [selectedModel])

  useEffect(() => {
    apiGet('/playground/models')
      .then(d => {
        const names = (d.models || [])
        setAvailableModels(names)
        if (names.length > 0) {
          setSelectedModel(names[0])
          selectedModelRef.current = names[0]
        }
      })
      .catch(e => setModelsError(e.message))
  }, [])

  // handleAsk is stable — no deps that cause stale closures
  const handleAsk = useCallback(async (q, modelOverride) => {
    const model = modelOverride || selectedModelRef.current
    if (!q?.trim() || !model || loadingRef.current) return
    loadingRef.current = true
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await apiPost('/playground/ask', { question: q.trim(), model })
      setResult(data)
    } catch (e) {
      setError(e.message || 'Request failed')
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }, [])

  function handleSubmit(e) {
    e.preventDefault()
    handleAsk(question)
  }

  const display = selectedModel ? getDisplay(selectedModel) : null
  const totalMs = result?.trace?.reduce((s, t) => s + (t.duration_ms || 0), 0) ?? 0

  return (
    <Section
      id="model-playground"
      eyebrow="Part A — Week 4"
      title="🤖 Model Playground"
      description="Select one LLM and ask a question. Retrieval (MiniLM + FAISS) is identical for every model — only the LLM changes."
    >
      {/* ── Model selector ─────────────────────────────────────────────────── */}
      <div className="panel p-5 mb-5">
        <p className="text-[12px] text-[#6b7683] uppercase tracking-widest mb-3 font-medium">Select LLM</p>
        {modelsError ? (
          <div className="p-3 rounded border border-red-500/30 bg-red-500/10 text-red-300 text-sm">
            Could not load models: {modelsError}
          </div>
        ) : availableModels.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-[#6b7683]">
            <span className="animate-pulse">Loading models from Ollama…</span>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {availableModels.map(m => {
              const d = getDisplay(m)
              const active = m === selectedModel
              return (
                <button
                  key={m}
                  onClick={() => { 
                    setSelectedModel(m)
                    selectedModelRef.current = m
                    setResult(null)
                    setError(null)
                  }}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-all
                    ${active
                      ? `${d.border} ${d.bg} ${d.color} shadow-sm`
                      : 'border-white/10 bg-white/[0.03] text-[#6b7683] hover:border-white/20 hover:text-[#a5b0bd]'
                    }`}
                >
                  <span>{d.icon}</span>
                  <span className="font-mono text-[12px]">{m}</span>
                  {active && <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />}
                </button>
              )
            })}
          </div>
        )}

        {/* Unavailable models note */}
        {availableModels.length > 0 && (
          <div className="mt-4 border-t border-white/[0.06] pt-4">
            <p className="text-[11.5px] text-[#6b7683] mb-2">Pull additional models via Ollama:</p>
            <div className="flex flex-wrap gap-2 text-[11px] font-mono">
              {['llama3.2:latest', 'gemma:2b', 'codellama:latest', 'wizardlm2:7b', 'mistral:latest']
                .filter(m => !availableModels.includes(m))
                .map(m => (
                  <span key={m} className="px-2 py-1 border border-dashed border-white/20 rounded text-[#6b7683]">
                    ollama pull {m}
                  </span>
                ))
              }
              {['llama3.2:latest', 'gemma:2b', 'codellama:latest', 'wizardlm2:7b', 'mistral:latest']
                .every(m => availableModels.includes(m)) && (
                <span className="text-[#34d399] text-[11.5px]">✓ All suggested models available</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Question input ─────────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} className="flex gap-2 mb-3">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder="Ask a loan question…"
          disabled={loading || !selectedModel}
          className="flex-1 min-w-0 bg-[#0a0a0f] border border-white/[0.1] rounded-lg px-4 py-2.5 text-[14px] text-[#f1f5f9] placeholder-[#6b7683] focus:outline-none focus:border-[rgba(99,102,241,0.5)] disabled:opacity-50"
        />
        <button type="submit" disabled={loading || !question.trim() || !selectedModelRef.current} className="btn btn-primary shrink-0">
          {loading ? 'Asking…' : 'Ask Model'}
        </button>
      </form>

      {/* Suggested questions */}
      <div className="flex flex-wrap gap-1.5 mb-6">
        {SUGGESTED.map(q => (
          <button
            key={q}
            onClick={() => { setQuestion(q); handleAsk(q) }}
            disabled={loading || !selectedModelRef.current}
            className={`text-[11.5px] px-2.5 py-1.5 rounded-md border transition-colors disabled:opacity-40
              ${q === 'Should I buy Bitcoin?'
                ? 'border-yellow-500/30 bg-yellow-500/5 text-yellow-400 hover:bg-yellow-500/10'
                : 'border-white/[0.08] bg-white/[0.03] text-[#a5b0bd] hover:text-[#f1f5f9] hover:border-white/[0.16]'
              }`}
          >
            {q}
          </button>
        ))}
      </div>

      {/* ── Error ─────────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-4 p-3.5 rounded-lg border border-red-500/30 bg-red-500/10">
          <p className="text-sm text-[#f87171]">{error}</p>
        </div>
      )}

      {/* ── Loading skeleton ──────────────────────────────────────────────── */}
      {loading && (
        <div className="panel p-5 space-y-4 animate-pulse">
          <div className="h-4 w-1/3 bg-white/10 rounded" />
          <div className="h-16 bg-white/5 rounded" />
          <div className="h-24 bg-white/5 rounded" />
        </div>
      )}

      {/* ── Result ───────────────────────────────────────────────────────── */}
      {result && !loading && (
        <div className="space-y-4">
          {/* Header row */}
          <div className="flex flex-wrap items-center gap-3">
            {display && (
              <span className={`flex items-center gap-1.5 text-sm px-3 py-1 rounded-full border font-medium ${display.border} ${display.bg} ${display.color}`}>
                {display.icon} {result.model || selectedModel}
              </span>
            )}
            <span className="text-xs text-[#6b7683]">
              Total latency: <span className="text-[#f1f5f9] font-mono">{(totalMs / 1000).toFixed(2)}s</span>
            </span>
            <span className="text-xs text-[#6b7683]">
              Sources: {result.sources?.map(s => (
                <span key={s} className="font-mono text-[#6366f1] ml-1">{s}</span>
              ))}
            </span>
          </div>

          {/* Retrieved context */}
          <div className="panel p-4">
            <p className="text-[11.5px] text-[#6b7683] uppercase tracking-widest mb-3">Retrieved Context</p>
            <div className="space-y-2">
              {result.retrieved_chunks?.map((chunk, i) => (
                <div key={i} className="bg-[#0a0a0f] border border-white/10 rounded-lg p-3">
                  <div className="flex flex-wrap items-center gap-2 mb-1.5">
                    <span className="text-xs font-semibold text-orange-400">Chunk {i + 1}</span>
                    <span className="text-xs text-[#6b7683] font-mono">{chunk.source}</span>
                    {result.distances?.[i] !== undefined && (
                      <span className="text-xs text-[#6b7683]">
                        L2: <span className="text-yellow-400 font-mono">{result.distances[i].toFixed(4)}</span>
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#cbd5e1] leading-relaxed">{chunk.text}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Pipeline trace */}
          {result.trace?.length > 0 && (
            <div className="panel p-4">
              <p className="text-[11.5px] text-[#6b7683] uppercase tracking-widest mb-3">Pipeline Trace</p>
              <div className="space-y-1.5">
                {result.trace.map((step, i) => (
                  <div key={i} className="flex items-center gap-3 text-xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#6366f1] shrink-0" />
                    <span className="text-[#f1f5f9] font-mono w-28 shrink-0">{step.step}</span>
                    <span className="text-[#6b7683] flex-1 truncate">{step.service}</span>
                    <span className={`font-mono tabular-nums ${step.status === 'ok' ? 'text-[#34d399]' : 'text-[#f87171]'}`}>
                      {step.duration_ms?.toFixed(0)}ms
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono
                      ${step.status === 'ok'
                        ? 'border-green-500/30 bg-green-500/10 text-green-400'
                        : 'border-red-500/30 bg-red-500/10 text-red-400'}`}>
                      {step.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* LLM Response */}
          <div className="panel p-4">
            <p className="text-[11.5px] text-[#6b7683] uppercase tracking-widest mb-3">LLM Response</p>
            {result.ollama_error ? (
              <div className="space-y-3">
                <div className="p-3 rounded border border-yellow-500/30 bg-yellow-500/10 text-yellow-300 text-sm">
                  ⚠ {result.ollama_error}
                </div>
                <p className="text-xs text-[#6b7683]">
                  To use this model, run: <code className="font-mono text-[#6366f1]">ollama pull {selectedModel}</code>
                </p>
              </div>
            ) : (
              <div className={`p-4 rounded-lg border ${
                result.answer?.includes('not available in my knowledge base')
                  ? 'border-red-500/30 bg-red-500/10'
                  : 'border-teal-500/30 bg-teal-500/5'
              }`}>
                <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">{result.answer}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {!result && !loading && !error && selectedModel && (        <div className="text-center py-12 text-[#6b7683]">
          <p className="text-4xl mb-3">🤖</p>
          <p className="text-sm">Select a model above and ask a question to see it work through the RAG pipeline.</p>
          <p className="text-[11.5px] mt-1 font-mono">Retrieval stays the same — only the LLM changes.</p>
        </div>
      )}
    </Section>
  )
}
