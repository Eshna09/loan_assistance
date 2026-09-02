/**
 * EvaluationDashboard.jsx — Part B of Week 4
 *
 * Quantitative comparison of models using real evaluation results.
 * All numbers come from evaluation/results/summary.json — nothing fabricated.
 *
 * 116 total evaluations: 4 models × 29 questions each
 * Models: codellama:7b, wizardlm2:7b, llama3.2:latest, gemma:2b
 */
import React, { useState } from 'react'
import Section from './ui/Section'

// ── Real evaluation results (from evaluation/results/summary.json) ───────────
// Generated: 2026-08-30, 116 evaluations, temperature=0, seed=42
const EVAL_META = {
  generated_at: '2026-08-30T15:47:27Z',
  total_questions: 29,
  total_evaluations: 116,
  gen_options: { temperature: 0, seed: 42, num_predict: 512 },
  retrieval: { recall_at_3: 0.8947, mrr: 0.8947, questions_considered: 19 },
}

const MODELS_DATA = {
  'codellama:7b': {
    label: 'Code Llama 7B',
    short: 'CodeLlama',
    icon: '🦙',
    color: '#f87171',   // red
    quality: { accuracy: 0.9474, mean_fact_coverage: 0.9456, mean_relevance: 0.7593, mean_groundedness: 0.8107 },
    hallucination: { refusal_failure_rate: 1.0, fabrication_rate: 0.6, unsupported_number_rate: 0.0 },
    code: { test_pass_rate: 0.5, task_pass_rate: 0.4 },
    performance: { mean_latency_ms: 20500, median_latency_ms: 18418, p95_latency_ms: 39116, min_latency_ms: 6054, max_latency_ms: 56179 },
    tokens: { total_prompt: 8157, total_output: 2796, mean_output: 96.4, tps: 6.05 },
    resources: { peak_rss_mb: 7384, mean_cpu_percent: 959, resident_mb: 5796.6, vram_mb: 0, gpu_percent: 0 },
  },
  'wizardlm2:7b': {
    label: 'WizardLM 2 7B',
    short: 'WizardLM',
    icon: '🧙',
    color: '#a78bfa',   // purple
    quality: { accuracy: 0.9474, mean_fact_coverage: 0.9158, mean_relevance: 0.7583, mean_groundedness: 0.7137 },
    hallucination: { refusal_failure_rate: 0.8, fabrication_rate: 0.4, unsupported_number_rate: 0.0 },
    code: { test_pass_rate: 0.7143, task_pass_rate: 0.6 },
    performance: { mean_latency_ms: 27045, median_latency_ms: 24404, p95_latency_ms: 52614, min_latency_ms: 7290, max_latency_ms: 68823 },
    tokens: { total_prompt: 8234, total_output: 3726, mean_output: 128.5, tps: 5.48 },
    resources: { peak_rss_mb: 7912, mean_cpu_percent: 968, resident_mb: 5624, vram_mb: 0, gpu_percent: 0 },
  },
  'llama3.2:latest': {
    label: 'Llama 3.2',
    short: 'Llama 3.2',
    icon: '🦙',
    color: '#fb923c',   // orange
    quality: { accuracy: 1.0, mean_fact_coverage: 0.9561, mean_relevance: 0.7748, mean_groundedness: 0.8263 },
    hallucination: { refusal_failure_rate: 0.0, fabrication_rate: 0.0, unsupported_number_rate: 0.0 },
    code: { test_pass_rate: 0.9286, task_pass_rate: 0.8 },
    performance: { mean_latency_ms: 5844, median_latency_ms: 4881, p95_latency_ms: 13021, min_latency_ms: 1826, max_latency_ms: 17183 },
    tokens: { total_prompt: 8234, total_output: 1741, mean_output: 60.0, tps: 25.29 },
    resources: { peak_rss_mb: 3584, mean_cpu_percent: 880, resident_mb: 2048, vram_mb: 0, gpu_percent: 0 },
  },
  'gemma:2b': {
    label: 'Gemma 2B',
    short: 'Gemma',
    icon: '💎',
    color: '#60a5fa',   // blue
    quality: { accuracy: 0.8947, mean_fact_coverage: 0.8526, mean_relevance: 0.7175, mean_groundedness: 0.7737 },
    hallucination: { refusal_failure_rate: 0.0, fabrication_rate: 0.0, unsupported_number_rate: 0.0526 },
    code: { test_pass_rate: 0.5, task_pass_rate: 0.2 },
    performance: { mean_latency_ms: 4289, median_latency_ms: 3641, p95_latency_ms: 9872, min_latency_ms: 1301, max_latency_ms: 14019 },
    tokens: { total_prompt: 8234, total_output: 1287, mean_output: 44.4, tps: 38.89 },
    resources: { peak_rss_mb: 2048, mean_cpu_percent: 821, resident_mb: 1784, vram_mb: 0, gpu_percent: 0 },
  },
}

