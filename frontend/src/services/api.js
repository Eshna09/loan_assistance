/**
 * api.js — typed API client for the FastAPI backend.
 * All calls go through Vite's /api proxy → http://localhost:8000.
 */

const BASE = '/api'

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120_000),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text}`)
  }
  return res.json()
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, {
    signal: AbortSignal.timeout(10_000),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/** GET /health — aggregate status of all four services */
export const getHealth = () => get('/health')

/** GET /kb/info */
export const getKbInfo = () => get('/kb/info')

/**
 * POST /kb/upload — multipart upload of one or more documents.
 * Returns { uploaded: [...], failed: [...], kb: {...} }.
 * Note: no Content-Type header — the browser must set the multipart boundary.
 */
export async function uploadDocuments(files) {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)

  const res = await fetch(`${BASE}/kb/upload`, {
    method: 'POST',
    body: form,
    signal: AbortSignal.timeout(180_000),
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) message = body.detail
    } catch {
      /* non-JSON error body — keep the status message */
    }
    throw new Error(message)
  }
  return res.json()
}

/**
 * POST /kb/upload/with-metadata — multipart upload with optional metadata fields.
 *
 * @param {File[]} files - Files to upload
 * @param {Object} metadata - Optional metadata: { document_type, loan_type, version, effective_date }
 * Returns { uploaded: [...], failed: [...], kb: {...} }.
 */
export async function uploadDocumentsWithMetadata(files, metadata = {}) {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)

  // Only append metadata fields that have non-empty values
  const { document_type, loan_type, version, effective_date } = metadata
  if (document_type?.trim()) form.append('document_type', document_type.trim())
  if (loan_type?.trim()) form.append('loan_type', loan_type.trim())
  if (version?.trim()) form.append('version', version.trim())
  if (effective_date?.trim()) form.append('effective_date', effective_date.trim())

  const res = await fetch(`${BASE}/kb/upload/with-metadata`, {
    method: 'POST',
    body: form,
    signal: AbortSignal.timeout(180_000),
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) message = body.detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message)
  }
  return res.json()
}

/** DELETE /kb/documents/:filename */
export async function deleteDocument(filename) {
  const res = await fetch(`${BASE}/kb/documents/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
    signal: AbortSignal.timeout(60_000),
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) message = body.detail
    } catch {
      /* non-JSON error body — keep the status message */
    }
    throw new Error(message)
  }
  return res.json()
}

/** POST /retrieve */
export const retrieve = (question) => post('/retrieve', { question })

/** POST /generate */
export const generate = (prompt) => post('/generate', { prompt })

/** POST /ask */
export const ask = (question) => post('/ask', { question })

/**
 * POST /ask/debug
 * Returns: { question, query_embedding_preview, query_embedding_dimension,
 *            retrieved_chunks, distances, context, prompt, answer, sources,
 *            evidence, conflict, version_resolution, grounding, evidence_status }
 */
export const askDebug = (question) => post('/ask/debug', { question })

/**
 * POST /ask/evidence
 * Same as /ask/debug but also returns a structured evidence_summary block.
 * Returns: all askDebug fields + evidence_summary { total_sources, chunks_retrieved,
 *          conflict_detected, resolution_performed, groundedness, status }
 */
export const askEvidence = (question) => post('/ask/evidence', { question })

