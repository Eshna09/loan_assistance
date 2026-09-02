/**
 * SourceGraph.jsx
 * Answer provenance graph — where the answer actually came from.
 *
 *     question ──retrieved──► chunk ──belongs_to──► document
 *
 * plus the two document-level relations the evidence layer computes:
 * `conflict` (two sources disagree on the same field) and `supersedes`
 * (version resolution picked a winner).
 *
 * The backend returns nodes and edges only; every coordinate here is computed
 * locally in a deterministic layered layout, drawn as inline SVG. No graph
 * library, matching the hand-built diagrams in ServiceArchitecture and
 * ApiArchitecture.
 *
 * Two things the graph shows that the Evidence list cannot:
 *   - which retrieved chunks the LLM never saw (dimmed, dashed)
 *   - how much of the answer each source accounts for (the overlap bar),
 *     which is often nothing like the retrieval ranking
 */
import React, { useMemo, useState } from 'react'

// ── Layout constants ───────────────────────────────────────────────────────
const PAD_X = 30
const Q_BOX = { w: 320, h: 48, y: 12 }
const CHUNK_BOX = { w: 92, h: 64, y: 154, gap: 14 }
const DOC_BOX = { w: 146, h: 60, y: 322, gap: 18 }
const ARC_SPACE = 84 // room under the document row for conflict / supersedes arcs

const COLOR = {
  accent: '#818cf8',
  accentDim: 'rgba(99, 102, 241, 0.30)',
  ok: '#34d399',
  warn: '#fbbf24',
  bad: '#f87171',
  text: '#f1f5f9',
  dim: '#6b7683',
  line: 'rgba(255, 255, 255, 0.16)',
  panel: '#0a0a0f',
}

// ── Helpers ────────────────────────────────────────────────────────────────
/** Rough character budget for a box of `px` width at `size` px font. */
function fit(text, px, size = 10) {
  const max = Math.max(3, Math.floor(px / (size * 0.58)))
  const s = String(text ?? '')
  return s.length <= max ? s : s.slice(0, max - 1) + '…'
}

function pct(v) {
  return v == null ? '—' : `${Math.round(v * 100)}%`
}

/** Cubic bezier that leaves the source downward and enters the target downward. */
function vBezier(x1, y1, x2, y2) {
  const dy = (y2 - y1) * 0.55
  return `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`
}

/** Arc hanging below two document boxes, used for conflict / supersedes. */
function underArc(x1, y1, x2, y2, drop) {
  const mx = (x1 + x2) / 2
  return `M ${x1} ${y1} Q ${mx} ${Math.max(y1, y2) + drop}, ${x2} ${y2}`
}

// ── Layout ─────────────────────────────────────────────────────────────────
function useLayout(graph) {
  return useMemo(() => {
    if (!graph?.nodes?.length) return null

    const chunks = graph.nodes.filter(n => n.type === 'chunk')
    const docs = graph.nodes.filter(n => n.type === 'document')

    const chunkRow = chunks.length * CHUNK_BOX.w + Math.max(0, chunks.length - 1) * CHUNK_BOX.gap
    const docRow = docs.length * DOC_BOX.w + Math.max(0, docs.length - 1) * DOC_BOX.gap
    const inner = Math.max(chunkRow, docRow, Q_BOX.w, 360)
    const width = inner + PAD_X * 2

    const hasArcs = graph.edges.some(e => e.type === 'conflict' || e.type === 'supersedes')
    const height = DOC_BOX.y + DOC_BOX.h + (hasArcs ? ARC_SPACE : 24)

    const pos = {}

    pos.q = {
      x: width / 2 - Q_BOX.w / 2, y: Q_BOX.y, w: Q_BOX.w, h: Q_BOX.h,
      cx: width / 2, cy: Q_BOX.y + Q_BOX.h / 2,
    }

    const chunkStart = width / 2 - chunkRow / 2
    chunks.forEach((n, i) => {
      const x = chunkStart + i * (CHUNK_BOX.w + CHUNK_BOX.gap)
      pos[n.id] = {
        x, y: CHUNK_BOX.y, w: CHUNK_BOX.w, h: CHUNK_BOX.h,
        cx: x + CHUNK_BOX.w / 2, cy: CHUNK_BOX.y + CHUNK_BOX.h / 2,
      }
    })

    const docStart = width / 2 - docRow / 2
    docs.forEach((n, i) => {
      const x = docStart + i * (DOC_BOX.w + DOC_BOX.gap)
      pos[n.id] = {
        x, y: DOC_BOX.y, w: DOC_BOX.w, h: DOC_BOX.h,
        cx: x + DOC_BOX.w / 2, cy: DOC_BOX.y + DOC_BOX.h / 2,
      }
    })

    // Stroke width comes from a min-max rescale of similarity across this
    // result set. The raw values sit in a narrow band (e.g. 0.46–0.54), so
    // without rescaling every edge would look identical.
    const sims = chunks.map(c => c.similarity ?? 0)
    const lo = Math.min(...sims)
    const hi = Math.max(...sims)
    const spread = (s) => (hi - lo < 1e-9 ? 1 : (s - lo) / (hi - lo))

    return { width, height, pos, chunks, docs, spread, hasArcs }
  }, [graph])
}

