import React, { useCallback, useRef, useState } from 'react'
import { STATIC_KB_INFO } from '../data/staticData'
import { uploadDocuments, uploadDocumentsWithMetadata, deleteDocument } from '../services/api'
import Section, { Stat, StatRow } from './ui/Section'

const ACCEPT = '.txt,.md,.pdf,.docx'

// ── Metadata badges shown on doc cards ──────────────────────────────────────
function MetaBadge({ children, tone }) {
  const base = 'text-[10px] px-1.5 py-0.5 rounded border font-mono'
  const tones = {
    indigo: 'border-[rgba(99,102,241,0.35)] bg-[rgba(99,102,241,0.08)] text-[#818cf8]',
    teal:   'border-[rgba(52,211,153,0.3)] bg-[rgba(52,211,153,0.06)] text-[#34d399]',
    amber:  'border-[rgba(251,191,36,0.3)] bg-[rgba(251,191,36,0.06)] text-[#fbbf24]',
    gray:   'border-white/10 bg-white/5 text-[#6b7683]',
  }
  return <span className={`${base} ${tones[tone] || tones.gray}`}>{children}</span>
}

function DocCard({ doc, onDelete, busy }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="panel p-3.5 hover:border-white/[0.16] transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[12.5px] font-mono text-[#f1f5f9] truncate" title={doc.filename}>
            {doc.filename}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            <span className="text-[11.5px] text-[#6b7683] tabular">
              {doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''}
            </span>
            {doc.uploaded && <span className="chip chip-accent !py-0 !text-[10px]">yours</span>}
            {/* Metadata badges — shown when non-default values are present */}
            {doc.version && doc.version !== '1.0' && (
              <MetaBadge tone="indigo">v{doc.version}</MetaBadge>
            )}
            {doc.loan_type && doc.loan_type !== 'general' && (
              <MetaBadge tone="teal">{doc.loan_type}</MetaBadge>
            )}
            {doc.document_type && doc.document_type !== 'general' && (
              <MetaBadge tone="gray">{doc.document_type}</MetaBadge>
            )}
            {doc.effective_date && (
              <MetaBadge tone="amber">eff. {doc.effective_date}</MetaBadge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <button onClick={() => setOpen(!open)} className="btn btn-ghost !text-[11.5px]">
            {open ? 'Hide' : 'Preview'}
          </button>
          {doc.uploaded && onDelete && (
            <button
              onClick={() => onDelete(doc.filename)}
              disabled={busy}
              aria-label={`Remove ${doc.filename}`}
              title="Remove from knowledge base"
              className="btn btn-ghost !px-2 !text-[11.5px] hover:!text-[#f87171]"
            >
              ✕
            </button>
          )}
        </div>
      </div>
      {open && (
        <div className="mt-3 pt-3 border-t border-white/[0.07] max-h-56 overflow-y-auto rise">
          <p className="text-[11.5px] text-[#6b7683] leading-relaxed whitespace-pre-wrap">
            {doc.full_text || doc.preview}
          </p>
        </div>
      )}
    </div>
  )
}

// ── Metadata form ────────────────────────────────────────────────────────────
const DOC_TYPES = ['general', 'reference', 'policy', 'guide', 'legal', 'other']
const LOAN_TYPES = ['general', 'home', 'personal', 'auto', 'education', 'business', 'mortgage', 'other']

function MetadataForm({ metadata, onChange }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3 p-3.5 rounded-lg border border-white/[0.08] bg-white/[0.02]">
      <p className="col-span-full text-[11.5px] text-[#6b7683] mb-1">
        Optional document metadata — applied to all uploaded files in this batch.
      </p>

      {/* Document type */}
      <div>
        <label className="block text-[11px] text-[#6b7683] mb-1" htmlFor="meta-doc-type">
          Document type
        </label>
        <select
          id="meta-doc-type"
          value={metadata.document_type}
          onChange={(e) => onChange({ ...metadata, document_type: e.target.value })}
          className="w-full bg-[#0a0a0f] border border-white/[0.1] rounded px-2.5 py-1.5 text-[12.5px] text-[#f1f5f9] focus:outline-none focus:border-[rgba(99,102,241,0.5)]"
        >
          {DOC_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {/* Loan type */}
      <div>
        <label className="block text-[11px] text-[#6b7683] mb-1" htmlFor="meta-loan-type">
          Loan type
        </label>
        <select
          id="meta-loan-type"
          value={metadata.loan_type}
          onChange={(e) => onChange({ ...metadata, loan_type: e.target.value })}
          className="w-full bg-[#0a0a0f] border border-white/[0.1] rounded px-2.5 py-1.5 text-[12.5px] text-[#f1f5f9] focus:outline-none focus:border-[rgba(99,102,241,0.5)]"
        >
          {LOAN_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {/* Version */}
      <div>
        <label className="block text-[11px] text-[#6b7683] mb-1" htmlFor="meta-version">
          Version
        </label>
        <input
          id="meta-version"
          type="text"
          value={metadata.version}
          onChange={(e) => onChange({ ...metadata, version: e.target.value })}
          placeholder="e.g. 1.0, 2.3"
          className="w-full bg-[#0a0a0f] border border-white/[0.1] rounded px-2.5 py-1.5 text-[12.5px] text-[#f1f5f9] placeholder-[#6b7683] focus:outline-none focus:border-[rgba(99,102,241,0.5)]"
        />
      </div>

      {/* Effective date */}
      <div>
        <label className="block text-[11px] text-[#6b7683] mb-1" htmlFor="meta-effective-date">
          Effective date
        </label>
        <input
          id="meta-effective-date"
          type="date"
          value={metadata.effective_date}
          onChange={(e) => onChange({ ...metadata, effective_date: e.target.value })}
          className="w-full bg-[#0a0a0f] border border-white/[0.1] rounded px-2.5 py-1.5 text-[12.5px] text-[#f1f5f9] focus:outline-none focus:border-[rgba(99,102,241,0.5)]"
        />
      </div>
    </div>
  )
}

const DEFAULT_METADATA = {
  document_type: 'general',
  loan_type: 'general',
  version: '1.0',
  effective_date: '',
}

// ── Main component ──────────────────────────────────────────────────────────
export default function KnowledgeBase({ kbInfo, backendStatus, onKbUpdate }) {
  const data = kbInfo || STATIC_KB_INFO
  const online = backendStatus === 'online'

  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null) // { type: 'success'|'error', text }

  // Metadata form state
  const [showMeta, setShowMeta] = useState(false)
  const [metadata, setMetadata] = useState(DEFAULT_METADATA)

  const handleFiles = useCallback(
    async (fileList) => {
      const files = Array.from(fileList || [])
      if (!files.length) return

      if (!online) {
        setNotice({ type: 'error', text: 'Backend is offline — start it before uploading documents.' })
        return
      }

      setBusy(true)
      setNotice({ type: 'info', text: `Extracting, chunking and embedding ${files.length} file(s)…` })
      try {
        // Use with-metadata endpoint if metadata form has non-default values
        const hasCustomMeta =
          metadata.document_type !== 'general' ||
          metadata.loan_type !== 'general' ||
          metadata.version !== '1.0' ||
          metadata.effective_date !== ''

        const result = hasCustomMeta
          ? await uploadDocumentsWithMetadata(files, metadata)
          : await uploadDocuments(files)

        if (result.kb && onKbUpdate) onKbUpdate(result.kb)

        const added = result.uploaded || []
        const failed = result.failed || []
        const addedChunks = added.reduce((sum, d) => sum + d.chunk_count, 0)

        const parts = []
        if (added.length) {
          parts.push(
            `Indexed ${added.length} document${added.length !== 1 ? 's' : ''} (+${addedChunks} chunks): ${added
              .map((d) => d.filename)
              .join(', ')}`
          )
        }
        if (failed.length) {
          parts.push(`Skipped ${failed.map((f) => `${f.filename} — ${f.error}`).join('; ')}`)
        }
        setNotice({ type: failed.length && !added.length ? 'error' : 'success', text: parts.join(' · ') })
      } catch (err) {
        setNotice({ type: 'error', text: err.message || 'Upload failed.' })
      } finally {
        setBusy(false)
        if (inputRef.current) inputRef.current.value = ''
      }
    },
    [online, onKbUpdate, metadata]
  )

  const handleDelete = useCallback(
    async (filename) => {
      setBusy(true)
      try {
        const result = await deleteDocument(filename)
        if (result.kb && onKbUpdate) onKbUpdate(result.kb)
        setNotice({ type: 'success', text: `Removed ${filename} and rebuilt the index.` })
      } catch (err) {
        setNotice({ type: 'error', text: err.message || 'Delete failed.' })
      } finally {
        setBusy(false)
      }
    },
    [onKbUpdate]
  )

  const onDrop = useCallback(
    (e) => {
      e.preventDefault()
      setDragging(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles]
  )

  const noticeColor =
    notice?.type === 'error'
      ? 'text-[#f87171] border-[rgba(248,113,113,0.3)] bg-[rgba(248,113,113,0.08)]'
      : notice?.type === 'success'
        ? 'text-[#34d399] border-[rgba(52,211,153,0.3)] bg-[rgba(52,211,153,0.08)]'
        : 'text-[#818cf8] border-[rgba(99,102,241,0.3)] bg-[rgba(99,102,241,0.08)]'

  const uploadedCount = data.documents.filter((d) => d.uploaded).length

  return (
    <Section
      id="knowledge-base"
      eyebrow="Live system"
      title="Knowledge base"
      description="Answers are drawn from these documents rather than from the model's own memory."
      aside={
        <span className={online ? 'chip chip-ok' : 'chip'}>
          {online ? 'Live' : 'Static fallback'}
        </span>
      }
    >
      <StatRow cols={4}>
        <Stat label="Documents" value={data.documents.length} />
        <Stat label="Uploaded by you" value={uploadedCount} accent={uploadedCount > 0} />
        <Stat label="Chunks indexed" value={data.total_chunks} accent live={online} />
        <Stat label="Dimensions" value={data.embedding_dimension} />
      </StatRow>

      {/* Upload zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !busy && online && inputRef.current?.click()}
        role="button"
        tabIndex={online && !busy ? 0 : -1}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && online && !busy) {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        className={`mt-4 rounded-lg border border-dashed p-5 text-center transition-colors ${
          dragging
            ? 'border-[#6366f1] bg-[rgba(99,102,241,0.08)]'
            : 'border-white/[0.12] bg-white/[0.02] hover:border-white/25'
        } ${online && !busy ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <p className="text-[13.5px] text-[#f1f5f9] font-medium">
          {busy ? 'Processing…' : 'Add your own documents'}
        </p>
        <p className="text-[12px] text-[#6b7683] mt-1">
          {online ? 'Drop files here or click to browse · .txt .md .pdf .docx' : 'Start the backend to enable uploads'}
        </p>
        <p className="text-[11.5px] text-[#6b7683] mt-2 max-w-[52ch] mx-auto leading-relaxed">
          Uploads are chunked, embedded and added to the index immediately — answers start using
          them on the next question.
        </p>
      </div>

      {/* Metadata toggle + form — below the upload zone */}
      {online && (
        <div className="mt-2">
          <button
            onClick={() => setShowMeta((v) => !v)}
            className="text-[11.5px] text-[#6b7683] hover:text-[#f1f5f9] transition-colors flex items-center gap-1.5"
          >
            <span>{showMeta ? '▲' : '▼'}</span>
            {showMeta ? 'Hide metadata' : 'Add metadata (optional)'}
          </button>
          {showMeta && (
            <MetadataForm metadata={metadata} onChange={setMetadata} />
          )}
        </div>
      )}

      {notice && (
        <div className={`mt-4 rounded-lg border px-3.5 py-2.5 text-[12px] leading-relaxed ${noticeColor}`}>
          <div className="flex items-start justify-between gap-3">
            <span className="min-w-0 break-words">{notice.text}</span>
            <button
              onClick={() => setNotice(null)}
              className="shrink-0 opacity-60 hover:opacity-100"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Document grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 mt-4">
        {data.documents.map((doc) => (
          <DocCard
            key={doc.filename}
            doc={doc}
            onDelete={online ? handleDelete : null}
            busy={busy}
          />
        ))}
      </div>

      <p className="mt-4 pt-4 border-t border-white/[0.07] text-[11.5px] text-[#6b7683] font-mono">
        {data.faiss_index_type} · {data.embedding_dimension}-dim · chunk 300 / overlap 50
        {!online && <span className="text-[#fbbf24] ml-2">showing static fallback data</span>}
      </p>
    </Section>
  )
}
