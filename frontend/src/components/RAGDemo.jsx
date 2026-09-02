import React, { useState, useCallback } from 'react'
import { askDebug } from '../services/api'
import Section from './ui/Section'
import EvidencePanel from './EvidencePanel'
import SourceGraph from './SourceGraph'

const SUGGESTED = [
  'What is a secured loan?',
  'What is an EMI?',
  'How does loan interest work?',
  'What documents are needed for a loan?',
  'Should I invest in mutual funds?',
]

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  async function handleCopy() {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handleCopy}
      className="btn btn-ghost !text-[11.5px] font-mono"
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  )
}

function StepBadge({ n, active, done, error }) {
  const base =
    'w-[22px] h-[22px] rounded-full flex items-center justify-center text-[10.5px] font-semibold tabular shrink-0 border'
  if (error) {
    return (
      <span className={`${base} border-[rgba(251,191,36,0.4)] bg-[rgba(251,191,36,0.12)] text-[#fbbf24]`}>!</span>
    )
  }
  return (
    <span
      className={`${base} ${
        done
          ? 'border-[rgba(52,211,153,0.35)] bg-[rgba(52,211,153,0.12)] text-[#34d399]'
          : active
            ? 'border-[rgba(99,102,241,0.4)] bg-[rgba(99,102,241,0.12)] text-[#818cf8] step-active'
            : 'border-white/[0.1] bg-white/[0.03] text-[#6b7683]'
      }`}
    >
      {done ? '✓' : n}
    </span>
  )
}

function OllamaSetupGuide() {
  return (
    <div className="mt-4 p-4 rounded-lg border border-yellow-500/30 bg-yellow-500/5">
      <p className="text-sm font-semibold text-yellow-300 mb-3 flex items-center gap-2">
        🦙 Ollama Not Running — Setup Guide
      </p>
      <p className="text-xs text-[#6b7683] mb-3">
        Steps 1–5 above (embedding, retrieval, context, prompt) completed successfully.
        Only the final LLM step requires Ollama. To enable it:
      </p>
      <ol className="space-y-2 text-xs text-[#6b7683]">
        <li className="flex gap-2">
          <span className="text-yellow-400 shrink-0">1.</span>
          <span>
            Download and install Ollama from{' '}
            <a href="https://ollama.com" target="_blank" rel="noreferrer" className="text-yellow-300 underline hover:text-yellow-200">
              ollama.com
            </a>
          </span>
        </li>
        <li className="flex gap-2">
          <span className="text-yellow-400 shrink-0">2.</span>
          <span>Open a new terminal and run:</span>
        </li>
      </ol>
      <div className="mt-2 bg-[#0a0a0f] border border-white/10 rounded p-3 font-mono text-xs space-y-1">
        <p className="text-[#34d399]"># Start the Ollama server</p>
        <p className="text-white">ollama serve</p>
        <p className="text-[#34d399] mt-2"># In another terminal, pull Code Llama</p>
        <p className="text-white">ollama pull codellama:7b</p>
      </div>
      <p className="text-xs text-[#6b7683] mt-3">
        Once running on port 11434, the backend will automatically connect and Step 6 will work.
        The retrieval pipeline (Steps 1–5) is fully functional without Ollama.
      </p>
    </div>
  )
}