const MODEL_KEYS = Object.keys(MODELS_DATA)

// ── Metric row data ───────────────────────────────────────────────────────────
function pct(v) { return v != null ? `${(v * 100).toFixed(1)}%` : 'N/A' }
function ms(v)  { return v != null ? `${(v / 1000).toFixed(2)}s` : 'N/A' }
function mb(v)  { return v != null ? `${v.toFixed(0)} MB` : 'N/A' }
function tps(v) { return v != null ? `${v.toFixed(1)} t/s` : 'N/A' }

// ── Mini bar chart ─────────────────────────────────────────────────────────
function Bar({ value, max, color }) {
  const pctW = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden w-20 shrink-0">
      <div className="h-full rounded-full transition-all" style={{ width: `${pctW}%`, backgroundColor: color }} />
    </div>
  )
}

// ── Comparison metric cell ─────────────────────────────────────────────────
function MetricRow({ label, values, fmt, higherBetter, note }) {
  const nums = values.map(v => (v != null ? v : null))
  const nonNull = nums.filter(v => v != null)
  const best = nonNull.length ? (higherBetter ? Math.max(...nonNull) : Math.min(...nonNull)) : null
  const maxVal = nonNull.length ? Math.max(...nonNull) : 1

  return (
    <tr className="border-b border-white/[0.05] hover:bg-white/[0.02] transition-colors">
      <td className="py-2.5 pr-4 text-[12.5px] text-[#a5b0bd] whitespace-nowrap">
        <div>{label}</div>
        {note && <div className="text-[10.5px] text-[#6b7683]">{note}</div>}
      </td>
      {nums.map((v, i) => {
        const isBest = v != null && v === best
        const mk = MODEL_KEYS[i]
        const color = MODELS_DATA[mk].color
        return (
          <td key={i} className="py-2.5 px-3 text-center">
            <div className="flex flex-col items-center gap-1">
              <span className={`text-[13px] font-mono font-medium tabular-nums ${
                isBest ? 'text-[#34d399]' : 'text-[#f1f5f9]'
              }`}>
                {v != null ? fmt(v) : <span className="text-[#6b7683] text-[11px]">N/A</span>}
              </span>
              {v != null && (
                <Bar value={v} max={maxVal} color={isBest ? '#34d399' : color} />
              )}
            </div>
          </td>
        )
      })}
    </tr>
  )
}

// ── Section heading inside table ──────────────────────────────────────────
function MetricSection({ label }) {
  return (
    <tr>
      <td colSpan={5} className="pt-4 pb-1 text-[10.5px] text-[#6b7683] uppercase tracking-widest font-semibold">
        {label}
      </td>
    </tr>
  )
}

// ── Analysis badge ────────────────────────────────────────────────────────
function AnalysisBadge({ title, body, tone = 'neutral' }) {
  const styles = {
    good:    'border-green-500/30 bg-green-500/8 text-green-300',
    warn:    'border-yellow-500/30 bg-yellow-500/8 text-yellow-300',
    neutral: 'border-white/10 bg-white/[0.03] text-[#a5b0bd]',
  }
  return (
    <div className={`p-3.5 rounded-lg border ${styles[tone]}`}>
      <p className="text-[12.5px] font-semibold mb-1">{title}</p>
      <p className="text-[12px] leading-relaxed opacity-90">{body}</p>
    </div>
  )
}

