import { useState, useEffect, useMemo } from 'react'
import {
  ArrowLeft, FloppyDisk, CheckCircle, SpinnerGap, DownloadSimple,
  PencilSimple, ArrowCounterClockwise, WarningCircle, Robot, User,
  CaretDown, CaretRight, IdentificationCard,
} from '@phosphor-icons/react'
import { getDraft, saveDraft, finalizeDraft, downloadIEP } from '../api/samarth'

/**
 * ReviewPage — the Human Review step.
 *
 * Two kinds of content are edited here:
 *   1. Student Details (Section 1) — STRUCTURED fields such as grade and age.
 *      The PDF's Section 1 table is built from these directly.
 *   2. Prose sections (Sections 2–11) — the drafting agent's text.
 *
 * Nothing on this page calls the AI, so reviewing uses no API quota.
 */

// Small AI / Human provenance badge
function Provenance({ changed }) {
  return (
    <span
      title={changed ? 'Edited by a human' : 'Original AI output'}
      style={{
        fontSize: 11, padding: '2px 8px', borderRadius: 999,
        display: 'inline-flex', alignItems: 'center', gap: 4,
        background: changed ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.15)',
        color: changed ? '#22c55e' : 'var(--text-muted, #94a3b8)',
      }}
    >
      {changed ? <User size={12} /> : <Robot size={12} />}
      {changed ? 'Human' : 'AI'}
    </span>
  )
}

function UnsavedChip() {
  return (
    <span style={{
      fontSize: 11, padding: '2px 8px', borderRadius: 999,
      background: 'rgba(234,179,8,0.15)', color: '#eab308',
    }}>
      Unsaved
    </span>
  )
}

const same = (a, b) => String(a ?? '').trim() === String(b ?? '').trim()