export default function RAGDemo({ backendStatus, onQueryComplete, onEmbeddingReceived }) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [animStep, setAnimStep] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const runQuery = useCallback(async (q) => {
    if (loading) return
    if (backendStatus !== 'online') {
      setError('Backend is offline. Start the FastAPI server (start_backend.bat) to use the live demo.')
      return
    }
    const question = q.trim()
    if (!question) return

    setLoading(true)
    setError(null)
    setResult(null)
    setAnimStep(1)

    // Animate through retrieval steps while waiting
    const stepTimer = setInterval(() => {
      setAnimStep((s) => (s < 4 ? s + 1 : s))
    }, 700)

    try {
      const data = await askDebug(question)
      clearInterval(stepTimer)
      setResult(data)
      setAnimStep(7)
      if (onQueryComplete) onQueryComplete(question, data)
      if (onEmbeddingReceived && data.query_embedding_preview) {
        onEmbeddingReceived(data.query_embedding_preview)
      }
    } catch (e) {
      clearInterval(stepTimer)
      setError(e.message || 'Request failed.')
      setAnimStep(0)
    } finally {
      setLoading(false)
    }
  }, [loading, backendStatus, onQueryComplete, onEmbeddingReceived])

  function handleSubmit(e) {
    e.preventDefault()
    runQuery(query)
  }

  const isDone = animStep === 7
  const done = (n) => isDone && n <= 5
  const llmDone = isDone && result && !result.ollama_error
  const active = (n) => loading && animStep === n

  return (
    <Section
      id="rag-demo"
      tone="lit"
      eyebrow="Ask the assistant"
      title="Put a question through the pipeline"
      description="Every stage below is real output from the running system — embedding, retrieval, prompt and answer."
    >
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question about loans…"
          disabled={loading}
          aria-label="Your question"
          className="flex-1 min-w-0 bg-[#0a0a0f] border border-white/[0.1] rounded-lg px-4 py-2.5 text-[14px] text-[#f1f5f9] placeholder-[#6b7683] focus:outline-none focus:border-[rgba(99,102,241,0.5)] disabled:opacity-50 transition-colors"
        />
        <button type="submit" disabled={loading || !query.trim()} className="btn btn-primary shrink-0">
          {loading ? 'Asking…' : 'Ask'}
        </button>
      </form>

      <div className="flex flex-wrap gap-1.5 mt-3">
        {SUGGESTED.map((q) => {
          const outOfScope = q === 'Should I invest in mutual funds?'
          return (
            <button
              key={q}
              onClick={() => {
                setQuery(q)
                runQuery(q)
              }}
              disabled={loading}
              title={outOfScope ? 'Outside the knowledge base — the assistant should decline' : undefined}
              className={`text-[12px] px-2.5 py-1.5 rounded-md border transition-colors disabled:opacity-40 ${
                outOfScope
                  ? 'border-[rgba(251,191,36,0.28)] bg-[rgba(251,191,36,0.06)] text-[#fbbf24] hover:bg-[rgba(251,191,36,0.12)]'
                  : 'border-white/[0.08] bg-white/[0.03] text-[#a5b0bd] hover:text-[#f1f5f9] hover:border-white/[0.16]'
              }`}
            >
              {q}
              {outOfScope && <span className="ml-1.5 text-[10px] opacity-70">out of scope</span>}
            </button>
          )
        })}
      </div>

      {error && !result && (
        <div className="mt-4 p-3.5 rounded-lg border border-[rgba(248,113,113,0.3)] bg-[rgba(248,113,113,0.08)]">
          <p className="text-[13px] text-[#f87171]">{error}</p>
        </div>
      )}

      {(loading || result) && (
        <div className="flex flex-col gap-2.5 mt-5">

            {/* Step 1 — User Query */}
            <PipelineStep
              n={1} label="User Query"
              active={active(1)} done={done(1) || isDone}
            >
              <p className="text-sm text-[#6366f1] font-mono ml-9">
                "{result?.question || query}"
              </p>
            </PipelineStep>

            {/* Step 2 — Query Embedding */}
            <PipelineStep
              n={2} label="Query Embedding"
              active={active(2)} done={done(2) || isDone}
              hint={loading && animStep <= 2 ? 'Converting query into 384-dimensional vector...' : ''}
            >
              <div className="ml-9 space-y-2">
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="px-2 py-0.5 border border-white/10 bg-white/5 rounded font-mono text-[#6b7683]">all-MiniLM-L6-v2</span>
                  <span className="px-2 py-0.5 border border-white/10 bg-white/5 rounded font-mono text-[#6b7683]">
                    {result?.query_embedding_dimension ?? 384} dims
                  </span>
                </div>
                {result?.query_embedding_preview ? (
                  <p className="text-xs text-[#34d399] font-mono break-all">
                    [{result.query_embedding_preview.slice(0, 8).map(v => v.toFixed(4)).join(', ')},
                    <span className="text-[#6b7683]"> … </span>
                    {result.query_embedding_preview.slice(-2).map(v => v.toFixed(4)).join(', ')}]
                  </p>
                ) : loading ? (
                  <div className="h-4 bg-white/10 rounded animate-pulse w-3/4" />
                ) : null}
              </div>
            </PipelineStep>

            {/* Step 3 — FAISS Search */}
            <PipelineStep
              n={3} label="FAISS Search"
              active={active(3)} done={done(3) || isDone}
              hint={loading && animStep <= 3 ? 'Searching FAISS index (top_k=3)...' : result ? 'top K = 3' : ''}
            >
              {result?.retrieved_chunks ? (
                <div className="ml-9 space-y-2">
                  {result.retrieved_chunks.map((chunk, i) => (
                    <div key={i} className="bg-[#0a0a0f] border border-white/10 rounded-lg p-3">
                      <div className="flex flex-wrap items-center gap-2 mb-1.5">
                        <span className="text-xs font-semibold text-orange-400">Chunk {i + 1}</span>
                        <span className="text-xs text-[#6b7683] font-mono">{chunk.source}</span>
                        {result.distances?.[i] !== undefined ? (
                          <span className="text-xs text-[#6b7683]">
                            L2 distance: <span className="text-yellow-400 font-mono">{result.distances[i].toFixed(4)}</span>
                          </span>
                        ) : (
                          <span className="text-xs text-[#6b7683]">Relevant chunk retrieved</span>
                        )}
                      </div>
                      <p className="text-xs text-[#cbd5e1] leading-relaxed">{chunk.text}</p>
                    </div>
                  ))}
                </div>
              ) : loading ? (
                <div className="ml-9 space-y-2">
                  {[1,2,3].map(i => <div key={i} className="h-14 bg-white/5 rounded animate-pulse" />)}
                </div>
              ) : null}
            </PipelineStep>

            {/* Step 4 — Retrieved Context */}
            <PipelineStep
              n={4} label="Context supplied to the LLM"
              active={active(4)} done={done(4) || isDone}
              extra={result?.context ? <CopyButton text={result.context} /> : null}
            >
              {result?.context && (
                <pre className="ml-9 text-xs text-[#cbd5e1] bg-[#0a0a0f] border border-white/10 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed max-h-48 overflow-y-auto">
                  {result.context}
                </pre>
              )}
            </PipelineStep>

            {/* Step 5 — RAG Prompt */}
            <PipelineStep
              n={5} label="RAG Prompt"
              active={active(5)} done={done(5) || isDone}
              extra={result?.prompt ? <CopyButton text={result.prompt} /> : null}
            >
              {result?.prompt && (
                <div className="ml-9 space-y-2">
                  <div className="bg-pink-500/5 border border-pink-500/20 rounded p-2">
                    <p className="text-xs text-pink-300">
                      System: <span className="text-[#6b7683]">
                        "Answer ONLY using the provided context. Do not invent information."
                      </span>
                    </p>
                  </div>
                  <pre className="text-xs text-[#cbd5e1] bg-[#0a0a0f] border border-white/10 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed max-h-56 overflow-y-auto">
                    {result.prompt}
                  </pre>
                </div>
              )}
            </PipelineStep>

            {/* Step 6 — LLM Generation */}
            <PipelineStep
              n={6} label="LLM Generation"
              active={loading && animStep >= 4}
              done={llmDone}
              error={isDone && !!result?.ollama_error}
            >
              <div className="ml-9">
                {/* Loading */}
                {loading && animStep >= 4 && (
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      <span className="w-1.5 h-1.5 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-1.5 h-1.5 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-1.5 h-1.5 bg-[#6366f1] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <span className="text-xs text-[#6b7683]">Generating via Code Llama / Ollama...</span>
                  </div>
                )}

                {/* Ollama error — show setup guide but don't treat as a crash */}
                {isDone && result?.ollama_error && (
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span className="text-xs px-2 py-0.5 border border-red-500/30 bg-red-500/10 text-red-300 rounded font-mono">🦙 Code Llama</span>
                      <span className="text-xs px-2 py-0.5 border border-yellow-500/30 bg-yellow-500/10 text-yellow-300 rounded">Not running</span>
                    </div>
                    <p className="text-xs text-yellow-300 mb-2">
                      ⚠ {result.ollama_error}
                    </p>
                    <p className="text-xs text-[#6b7683]">
                      Steps 1–5 completed successfully. The retrieval pipeline is fully functional.
                      Install Ollama to enable the final answer generation step.
                    </p>
                  </div>
                )}

                {/* Successful answer */}
                {isDone && result?.answer && !result.ollama_error && (
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <span className="text-xs px-2 py-0.5 border border-red-500/30 bg-red-500/10 text-red-300 rounded font-mono">🦙 Code Llama</span>
                      <span className="text-xs px-2 py-0.5 border border-pink-500/30 bg-pink-500/10 text-pink-300 rounded font-mono">Ollama :11434</span>
                      <span className="text-xs text-[#34d399]">✓ Response received</span>
                    </div>
                    <div className={`p-4 rounded-lg border ${
                      result.answer?.includes('not available in my knowledge base')
                        ? 'border-red-500/40 bg-red-500/10'
                        : 'border-teal-500/30 bg-teal-500/5'
                    }`}>
                      <p className="text-sm text-white leading-relaxed">{result.answer}</p>
                    </div>
                    {result.sources?.length > 0 && (
                      <p className="mt-2 text-xs text-[#6b7683]">
                        Sources:{result.sources.map(s => (
                          <span key={s} className="font-mono text-[#6366f1] ml-1">{s}</span>
                        ))}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </PipelineStep>

            {/* Ollama setup guide — shown below pipeline when Ollama is missing */}
            {isDone && result?.ollama_error && <OllamaSetupGuide />}

            {/* Source graph — provenance of the answer across chunks and documents */}
            {isDone && result?.source_graph && (
              <SourceGraph result={result} defaultOpen={false} />
            )}

            {/* Evidence & Sources — shown when result has evidence data */}
            {isDone && result?.evidence && (
              <EvidencePanel result={result} defaultOpen={false} />
            )}
          </div>
        )}

        {/* Hallucination safety card */}
        <div className="mt-6 p-4 rounded-lg border border-red-500/30 bg-red-500/5">
          <div className="flex items-start gap-3">
            <span className="text-xl">🛡️</span>
            <div>
              <p className="text-sm font-semibold text-red-300 mb-1">Knowledge Boundary Test</p>
              <p className="text-xs text-[#6b7683] mb-2">
                Try asking:{' '}
                <button
                  onClick={() => { setQuery('Should I invest in mutual funds?'); runQuery('Should I invest in mutual funds?') }}
                  disabled={loading || backendStatus !== 'online'}
                  className="text-red-300 underline hover:text-red-200 disabled:opacity-40"
                >
                  "Should I invest in mutual funds?"
                </button>
              </p>
              <p className="text-xs text-[#6b7683] mb-1.5">
                Expected response:{' '}
                <span className="text-white italic">"This information is not available in my knowledge base."</span>
              </p>
              <p className="text-xs text-[#6b7683]">
                The RAG prompt explicitly instructs Code Llama to answer ONLY from the retrieved context.
                When investing is not in the loan knowledge base, no relevant chunks are retrieved and the LLM
                correctly declines to answer.
              </p>
            </div>
          </div>
        </div>
    </Section>
  )
}

// ── Reusable pipeline step wrapper ─────────────────────────────────────────
function PipelineStep({ n, label, active, done, error, hint, extra, children }) {
  const isVisible = active || done || error

  return (
    <div
      className={`rounded-lg border p-4 transition-colors duration-300 ${
        error
          ? 'border-[rgba(251,191,36,0.3)] bg-[rgba(251,191,36,0.04)]'
          : isVisible
            ? 'border-white/[0.1] bg-white/[0.028]'
            : 'border-white/[0.06] bg-transparent opacity-45'
      }`}
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-3 min-w-0">
          <StepBadge n={n} active={active} done={done} error={error} />
          <span className="text-[13px] font-medium text-[#f1f5f9]">{label}</span>
          {hint && <span className="text-[11.5px] text-[#6b7683] hidden sm:block truncate">{hint}</span>}
        </div>
        {extra}
      </div>
      {isVisible && children}
    </div>
  )
}
