import React, { useState } from 'react'
import { ILLUSTRATIVE_EMBEDDING_PREVIEW } from '../data/staticData'
import Section from './ui/Section'

const SAMPLE_TEXT =
  'A secured loan is backed by collateral such as a house, car, deposit, or other asset...'

/** One step of the text → model → vector transformation. */
function Stage({ label, children, accent = false }) {
  return (
    <div className={`flex-1 min-w-0 ${accent ? 'panel border-[rgba(99,102,241,0.32)]' : 'panel'} p-3.5`}>
      <p className="eyebrow mb-2">{label}</p>
      {children}
    </div>
  )
}

function Arrow() {
  return (
    <div className="flex items-center justify-center shrink-0 px-1 py-1 sm:py-0">
      <span className="text-[#6366f1] text-sm rotate-90 sm:rotate-0">→</span>
    </div>
  )
}

export default function EmbeddingViewer({ backendStatus, liveEmbedding }) {
  const [expanded, setExpanded] = useState(false)

  const isLive = backendStatus === 'online' && liveEmbedding && liveEmbedding.length > 0
  const preview = isLive ? liveEmbedding : ILLUSTRATIVE_EMBEDDING_PREVIEW
  const first8 = preview.slice(0, 8)
  const last2 = preview.slice(-2)

  return (
    <Section
      id="embeddings"
      eyebrow="Stage 03 · Embeddings"
      title="Text becomes a vector"
      description="Each chunk is encoded into 384 numbers. Text with similar meaning lands close together in that space."
      aside={<span className="chip font-mono">384-dim</span>}
    >
      <div className="flex flex-col sm:flex-row items-stretch gap-2">
        <Stage label="Text chunk">
          <p className="text-[12.5px] text-[#a5b0bd] italic leading-relaxed">"{SAMPLE_TEXT}"</p>
        </Stage>

        <Arrow />

        <Stage label="Model" accent>
          <p className="text-[12.5px] font-mono text-[#818cf8] break-all">all-MiniLM-L6-v2</p>
          <p className="text-[11.5px] text-[#6b7683] mt-1">sentence-transformers</p>
        </Stage>

        <Arrow />

        <Stage label="Vector">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="text-[11px] text-[#6b7683]">first 8 + last 2</span>
            <span className={isLive ? 'chip chip-ok' : 'chip'}>
              {isLive ? 'Live' : 'Illustrative'}
            </span>
          </div>
          <p className="text-[11.5px] text-[#818cf8] font-mono leading-relaxed break-all">
            [{first8.map((v) => v.toFixed(4)).join(', ')}
            <span className="text-[#6b7683]"> … </span>
            {last2.map((v) => v.toFixed(4)).join(', ')}]
          </p>
        </Stage>
      </div>

      <button onClick={() => setExpanded(!expanded)} className="btn btn-ghost mt-3 text-[12px]">
        {expanded ? 'Hide values' : 'Show the 10 preview values'}
      </button>

      {expanded && (
        <div className="panel p-3.5 mt-2 rise">
          <div className="grid grid-cols-5 gap-1.5">
            {[...first8, ...last2].map((v, i) => (
              <span
                key={i}
                className="text-[11px] font-mono tabular text-[#818cf8] bg-white/[0.04] rounded px-1.5 py-1 text-center"
              >
                {v.toFixed(4)}
              </span>
            ))}
          </div>
          <p className="text-[11.5px] text-[#6b7683] mt-2.5">
            {isLive
              ? 'Real values returned by the backend for the last question asked.'
              : 'Illustrative values. Ask a question with the backend running to see real ones.'}
          </p>
        </div>
      )}

      <p className="text-[12.5px] text-[#a5b0bd] leading-relaxed mt-4 pt-4 border-t border-white/[0.07]">
        <span className="text-[#f1f5f9] font-medium">Why this matters.</span> "Secured loan" and
        "collateral-backed borrowing" share almost no words but produce vectors a short distance
        apart, which is how FAISS finds the right chunk when the wording differs.
      </p>
    </Section>
  )
}
