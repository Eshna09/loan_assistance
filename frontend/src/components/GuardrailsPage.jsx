/**
 * GuardrailsPage.jsx — Week 5
 *
 * Four independently testable guardrail cards:
 *  1. Input Validation     → POST /api/guardrails/check-input
 *  2. Scope & Intent       → POST /api/guardrails/check-scope
 *  3. Retrieval & Evidence → POST /api/guardrails/check-evidence
 *  4. Output Validation    → POST /api/guardrails/check-output
 *
 * All results come from the real backend (services/app_service/guardrails.py).
 * No hardcoded pass/fail values.
 */
import React, { useState, useCallback } from 'react'

const BASE = '/api'

async function apiPost(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120_000),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json()
}

// ── Shared primitives ────────────────────────────────────────────────────────

function Badge({ value, variant }) {
  if (!value) return null
  const v = String(value).toLowerCase()
  const base = 'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-semibold border'

  if (variant === 'status') {
    const passed = v === 'pass' || v === 'passed' || v === 'sufficient' || v === 'accepted' || v === 'allow'
    const blocked = v.startsWith('reject') || v === 'blocked' || v === 'fail' || v === 'failed' || v === 'flagged' || v === 'insufficient'
    if (passed)  return <span className={`${base} border-green-500/40 bg-green-500/10 text-green-400`}>{String(value).toUpperCase()}</span>
    if (blocked) return <span className={`${base} border-red-500/40 bg-red-500/10 text-red-400`}>{String(value).toUpperCase()}</span>
    return <span className={`${base} border-yellow-500/40 bg-yellow-500/10 text-yellow-400`}>{String(value).toUpperCase()}</span>
  }

  return <span className={`${base} border-white/20 bg-white/[0.05] text-[#a5b0bd]`}>{value}</span>
}

function ResultRow({ label, value, mono = false }) {
  if (value === null || value === undefined) return null
  return (
    <div className="flex items-start justify-between gap-3 text-[12px]">
      <span className="text-[#6b7683] shrink-0">{label}</span>
      <span className={`text-right ${mono ? 'font-mono text-[#f1f5f9]' : 'text-[#cbd5e1]'}`}>
        {String(value)}
      </span>
    </div>
  )
}

function ImplBlock({ file, fn }) {
  return (
    <div className="rounded-md border border-white/[0.07] bg-white/[0.02] px-3 py-2 space-y-1">
      <p className="text-[10.5px] text-[#6b7683] uppercase tracking-widest font-medium mb-1">Implementation</p>
      <div className="flex items-start gap-2 text-[11.5px]">
        <span className="text-[#6b7683] shrink-0">File</span>
        <span className="font-mono text-[#818cf8] break-all">{file}</span>
      </div>
      <div className="flex items-start gap-2 text-[11.5px]">
        <span className="text-[#6b7683] shrink-0">Function</span>
        <span className="font-mono text-[#34d399] break-all">{fn}</span>
      </div>
    </div>
  )
}

function RunButton({ loading, onClick, accent }) {
  const colors = {
    blue:   'bg-blue-600/80 hover:bg-blue-600 border-blue-500/50',
    green:  'bg-emerald-600/80 hover:bg-emerald-600 border-emerald-500/50',
    orange: 'bg-orange-600/80 hover:bg-orange-600 border-orange-500/50',
    purple: 'bg-violet-600/80 hover:bg-violet-600 border-violet-500/50',
  }
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`w-full py-2 rounded-lg border text-[12.5px] font-semibold text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed ${colors[accent]}`}
    >
      {loading ? (
        <span className="flex items-center justify-center gap-2">
          <span className="w-3 h-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
          Running…
        </span>
      ) : 'Run Test'}
    </button>
  )
}

const ACCENT_RING = {
  blue:   'ring-blue-500/20 border-blue-500/20',
  green:  'ring-emerald-500/20 border-emerald-500/20',
  orange: 'ring-orange-500/20 border-orange-500/20',
  purple: 'ring-violet-500/20 border-violet-500/20',
}

const ACCENT_TITLE = {
  blue:   'text-blue-400',
  green:  'text-emerald-400',
  orange: 'text-orange-400',
  purple: 'text-violet-400',
}

const ACCENT_NUM = {
  blue:   'bg-blue-500/15 text-blue-300 border-blue-500/30',
  green:  'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  orange: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  purple: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
}