/** Which nodes and edges stay lit when `activeId` is focused. */
function relatedTo(activeId, graph) {
  if (!activeId) return null
  const nodes = new Set([activeId])
  const edges = new Set()

  for (const e of graph.edges) {
    if (e.source === activeId || e.target === activeId) {
      edges.add(e.id)
      nodes.add(e.source)
      nodes.add(e.target)
    }
  }
  // A document lights up the chunks that feed it, and through them the
  // question, so selecting a source shows its whole path.
  if (activeId.startsWith('doc:')) {
    for (const e of graph.edges) {
      if (e.type === 'belongs_to' && e.target === activeId) {
        nodes.add(e.source)
        edges.add(e.id)
        for (const q of graph.edges) {
          if (q.type === 'retrieved' && q.target === e.source) {
            edges.add(q.id)
            nodes.add(q.source)
          }
        }
      }
    }
  }
  // The question lights the whole graph — dimming everything else would be
  // the same as dimming nothing.
  if (activeId === 'q') {
    graph.nodes.forEach(n => nodes.add(n.id))
    graph.edges.forEach(e => edges.add(e.id))
  }
  return { nodes, edges }
}

// ── Node renderers ─────────────────────────────────────────────────────────
function QuestionNode({ p, node, faded, onEnter, onLeave, onClick }) {
  return (
    <g
      opacity={faded ? 0.2 : 1}
      style={{ cursor: 'pointer', transition: 'opacity 140ms' }}
      onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onClick}
    >
      <title>{node.label}</title>
      <rect
        x={p.x} y={p.y} width={p.w} height={p.h} rx={9}
        fill="rgba(99, 102, 241, 0.12)" stroke={COLOR.accent} strokeWidth={1.2}
      />
      <text x={p.cx} y={p.y + 19} textAnchor="middle" fontSize={9}
            fill={COLOR.accent} letterSpacing="0.08em" fontWeight="600">
        QUESTION
      </text>
      <text x={p.cx} y={p.y + 34} textAnchor="middle" fontSize={10.5} fill={COLOR.text}>
        {fit(node.label, p.w - 20, 10.5)}
      </text>
    </g>
  )
}

function ChunkNode({ p, node, faded, onEnter, onLeave, onClick }) {
  const used = node.used_by_llm
  const overlap = node.answer_overlap ?? 0
  const barW = (p.w - 16) * Math.min(overlap, 1)
  const barColor = overlap >= 0.5 ? COLOR.ok : overlap >= 0.2 ? COLOR.warn : COLOR.dim

  return (
    <g
      opacity={faded ? 0.16 : 1}
      style={{ cursor: 'pointer', transition: 'opacity 140ms' }}
      onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onClick}
    >
      <title>
        {`Rank ${node.rank} · ${node.source}\nL2 ${node.distance} · ${used ? 'sent to LLM' : 'retrieved, not sent'}\nAnswer overlap ${pct(node.answer_overlap)}`}
      </title>
      <rect
        x={p.x} y={p.y} width={p.w} height={p.h} rx={8}
        fill={used ? 'rgba(99, 102, 241, 0.10)' : 'rgba(255, 255, 255, 0.025)'}
        stroke={used ? COLOR.accent : COLOR.line}
        strokeWidth={used ? 1.2 : 1}
        strokeDasharray={used ? undefined : '3 3'}
      />
      <text x={p.cx} y={p.y + 16} textAnchor="middle" fontSize={10.5}
            fontWeight="700" fill={used ? COLOR.accent : COLOR.dim}>
        #{node.rank}
      </text>
      <text x={p.cx} y={p.y + 30} textAnchor="middle" fontSize={9}
            fill={COLOR.dim} fontFamily="ui-monospace, monospace">
        L2 {Number(node.distance).toFixed(3)}
      </text>
      {/* answer-overlap bar */}
      <rect x={p.x + 8} y={p.y + 38} width={p.w - 16} height={4} rx={2}
            fill="rgba(255, 255, 255, 0.09)" />
      <rect x={p.x + 8} y={p.y + 38} width={barW} height={4} rx={2} fill={barColor} />
      <text x={p.cx} y={p.y + 55} textAnchor="middle" fontSize={8.5}
            fill={barColor} fontFamily="ui-monospace, monospace">
        {pct(node.answer_overlap)}
      </text>
    </g>
  )
}

