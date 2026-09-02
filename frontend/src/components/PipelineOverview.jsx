import React, { useState } from 'react'
import Section from './ui/Section'

// The stages are a real sequence, so they are numbered. Colour is not used to
// distinguish them — eight accent hues competing was most of the visual noise.
const STAGES = [
  {
    id: 'documents',
    label: 'Documents',
    description: 'Six educational loan text files form the trusted knowledge base.',
    detail: 'loans · types · interest · repayment · eligibility · risks',
    section: 'knowledge-base',
  },
  {
    id: 'chunking',
    label: 'Chunking',
    description: 'Each document is split by a sliding window into overlapping pieces.',
    detail: 'chunk_size=300, overlap=50',
    section: 'chunking',
  },
  {
    id: 'embeddings',
    label: 'Embeddings',
    description: 'Every chunk is encoded into a 384-dimension float vector by MiniLM.',
    detail: 'sentence-transformers/all-MiniLM-L6-v2',
    section: 'embeddings',
  },
  {
    id: 'faiss',
    label: 'FAISS',
    description: 'Vectors are stored in a flat index for L2 nearest-neighbour search.',
    detail: 'IndexFlatL2 · 384 dimensions',
    section: 'vector-database',
  },
  {
    id: 'retrieval',
    label: 'Retrieval',
    description: 'The query is embedded and the three closest chunks are returned.',
    detail: 'top_k=3 · ranked by L2 distance',
    section: 'rag-demo',
  },
  {
    id: 'rag-prompt',
    label: 'Prompt',
    description: 'Retrieved chunks are assembled into a context block inside a strict template.',
    detail: '"Answer ONLY using the provided context."',
    section: 'rag-demo',
  },
  {
    id: 'code-llama',
    label: 'Code Llama',
    description: 'The prompt is sent to Code Llama running locally through Ollama.',
    detail: 'codellama:7b · Ollama · :11434',
    section: 'rag-demo',
  },
  {
    id: 'answer',
    label: 'Answer',
    description: 'The model returns an answer derived solely from the retrieved context.',
    detail: 'Out of scope → "not available in my knowledge base"',
    section: 'rag-demo',
  },
]

export default function PipelineOverview() {
  const [selected, setSelected] = useState(null)

  function handleClick(stage) {
    const next = selected?.id === stage.id ? null : stage
    setSelected(next)
    if (next) {
      document.getElementById(stage.section)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <Section
      id="pipeline-overview"
      eyebrow="Overview"
      title="Documents to answer, in eight stages"
      description="Select a stage for detail and to jump to its section."
    >
      <ol className="flex items-stretch gap-1 overflow-x-auto pb-1 -mx-1 px-1">
        {STAGES.map((stage, i) => {
          const active = selected?.id === stage.id
          return (
            <React.Fragment key={stage.id}>
              <li className="shrink-0">
                <button
                  onClick={() => handleClick(stage)}
                  aria-pressed={active}
                  className={`h-full flex flex-col items-start gap-1 px-3 py-2.5 rounded-lg border text-left transition-colors ${
                    active
                      ? 'border-[rgba(99,102,241,0.45)] bg-[rgba(99,102,241,0.12)]'
                      : 'border-white/[0.08] bg-white/[0.03] hover:border-white/[0.16]'
                  }`}
                >
                  <span
                    className={`text-[10px] font-mono tabular ${
                      active ? 'text-[#818cf8]' : 'text-[#6b7683]'
                    }`}
                  >
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span
                    className={`text-[12.5px] font-medium whitespace-nowrap ${
                      active ? 'text-[#f1f5f9]' : 'text-[#a5b0bd]'
                    }`}
                  >
                    {stage.label}
                  </span>
                </button>
              </li>
              {i < STAGES.length - 1 && (
                <li aria-hidden="true" className="flex items-center shrink-0">
                  <span className="text-white/15 text-[11px]">→</span>
                </li>
              )}
            </React.Fragment>
          )
        })}
      </ol>

      {selected && (
        <div className="panel p-4 mt-3 rise border-[rgba(99,102,241,0.28)]">
          <p className="eyebrow eyebrow-accent mb-1.5">
            Stage {String(STAGES.findIndex((s) => s.id === selected.id) + 1).padStart(2, '0')} ·{' '}
            {selected.label}
          </p>
          <p className="text-[13.5px] text-[#f1f5f9] leading-relaxed">{selected.description}</p>
          <p className="text-[11.5px] text-[#6b7683] font-mono mt-1.5 break-words">
            {selected.detail}
          </p>
        </div>
      )}
    </Section>
  )
}
