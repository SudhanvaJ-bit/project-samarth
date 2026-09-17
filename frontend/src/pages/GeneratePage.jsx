import { useState, useRef } from 'react'
import {
  Bell, MagicWand, SpinnerGap, CheckCircle, Circle,
  FilePdf, PencilSimple, TrendUp, WarningCircle, Pulse, Heart,
  Lightbulb, Paperclip, DownloadSimple, FileText, X,
} from '@phosphor-icons/react'
import { generateIEP, generateIEPFromReport, downloadIEP } from '../api/samarth'

const DISABILITIES = [
  'Dyslexia', 'Dysgraphia', 'Dyscalculia', 'Autism Spectrum Disorder', 'ADHD',
  'Visual Impairment', 'Hearing Impairment', 'Intellectual Disability',
  'Cerebral Palsy', 'Speech and Language Disability', 'Multiple Disabilities', 'Other',
]

const WORKFLOW_STEPS = [
  { id: 'profile',    label: 'Student Profile Processing',   activeDesc: 'Extracting data…',          doneDesc: 'Data extracted' },
  { id: 'compliance', label: 'Educational Standards Review', activeDesc: 'Aligning with RPwD Act…',   doneDesc: 'Compliant with RPwD Act 2016' },
  { id: 'drafting',   label: 'Draft Preparation',            activeDesc: 'Writing IEP sections…',     doneDesc: 'IEP sections written' },
  { id: 'pdf',        label: 'PDF Generation',               activeDesc: 'Building document…',        doneDesc: 'Document ready' },
  { id: 'review',     label: 'Human Review',                 activeDesc: 'Awaiting educator…',        doneDesc: 'Ready for approval' },
]

// ── BUG FIX: keys now match the actual NASET DraftedIEP keys from the backend
// Old keys (student_profile_summary, present_levels) don't exist → preview was always blank
const PREVIEW_SECTIONS = [
  ['background_info',           'Background Information'],
  ['academic_performance',      'Academic Performance'],
  ['annual_goals',              'Annual Goals'],
  ['special_education_services','Special Education Services'],
]

const NOTIFICATIONS = [
  { id: 1, unread: true,  color: 'var(--teal)',       icon: <CheckCircle size={20} />,   msg: 'IEP Generated for Alex Johnson',        time: '2 mins ago' },
  { id: 2, unread: true,  color: 'var(--lavender)',   icon: <WarningCircle size={20} />, msg: 'Review Required for Marcus Rodriguez',  time: '1 hour ago' },
  { id: 3, unread: false, color: 'var(--sage-green)', icon: <Bell size={20} />,          msg: 'New student profile: Mia Chen',         time: 'Yesterday' },
]

function getStepStatus(stepId, loading, result) {
  if (!loading && !result) return 'pending'
  if (result) return 'completed'
  return stepId === 'profile' ? 'active' : 'pending'
}

// Safely convert any drafted_iep field value to a displayable string
function toPreviewText(value) {
  if (!value) return ''
  if (Array.isArray(value)) return value.map(String).join(' ')
  if (typeof value === 'object') return Object.values(value).map(String).join(' ')
  return String(value)
}

// Read history from localStorage once at module level isn't safe across tabs,
// so we read inside the component via useState initialiser instead.
function readHistory() {
  try {
    return JSON.parse(localStorage.getItem('samarth_iep_history') || '[]')
  } catch {
    return []
  }
}