function DocumentNode({ p, node, faded, onEnter, onLeave, onClick }) {
  const stroke = node.in_conflict ? COLOR.bad
    : node.superseded ? COLOR.warn
    : node.authoritative ? COLOR.ok
    : node.used_by_llm ? 'rgba(52, 211, 153, 0.45)'
    : COLOR.line
  const overlap = node.answer_overlap ?? 0
  const barColor = overlap >= 0.5 ? COLOR.ok : overlap >= 0.2 ? COLOR.warn : COLOR.dim

  return (
    <g
      opacity={faded ? 0.16 : 1}
      style={{ cursor: 'pointer', transition: 'opacity 140ms' }}
      onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onClick}
    >
      <title>
        {`${node.source}\n${node.chunk_count} chunk(s) retrieved · best rank ${node.best_rank}\nAnswer overlap ${pct(node.answer_overlap)}`}
      </title>
      <rect
        x={p.x} y={p.y} width={p.w} height={p.h} rx={8}
        fill={node.used_by_llm ? 'rgba(52, 211, 153, 0.06)' : 'rgba(255, 255, 255, 0.025)'}
        stroke={stroke} strokeWidth={node.authoritative || node.in_conflict ? 1.5 : 1}
        strokeDasharray={node.used_by_llm ? undefined : '3 3'}
      />
      <text x={p.cx} y={p.y + 17} textAnchor="middle" fontSize={10}
            fill={COLOR.text} fontFamily="ui-monospace, monospace">
        {fit(node.label, p.w - 14, 10)}
      </text>
      <text x={p.cx} y={p.y + 30} textAnchor="middle" fontSize={8.5} fill={COLOR.dim}>
        {node.chunk_count} chunk{node.chunk_count !== 1 ? 's' : ''} · v{node.version}
        {node.used_by_llm ? '' : ' · unused'}
      </text>
      <rect x={p.x + 10} y={p.y + 38} width={p.w - 20} height={4} rx={2}
            fill="rgba(255, 255, 255, 0.09)" />
      <rect x={p.x + 10} y={p.y + 38} width={(p.w - 20) * Math.min(overlap, 1)} height={4}
            rx={2} fill={barColor} />
      <text x={p.cx} y={p.y + 52} textAnchor="middle" fontSize={8.5}
            fill={barColor} fontFamily="ui-monospace, monospace">
        {pct(node.answer_overlap)} of answer
      </text>
    </g>
  )
}

// ── Detail card ────────────────────────────────────────────────────────────
function Row({ k, v, tone }) {
  if (v == null || v === '') return null
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[10px] uppercase tracking-wider text-[#6b7683] w-[104px] shrink-0">{k}</span>
      <span className={`text-[11.5px] font-mono ${tone || 'text-[#f1f5f9]'}`}>{v}</span>
    </div>
  )
}