function GuardrailCard({ num, title, purpose, impl, testPlaceholder, accent, onRun, loading, result, error }) {
  const [input, setInput] = useState('')

  const handleRun = () => onRun(input)

  return (
    <div className={`rounded-xl border bg-[#111118] ring-1 p-5 flex flex-col gap-4 ${ACCENT_RING[accent]}`}>
      {/* Header */}
      <div className="flex items-start gap-3">
        <span className={`shrink-0 text-[11px] font-bold px-2 py-0.5 rounded border ${ACCENT_NUM[accent]}`}>{num}</span>
        <div>
          <h3 className={`text-[15px] font-semibold leading-tight ${ACCENT_TITLE[accent]}`}>{title}</h3>
          <p className="text-[12px] text-[#6b7683] mt-0.5 leading-relaxed">{purpose}</p>
        </div>
      </div>

      {/* Implementation */}
      <ImplBlock file={impl.file} fn={impl.fn} />

      {/* Input */}
      <div className="flex flex-col gap-2">
        <textarea
          rows={2}
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={testPlaceholder}
          disabled={loading}
          className="w-full bg-[#0a0a0f] border border-white/[0.1] rounded-lg px-3 py-2 text-[12.5px] text-[#f1f5f9] placeholder-[#6b7683] focus:outline-none focus:border-[rgba(99,102,241,0.4)] resize-none disabled:opacity-50"
        />
        <RunButton loading={loading} onClick={handleRun} accent={accent} />
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/8 px-3 py-2 text-[12px] text-red-400">
          {error}
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="rounded-lg border border-white/[0.08] bg-[#0a0a0f] p-3 space-y-2">
          <p className="text-[10.5px] text-[#6b7683] uppercase tracking-widest font-medium">Result</p>
          {result}
        </div>
      )}
    </div>
  )
}

