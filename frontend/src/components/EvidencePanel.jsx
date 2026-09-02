/**
 * EvidencePanel.jsx
 * Expandable panel that shows evidence, grounding, conflict detection,
 * and version resolution results from the RAG pipeline.
 *
 * Conflicts tab: shows structured claim-vs-claim data per conflicting field.
 * Version Resolution tab: shows which source was selected and why.
 * All data comes from the backend — nothing is hard-coded.
 */
import React, { useState } from 'react'

// ── Helpers ────────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const MAP = {
    supported:             { label: '✓ Supported',          cls: 'border-teal-500/40 bg-teal-500/10 text-teal-300' },
    partially_supported:   { label: '~ Partial',            cls: 'border-yellow-500/40 bg-yellow-500/10 text-yellow-300' },
    unsupported:           { label: '✗ Unsupported',        cls: 'border-red-500/40 bg-red-500/10 text-red-300' },
    insufficient_evidence: { label: '○ No evidence',        cls: 'border-white/20 bg-white/5 text-[#6b7683]' },
    conflict_detected:     { label: '⚡ Conflict detected', cls: 'border-orange-500/40 bg-orange-500/10 text-orange-300' },
  }
  const { label, cls } = MAP[status] || { label: status || '—', cls: 'border-white/20 bg-white/5 text-[#6b7683]' }
  return (
    <span className={`text-[10.5px] font-mono px-2 py-0.5 rounded border ${cls}`}>
      {label}
    </span>
  )
}

function GroundednessBar({ value }) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const color = pct >= 60 ? '#34d399' : pct >= 30 ? '#fbbf24' : '#f87171'
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-[10.5px] font-mono tabular" style={{ color }}>{pct}%</span>
    </div>
  )
}

