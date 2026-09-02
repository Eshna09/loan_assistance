import React from 'react'
import Section from './ui/Section'

const STEPS = [
  ['Load trusted loan documents', '6 loan-focused .txt files'],
  ['Split documents into overlapping chunks', 'chunk_size=300, overlap=50'],
  ['Generate 384-dimension MiniLM embeddings', 'sentence-transformers/all-MiniLM-L6-v2'],
  ['Store embeddings in FAISS', 'IndexFlatL2, 384-dim vectors'],
  ['Convert the user query into an embedding', 'Same model, same vector space'],
  ['Retrieve the top-3 relevant chunks', 'FAISS L2 nearest-neighbour search'],
  ['Build a context-grounded prompt', '"Answer ONLY using the provided context"'],
  ['Send the prompt to Code Llama', 'POST /api/generate via Ollama'],
  ['Answer using only retrieved context', 'Otherwise: "not available in my knowledge base"'],
  ['Return the response through the API', 'FastAPI /ask → JSON'],
]

export default function PipelineSummary({ backendStatus }) {
  const online = backendStatus === 'online'

  return (
    <Section
      id="pipeline-summary"
      eyebrow="Recap"
      title="The complete pipeline"
      description="Every stage from document loading to API response."
      aside={
        <span className={online ? 'chip chip-ok' : 'chip'}>
          {online ? 'All stages verified' : 'Backend offline'}
        </span>
      }
    >
      <ol className="relative flex flex-col gap-0.5">
        {/* Connector sits behind the markers rather than between list items. */}
        <span
          aria-hidden="true"
          className="absolute left-[11px] top-4 bottom-4 w-px bg-white/[0.08]"
        />
        {STEPS.map(([text, detail], i) => (
          <li key={i} className="relative flex items-start gap-3.5 py-2">
            <span
              className={`relative z-10 mt-0.5 w-[23px] h-[23px] rounded-full flex items-center justify-center text-[10px] font-semibold tabular shrink-0 border ${
                online
                  ? 'border-[rgba(52,211,153,0.35)] bg-[rgba(52,211,153,0.12)] text-[#34d399]'
                  : 'border-white/10 bg-[#12121a] text-[#6b7683]'
              }`}
            >
              {online ? '✓' : i + 1}
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-[13.5px] text-[#f1f5f9] leading-snug">{text}</p>
              <p className="text-[11.5px] text-[#6b7683] font-mono mt-0.5 break-words">{detail}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-5 panel p-4">
        <p className="text-[13px] font-medium text-[#f1f5f9] mb-1">
          Why RAG rather than a plain LLM?
        </p>
        <p className="text-[12.5px] text-[#a5b0bd] leading-relaxed">
          An ungrounded model can state lending facts it was never given. Grounding every answer in
          retrieved documents constrains the assistant to what the knowledge base actually contains —
          and lets it say plainly when a question falls outside it.
        </p>
      </div>
    </Section>
  )
}
