import React from 'react'
import { STATIC_KB_INFO } from '../data/staticData'
import Section, { Stat, StatRow } from './ui/Section'

// Deterministic illustrative per-chunk vector previews.
const CHUNK_VECTOR_EXAMPLES = [
  '[0.0234, -0.1821,  0.0917,  0.4421, ...]',
  '[0.1143,  0.0402, -0.2310,  0.1982, ...]',
  '[-0.0712, 0.3101,  0.1554, -0.0880, ...]',
  '[0.2215, -0.0533,  0.3008,  0.0124, ...]',
  '[-0.1444, 0.2771, -0.0990,  0.3315, ...]',
  '[0.0891, -0.1032,  0.1780, -0.2441, ...]',
  '[0.3312,  0.1560, -0.0320,  0.0903, ...]',
  '[-0.0220, 0.4102,  0.0655, -0.1778, ...]',
]

const SEARCH_STEPS = [
  ['Query embedding', 'The question becomes a 384-dimension vector using the same MiniLM model.'],
  ['L2 distance search', 'IndexFlatL2 computes Euclidean distance against every stored vector.'],
  ['Top-k retrieval', 'The 3 nearest chunks — smallest distance — are returned as context.'],
]

export default function VectorDatabase({ kbInfo, backendStatus }) {
  const totalVectors = kbInfo?.total_chunks ?? STATIC_KB_INFO.total_chunks
  const dimension = kbInfo?.embedding_dimension ?? STATIC_KB_INFO.embedding_dimension
  const indexType = kbInfo?.faiss_index_type ?? STATIC_KB_INFO.faiss_index_type
  const online = backendStatus === 'online'

  return (
    <Section
      id="vector-database"
      eyebrow="Stage 04 · Vector store"
      title="FAISS index"
      description="Embeddings are stored in a flat L2 index and searched by nearest-neighbour distance."
    >
      <StatRow cols={4}>
        <Stat label="Database" value="FAISS" />
        <Stat label="Index type" value={indexType} />
        <Stat label="Stored vectors" value={totalVectors} accent live={online} />
        <Stat label="Dimensions" value={dimension} />
      </StatRow>

      <div className="mt-5">
        <div className="flex items-baseline justify-between gap-3 mb-2.5">
          <p className="eyebrow">Chunk to vector</p>
          <p className="text-[11px] text-[#6b7683]">illustrative previews</p>
        </div>
        <div className="code-block">
          {CHUNK_VECTOR_EXAMPLES.slice(0, Math.min(totalVectors, 8)).map((preview, i) => (
            <div key={i} className="flex items-center gap-3 whitespace-nowrap">
              <span className="text-[#6b7683] w-[68px] shrink-0">chunk {String(i + 1).padStart(2, '0')}</span>
              <span className="text-[#6b7683] shrink-0">→</span>
              <span className="text-[#818cf8]">{preview}</span>
            </div>
          ))}
          {totalVectors > 8 && (
            <div className="text-[#6b7683] pt-1">… {totalVectors - 8} more</div>
          )}
        </div>
      </div>

      <ol className="mt-4 grid sm:grid-cols-3 gap-2.5">
        {SEARCH_STEPS.map(([title, body], i) => (
          <li key={title} className="panel p-3.5">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[10px] font-mono text-[#818cf8] tabular">
                {String(i + 1).padStart(2, '0')}
              </span>
              <p className="text-[12.5px] font-medium text-[#f1f5f9]">{title}</p>
            </div>
            <p className="text-[12px] text-[#6b7683] leading-relaxed">{body}</p>
          </li>
        ))}
      </ol>
    </Section>
  )
}
