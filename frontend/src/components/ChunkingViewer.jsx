import React, { useMemo, useState } from 'react'
import { STATIC_KB_INFO } from '../data/staticData'
import Section from './ui/Section'

const CHUNK_SIZE = 300
const OVERLAP = 50
const PREVIEW_COUNT = 3

function computeChunks(text) {
  const chunks = []
  let start = 0
  while (start < text.length) {
    chunks.push({ text: text.slice(start, start + CHUNK_SIZE), start })
    start += CHUNK_SIZE - OVERLAP
  }
  return chunks
}

function ChunkCard({ chunk, index, totalChunks }) {
  // The overlapping part is the last OVERLAP characters of this chunk, which
  // are also the first OVERLAP characters of the next one.
  const overlapStart = Math.max(0, chunk.text.length - OVERLAP)
  const head = chunk.text.slice(0, overlapStart)
  const tail = chunk.text.slice(overlapStart)
  const isLast = index === totalChunks - 1

  return (
    <div className="panel p-3.5">
      <div className="flex items-center gap-2.5 mb-2">
        <span className="text-[10.5px] font-mono font-semibold text-[#818cf8] tabular">
          CHUNK {String(index + 1).padStart(2, '0')}
        </span>
        <span className="text-[11px] text-[#6b7683] tabular">{chunk.text.length} chars</span>
        {!isLast && (
          <span className="text-[11px] text-[#6b7683] ml-auto">
            last {OVERLAP} repeat in chunk {index + 2}
          </span>
        )}
      </div>
      <p className="text-[12px] text-[#a5b0bd] font-mono leading-relaxed break-words">
        {isLast ? (
          chunk.text
        ) : (
          <>
            {head}
            <mark className="overlap-highlight text-[#c7d2fe]">{tail}</mark>
          </>
        )}
      </p>
    </div>
  )
}

export default function ChunkingViewer({ kbInfo }) {
  const [selectedDoc, setSelectedDoc] = useState('loans.txt')
  const [showAll, setShowAll] = useState(false)

  const docList = kbInfo?.documents || STATIC_KB_INFO.documents
  const docData = docList.find((d) => d.filename === selectedDoc) || docList[0]
  const chunks = useMemo(() => computeChunks(docData.full_text), [docData])
  const visible = showAll ? chunks : chunks.slice(0, PREVIEW_COUNT)

  return (
    <Section
      id="chunking"
      eyebrow="Stage 02 · Chunking"
      title="Documents become overlapping pieces"
      description="A sliding window splits each document so a sentence spanning a boundary is still retrievable from either side."
      aside={<span className="chip font-mono">300 / 50</span>}
    >
      <div className="flex flex-wrap gap-2 mb-4">
        <span className="chip">
          Chunk size <span className="text-[#f1f5f9] font-mono tabular">{CHUNK_SIZE}</span>
        </span>
        <span className="chip">
          Overlap <span className="text-[#f1f5f9] font-mono tabular">{OVERLAP}</span>
        </span>
        <span className="chip chip-accent">
          <span className="font-mono tabular">{chunks.length}</span> chunks in this document
        </span>
      </div>

      <p className="eyebrow mb-2">Document</p>
      <div className="flex flex-wrap gap-1.5 mb-4">
        {docList.map((d) => (
          <button
            key={d.filename}
            onClick={() => {
              setSelectedDoc(d.filename)
              setShowAll(false)
            }}
            aria-pressed={selectedDoc === d.filename}
            className={`text-[11.5px] font-mono px-2.5 py-1.5 rounded-md border transition-colors ${
              selectedDoc === d.filename
                ? 'border-[rgba(99,102,241,0.4)] bg-[rgba(99,102,241,0.12)] text-[#818cf8]'
                : 'border-white/[0.08] bg-white/[0.03] text-[#6b7683] hover:text-[#a5b0bd] hover:border-white/[0.14]'
            }`}
          >
            {d.filename}
          </button>
        ))}
      </div>

      <details className="mb-4 group">
        <summary className="eyebrow cursor-pointer list-none flex items-center gap-2 select-none">
          <span className="text-[#6b7683] transition-transform group-open:rotate-90">▸</span>
          Original document · {docData.full_text.length} characters
        </summary>
        <div className="code-block mt-2">{docData.full_text}</div>
      </details>

      <div className="flex flex-col gap-2">
        {visible.map((chunk, i) => (
          <ChunkCard key={i} chunk={chunk} index={i} totalChunks={chunks.length} />
        ))}
      </div>

      {chunks.length > PREVIEW_COUNT && (
        <button onClick={() => setShowAll(!showAll)} className="btn btn-ghost mt-2.5 text-[12px]">
          {showAll ? 'Show fewer' : `Show all ${chunks.length} chunks`}
        </button>
      )}

      <p className="text-[12.5px] text-[#a5b0bd] leading-relaxed mt-4 pt-4 border-t border-white/[0.07]">
        <span className="text-[#f1f5f9] font-medium">Why overlap?</span> The highlighted tail of each
        chunk repeats at the start of the next one, so a sentence cut in half by a boundary still
        appears whole in one of them.
      </p>
    </Section>
  )
}