function DetailCard({ node, graph }) {
  if (!node) return null

  const conflicts = graph.edges.filter(
    e => e.type === 'conflict' && (e.source === node.id || e.target === node.id)
  )

  return (
    <div className="mt-3 bg-[#0a0a0f] border border-white/[0.08] rounded-lg p-3 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <span className="text-[11px] font-semibold text-[#818cf8] uppercase tracking-wider">
          {node.type}
        </span>
        <span className="text-[12px] font-mono text-[#f1f5f9]">
          {node.type === 'question' ? 'user query' : node.label}
        </span>
      </div>

      {node.type === 'question' && (
        <>
          <p className="text-[11.5px] text-[#a5b0bd] italic leading-relaxed">"{node.label}"</p>
          <Row k="Retrieved" v={`${node.retrieved_count} chunks`} />
          <Row k="Sent to LLM" v={`${node.used_by_llm_count} chunks`} />
        </>
      )}

      {node.type === 'chunk' && (
        <>
          <Row k="Rank" v={`#${node.rank}`} />
          <Row k="Source" v={node.source} />
          <Row k="L2 distance" v={Number(node.distance).toFixed(4)} tone="text-yellow-400" />
          <Row k="Similarity" v={Number(node.similarity).toFixed(4)} />
          <Row
            k="Sent to LLM"
            v={node.used_by_llm ? 'yes' : 'no — retrieved only'}
            tone={node.used_by_llm ? 'text-[#34d399]' : 'text-[#6b7683]'}
          />
          <Row k="Answer overlap" v={pct(node.answer_overlap)} />
          <Row k="Characters" v={node.characters} />
          <p className="text-[11px] text-[#6b7683] italic leading-relaxed pt-1.5 border-t border-white/[0.06] mt-2">
            "{node.text_preview}{node.truncated ? '…' : ''}"
          </p>
        </>
      )}

      {node.type === 'document' && (
        <>
          <Row k="Chunks here" v={`${node.chunk_count} (ranks ${node.ranks.join(', ')})`} />
          <Row k="Best rank" v={`#${node.best_rank} · L2 ${Number(node.best_distance).toFixed(4)}`} />
          <Row k="Answer overlap" v={pct(node.answer_overlap)} />
          <Row k="Version" v={`v${node.version}`} />
          <Row k="Effective date" v={node.effective_date} />
          <Row k="Loan type" v={node.loan_type !== 'general' ? node.loan_type : null} />
          <Row
            k="Reached LLM"
            v={node.used_by_llm ? 'yes' : 'no — outside top-k'}
            tone={node.used_by_llm ? 'text-[#34d399]' : 'text-[#6b7683]'}
          />
          {node.authoritative && (
            <Row k="Resolution" v="authoritative source" tone="text-[#34d399]" />
          )}
          {node.superseded && (
            <Row k="Resolution" v="superseded on a conflicting field" tone="text-orange-300" />
          )}
          {!node.superseded && !node.authoritative && node.undated && (
            <Row k="Metadata" v="no effective date" tone="text-[#6b7683]" />
          )}
          {conflicts.map(c => (
            <Row
              key={c.id}
              k="Conflict"
              v={`${c.topics.join(', ')} vs ${
                (c.source === node.id ? c.target : c.source).replace('doc:', '')
              }`}
              tone="text-red-300"
            />
          ))}
        </>
      )}
    </div>
  )
}

// ── Legend ─────────────────────────────────────────────────────────────────
function Legend({ hasArcs }) {
  const items = [
    { swatch: <span className="inline-block w-3 h-3 rounded-sm border border-[#818cf8] bg-[rgba(99,102,241,0.12)]" />, label: 'Sent to the LLM' },
    { swatch: <span className="inline-block w-3 h-3 rounded-sm border border-dashed border-white/25" />, label: 'Retrieved, never sent' },
    { swatch: <span className="inline-block w-6 h-[3px] rounded-full bg-[#818cf8]" />, label: 'Thicker edge = closer match' },
    { swatch: <span className="inline-block w-3 h-[4px] rounded-sm bg-[#34d399]" />, label: 'Bar = share of answer wording' },
  ]
  if (hasArcs) {
    items.push(
      { swatch: <span className="inline-block w-6 h-[2px] bg-[#f87171]" style={{ borderTop: '2px dashed #f87171', background: 'none' }} />, label: 'Conflicting claims' },
      { swatch: <span className="inline-block w-6 h-[2px] rounded-full bg-[#fbbf24]" />, label: 'Supersedes' },
    )
  }
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2 mt-3">
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-1.5">
          {it.swatch}
          <span className="text-[10.5px] text-[#6b7683]">{it.label}</span>
        </div>
      ))}
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────
export default function SourceGraph({ result, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  const [hovered, setHovered] = useState(null)
  const [selected, setSelected] = useState(null)

  const graph = result?.source_graph
  const layout = useLayout(graph)

  const activeId = hovered || selected
  const lit = useMemo(
    () => (graph && activeId ? relatedTo(activeId, graph) : null),
    [activeId, graph]
  )

  if (!graph || !layout) return null

  const { width, height, pos, chunks, docs, spread, hasArcs } = layout
  const stats = graph.stats || {}
  const selectedNode = graph.nodes.find(n => n.id === selected) || null

  const dimNode = (id) => (lit ? !lit.nodes.has(id) : false)
  const dimEdge = (id) => (lit ? !lit.edges.has(id) : false)
  const pick = (id) => setSelected(prev => (prev === id ? null : id))

  const retrievedEdges = graph.edges.filter(e => e.type === 'retrieved')
  const belongsEdges = graph.edges.filter(e => e.type === 'belongs_to')
  const conflictEdges = graph.edges.filter(e => e.type === 'conflict')
  const supersedesEdges = graph.edges.filter(e => e.type === 'supersedes')

  return (
    <div className="rounded-lg border border-white/[0.1] bg-white/[0.02]">
      {/* Header toggle */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="text-[13px] font-medium text-[#f1f5f9]">Source Graph</span>
          <span className="text-[10.5px] font-mono px-2 py-0.5 rounded border border-[rgba(99,102,241,0.3)] bg-[rgba(99,102,241,0.06)] text-[#818cf8]">
            provenance
          </span>
          <span className="text-[11px] text-[#6b7683]">
            {stats.chunks} chunk{stats.chunks !== 1 ? 's' : ''} → {stats.documents} source
            {stats.documents !== 1 ? 's' : ''} · {stats.chunks_used_by_llm} sent to LLM
            {stats.conflict_edges > 0 && (
              <span className="text-red-300"> · {stats.conflict_edges} conflict edge{stats.conflict_edges !== 1 ? 's' : ''}</span>
            )}
          </span>
        </div>
        <span className="text-[#6b7683] text-[11px] shrink-0">{open ? '▲ Collapse' : '▼ Expand'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-white/[0.07]">
          <p className="text-[11.5px] text-[#6b7683] mt-3 mb-1 leading-relaxed">
            Every path the answer could have come from. Hover to trace one, click to pin it.
            The bar on each node is the share of the answer's content words that also appear in
            that source — a lexical proxy for contribution, not a causal attribution.
          </p>

          <div className="overflow-x-auto -mx-1 px-1">
            <svg
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-label={`Provenance graph: question, ${chunks.length} retrieved chunks, ${docs.length} source documents`}
              onClick={(e) => { if (e.target.tagName === 'svg') setSelected(null) }}
            >
              <defs>
                <marker id="sg-arrow" viewBox="0 0 8 8" refX="7" refY="4"
                        markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 8 4 L 0 8 z" fill={COLOR.warn} />
                </marker>
              </defs>

              {/* Row labels */}
              <text x={6} y={Q_BOX.y + 30} fontSize={8.5} fill={COLOR.dim}
                    letterSpacing="0.1em">QUERY</text>
              <text x={6} y={CHUNK_BOX.y + 20} fontSize={8.5} fill={COLOR.dim}
                    letterSpacing="0.1em">CHUNKS</text>
              <text x={6} y={DOC_BOX.y + 20} fontSize={8.5} fill={COLOR.dim}
                    letterSpacing="0.1em">SOURCES</text>

              {/* question → chunk */}
              {retrievedEdges.map(e => {
                const a = pos.q, b = pos[e.target]
                if (!a || !b) return null
                const w = 1 + 3 * spread(e.similarity ?? 0)
                return (
                  <path
                    key={e.id}
                    d={vBezier(a.cx, a.y + a.h, b.cx, b.y)}
                    fill="none"
                    stroke={e.used_by_llm ? COLOR.accent : COLOR.line}
                    strokeWidth={w}
                    strokeDasharray={e.used_by_llm ? undefined : '4 4'}
                    opacity={dimEdge(e.id) ? 0.1 : e.used_by_llm ? 0.85 : 0.5}
                    style={{ transition: 'opacity 140ms' }}
                  />
                )
              })}

              {/* chunk → document */}
              {belongsEdges.map(e => {
                const a = pos[e.source], b = pos[e.target]
                if (!a || !b) return null
                return (
                  <path
                    key={e.id}
                    d={vBezier(a.cx, a.y + a.h, b.cx, b.y)}
                    fill="none"
                    stroke={e.used_by_llm ? 'rgba(52, 211, 153, 0.55)' : COLOR.line}
                    strokeWidth={1.2}
                    strokeDasharray={e.used_by_llm ? undefined : '4 4'}
                    opacity={dimEdge(e.id) ? 0.1 : 0.75}
                    style={{ transition: 'opacity 140ms' }}
                  />
                )
              })}

              {/* document ↔ document: conflict */}
              {conflictEdges.map((e, i) => {
                const a = pos[e.source], b = pos[e.target]
                if (!a || !b) return null
                const drop = 26 + i * 16
                return (
                  <g key={e.id} opacity={dimEdge(e.id) ? 0.1 : 1}
                     style={{ transition: 'opacity 140ms' }}>
                    <title>{`Conflict: ${e.topics.join(', ')}`}</title>
                    <path
                      d={underArc(a.cx, a.y + a.h, b.cx, b.y + b.h, drop)}
                      fill="none" stroke={COLOR.bad} strokeWidth={1.4} strokeDasharray="5 4"
                    />
                    <text
                      x={(a.cx + b.cx) / 2}
                      y={Math.max(a.y + a.h, b.y + b.h) + drop * 0.62 + 4}
                      textAnchor="middle" fontSize={9} fill={COLOR.bad}
                    >
                      ⚡ {fit(e.topics.join(', '), 180, 9)}
                    </text>
                  </g>
                )
              })}

              {/* document → document: supersedes */}
              {supersedesEdges.map((e, i) => {
                const a = pos[e.source], b = pos[e.target]
                if (!a || !b) return null
                const drop = 52 + i * 16
                return (
                  <g key={e.id} opacity={dimEdge(e.id) ? 0.1 : 1}
                     style={{ transition: 'opacity 140ms' }}>
                    <title>{`Supersedes — ${e.reason_label || e.reason}`}</title>
                    <path
                      d={underArc(a.cx, a.y + a.h, b.cx, b.y + b.h, drop)}
                      fill="none" stroke={COLOR.warn} strokeWidth={1.4}
                      markerEnd="url(#sg-arrow)"
                    />
                  </g>
                )
              })}

              {/* Nodes last so they sit above every edge */}
              <QuestionNode
                p={pos.q}
                node={graph.nodes.find(n => n.type === 'question')}
                faded={dimNode('q')}
                onEnter={() => setHovered('q')}
                onLeave={() => setHovered(null)}
                onClick={() => pick('q')}
              />
              {chunks.map(n => (
                <ChunkNode
                  key={n.id} p={pos[n.id]} node={n} faded={dimNode(n.id)}
                  onEnter={() => setHovered(n.id)}
                  onLeave={() => setHovered(null)}
                  onClick={() => pick(n.id)}
                />
              ))}
              {docs.map(n => (
                <DocumentNode
                  key={n.id} p={pos[n.id]} node={n} faded={dimNode(n.id)}
                  onEnter={() => setHovered(n.id)}
                  onLeave={() => setHovered(null)}
                  onClick={() => pick(n.id)}
                />
              ))}
            </svg>
          </div>

          <Legend hasArcs={hasArcs} />

          {selectedNode
            ? <DetailCard node={selectedNode} graph={graph} />
            : (
              <p className="mt-3 text-[11px] text-[#6b7683]">
                Answer wording traced to the {stats.chunks_used_by_llm} chunks the model
                actually saw:{' '}
                <span className="font-mono text-[#f1f5f9]">{pct(stats.llm_context_overlap)}</span>.
                Closest match L2{' '}
                <span className="font-mono text-yellow-400">{stats.best_distance}</span>.
                {stats.supersedes_suppressed > 0 && (
                  <>
                    {' '}
                    <span className="text-[#6b7683]">
                      {stats.supersedes_suppressed} further source
                      {stats.supersedes_suppressed !== 1 ? 's were' : ' was'} ranked lower by
                      version resolution for having no effective date; no arc is drawn because
                      {stats.supersedes_suppressed !== 1 ? ' they' : ' it'} never disagreed with
                      the authoritative source.
                    </span>
                  </>
                )}
              </p>
            )}
        </div>
      )}
    </div>
  )
}