function MetaTag({ children, tone = 'gray' }) {
  const styles = {
    indigo: 'border-[rgba(99,102,241,0.3)] bg-[rgba(99,102,241,0.06)] text-[#818cf8]',
    teal:   'border-[rgba(52,211,153,0.3)] bg-[rgba(52,211,153,0.06)] text-[#34d399]',
    orange: 'border-orange-500/30 bg-orange-500/5 text-orange-300',
    gray:   'border-white/10 bg-white/5 text-[#6b7683]',
  }
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${styles[tone] || styles.gray}`}>
      {children}
    </span>
  )
}

// ── Evidence list tab ──────────────────────────────────────────────────────
function EvidenceList({ evidence }) {
  if (!evidence || !evidence.length)
    return <p className="text-[11.5px] text-[#6b7683]">No evidence records.</p>
  return (
    <div className="space-y-2">
      {evidence.map((ev) => (
        <div key={ev.rank} className="bg-[#0a0a0f] border border-white/[0.08] rounded-lg p-3">
          <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
            <span className="text-[10px] font-bold text-[#818cf8]">#{ev.rank}</span>
            <span className="text-[11px] font-mono text-[#f1f5f9] truncate max-w-[200px]" title={ev.source}>
              {ev.source}
            </span>
            <span className="text-[10px] text-[#6b7683] font-mono">
              L2 <span className="text-yellow-400">{ev.distance.toFixed(4)}</span>
            </span>
            <MetaTag tone="indigo">v{ev.version}</MetaTag>
            {ev.effective_date && <MetaTag tone="gray">eff. {ev.effective_date}</MetaTag>}
            {ev.loan_type && ev.loan_type !== 'general' && <MetaTag>{ev.loan_type}</MetaTag>}
          </div>
          <p className="text-[11px] text-[#6b7683] italic leading-relaxed">
            "{ev.text_preview}{ev.text_preview?.length >= 150 ? '…' : ''}"
          </p>
        </div>
      ))}
    </div>
  )
}

// ── Grounding tab ──────────────────────────────────────────────────────────
function GroundingSection({ grounding }) {
  if (!grounding) return null
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={grounding.status} />
        {grounding.groundedness != null && (
          <span className="text-[11px] text-[#6b7683]">Groundedness</span>
        )}
      </div>
      {grounding.groundedness != null && <GroundednessBar value={grounding.groundedness} />}
      <p className="text-[12px] text-[#a5b0bd] leading-relaxed">{grounding.explanation}</p>
    </div>
  )
}

// ── Conflicts tab ──────────────────────────────────────────────────────────
function ConflictSection({ conflict }) {
  if (!conflict) return null

  if (!conflict.conflict_detected) {
    return (
      <div className="p-3 rounded-lg border border-teal-500/20 bg-teal-500/5">
        <p className="text-[12.5px] text-teal-400 font-medium">✓ No policy conflicts detected</p>
        <p className="text-[11.5px] text-[#6b7683] mt-1">
          All retrieved chunks are consistent — no conflicting numeric claims found across sources.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-orange-300 font-semibold text-[13px]">⚡ Conflict Detected</span>
        <MetaTag tone="orange">{conflict.conflicts.length} field{conflict.conflicts.length !== 1 ? 's' : ''}</MetaTag>
      </div>

      {conflict.conflicts.map((c, i) => (
        <div key={i} className="border border-orange-500/25 bg-orange-500/5 rounded-lg p-4">
          {/* Field heading */}
          <p className="text-[12.5px] font-semibold text-orange-200 mb-3">{c.topic}</p>

          {/* Claim cards side by side */}
          <div className="grid sm:grid-cols-2 gap-2">
            {c.claims.map((claim, j) => (
              <div
                key={j}
                className={`rounded-lg p-3 border ${
                  j === 0
                    ? 'border-white/10 bg-[#0a0a0f]'
                    : 'border-white/10 bg-[#0a0a0f]'
                }`}
              >
                <p className="text-[10.5px] text-[#6b7683] mb-1.5 font-medium uppercase tracking-wider">
                  Source {j + 1}
                </p>
                <p className="text-[11.5px] font-mono text-[#f1f5f9] truncate mb-2" title={claim.source}>
                  {claim.source}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  <MetaTag tone="indigo">v{claim.version}</MetaTag>
                  {claim.effective_date
                    ? <MetaTag tone="gray">eff. {claim.effective_date}</MetaTag>
                    : <MetaTag tone="gray">no effective date</MetaTag>
                  }
                </div>
                <div className="mt-2 px-2 py-1.5 rounded bg-orange-500/10 border border-orange-500/20">
                  <p className="text-[10.5px] text-[#6b7683]">{claim.field_label || c.topic}</p>
                  <p className="text-[14px] font-bold text-orange-200 font-mono">{claim.value}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Version Resolution tab ─────────────────────────────────────────────────
function VersionSection({ versionResolution, conflict }) {
  if (!versionResolution) return null
  const vr = versionResolution
  const hasConflict = conflict?.conflict_detected

  if (!vr.resolution_performed) {
    if (vr.reason === 'single_source') {
      return (
        <p className="text-[12px] text-[#6b7683]">Only one source document — no version resolution needed.</p>
      )
    }
    // insufficient_metadata — conflict but can't resolve
    return (
      <div className="p-3.5 rounded-lg border border-yellow-500/25 bg-yellow-500/5">
        <p className="text-[12.5px] font-semibold text-yellow-300 mb-1">⚠ Resolution Not Possible</p>
        <p className="text-[12px] text-[#a5b0bd] leading-relaxed">
          {vr.message || 'Conflicting information found but metadata is insufficient to determine which policy is current.'}
        </p>
      </div>
    )
  }

  const REASON_LABELS = {
    latest_effective_date: 'Latest effective date',
    only_dated_source:     'Only source with effective date',
    highest_version_number: 'Highest version number',
  }

  return (
    <div className="space-y-3">
      {/* Status header */}
      {hasConflict && (
        <div className="flex items-center gap-2 text-[12px]">
          <span className="text-orange-300">⚡ Conflict detected</span>
          <span className="text-[#6b7683]">→</span>
          <span className="text-teal-300">✓ Resolved using {REASON_LABELS[vr.reason] || vr.reason}</span>
        </div>
      )}

      {/* Comparison: superseded vs authoritative */}
      {vr.superseded_values?.length > 0 && vr.resolved_values?.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-2">
          {/* Superseded */}
          {vr.superseded_values.slice(0, 1).map((sv, i) => (
            <div key={i} className="rounded-lg border border-white/10 bg-[#0a0a0f] p-3 opacity-60">
              <p className="text-[10.5px] text-[#6b7683] uppercase tracking-wider mb-1.5">Superseded</p>
              <p className="text-[11.5px] font-mono text-[#f1f5f9] truncate mb-2" title={sv.source}>{sv.source}</p>
              <div className="flex flex-wrap gap-1.5 mb-2">
                <MetaTag tone="gray">v{sv.version}</MetaTag>
                {sv.effective_date
                  ? <MetaTag tone="gray">eff. {sv.effective_date}</MetaTag>
                  : <MetaTag tone="gray">no effective date</MetaTag>}
              </div>
              <div className="px-2 py-1.5 rounded bg-white/5 border border-white/10">
                <p className="text-[10.5px] text-[#6b7683]">{sv.field}</p>
                <p className="text-[14px] font-bold text-[#6b7683] font-mono line-through">{sv.value}</p>
              </div>
            </div>
          ))}

          {/* Authoritative */}
          <div className="rounded-lg border border-teal-500/30 bg-teal-500/5 p-3">
            <p className="text-[10.5px] text-teal-400 uppercase tracking-wider mb-1.5 font-semibold">✓ Current Policy</p>
            <p className="text-[11.5px] font-mono text-[#f1f5f9] truncate mb-2" title={vr.authoritative_source}>
              {vr.authoritative_source}
            </p>
            <div className="flex flex-wrap gap-1.5 mb-2">
              <MetaTag tone="indigo">v{vr.authoritative_version}</MetaTag>
              {vr.authoritative_effective_date && (
                <MetaTag tone="teal">eff. {vr.authoritative_effective_date}</MetaTag>
              )}
            </div>
            {vr.resolved_values?.slice(0, 1).map((rv, i) => (
              <div key={i} className="px-2 py-1.5 rounded bg-teal-500/10 border border-teal-500/20">
                <p className="text-[10.5px] text-teal-400/70">{rv.field}</p>
                <p className="text-[14px] font-bold text-teal-300 font-mono">{rv.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Fallback: no resolved_values but resolution_performed */}
      {(!vr.resolved_values || vr.resolved_values.length === 0) && (
        <div className="rounded-lg border border-teal-500/30 bg-teal-500/5 p-3">
          <p className="text-[11.5px] text-teal-300 font-semibold mb-1">✓ Authoritative source identified</p>
          <div className="flex flex-wrap gap-2 text-[11.5px]">
            <span className="font-mono text-[#f1f5f9]">{vr.authoritative_source}</span>
            {vr.authoritative_version && <MetaTag tone="indigo">v{vr.authoritative_version}</MetaTag>}
            {vr.authoritative_effective_date && <MetaTag tone="teal">eff. {vr.authoritative_effective_date}</MetaTag>}
          </div>
        </div>
      )}

      {/* Reason explanation */}
      <div className="p-2.5 rounded border border-white/[0.07] bg-white/[0.02]">
        <p className="text-[11.5px] text-[#6b7683]">
          <span className="text-[#a5b0bd] font-medium">Reason: </span>
          {REASON_LABELS[vr.reason] || vr.reason}
          {vr.authoritative_effective_date && vr.reason === 'latest_effective_date' && (
            <> — version {vr.authoritative_version} has effective date {vr.authoritative_effective_date}</>
          )}
        </p>
      </div>

      {/* Superseded sources list */}
      {vr.superseded_sources?.length > 0 && (
        <div>
          <p className="text-[10.5px] text-[#6b7683] mb-1">Superseded sources:</p>
          <div className="flex flex-wrap gap-1">
            {vr.superseded_sources.map((s) => (
              <span key={s} className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-white/10 bg-white/5 text-[#6b7683]">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Tab button ─────────────────────────────────────────────────────────────
function Tab({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-[11.5px] rounded-md transition-colors whitespace-nowrap ${
        active
          ? 'bg-[rgba(99,102,241,0.15)] text-[#818cf8] border border-[rgba(99,102,241,0.3)]'
          : 'text-[#6b7683] hover:text-[#f1f5f9] border border-transparent'
      }`}
    >
      {children}
    </button>
  )
}