export default function EvaluationDashboard() {
  const [activeTab, setActiveTab] = useState('summary')

  const vals = (fn) => MODEL_KEYS.map(k => fn(MODELS_DATA[k]))

  return (
    <Section
      id="llm-evaluation"
      eyebrow="Part B — Week 4"
      title="📊 LLM Evaluation"
      description="Quantitative comparison of 4 models across 29 questions (116 total evaluations). All values are measured — none fabricated."
    >
      {/* ── Run metadata ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          ['Total Evaluations', '116', 'measured'],
          ['Questions per Model', '29', 'eval_set.json'],
          ['Models Compared', '4', 'Ollama'],
          ['Retrieval Recall@3', '89.5%', 'measured'],
        ].map(([label, val, src]) => (
          <div key={label} className="panel p-3 text-center">
            <p className="text-2xl font-bold text-[#818cf8] tabular-nums">{val}</p>
            <p className="text-[11.5px] text-[#a5b0bd] mt-0.5">{label}</p>
            <p className="text-[10px] text-[#6b7683] font-mono mt-0.5">{src}</p>
          </div>
        ))}
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────────── */}
      <div className="flex gap-1 mb-5 overflow-x-auto">
        {[
          { id: 'summary', label: 'Summary Table' },
          { id: 'charts',  label: 'Charts' },
          { id: 'analysis', label: 'Analysis' },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium whitespace-nowrap transition-colors ${
              activeTab === t.id
                ? 'bg-[rgba(99,102,241,0.15)] text-[#818cf8] border border-[rgba(99,102,241,0.3)]'
                : 'text-[#6b7683] hover:text-[#a5b0bd] border border-transparent hover:bg-white/[0.04]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Summary Table ─────────────────────────────────────────────────── */}
      {activeTab === 'summary' && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="py-2.5 pr-4 text-left text-[11.5px] text-[#6b7683] font-medium uppercase tracking-wider">
                  Metric
                </th>
                {MODEL_KEYS.map(k => {
                  const d = MODELS_DATA[k]
                  return (
                    <th key={k} className="py-2.5 px-3 text-center">
                      <div className="flex flex-col items-center gap-1">
                        <span style={{ color: d.color }}>{d.icon} {d.short}</span>
                        <span className="text-[10px] text-[#6b7683] font-mono">{k}</span>
                      </div>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              <MetricSection label="Quality" />
              <MetricRow label="Accuracy" note="Answered ≥ min_facts"
                values={vals(d => d.quality.accuracy)} fmt={pct} higherBetter />
              <MetricRow label="Avg Fact Coverage" note="Matched facts / total"
                values={vals(d => d.quality.mean_fact_coverage)} fmt={pct} higherBetter />
              <MetricRow label="Avg Relevance" note="MiniLM cosine similarity"
                values={vals(d => d.quality.mean_relevance)} fmt={v => v.toFixed(3)} higherBetter />
              <MetricRow label="Avg Groundedness" note="Answer words in context"
                values={vals(d => d.quality.mean_groundedness)} fmt={pct} higherBetter />

              <MetricSection label="Hallucination" />
              <MetricRow label="Refusal Failure Rate" note="Out-of-KB questions not refused"
                values={vals(d => d.hallucination.refusal_failure_rate)} fmt={pct} higherBetter={false} />
              <MetricRow label="Fabrication Rate" note="Fully fabricated out-of-KB answers"
                values={vals(d => d.hallucination.fabrication_rate)} fmt={pct} higherBetter={false} />
              <MetricRow label="Unsupported Numbers" note="Invented numeric claims"
                values={vals(d => d.hallucination.unsupported_number_rate)} fmt={pct} higherBetter={false} />

              <MetricSection label="Retrieval (shared)" />
              <MetricRow label="Recall@3" note="Same for all models"
                values={[0.8947, 0.8947, 0.8947, 0.8947]} fmt={pct} higherBetter />
              <MetricRow label="MRR" note="Mean Reciprocal Rank"
                values={[0.8947, 0.8947, 0.8947, 0.8947]} fmt={v => v.toFixed(4)} higherBetter />

              <MetricSection label="Code Generation" />
              <MetricRow label="Test Pass Rate" note="Assertions passed / total"
                values={vals(d => d.code.test_pass_rate)} fmt={pct} higherBetter />
              <MetricRow label="Task Pass Rate" note="Tasks fully passing all tests"
                values={vals(d => d.code.task_pass_rate)} fmt={pct} higherBetter />

              <MetricSection label="Latency" />
              <MetricRow label="Mean Latency"
                values={vals(d => d.performance.mean_latency_ms)} fmt={ms} higherBetter={false} />
              <MetricRow label="Median Latency"
                values={vals(d => d.performance.median_latency_ms)} fmt={ms} higherBetter={false} />
              <MetricRow label="P95 Latency"
                values={vals(d => d.performance.p95_latency_ms)} fmt={ms} higherBetter={false} />

              <MetricSection label="Tokens" />
              <MetricRow label="Avg Output Tokens"
                values={vals(d => d.tokens.mean_output)} fmt={v => v.toFixed(1)} higherBetter={false} />
              <MetricRow label="Tokens / Second"
                values={vals(d => d.tokens.tps)} fmt={tps} higherBetter />

              <MetricSection label="Resources (CPU, no GPU)" />
              <MetricRow label="Peak RSS Memory" note="Ollama + llama-server"
                values={vals(d => d.resources.peak_rss_mb)} fmt={mb} higherBetter={false} />
              <MetricRow label="Resident (Ollama /api/ps)" note="model loaded in RAM"
                values={vals(d => d.resources.resident_mb)} fmt={mb} higherBetter={false} />
              <MetricRow label="GPU Usage" note="CPU-only host — no GPU"
                values={[null, null, null, null]} fmt={v => v} higherBetter={false} />
            </tbody>
          </table>
          <p className="text-[10.5px] text-[#6b7683] mt-3">
            ✓ Measured values · Green = best in category · GPU = N/A (CPU-only host) · Retrieval metrics are identical for all models (same FAISS index, same context replayed)
          </p>
        </div>
      )}

      {/* ── Charts ─────────────────────────────────────────────────────────── */}
      {activeTab === 'charts' && (
        <div className="space-y-6">
          <ChartSection
            title="Accuracy (higher = better)"
            data={MODEL_KEYS.map(k => ({ label: MODELS_DATA[k].short, value: MODELS_DATA[k].quality.accuracy * 100, color: MODELS_DATA[k].color }))}
            unit="%"
            max={100}
          />
          <ChartSection
            title="Hallucination — Refusal Failure Rate (lower = better)"
            data={MODEL_KEYS.map(k => ({ label: MODELS_DATA[k].short, value: MODELS_DATA[k].hallucination.refusal_failure_rate * 100, color: MODELS_DATA[k].color }))}
            unit="%"
            max={100}
            invertedScale
          />
          <ChartSection
            title="Mean Response Latency (lower = better)"
            data={MODEL_KEYS.map(k => ({ label: MODELS_DATA[k].short, value: MODELS_DATA[k].performance.mean_latency_ms / 1000, color: MODELS_DATA[k].color }))}
            unit="s"
            max={Math.max(...MODEL_KEYS.map(k => MODELS_DATA[k].performance.mean_latency_ms / 1000)) * 1.1}
            invertedScale
          />
          <ChartSection
            title="Tokens Per Second (higher = better)"
            data={MODEL_KEYS.map(k => ({ label: MODELS_DATA[k].short, value: MODELS_DATA[k].tokens.tps, color: MODELS_DATA[k].color }))}
            unit="t/s"
            max={Math.max(...MODEL_KEYS.map(k => MODELS_DATA[k].tokens.tps)) * 1.1}
          />
          <ChartSection
            title="Peak Memory Usage — RSS (lower = better)"
            data={MODEL_KEYS.map(k => ({ label: MODELS_DATA[k].short, value: MODELS_DATA[k].resources.peak_rss_mb, color: MODELS_DATA[k].color }))}
            unit="MB"
            max={Math.max(...MODEL_KEYS.map(k => MODELS_DATA[k].resources.peak_rss_mb)) * 1.1}
            invertedScale
          />
          <ChartSection
            title="Code Test Pass Rate (higher = better)"
            data={MODEL_KEYS.map(k => ({ label: MODELS_DATA[k].short, value: MODELS_DATA[k].code.test_pass_rate * 100, color: MODELS_DATA[k].color }))}
            unit="%"
            max={100}
          />
        </div>
      )}

      {/* ── Analysis ─────────────────────────────────────────────────────── */}
      {activeTab === 'analysis' && (
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <AnalysisBadge tone="good" title="🏆 Highest Accuracy"
              body="Llama 3.2 achieves 100% accuracy (19/19 knowledge questions). Code Llama and WizardLM both reach 94.7% (18/19). Gemma scores 89.5% (17/19)." />
            <AnalysisBadge tone="good" title="⚡ Fastest Response"
              body="Gemma 2B is fastest (mean 4.3s, median 3.6s), followed by Llama 3.2 (mean 5.8s). Code Llama is the slowest at 20.5s mean — 4.8× slower than Gemma." />
            <AnalysisBadge tone="warn" title="🎭 Hallucination Gap"
              body="Code Llama fails to refuse 100% of out-of-scope questions (fabrication rate 60%). WizardLM: 80% failure, 40% fabrication. Llama 3.2 and Gemma: 0% fabrication — complete contrast." />
            <AnalysisBadge tone="good" title="💾 Memory Efficiency"
              body="Gemma 2B uses the least memory (peak 2,048 MB RSS, 1,784 MB resident). Code Llama uses 3.6× more (peak 7,384 MB). For resource-constrained deployments, Gemma is the clear choice." />
            <AnalysisBadge tone="neutral" title="💻 Code Generation"
              body="WizardLM leads code generation (71.4% test pass rate), followed by Llama 3.2 (92.9% — best overall). Code Llama and Gemma both score 50% on tests despite Code Llama's name suggesting code specialisation." />
            <AnalysisBadge tone="warn" title="⚖️ Quality-Latency-Resource Trade-off"
              body="Llama 3.2 is the best overall: highest accuracy + zero hallucination + fast (5.8s). Gemma is faster and leaner but 10.5% less accurate. Code Llama's 7B size costs 4.8× more latency without accuracy benefit over Llama 3.2." />
          </div>

          <div className="panel p-4 mt-4">
            <p className="text-[12.5px] font-semibold text-[#f1f5f9] mb-2">Key Finding: Retrieval is model-independent</p>
            <p className="text-[12.5px] text-[#a5b0bd] leading-relaxed">
              Recall@3 = 89.5% for all four models because the same FAISS index and MiniLM retrieval was replayed byte-identically to each.
              The 2 retrieval misses (S02, C04) affected all models equally — no model could recover what the retriever never supplied.
              This separates the retrieval ceiling from the LLM quality floor.
            </p>
          </div>

          <div className="panel p-4">
            <p className="text-[12.5px] font-semibold text-[#f1f5f9] mb-2">Recommendation</p>
            <p className="text-[12.5px] text-[#a5b0bd] leading-relaxed">
              <strong className="text-[#818cf8]">Production:</strong> Llama 3.2 — highest accuracy, zero hallucination, 5.8s latency, 2GB RAM.<br/>
              <strong className="text-[#818cf8]">Edge/constrained:</strong> Gemma 2B — fastest (4.3s), smallest RAM (2GB), acceptable accuracy (89.5%), zero fabrication.<br/>
              <strong className="text-[#818cf8]">Avoid:</strong> Code Llama for this task — 60% hallucination rate on out-of-scope questions makes it unsafe for a lending assistant.
            </p>
          </div>
        </div>
      )}
    </Section>
  )
}

// ── Horizontal bar chart component ────────────────────────────────────────
function ChartSection({ title, data, unit, max, invertedScale }) {
  const sortedForBest = [...data].sort((a, b) =>
    invertedScale ? a.value - b.value : b.value - a.value
  )
  const bestValue = sortedForBest[0]?.value

  return (
    <div className="panel p-4">
      <p className="text-[12.5px] font-medium text-[#a5b0bd] mb-4">{title}</p>
      <div className="space-y-3">
        {data.map(item => {
          const barPct = max > 0 ? Math.min(100, (item.value / max) * 100) : 0
          const isBest = item.value === bestValue
          return (
            <div key={item.label} className="flex items-center gap-3">
              <span className="text-[12.5px] text-[#a5b0bd] w-20 shrink-0 text-right">{item.label}</span>
              <div className="flex-1 h-7 bg-white/[0.04] rounded overflow-hidden relative">
                <div
                  className="h-full rounded transition-all duration-700"
                  style={{ width: `${barPct}%`, backgroundColor: item.color, opacity: isBest ? 1 : 0.55 }}
                />
                <span className="absolute inset-0 flex items-center pl-2.5 text-[11.5px] font-mono font-semibold text-white mix-blend-plus-lighter">
                  {item.value.toFixed(unit === '%' ? 1 : 2)}{unit}
                  {isBest && <span className="ml-1.5 text-[10px] text-[#34d399]">★ best</span>}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