export default function ReviewPage({ iepId, user, showToast, onBack }) {
  const [loading, setLoading]       = useState(true)
  const [saving, setSaving]         = useState(false)
  const [finalizing, setFinalizing] = useState(false)
  const [error, setError]           = useState(null)

  const [meta, setMeta]             = useState(null)

  // Section 1 — structured fields
  const [student, setStudent]       = useState([])   // [{key,label,value,original,human_edited}]
  const [severityOptions, setSeverityOptions] = useState(['Mild', 'Moderate', 'Severe'])
  const [profileEdits, setProfileEdits] = useState({})  // key -> value (dirty only)

  // Sections 2–11 — prose
  const [sections, setSections]     = useState([])
  const [edits, setEdits]           = useState({})
  const [expanded, setExpanded]     = useState({})

  // Who last reviewed this IEP, as recorded by the server from their login
  const [lastReviewer, setLastReviewer] = useState('')
  const [reviewNotes, setReviewNotes] = useState('')

  // ── Load ────────────────────────────────────────────
  useEffect(() => {
    if (!iepId) return
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const { data } = await getDraft(iepId)
        if (cancelled) return
        setMeta({
          student_name:  data.student_name,
          review_status: data.review_status,
          revision:      data.revision,
        })
        setStudent(data.student || [])
        if (data.severity_options?.length) setSeverityOptions(data.severity_options)
        setSections(data.sections || [])
        setLastReviewer(data.reviewed_by || '')
        setReviewNotes(data.review_notes || '')
        if (data.sections?.length) setExpanded({ [data.sections[0].key]: true })
      } catch (err) {
        if (cancelled) return
        setError(
          err?.response?.status === 404
            ? 'No editable draft exists for this IEP. Drafts are only stored for IEPs generated after the review feature was added.'
            : (err?.response?.data?.detail ?? 'Could not load this draft.')
        )
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [iepId])

  // ── Dirty tracking ──────────────────────────────────
  const sectionDirty = useMemo(() => Object.keys(edits), [edits])
  const profileDirty = useMemo(() => Object.keys(profileEdits), [profileEdits])
  const dirtyCount   = sectionDirty.length + profileDirty.length
  const hasUnsaved   = dirtyCount > 0

  const fieldValue   = (f) => (f.key in profileEdits ? profileEdits[f.key] : f.value)
  const sectionText  = (s) => (s.key in edits ? edits[s.key] : s.content)

  const setField = (key, value) => {
    const field = student.find(f => f.key === key)
    setProfileEdits(prev => {
      if (field && same(value, field.value)) {
        const { [key]: _drop, ...rest } = prev
        return rest
      }
      return { ...prev, [key]: value }
    })
  }

  const setText = (key, value) => {
    const section = sections.find(s => s.key === key)
    setEdits(prev => {
      if (section && value === section.content) {
        const { [key]: _drop, ...rest } = prev
        return rest
      }
      return { ...prev, [key]: value }
    })
  }

  const revertField   = (key) => {
    const f = student.find(x => x.key === key)
    if (f) setField(key, f.original)
  }
  const revertSection = (key) => {
    const s = sections.find(x => x.key === key)
    if (s) { setText(key, s.original); showToast?.('Reverted to the original AI text') }
  }

  const toggle = (key) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  // Fold saved edits into the base state so dirty tracking resets cleanly
  const commitLocal = (res) => {
    setStudent(prev => prev.map(f =>
      f.key in profileEdits
        ? { ...f, value: String(profileEdits[f.key]),
            human_edited: !same(profileEdits[f.key], f.original) }
        : f
    ))
    setSections(prev => prev.map(s =>
      s.key in edits
        ? { ...s, content: edits[s.key], human_edited: !same(edits[s.key], s.original) }
        : s
    ))
    setProfileEdits({})
    setEdits({})
    setMeta(m => ({
      ...m,
      revision:      res.data.revision,
      review_status: res.data.review_status,
      student_name:  profileEdits.student_name ?? m?.student_name,
    }))
    if (res.data.reviewed_by) setLastReviewer(res.data.reviewed_by)
  }

  const errMsg = (err, fallback) =>
    err?.response?.data?.detail
      ? (typeof err.response.data.detail === 'string'
          ? err.response.data.detail
          : JSON.stringify(err.response.data.detail))
      : fallback

  // ── Save ────────────────────────────────────────────
  const handleSave = async () => {
    if (!hasUnsaved) { showToast?.('No changes to save'); return }
    setSaving(true)
    try {
      const res = await saveDraft(iepId, edits, {
        profile: profileEdits, reviewNotes,
      })
      commitLocal(res)
      showToast?.(`Saved — revision ${res.data.revision}`)
    } catch (err) {
      showToast?.(errMsg(err, 'Save failed — is the backend running?'), 'error')
    } finally {
      setSaving(false)
    }
  }

  // ── Finalise ────────────────────────────────────────
  const handleFinalize = async () => {
    setFinalizing(true)
    try {
      const res = await finalizeDraft(
        iepId,
        sectionDirty.length ? edits : null,
        { profile: profileDirty.length ? profileEdits : null, reviewNotes },
      )
      commitLocal(res)
      showToast?.('IEP finalised — PDF rebuilt from your reviewed content')
    } catch (err) {
      showToast?.(errMsg(err, 'Finalise failed — is the backend running?'), 'error')
    } finally {
      setFinalizing(false)
    }
  }

  // ── Download ────────────────────────────────────────
  const handleDownload = async () => {
    try {
      const res = await downloadIEP(iepId)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a   = document.createElement('a')
      a.href     = url
      a.download = `IEP_${meta?.student_name ?? 'student'}_${iepId.slice(0, 8)}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
      showToast?.('PDF downloaded')
    } catch {
      showToast?.('Download failed — is the backend running?', 'error')
    }
  }

  // ── Render: loading / error ─────────────────────────
  if (loading) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center' }}>
        <SpinnerGap size={28} className="spin" />
        <p style={{ marginTop: 12 }}>Loading draft…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card" style={{ padding: 32 }}>
        <div style={{
          background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 10, padding: '14px 18px', fontSize: 14, color: '#ef4444',
        }}>
          <WarningCircle size={18} style={{ verticalAlign: -3, marginRight: 6 }} />
          {error}
        </div>
        {onBack && (
          <button className="btn btn-secondary" style={{ marginTop: 16 }} onClick={onBack}>
            <ArrowLeft size={16} /> Back
          </button>
        )}
      </div>
    )
  }

  const editedCount =
    student.filter(f => !same(fieldValue(f), f.original)).length +
    sections.filter(s => !same(sectionText(s), s.original)).length
  const totalCount = student.length + sections.length

  return (
    <>
      {/* ── Header ───────────────────────────────────── */}
      <header className="page-header">
        <div>
          <h2>Human Review</h2>
          <p>
            Review and correct the draft before finalising.
            Nothing here calls the AI — your changes are used exactly as written.
          </p>
        </div>
        <div className="header-actions" style={{ display: 'flex', gap: 8 }}>
          {onBack && (
            <button className="btn btn-secondary" onClick={onBack}>
              <ArrowLeft size={16} /> Back
            </button>
          )}
          <button className="btn btn-secondary" onClick={handleDownload}>
            <DownloadSimple size={16} /> Download PDF
          </button>
        </div>
      </header>

      {/* ── Status strip ─────────────────────────────── */}
      <section className="stats-row">
        <div className="stat-card">
          <div className="stat-icon"><User size={28} /></div>
          <div className="stat-info">
            <h3>Student</h3>
            <div className="stat-value" style={{ fontSize: 20 }}>{meta?.student_name || '—'}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon teal"><PencilSimple size={28} /></div>
          <div className="stat-info">
            <h3>Human-Edited</h3>
            <div className="stat-value">{editedCount} / {totalCount}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon lavender"><CheckCircle size={28} /></div>
          <div className="stat-info">
            <h3>Status</h3>
            <div className="stat-value" style={{ fontSize: 20, textTransform: 'capitalize' }}>
              {meta?.review_status || 'pending'}{meta?.revision ? ` · r${meta.revision}` : ''}
            </div>
          </div>
        </div>
      </section>

      {/* ── Action bar ───────────────────────────────── */}
      <section className="card" style={{ marginBottom: 16 }}>
        <div className="card-header flex-between">
          <div>
            <h3>Reviewer</h3>
            <span className="subtitle">
              {hasUnsaved
                ? `${dirtyCount} unsaved change${dirtyCount > 1 ? 's' : ''}`
                : 'All changes saved'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary" onClick={handleSave}
              disabled={saving || !hasUnsaved}>
              {saving
                ? <><SpinnerGap size={16} className="spin" /> Saving…</>
                : <><FloppyDisk size={16} /> Save Draft</>}
            </button>
            <button className="btn btn-primary" onClick={handleFinalize} disabled={finalizing}>
              {finalizing
                ? <><SpinnerGap size={16} className="spin" /> Rebuilding PDF…</>
                : <><CheckCircle size={16} weight="fill" /> Approve &amp; Rebuild PDF</>}
            </button>
          </div>
        </div>
        <div className="modern-form">
          <div className="form-row">
            <div className="form-group">
              <label>Reviewing as</label>
              {/* Read-only: the server records the signed-in account, so the
                  audit trail shows who actually made each change. */}
              <input type="text" readOnly value={user ? `${user.full_name} (${user.email})` : ''}
                style={{ opacity: 0.8, cursor: 'default' }} />
              {lastReviewer && (
                <span style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>
                  Last saved by {lastReviewer}
                </span>
              )}
            </div>
            <div className="form-group">
              <label>Review notes (optional)</label>
              <input type="text" placeholder="e.g. Corrected grade and Section 10 wording"
                value={reviewNotes} onChange={e => setReviewNotes(e.target.value)} />
            </div>
          </div>
        </div>
      </section>

      {/* ── Section 1: Student Details (structured) ──── */}
      <section className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <IdentificationCard size={20} /> Section 1 — Student Details
          </h3>
          <span className="subtitle">
            These values fill the Background Information table in the PDF.
          </span>
        </div>

        <div className="modern-form" style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 16,
        }}>
          {student.map(f => {
            const value   = fieldValue(f)
            const dirty   = f.key in profileEdits
            const changed = !same(value, f.original)
            return (
              <div key={f.key} className="form-group" style={{ margin: 0 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  {f.label}
                  <Provenance changed={changed} />
                  {dirty && <UnsavedChip />}
                </label>

                {f.key === 'disability_severity' ? (
                  <select value={value} onChange={e => setField(f.key, e.target.value)}>
                    {!severityOptions.includes(value) && value && <option value={value}>{value}</option>}
                    {severityOptions.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    type={f.key === 'age' ? 'number' : 'text'}
                    min={f.key === 'age' ? 3 : undefined}
                    max={f.key === 'age' ? 25 : undefined}
                    value={value}
                    onChange={e => setField(f.key, e.target.value)}
                  />
                )}

                {changed && (
                  <button type="button" onClick={() => revertField(f.key)}
                    style={{
                      marginTop: 4, background: 'none', border: 'none', padding: 0,
                      fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer',
                      textAlign: 'left',
                    }}>
                    <ArrowCounterClockwise size={11} /> Revert to “{f.original || '—'}”
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Sections 2–11: prose ─────────────────────── */}
      <section className="card">
        <div className="card-header">
          <h3>IEP Sections</h3>
          <span className="subtitle">Click a section to expand and edit it.</span>
        </div>

        <div style={{ padding: '8px 0' }}>
          {sections.map(s => {
            const isOpen  = !!expanded[s.key]
            const text    = sectionText(s)
            const changed = !same(text, s.original)
            return (
              <div key={s.key} style={{
                borderBottom: '1px solid var(--border, rgba(255,255,255,0.08))',
                padding: '10px 16px',
              }}>
                <div onClick={() => toggle(s.key)} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  cursor: 'pointer', userSelect: 'none',
                }}>
                  {isOpen ? <CaretDown size={16} /> : <CaretRight size={16} />}
                  <h4 style={{ margin: 0, flex: 1, fontSize: 14 }}>{s.label}</h4>
                  {s.key in edits && <UnsavedChip />}
                  <Provenance changed={changed} />
                </div>

                {isOpen && (
                  <div style={{ marginTop: 10 }}>
                    <textarea
                      value={text}
                      onChange={e => setText(s.key, e.target.value)}
                      rows={Math.min(24, Math.max(6, text.split('\n').length + 2))}
                      style={{ width: '100%', fontSize: 13, lineHeight: 1.6,
                               fontFamily: 'inherit', resize: 'vertical' }}
                    />
                    <div style={{ display: 'flex', alignItems: 'center',
                                  justifyContent: 'space-between', marginTop: 6 }}>
                      <button className="btn btn-secondary"
                        style={{ fontSize: 12, padding: '4px 10px' }}
                        onClick={() => revertSection(s.key)} disabled={!changed}>
                        <ArrowCounterClockwise size={13} /> Revert to AI original
                      </button>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        {text.length} chars
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>
    </>
  )
}