// ── Main component ─────────────────────────────────────────────────────────
export default function EvidencePanel({ result, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  const [tab, setTab] = useState('evidence')

  if (!result) return null

  const { evidence, conflict, version_resolution, grounding, evidence_status } = result
  if (!evidence && !conflict && !grounding) return null

  const hasConflict = conflict?.conflict_detected
  const hasResolution = version_resolution?.resolution_performed

  return (
    <div className={`rounded-lg border transition-colors ${
      hasConflict
        ? 'border-orange-500/30 bg-orange-500/5'
        : 'border-white/[0.1] bg-white/[0.02]'
    }`}>
      {/* Header toggle */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="text-[13px] font-medium text-[#f1f5f9]">Evidence &amp; Sources</span>
          {evidence_status && <StatusBadge status={evidence_status} />}
          {hasConflict && (
            <span className="text-[11px] text-orange-300 font-semibold">
              {conflict.conflicts.length} conflict{conflict.conflicts.length !== 1 ? 's' : ''}
            </span>
          )}
          {!hasConflict && evidence?.length > 0 && (
            <span className="text-[11px] text-[#6b7683]">
              {evidence.length} chunk{evidence.length !== 1 ? 's' : ''} ·{' '}
              {[...new Set(evidence.map(e => e.source))].length} source{[...new Set(evidence.map(e => e.source))].length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <span className="text-[#6b7683] text-[11px] shrink-0">{open ? '▲ Collapse' : '▼ Expand'}</span>
      </button>

      {/* Body */}
      {open && (
        <div className="px-4 pb-4 border-t border-white/[0.07]">
          <div className="flex flex-wrap gap-1.5 mt-3 mb-4">
            <Tab active={tab === 'evidence'} onClick={() => setTab('evidence')}>
              Evidence ({evidence?.length ?? 0})
            </Tab>
            <Tab active={tab === 'grounding'} onClick={() => setTab('grounding')}>
              Grounding
            </Tab>
            <Tab active={tab === 'conflicts'} onClick={() => setTab('conflicts')}>
              {hasConflict
                ? `⚡ Conflicts (${conflict.conflicts.length})`
                : 'Conflicts'}
            </Tab>
            <Tab active={tab === 'versions'} onClick={() => setTab('versions')}>
              {hasResolution ? '✓ Version Resolution' : 'Version Resolution'}
            </Tab>
          </div>

          {tab === 'evidence'  && <EvidenceList evidence={evidence} />}
          {tab === 'grounding' && <GroundingSection grounding={grounding} />}
          {tab === 'conflicts' && <ConflictSection conflict={conflict} />}
          {tab === 'versions'  && <VersionSection versionResolution={version_resolution} conflict={conflict} />}
        </div>
      )}
    </div>
  )
}