export default function GeneratePage({ showToast }) {
  const [form, setForm] = useState({
    student_name: '', age: '', grade: '', school_name: '',
    disability_category: '', disability_severity: 'moderate',
    raw_notes: '', academic_history: '', teacher_observations: '', parent_concerns: '',
  })

  const [errors, setErrors]         = useState({})
  const [attachedFile, setAttachedFile] = useState(null)
  const [loading, setLoading]       = useState(false)
  const [result, setResult]         = useState(null)
  const [error, setError]           = useState(null)
  const [notifOpen, setNotifOpen]   = useState(false)
  const [notifs, setNotifs]         = useState(NOTIFICATIONS)
  const [history, setHistory]       = useState(readHistory)

  const fileRef = useRef()

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const unreadCount = notifs.filter(n => n.unread).length

  const studentsThisMonth = history.filter(h => {
    const now  = new Date()
    const date = new Date(h.created_at || h.date)
    return date.getMonth() === now.getMonth() && date.getFullYear() === now.getFullYear()
  }).length

  const validate = () => {
    if (attachedFile) return {}   // PDF route — backend extracts everything
    const e = {}
    if (!form.student_name.trim())              e.student_name        = 'Required'
    if (!form.age || form.age < 3 || form.age > 25) e.age             = 'Age must be 3–25'
    if (!form.grade.trim())                     e.grade               = 'Required'
    if (!form.school_name.trim())               e.school_name         = 'Required'
    if (!form.disability_category)              e.disability_category = 'Required'
    if (form.raw_notes.trim().length < 50)      e.raw_notes           = 'Minimum 50 characters'
    return e
  }

  const saveToHistory = (responseData) => {
    const prev = readHistory()
    const entry = {
      iep_id:              responseData.iep_id,
      student_name:        responseData.student_name        ?? form.student_name        ?? 'Unknown',
      disability_category: responseData.disability_category ?? form.disability_category ?? '',
      // ── BUG FIX: grade was missing from history → AnalyticsPage showed "Unknown" for all entries
      grade:               form.grade || '',
      workflow_status:     responseData.workflow_status,
      created_at:          new Date().toISOString(),
      date:                new Date().toISOString(),  // kept for backwards-compat
    }
    const updated = [entry, ...prev].slice(0, 50)
    localStorage.setItem('samarth_iep_history', JSON.stringify(updated))
    setHistory(updated)   // immediate re-render of stats row
    return entry
  }

  const handleGenerate = async () => {
    const e = validate()
    if (Object.keys(e).length) { setErrors(e); return }
    setErrors({})
    setLoading(true)
    setError(null)

    try {
      let res
      if (attachedFile) {
        // Pass the File object directly — samarth.js builds FormData internally
        res = await generateIEPFromReport(attachedFile)
      } else {
        res = await generateIEP({ ...form, age: parseInt(form.age, 10) })
      }

      setResult(res.data)
      saveToHistory(res.data)
      showToast(`IEP generated for ${res.data.student_name ?? form.student_name ?? 'student'}`)
    } catch (err) {
      const msg = err?.response?.data?.detail
        ?? (err?.code === 'ECONNABORTED' ? 'Request timed out — backend may still be processing' : null)
        ?? 'Generation failed. Is the backend running on port 8000?'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = async () => {
    if (!result?.iep_id) return
    try {
      const res = await downloadIEP(result.iep_id)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a   = document.createElement('a')
      a.href     = url
      a.download = `IEP_${result.student_name ?? 'student'}_${result.iep_id.slice(0, 8)}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
      showToast('PDF downloaded')
    } catch {
      showToast('Download failed — is the backend running?', 'error')
    }
  }

  const reset = () => { setResult(null); setError(null); setAttachedFile(null) }

  const inpClass = (k) => errors[k] ? 'error' : ''

  const complianceBadge = () => {
    const s = (result?.compliance_status ?? '').toLowerCase()
    if (s.includes('compliant') && !s.includes('partial') && !s.includes('non'))
      return { cls: 'compliant', label: '✅ Fully Compliant' }
    if (s.includes('partial'))
      return { cls: 'partial',   label: '⚠️ Partially Compliant' }
    return   { cls: 'non',       label: '❌ Non-Compliant' }
  }

  return (
    <>
      {/* ── Header ───────────────────────────────────────────── */}
      <header className="page-header">
        <div>
          <h2>Generate New IEP</h2>
          <p>Fill in student details — the system prepares a structured educational plan.</p>
        </div>

        <div className="header-actions" style={{ position: 'relative' }}>
          <button className="btn btn-icon" style={{ position: 'relative' }}
            onClick={() => setNotifOpen(o => !o)}>
            <Bell size={20} />
            {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
          </button>

          {notifOpen && (
            <div className="notification-dropdown">
              <div className="dropdown-header">
                <h3>Notifications</h3>
                <button className="btn-clear-all" onClick={() => {
                  setNotifs(ns => ns.map(n => ({ ...n, unread: false })))
                  setNotifOpen(false)
                }}>
                  Mark all as read
                </button>
              </div>
              {notifs.map(n => (
                <div key={n.id} className={`notification-item ${n.unread ? 'unread' : ''}`}>
                  <div className="notif-icon" style={{ color: n.color }}>{n.icon}</div>
                  <div className="notif-content">
                    <p>{n.msg}</p>
                    <span>{n.time}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* ── Stats row — fully dynamic ─────────────────────────── */}
      <section className="stats-row">
        <div className="stat-card">
          <div className="stat-icon"><FileText size={28} /></div>
          <div className="stat-info">
            <h3>IEPs Generated</h3>
            <div className="stat-value">{history.length}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon teal"><Bell size={28} /></div>
          <div className="stat-info">
            <h3>Students This Month</h3>
            <div className="stat-value">{studentsThisMonth}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon lavender"><CheckCircle size={28} /></div>
          <div className="stat-info">
            <h3>Disabilities Supported</h3>
            <div className="stat-value">{DISABILITIES.length}</div>
          </div>
        </div>
      </section>

      {/* ── 3-column layout ──────────────────────────────────── */}
      <section className="three-column-layout">

        {/* Col 1 — Student form */}
        <div className="layout-column">
          <div className="card">
            <div className="card-header"><h3>Student Details</h3></div>
            <div className="modern-form">

              <div className="form-group">
                <label>Student Name</label>
                <input className={inpClass('student_name')} type="text"
                  placeholder="e.g. Arjun Sharma" value={form.student_name}
                  onChange={e => set('student_name', e.target.value)} />
                {errors.student_name && <span className="err-msg">{errors.student_name}</span>}
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Age</label>
                  <input className={inpClass('age')} type="number" min="3" max="25"
                    placeholder="e.g. 10" value={form.age}
                    onChange={e => set('age', e.target.value)} />
                  {errors.age && <span className="err-msg">{errors.age}</span>}
                </div>
                <div className="form-group">
                  <label>Grade</label>
                  <input className={inpClass('grade')} type="text"
                    placeholder="e.g. Grade 5" value={form.grade}
                    onChange={e => set('grade', e.target.value)} />
                  {errors.grade && <span className="err-msg">{errors.grade}</span>}
                </div>
              </div>

              <div className="form-group">
                <label>School</label>
                <input className={inpClass('school_name')} type="text"
                  placeholder="e.g. DPS Bengaluru" value={form.school_name}
                  onChange={e => set('school_name', e.target.value)} />
                {errors.school_name && <span className="err-msg">{errors.school_name}</span>}
              </div>

              <div className="form-group">
                <label>Disability Category</label>
                <select className={inpClass('disability_category')}
                  value={form.disability_category}
                  onChange={e => set('disability_category', e.target.value)}>
                  <option value="">Select category…</option>
                  {DISABILITIES.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
                {errors.disability_category && <span className="err-msg">{errors.disability_category}</span>}
              </div>

              <div className="form-group">
                <label>Severity</label>
                <select value={form.disability_severity}
                  onChange={e => set('disability_severity', e.target.value)}>
                  <option value="mild">Mild</option>
                  <option value="moderate">Moderate</option>
                  <option value="severe">Severe</option>
                </select>
              </div>

              <div className="form-group">
                <label>
                  Teacher Notes{attachedFile ? ' (optional — PDF attached)' : ''}
                </label>
                <textarea className={inpClass('raw_notes')} rows="3"
                  placeholder="Key observations, clinical notes (min 50 chars)…"
                  value={form.raw_notes}
                  onChange={e => set('raw_notes', e.target.value)} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  {errors.raw_notes && <span className="err-msg">{errors.raw_notes}</span>}
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                    {form.raw_notes.length} chars
                  </span>
                </div>
              </div>

              {/* ── Action buttons ── */}
              <div className="form-actions">
                <input type="file" accept="application/pdf" ref={fileRef}
                  style={{ display: 'none' }}
                  onChange={e => {
                    const f = e.target.files[0]
                    if (f?.type === 'application/pdf') {
                      setAttachedFile(f)
                      showToast(`Report attached: ${f.name}`)
                    } else if (f) {
                      showToast('Only PDF files are accepted', 'error')
                    }
                  }} />

                <button type="button" className="btn btn-secondary"
                  onClick={() => fileRef.current.click()}
                  style={attachedFile
                    ? { borderColor: 'var(--sage-green)', color: 'var(--sage-green)' }
                    : {}}>
                  <Paperclip size={16} />
                  {attachedFile
                    ? attachedFile.name.slice(0, 16) + (attachedFile.name.length > 16 ? '…' : '')
                    : 'Upload Report'}
                </button>

                <button type="button" className="btn btn-primary"
                  onClick={handleGenerate} disabled={loading}>
                  {loading
                    ? <><SpinnerGap size={16} className="spin" /> Generating…</>
                    : result
                    ? <><CheckCircle size={16} weight="fill" /> Generated</>
                    : <><MagicWand size={16} /> Generate IEP</>}
                </button>
              </div>

              {/* Attached file indicator */}
              {attachedFile && (
                <div className="file-attached">
                  <FileText size={14} />
                  <span>{attachedFile.name}</span>
                  <button onClick={() => setAttachedFile(null)}
                    style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', padding: 0, marginLeft: 4 }}>
                    <X size={13} />
                  </button>
                </div>
              )}

              {/* Error banner */}
              {error && (
                <div style={{
                  background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
                  borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#ef4444',
                }}>
                  ❌ {error}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Col 2 — Workflow tracker */}
        <div className="layout-column">
          <div className="workflow-header"><h3>IEP Preparation Workflow</h3></div>
          <div className="workflow-container">
            {WORKFLOW_STEPS.map((step, i) => {
              const status = getStepStatus(step.id, loading, result)
              return (
                <div key={step.id} className={`workflow-step ${status}`}>
                  <div className="step-icon">
                    {status === 'completed' && <CheckCircle size={16} weight="fill" />}
                    {status === 'active'    && <SpinnerGap  size={16} className="spin" />}
                    {status === 'pending'   && <Circle      size={16} />}
                  </div>
                  <div className="step-content">
                    <h4>{step.label}</h4>
                    <span>
                      {status === 'completed' ? step.doneDesc
                        : status === 'active' ? step.activeDesc
                        : i === 0 ? 'Awaiting generation'
                        : `Pending step ${i}`}
                    </span>
                  </div>
                  {i < WORKFLOW_STEPS.length - 1 && <div className="step-indicator" />}
                </div>
              )
            })}
          </div>
        </div>

        {/* Col 3 — AI Insights */}
        <div className="layout-column">
          <div className="card" style={{ flex: 1 }}>
            <div className="card-header"><h3>AI Insights Panel</h3></div>
            <div className="insights-list">
              {result ? (
                <>
                  <div className="insight-item">
                    <div className="insight-header text-sage">
                      <TrendUp size={20} /><span>Compliance Status</span>
                    </div>
                    <span className={`compliance-badge ${complianceBadge().cls}`}>
                      {complianceBadge().label}
                    </span>
                    <p style={{ fontSize: 12, marginTop: 8 }}>
                      IEP ID: <code style={{ color: 'var(--teal)' }}>
                        {result.iep_id?.slice(0, 16)}…
                      </code>
                    </p>
                  </div>

                  <div className="insight-item">
                    <div className="insight-header text-teal">
                      <Pulse size={20} /><span>Pipeline Complete</span>
                    </div>
                    <p style={{ fontSize: 13 }}>{result.workflow_status}</p>
                    {result.errors?.length > 0 && (
                      <p style={{ fontSize: 12, color: '#ef4444' }}>
                        {result.errors.join('; ')}
                      </p>
                    )}
                  </div>

                  {result.message && (
                    <div className="insight-item">
                      <div className="insight-header text-sage">
                        <Lightbulb size={20} /><span>Next Step</span>
                      </div>
                      <p style={{ fontSize: 13 }}>{result.message}</p>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="insight-item">
                    <div className="insight-header text-sage">
                      <TrendUp size={20} /><span>Student Strengths</span>
                    </div>
                    <p>Insights will appear here after generating an IEP.</p>
                  </div>
                  <div className="insight-item">
                    <div className="insight-header text-lavender">
                      <WarningCircle size={20} /><span>Academic Challenges</span>
                    </div>
                    <p>Extracted from the student profile or uploaded report.</p>
                  </div>
                  <div className="insight-item">
                    <div className="insight-header text-teal">
                      <Pulse size={20} /><span>Pipeline Status</span>
                    </div>
                    <p>Waiting for student details or a PDF report.</p>
                  </div>
                  <div className="insight-item">
                    <div className="insight-header text-lavender">
                      <Heart size={20} /><span>Support Planning</span>
                    </div>
                    <p>Recommended supports will be generated after processing.</p>
                  </div>
                  <div className="insight-item">
                    <div className="insight-header text-sage">
                      <Lightbulb size={20} /><span>Recommended Accommodations</span>
                    </div>
                    <ul className="accommodation-tags">
                      <li>Generated after analysis</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Draft preview ─────────────────────────────────────── */}
      <section className="bottom-section">
        <div className="card draft-preview-card">
          <div className="card-header flex-between">
            <div>
              <h3>IEP Draft Preview</h3>
              <span className="subtitle">
                {result ? 'Generation complete' : 'Generated draft preview will appear here'}
              </span>
            </div>
            <div className="draft-actions">
              {result ? (
                <>
                  <button className="btn btn-secondary" onClick={reset}>
                    <PencilSimple size={16} /> New IEP
                  </button>
                  <button className="btn btn-primary" onClick={handleDownload}>
                    <DownloadSimple size={16} /> Export PDF
                  </button>
                </>
              ) : (
                <button className="btn btn-secondary" disabled>
                  <FilePdf size={16} /> Export PDF
                </button>
              )}
            </div>
          </div>

          <div className="draft-content">
            {!result ? (
              <>
                <div className="draft-section">
                  <h4>Present Levels of Academic Achievement</h4>
                  <p style={{ color: 'var(--text-muted)', lineHeight: 1.7, fontSize: 14 }}>
                    Generate an IEP to preview the student-specific academic
                    achievement analysis, learning challenges, strengths,
                    accommodations, and educational recommendations.
                  </p>
                </div>
                <div className="draft-section">
                  <h4>Measurable Annual Goals</h4>
                  <div className="goal-item">
                    <span className="goal-badge">Waiting</span>
                    <p>
                      Student-specific measurable goals will appear here after
                      the AI pipeline processes the profile or uploaded report.
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <>
                {PREVIEW_SECTIONS.map(([key, label]) => {
                  const text = toPreviewText(result.drafted_iep?.[key])
                  return text ? (
                    <div key={key} className="draft-section">
                      <h4>{label}</h4>
                      <p>{text.slice(0, 400)}{text.length > 400 ? '…' : ''}</p>
                    </div>
                  ) : null
                })}

                {/* Fallback if drafted_iep is empty (download-only result) */}
                {(!result.drafted_iep || Object.keys(result.drafted_iep).length === 0) && (
                  <div className="draft-section">
                    <div className="goal-item">
                      <span className="goal-badge">Complete</span>
                      <p>{result.message}</p>
                      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>
                        Download the PDF to view all 14 NASET sections.
                      </p>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </section>
    </>
  )
}