import axios from 'axios'

/**
 * API client for SAMARTH.
 *
 * AUTH
 * After login the server returns a token. It is kept in localStorage so a
 * page refresh doesn't log you out, and attached to every request as
 * "Authorization: Bearer <token>".
 *
 * Trade-off worth knowing: localStorage can be read by any script running on
 * the page, so a cross-site-scripting bug could steal the token. An
 * httpOnly cookie avoids that but needs CSRF protection and cookie-aware
 * CORS. For this project the token expires after 8 hours, which limits the
 * damage; moving to cookies is the next hardening step.
 */

/**
 * WHERE THE BACKEND IS
 * Read from VITE_API_URL at build time (frontend/.env.local for local runs,
 * or the hosting dashboard's environment settings when deployed).
 * Falls back to the local backend so `npm run dev` works with no setup.
 *
 * Vite copies VITE_* values into the JavaScript bundle that every visitor
 * downloads — so this must only ever hold a public URL, never a secret.
 */
const BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '')
// Shown in connection-error messages. Empty BASE_URL means "this same site"
// (VITE_API_URL=/ — the website is served by the API server itself).
export const API_BASE_URL = BASE_URL || window.location.origin
const TOKEN_KEY = 'samarth_token'
const USER_KEY  = 'samarth_user'

// ── Session storage ───────────────────────────────────

export const getToken = () => localStorage.getItem(TOKEN_KEY)

export const getStoredUser = () => {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null') }
  catch { return null }
}

export const setSession = (token, user) => {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export const clearSession = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  // Pre-login versions kept IEP history in the browser. With accounts, the
  // server is the source of truth, so remove the old shared history.
  localStorage.removeItem('samarth_iep_history')
}

// App.jsx registers a handler so any 401 (expired / revoked session)
// sends the user back to the login screen.
let onUnauthorized = null
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

// ── Clients ───────────────────────────────────────────

const api       = axios.create({ baseURL: BASE_URL, timeout: 600000 })  // pipeline: minutes
const reviewApi = axios.create({ baseURL: BASE_URL, timeout: 60000 })   // no LLM calls

for (const client of [api, reviewApi]) {
  client.interceptors.request.use((config) => {
    const token = getToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  client.interceptors.response.use(
    (res) => res,
    (err) => {
      const isLoginCall = err?.config?.url?.includes('/auth/login')
      if (err?.response?.status === 401 && !isLoginCall) {
        clearSession()
        onUnauthorized?.()
      }
      return Promise.reject(err)
    },
  )
}

// ── Auth ──────────────────────────────────────────────

/** OAuth2 login expects form fields named username/password. */
export const login = async (email, password) => {
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)
  const { data } = await reviewApi.post('/auth/login', form)
  setSession(data.access_token, data.user)
  return data.user
}

export const fetchMe = () => reviewApi.get('/auth/me')

export const updateMe = (fullName) =>
  reviewApi.patch('/auth/me', { full_name: fullName })

export const changePassword = (currentPassword, newPassword) =>
  reviewApi.post('/auth/me/password', {
    current_password: currentPassword,
    new_password:     newPassword,
  })

// ── Generation ────────────────────────────────────────

export const generateIEP = (studentData) =>
  api.post('/iep/generate', studentData)

// Do NOT set Content-Type manually — axios must add the multipart boundary
export const generateIEPFromReport = (pdfFile, studentCode = '') => {
  const formData = new FormData()
  formData.append('file', pdfFile)
  if (studentCode) formData.append('student_code', studentCode)
  return api.post('/iep/generate-from-report', formData)
}

// ── Students (each educator's own register) ───────────

export const listStudents = (includeArchived = false) =>
  reviewApi.get('/students', { params: { include_archived: includeArchived } })

export const createStudent = (fields) =>
  reviewApi.post('/students', fields)

export const updateStudent = (code, fields) =>
  reviewApi.patch(`/students/${encodeURIComponent(code)}`, fields)

export const deleteStudent = (code) =>
  reviewApi.delete(`/students/${encodeURIComponent(code)}`)

export const listStudentIEPs = (code) =>
  reviewApi.get(`/students/${encodeURIComponent(code)}/ieps`)

/**
 * FastAPI validation errors arrive as a list of objects; turn any error
 * response into one readable sentence for the UI.
 */
export const errorText = (err, fallback = 'Something went wrong.') => {
  const detail = err?.response?.data?.detail
  if (Array.isArray(detail)) {
    return detail.map(d => {
      const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : ''
      const msg = String(d.msg || '').replace(/^Value error, /, '')
      return field && !msg.toLowerCase().includes(String(field).replace(/_/g, ' '))
        ? `${String(field).replace(/_/g, ' ')}: ${msg}` : msg
    }).join(' · ')
  }
  if (typeof detail === 'string') return detail
  if (!err?.response) return `Could not reach the server at ${API_BASE_URL}.`
  return fallback
}

// ── Human Review ──────────────────────────────────────

export const listDrafts = (limit = 50) =>
  reviewApi.get('/iep/drafts', { params: { limit } })

export const getDraft = (iepId) =>
  reviewApi.get(`/iep/${iepId}/draft`)

/** Reviewer identity comes from the login — the server ignores any name sent. */
export const saveDraft = (iepId, sections = {}, opts = {}) =>
  reviewApi.put(`/iep/${iepId}/draft`, {
    sections,
    profile:      opts.profile     ?? {},
    review_notes: opts.reviewNotes ?? '',
    approve:      opts.approve     ?? false,
  })

export const finalizeDraft = (iepId, sections = null, opts = {}) =>
  reviewApi.post(`/iep/${iepId}/finalize`, {
    sections,
    profile:      opts.profile     ?? null,
    review_notes: opts.reviewNotes ?? '',
  })

// ── Download / health ─────────────────────────────────

export const downloadIEP = (iepId) =>
  api.get(`/iep/${iepId}/download`, { responseType: 'blob' })

export const checkHealth = () =>
  reviewApi.get('/iep/health')

/** Public: {enabled:false}, or the demo login + sample students on the online demo. */
export const getDemoInfo = () =>
  reviewApi.get('/demo')

// ── Analytics & settings ──────────────────────────────

/** The browser's UTC offset in minutes (India = 330), so months match local time. */
const tzOffset = () => -new Date().getTimezoneOffset()

export const getAnalytics = () =>
  reviewApi.get('/analytics', { params: { tz_offset_minutes: tzOffset() } })

export const getPreferences  = () => reviewApi.get('/settings/preferences')
export const savePreferences = (prefs) => reviewApi.put('/settings/preferences', prefs)
export const getSystemInfo   = () => reviewApi.get('/settings/system')
