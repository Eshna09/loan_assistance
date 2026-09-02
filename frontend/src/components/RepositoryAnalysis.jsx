/**
 * RepositoryAnalysis.jsx — Part D of Week 4 (Exercise 6)
 *
 * Tests whether the LLM + RAG system can answer multi-file codebase questions.
 * Users can ask questions live or view pre-recorded results from the probe run.
 */
import React, { useState } from 'react'
import Section from './ui/Section'

const BASE = '/api'

// Pre-recorded results from evaluation/CODEBASE_UNDERSTANDING.md
const RECORDED_RESULTS = [
  {
    id: 'R01',
    question: 'What happens when POST /ask is called?',
    expected_files: ['services/app_service/main.py', 'services/retrieval_service/main.py', 'services/llm_service/main.py', 'services/common/prompts.py'],
    retrieved_files: ['services/app_service/main.py', 'services/common/prompts.py'],
    correctness: 'partial',
    answer_summary: 'Correctly described the 4-step orchestration (embed → retrieve → build_prompt → generate), named the Retrieval and LLM services, and cited the RAG prompt template. Did not name the specific service files beyond app_service.',
    missing: ['retrieval_service/main.py (details)', 'llm_service/main.py (details)'],
    note: 'Good high-level answer; missed service-level implementation details.',
  },
  {
    id: 'R02',
    question: 'Which component creates the text embeddings for retrieval?',
    expected_files: ['services/retrieval_service/main.py'],
    retrieved_files: ['services/retrieval_service/main.py', 'services/common/chunking.py'],
    correctness: 'correct',
    answer_summary: 'Correctly identified the Retrieval Service (retrieval_service/main.py), the SentenceTransformer model (all-MiniLM-L6-v2), and the embed() endpoint.',
    missing: [],
    note: 'Single-file question — retrieval worked correctly.',
  },
  {
    id: 'R03',
    question: 'Which service communicates with Ollama?',
    expected_files: ['services/llm_service/main.py'],
    retrieved_files: ['services/llm_service/main.py'],
    correctness: 'correct',
    answer_summary: 'Correctly identified llm_service/main.py, the OLLAMA_BASE_URL environment variable, and the /api/generate endpoint.',
    missing: [],
    note: 'Direct single-service question answered correctly.',
  },
  {
    id: 'R04',
    question: 'How is a stale FAISS index detected and what triggers a rebuild?',
    expected_files: ['services/retrieval_service/main.py', 'services/data_service/main.py', 'services/app_service/main.py'],
    retrieved_files: ['services/retrieval_service/main.py', 'services/data_service/main.py'],
    correctness: 'correct',
    answer_summary: 'Correctly described the version counter in data_service, the ensure_fresh_index() call in retrieval_service comparing indexed_version vs current version, and both the lazy (per-query) and eager (/reindex) rebuild paths.',
    missing: [],
    note: 'Multi-file question answered well — both services correctly identified.',
  },
  {
    id: 'R05',
    question: 'What happens if the LLM Service becomes unavailable during /ask?',
    expected_files: ['services/app_service/main.py'],
    retrieved_files: ['services/app_service/main.py', 'services/common/prompts.py'],
    correctness: 'correct',
    answer_summary: 'Correctly described the try/except HTTPException around the LLM call in application_service(), the answer=None path, the ollama_error field in the response, and that retrieval results are still returned.',
    missing: [],
    note: 'Fault-tolerance pattern correctly identified from app_service main.py.',
  },
  {
    id: 'R06',
    question: 'What changes would be required to replace the MiniLM embedding model?',
    expected_files: ['services/retrieval_service/main.py', 'docker-compose.yml', 'services/retrieval_service/Dockerfile'],
    retrieved_files: ['services/retrieval_service/main.py'],
    correctness: 'partial',
    answer_summary: 'Correctly identified the EMBEDDING_MODEL env var and SentenceTransformer initialisation in retrieval_service. Did not mention Dockerfile bake-in or dimension change implications for FAISS.',
    missing: ['services/retrieval_service/Dockerfile (model bake-in)', 'EMBEDDING_DIMENSION constant update'],
    note: 'Partial: identified the code change point but missed Docker/dimension implications.',
  },
  {
    id: 'R07',
    question: 'What happens internally during POST /ask/debug?',
    expected_files: ['services/app_service/main.py', 'services/common/prompts.py', 'services/retrieval_service/main.py'],
    retrieved_files: ['services/app_service/main.py', 'services/common/prompts.py'],
    correctness: 'correct',
    answer_summary: 'Correctly described all 4 trace steps (embed, retrieve, build_prompt, generate), the Trace class recording, intermediate values returned (embedding preview, chunks, distances, context, prompt), and graceful LLM fallback.',
    missing: [],
    note: 'Comprehensive answer correctly describing the debug endpoint behaviour.',
  },
  {
    id: 'R08',
    question: 'Which service owns document storage and what file types does it support?',
    expected_files: ['services/data_service/main.py'],
    retrieved_files: ['services/data_service/main.py'],
    correctness: 'correct',
    answer_summary: 'Correctly identified the Data Service (data_service/main.py), the SUPPORTED_EXTENSIONS set (.txt, .md, .pdf, .docx), KB_DIR and UPLOAD_DIR, and the text extraction functions.',
    missing: [],
    note: 'Direct single-service question answered correctly.',
  },
  {
    id: 'R09',
    question: 'What changes would be required to replace Ollama with a different LLM runtime?',
    expected_files: ['services/llm_service/main.py', 'docker-compose.yml'],
    retrieved_files: ['services/llm_service/main.py'],
    correctness: 'partial',
    answer_summary: 'Correctly identified that only llm_service/main.py needs to change (the architecture comment "swapping Ollama for another backend means editing one file" was retrieved). Did not mention docker-compose.yml environment variable changes.',
    missing: ['docker-compose.yml (OLLAMA_URL, ollama service removal)'],
    note: 'Core insight correct; missed Docker configuration implications.',
  },
  {
    id: 'R10',
    question: 'When a document is uploaded, how does the vector index get updated?',
    expected_files: ['services/app_service/main.py', 'services/data_service/main.py', 'services/retrieval_service/main.py'],
    retrieved_files: ['services/app_service/main.py', 'services/data_service/main.py', 'services/retrieval_service/main.py'],
    correctness: 'correct',
    answer_summary: 'Correctly traced the full flow: /kb/upload → Data Service POST /documents (increments _version) → App Service calls _trigger_reindex() → Retrieval Service POST /reindex → rebuild_index() pulls chunks and re-embeds.',
    missing: [],
    note: 'Three-service flow correctly described end-to-end.',
  },
]