// ── Card 1 — Input Validation ────────────────────────────────────────────────
function InputValidationCard() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleRun = useCallback(async (input) => {
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await apiPost('/guardrails/check-input', { question: input })
      setResult(
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-[#6b7683]">Result</span>
            <Badge value={data.passed ? 'PASSED' : 'BLOCKED'} variant="status" />
          </div>
          <ResultRow label="Status"       value={data.status} mono />
          <ResultRow label="Input length" value={`${data.input_length} chars`} mono />
          <ResultRow label="Max allowed"  value={`${data.limits?.max_input_length} chars`} mono />
          <ResultRow label="Action"       value={data.action} mono />
          {data.reason && <ResultRow label="Reason" value={data.reason} />}
          {data.checks && (
            <div className="pt-1 border-t border-white/[0.06] space-y-1">
              <p className="text-[10.5px] text-[#6b7683]">Checks</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(data.checks).map(([k, v]) => (
                  <span key={k} className="text-[11px] font-mono">
                    <span className="text-[#6b7683]">{k}: </span>
                    <Badge value={v} variant="status" />
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <GuardrailCard
      num="1"
      title="Input Validation"
      purpose="Validates the user's input before the request enters the processing pipeline. Checks for empty input, excessive length, and hard out-of-scope signals."
      impl={{ file: 'services/app_service/guardrails.py', fn: 'check_input(question)' }}
      testPlaceholder="Try: empty, a very long question, or 'What is Bitcoin?'"
      accent="blue"
      onRun={handleRun}
      loading={loading}
      result={result}
      error={error}
    />
  )
}

// ── Card 2 — Scope & Intent ──────────────────────────────────────────────────
function ScopeIntentCard() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleRun = useCallback(async (input) => {
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await apiPost('/guardrails/check-scope', { question: input })
      setResult(
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-[#6b7683]">Result</span>
            <Badge value={data.passed ? 'IN SCOPE' : 'OUT OF SCOPE'} variant="status" />
          </div>
          <ResultRow label="Status"          value={data.status} mono />
          <ResultRow label="Detected domain" value={data.domain} mono />
          <ResultRow label="Category"        value={data.category} mono />
          <ResultRow label="Scope status"    value={data.scope_status} mono />
          <ResultRow label="Action"          value={data.action} mono />
          <ResultRow label="LLM called"      value={String(data.llm_called)} mono />
          {data.reason && <ResultRow label="Reason" value={data.reason} />}
        </div>
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <GuardrailCard
      num="2"
      title="Scope & Intent"
      purpose="Determines whether the question belongs to a supported domain (Loan Knowledge or Codebase) and identifies the intent category."
      impl={{ file: 'services/app_service/guardrails.py', fn: 'classify_intent(question), check_input(question)' }}
      testPlaceholder="Try: 'What is an EMI?', 'Where is FAISS implemented?', 'What is the weather?'"
      accent="green"
      onRun={handleRun}
      loading={loading}
      result={result}
      error={error}
    />
  )
}

// ── Card 3 — Retrieval & Evidence ────────────────────────────────────────────
function RetrievalEvidenceCard() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleRun = useCallback(async (input) => {
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await apiPost('/guardrails/check-evidence', { question: input })
      setResult(
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-[#6b7683]">Result</span>
            <Badge value={data.passed ? 'SUFFICIENT' : 'INSUFFICIENT'} variant="status" />
          </div>
          <ResultRow label="Status"           value={data.status} mono />
          <ResultRow label="Domain"           value={data.domain} mono />
          <ResultRow label="Retrieved chunks" value={data.retrieved_chunks} mono />
          <ResultRow label="Best L2 distance" value={data.best_distance !== null ? data.best_distance : 'N/A'} mono />
          <ResultRow label="Max threshold"    value={data.threshold} mono />
          <ResultRow label="Evidence"         value={data.evidence_status} mono />
          <ResultRow label="Action"           value={data.action} mono />
          <ResultRow label="LLM called"       value={String(data.llm_called)} mono />
          {data.reason && <ResultRow label="Reason" value={data.reason} />}
          {data.chunks_preview?.length > 0 && (
            <div className="pt-1.5 border-t border-white/[0.06]">
              <p className="text-[10.5px] text-[#6b7683] mb-1.5">Top chunks</p>
              <div className="space-y-1.5">
                {data.chunks_preview.map((c, i) => (
                  <div key={i} className="bg-white/[0.03] border border-white/[0.06] rounded p-2">
                    <span className="text-[10.5px] font-mono text-orange-400">{c.source}</span>
                    <p className="text-[11px] text-[#94a3b8] mt-0.5 leading-relaxed">{c.text}…</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <GuardrailCard
      num="3"
      title="Retrieval & Evidence"
      purpose="Retrieves relevant information from the knowledge base and checks whether sufficient evidence exists to answer the question."
      impl={{ file: 'services/app_service/guardrails.py', fn: 'check_evidence_sufficiency(question, chunks, distances)' }}
      testPlaceholder="Try: 'What is compound interest?', 'What is the exact RBI repo rate?'"
      accent="orange"
      onRun={handleRun}
      loading={loading}
      result={result}
      error={error}
    />
  )
}

// ── Card 4 — Output Validation ───────────────────────────────────────────────
function OutputValidationCard() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleRun = useCallback(async (input) => {
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await apiPost('/guardrails/check-output', { question: input })
      const ov = data.output_validation
      setResult(
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-[#6b7683]">Result</span>
            <Badge value={data.passed ? 'PASSED' : 'FAILED'} variant="status" />
          </div>
          <ResultRow label="Status"   value={data.status} mono />
          <ResultRow label="Domain"   value={data.domain} mono />
          <ResultRow label="Action"   value={data.action} mono />
          {data.reason && <ResultRow label="Reason" value={data.reason} />}
          {ov && (
            <div className="pt-1.5 border-t border-white/[0.06] space-y-1.5">
              <p className="text-[10.5px] text-[#6b7683]">Validation checks</p>
              {[
                ['Relevance',          ov.relevance],
                ['Grounding',          ov.grounding],
                ['Unsupported claims', ov.unsupported_claims],
                ['Expected behavior',  ov.expected_behavior],
                ['Format',             ov.format],
                ['Overall',            ov.overall],
              ].map(([label, val]) => val !== undefined && (
                <div key={label} className="flex items-center justify-between text-[12px]">
                  <span className="text-[#6b7683]">{label}</span>
                  <Badge value={val} variant="status" />
                </div>
              ))}
              {ov.details?.relevance_overlap !== undefined && (
                <ResultRow label="Relevance overlap" value={`${(ov.details.relevance_overlap * 100).toFixed(1)}%`} mono />
              )}
              {ov.details?.groundedness !== undefined && ov.details.groundedness !== null && (
                <ResultRow label="Groundedness" value={`${(ov.details.groundedness * 100).toFixed(1)}%`} mono />
              )}
            </div>
          )}
          {data.answer && (
            <div className="pt-1.5 border-t border-white/[0.06]">
              <p className="text-[10.5px] text-[#6b7683] mb-1">Generated answer</p>
              <p className="text-[11.5px] text-[#cbd5e1] leading-relaxed line-clamp-4">{data.answer}</p>
            </div>
          )}
        </div>
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <GuardrailCard
      num="4"
      title="Output Validation"
      purpose="Validates the generated response before returning it to the user. Checks relevance, grounding, unsupported claims, and format."
      impl={{ file: 'services/app_service/guardrails.py', fn: 'validate_output(answer, question, context)' }}
      testPlaceholder="Try: 'What is a home loan?', 'What is the difference between simple and compound interest?'"
      accent="purple"
      onRun={handleRun}
      loading={loading}
      result={result}
      error={error}
    />
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function GuardrailsPage() {
  return (
    <div className="flex flex-col gap-8">
      {/* Page header */}
      <div>
        <p className="text-[11px] uppercase tracking-widest text-[#6b7683] font-medium mb-1">Week 5</p>
        <h1 className="text-2xl font-bold text-[#f1f5f9] mb-2">🛡 Guardrails &amp; AI Safety</h1>
        <p className="text-[13.5px] text-[#6b7683] max-w-2xl">
          Test and understand each guardrail independently and observe its real-time result.
          Each card calls the actual backend — no hardcoded values.
        </p>
      </div>

      {/* 2 × 2 grid */}
      <div className="grid md:grid-cols-2 gap-5">
        <InputValidationCard />
        <ScopeIntentCard />
        <RetrievalEvidenceCard />
        <OutputValidationCard />
      </div>
    </div>
  )
}
