import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 600000, // 10 min — full pipeline runs ~3-5 min
})

// A separate short-timeout client for review calls.
// Editing and finalising make no LLM calls, so they should be fast —
// a long timeout here would just hide a genuine failure.
const reviewApi = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 60000, // 1 min
})

// ── Generation ────────────────────────────────────────

// Manual form entry → POST /iep/generate
export const generateIEP = (studentData) =>
  api.post('/iep/generate', studentData)

// PDF report upload → POST /iep/generate-from-report
// NOTE: do NOT set Content-Type manually — axios must set it itself so the
// multipart boundary parameter is included, otherwise FastAPI returns 422
export const generateIEPFromReport = (pdfFile) => {
  const formData = new FormData()
  formData.append('file', pdfFile)
  return api.post('/iep/generate-from-report', formData)
}

// ── Human Review ──────────────────────────────────────

// Review queue → GET /iep/drafts
export const listDrafts = (limit = 50) =>
  reviewApi.get('/iep/drafts', { params: { limit } })

// Load the 14 editable sections → GET /iep/{id}/draft
export const getDraft = (iepId) =>
  reviewApi.get(`/iep/${iepId}/draft`)

// Save edits without finalising → PUT /iep/{id}/draft
// sections: { background_info: "...", annual_goals: "...", ... }
export const saveDraft = (iepId, sections, opts = {}) =>
  reviewApi.put(`/iep/${iepId}/draft`, {
    sections,
    reviewed_by:  opts.reviewedBy  ?? '',
    review_notes: opts.reviewNotes ?? '',
    approve:      opts.approve     ?? false,
  })

// Approve + rebuild PDF from edited content → POST /iep/{id}/finalize
// Makes no LLM calls, so consumes no API quota.
export const finalizeDraft = (iepId, sections = null, opts = {}) =>
  reviewApi.post(`/iep/${iepId}/finalize`, {
    sections,
    reviewed_by:  opts.reviewedBy  ?? '',
    review_notes: opts.reviewNotes ?? '',
  })

// ── Download ──────────────────────────────────────────

export const downloadIEP = (iepId) =>
  api.get(`/iep/${iepId}/download`, { responseType: 'blob' })

// ── Health ────────────────────────────────────────────

export const checkHealth = () =>
  reviewApi.get('/iep/health')