const CORRECTNESS_STYLES = {
  correct:   { cls: 'border-green-500/30 bg-green-500/10 text-green-300', label: '✓ Correct' },
  partial:   { cls: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300', label: '~ Partial' },
  incorrect: { cls: 'border-red-500/30 bg-red-500/10 text-red-300', label: '✗ Incorrect' },
}

// Pre-built repo questions for live querying
const REPO_QUESTIONS = [
  'What happens when POST /ask is called?',
  'Which component creates the text embeddings?',
  'Which service communicates with Ollama?',
  'How is a stale FAISS index detected?',
  'What happens if the LLM service is unavailable?',
  'When is the FAISS index rebuilt?',
]

export default function RepositoryAnalysis() {
  const [activeResult, setActiveResult] = useState('R01')
  const [liveQuestion, setLiveQuestion] = useState('')
  const [liveModel, setLiveModel] = useState('codellama:latest')
  const [liveLoading, setLiveLoading] = useState(false)
  const [liveResult, setLiveResult] = useState(null)
  const [liveError, setLiveError] = useState(null)
  const [tab, setTab] = useState('recorded')

  const r = RECORDED_RESULTS.find(x => x.id === activeResult)

  const correctCount = RECORDED_RESULTS.filter(r => r.correctness === 'correct').length
  const partialCount = RECORDED_RESULTS.filter(r => r.correctness === 'partial').length

  async function handleLiveAsk(e) {
    e.preventDefault()
    if (!liveQuestion.trim()) return
    setLiveLoading(true)
    setLiveResult(null)
    setLiveError(null)
    try {
      const res = await fetch(`${BASE}/playground/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: liveQuestion, model: liveModel }),
        signal: AbortSignal.timeout(300_000),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setLiveResult(await res.json())
    } catch (e) {
      setLiveError(e.message)
    } finally {
      setLiveLoading(false)
    }
  }

  return (
    <Section
      id="repository-analysis"
      eyebrow="Part D — Week 4 · Exercise 6"
      title="💻 Repository Analysis"
      description="Testing whether the RAG system can answer questions requiring multi-file codebase understanding."
    >
      {/* ── Summary stats ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="panel p-3 text-center">
          <p className="text-2xl font-bold text-[#34d399]">{correctCount}/10</p>
          <p className="text-[11.5px] text-[#a5b0bd] mt-0.5">Correct answers</p>
        </div>
        <div className="panel p-3 text-center">
          <p className="text-2xl font-bold text-yellow-400">{partialCount}/10</p>
          <p className="text-[11.5px] text-[#a5b0bd] mt-0.5">Partial answers</p>
        </div>
        <div className="panel p-3 text-center">
          <p className="text-2xl font-bold text-[#818cf8]">llama3.2</p>
          <p className="text-[11.5px] text-[#a5b0bd] mt-0.5">Model used</p>
        </div>
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────────── */}
      <div className="flex gap-1 mb-5">
        {[{ id: 'recorded', label: 'Recorded Results' }, { id: 'live', label: 'Live Query' }].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-colors ${
              tab === t.id
                ? 'bg-[rgba(99,102,241,0.15)] text-[#818cf8] border border-[rgba(99,102,241,0.3)]'
                : 'text-[#6b7683] hover:text-[#a5b0bd] border border-transparent hover:bg-white/[0.04]'
            }`}
          >{t.label}</button>
        ))}
      </div>

      {tab === 'recorded' && (
        <div className="flex flex-col lg:flex-row gap-4">
          {/* Question list */}
          <div className="lg:w-56 shrink-0 space-y-1.5">
            {RECORDED_RESULTS.map(res => {
              const cs = CORRECTNESS_STYLES[res.correctness]
              return (
                <button key={res.id} onClick={() => setActiveResult(res.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg border text-[12px] transition-colors
                    ${activeResult === res.id
                      ? 'border-[rgba(99,102,241,0.3)] bg-[rgba(99,102,241,0.08)] text-[#818cf8]'
                      : 'border-white/[0.06] bg-white/[0.02] text-[#6b7683] hover:border-white/[0.12] hover:text-[#a5b0bd]'
                    }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono font-semibold">{res.id}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${cs.cls}`}>{cs.label}</span>
                  </div>
                  <p className="mt-1 leading-snug line-clamp-2 text-[11px]">{res.question}</p>
                </button>
              )
            })}
          </div>

          {/* Detail */}
          {r && (
            <div className="flex-1 space-y-3 min-w-0">
              <div className="panel p-4">
                <div className="flex items-start justify-between gap-2 mb-3">
                  <p className="text-[13.5px] font-semibold text-[#f1f5f9]">"{r.question}"</p>
                  <span className={`text-[11.5px] px-2 py-0.5 rounded border font-medium shrink-0 ${CORRECTNESS_STYLES[r.correctness].cls}`}>
                    {CORRECTNESS_STYLES[r.correctness].label}
                  </span>
                </div>

                <div className="grid sm:grid-cols-2 gap-3 text-[12px]">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-[#6b7683] mb-1.5">Expected Files</p>
                    <div className="space-y-1">
                      {r.expected_files.map(f => (
                        <div key={f} className={`font-mono text-[11px] px-2 py-1 rounded border flex items-center gap-1.5
                          ${r.retrieved_files.includes(f)
                            ? 'border-green-500/20 bg-green-500/5 text-green-300'
                            : 'border-red-500/20 bg-red-500/5 text-red-300'
                          }`}>
                          <span>{r.retrieved_files.includes(f) ? '✓' : '✗'}</span>
                          {f}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-[#6b7683] mb-1.5">Retrieved Files</p>
                    <div className="space-y-1">
                      {r.retrieved_files.map(f => (
                        <div key={f} className="font-mono text-[11px] px-2 py-1 rounded border border-white/[0.08] bg-white/[0.03] text-[#a5b0bd]">
                          {f}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="panel p-4">
                <p className="text-[10px] uppercase tracking-widest text-[#6b7683] mb-2">Answer Summary</p>
                <p className="text-[13px] text-[#f1f5f9] leading-relaxed">{r.answer_summary}</p>
                {r.missing.length > 0 && (
                  <div className="mt-3 p-2.5 rounded border border-yellow-500/20 bg-yellow-500/5">
                    <p className="text-[11px] text-yellow-400 font-semibold mb-1">Missing from answer:</p>
                    {r.missing.map(m => (
                      <p key={m} className="text-[11.5px] text-yellow-300 font-mono">{m}</p>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-[11.5px] text-[#6b7683] italic">{r.note}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'live' && (
        <div className="space-y-4">
          <div className="panel p-4">
            <p className="text-[12.5px] text-[#a5b0bd] mb-3">
              Ask a codebase question live. The same loan-document RAG pipeline will retrieve code chunks and use the selected model to answer.
              This tests whether the system can navigate multi-file architecture.
            </p>
            <form onSubmit={handleLiveAsk} className="space-y-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={liveQuestion}
                  onChange={e => setLiveQuestion(e.target.value)}
                  placeholder="Ask about the codebase structure…"
                  disabled={liveLoading}
                  className="flex-1 min-w-0 bg-[#0a0a0f] border border-white/[0.1] rounded-lg px-4 py-2.5 text-[13px] text-[#f1f5f9] placeholder-[#6b7683] focus:outline-none focus:border-[rgba(99,102,241,0.5)] disabled:opacity-50"
                />
                <button type="submit" disabled={liveLoading || !liveQuestion.trim()} className="btn btn-primary shrink-0">
                  {liveLoading ? 'Asking…' : 'Ask'}
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {REPO_QUESTIONS.map(q => (
                  <button key={q} type="button" onClick={() => setLiveQuestion(q)} disabled={liveLoading}
                    className="text-[11px] px-2 py-1 rounded border border-white/[0.08] text-[#6b7683] hover:text-[#a5b0bd] hover:border-white/[0.16] disabled:opacity-40">
                    {q}
                  </button>
                ))}
              </div>
            </form>
          </div>

          {liveError && (
            <div className="p-3 rounded border border-red-500/30 bg-red-500/8 text-red-300 text-sm">{liveError}</div>
          )}

          {liveLoading && (
            <div className="panel p-6 text-center animate-pulse">
              <p className="text-[#6b7683] text-sm">Querying the codebase RAG pipeline…</p>
            </div>
          )}

          {liveResult && !liveLoading && (
            <div className="space-y-3">
              <div className="panel p-4">
                <p className="text-[11px] uppercase tracking-widest text-[#6b7683] mb-2">Retrieved Sources</p>
                <div className="flex flex-wrap gap-1.5">
                  {liveResult.sources?.map(s => (
                    <span key={s} className="font-mono text-[11.5px] px-2 py-1 border border-[#6366f1]/30 bg-[#6366f1]/8 text-[#818cf8] rounded">{s}</span>
                  ))}
                </div>
              </div>
              <div className="panel p-4">
                <p className="text-[11px] uppercase tracking-widest text-[#6b7683] mb-2">Response — {liveResult.model}</p>
                <p className="text-sm text-[#f1f5f9] leading-relaxed whitespace-pre-wrap">{liveResult.answer}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Limitations ───────────────────────────────────────────────────── */}
      <div className="mt-6 panel p-4">
        <p className="text-[12.5px] font-semibold text-[#f1f5f9] mb-3">Identified Limitations</p>
        <div className="grid sm:grid-cols-2 gap-2 text-[12px]">
          {[
            ['Poor cross-file following', '300-char chunks sever function calls from their callers. The model sees a fragment but not the call chain.'],
            ['Context window cap', '3 chunks × ~300 chars = ~900 chars. Multi-file questions need more context than top_k=3 provides.'],
            ['No semantic code understanding', 'MiniLM was trained on natural language. Variable names and imports score poorly unless they match query words.'],
            ['Chunk boundaries split imports', 'A chunk may contain a function but not its imports, making generated answers incomplete.'],
            ['Retrieval ranking problems', 'Architecture comments in one file often outrank implementation in another because they contain more query keywords.'],
            ['Next stage: Sourcegraph', 'Repository-aware tooling with AST-level navigation and cross-reference indexing would resolve most of these limitations.'],
          ].map(([title, body]) => (
            <div key={title} className="p-2.5 rounded border border-white/[0.06] bg-white/[0.02]">
              <p className="font-semibold text-[#a5b0bd] mb-1">{title}</p>
              <p className="text-[#6b7683] leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}
