import { useState, useEffect, useMemo } from 'react'
import {
  ArrowLeft, FloppyDisk, CheckCircle, SpinnerGap, DownloadSimple,
  PencilSimple, ArrowCounterClockwise, WarningCircle, Robot, User,
  CaretDown, CaretRight,
} from '@phosphor-icons/react'
import { getDraft, saveDraft, finalizeDraft, downloadIEP } from '../api/samarth'

/**
 * ReviewPage — the Human Review step.
 *
 * Loads the 14 NASET sections produced by the pipeline, lets an educator
 * edit any of them, then rebuilds the PDF from the reviewed content.
 *
 * No LLM calls are made here: editing and finalising are free of API quota.
 *
 * Props:
 *   iepId     — the IEP to review (required)
 *   showToast — (msg, type?) => void
 *   onBack    — optional; called when the back button is pressed
 */
export default function ReviewPage({ iepId, showToast, onBack }) {
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState(false)
  const [finalizing, setFinalizing] = useState(false)
  const [error, setError]         = useState(null)

  const [meta, setMeta]           = useState(null)   // student_name, revision, etc.
  const [sections, setSections]   = useState([])     // [{key,label,content,original,human_edited}]
  const [edits, setEdits]         = useState({})     // key -> edited text (dirty only)
  const [expanded, setExpanded]   = useState({})     // key -> bool
  const [reviewedBy, setReviewedBy]   = useState('')
  const [reviewNotes, setReviewNotes] = useState('')

  // ── Load draft ──────────────────────────────────────
  useEffect(() => {
    if (!iepId) return
    let cancelled = false

    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getDraft(iepId)
        if (cancelled) return
        const data = res.data
        setMeta({
          student_name:  data.student_name,
          review_status: data.review_status,
          revision:      data.revision,
          edited_count:  data.edited_count,
        })
        setSections(data.sections || [])
        setReviewedBy(data.reviewed_by || '')
        setReviewNotes(data.review_notes || '')
        // Open the first section by default so the page isn't a wall of headers
        if (data.sections?.length) {
          setExpanded({ [data.sections[0].key]: true })
        }
      } catch (err) {
        if (cancelled) return
        setError(
          err?.response?.data?.detail ??
          'Could not load this draft. It may predate the review feature.'
        )
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [iepId])

  // ── Derived state ───────────────────────────────────
  const dirtyKeys = useMemo(() => Object.keys(edits), [edits])
  const hasUnsaved = dirtyKeys.length > 0

  const currentText = (s) => (s.key in edits ? edits[s.key] : s.content)

  const setText = (key, value) => {
    setEdits(prev => {
      const section = sections.find(s => s.key === key)
      // If the user typed it back to the saved value, drop it from dirty set
      if (section && value === section.content) {
        const { [key]: _removed, ...rest } = prev
        return rest
      }
      return { ...prev, [key]: value }
    })
  }

  const revertToOriginal = (key) => {
    const section = sections.find(s => s.key === key)
    if (!section) return
    setText(key, section.original)
    showToast?.('Reverted to the original AI text')
  }

  const toggle = (key) =>
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  // ── Save (no finalise) ──────────────────────────────
  const handleSave = async () => {
    if (!hasUnsaved) { showToast?.('No changes to save'); return }
    setSaving(true)
    try {
      const res = await saveDraft(iepId, edits, { reviewedBy, reviewNotes })
      // Fold saved edits into the base content so dirty state resets cleanly
      setSections(prev => prev.map(s =>
        s.key in edits
          ? { ...s, content: edits[s.key],
              human_edited: edits[s.key].trim() !== s.original.trim() }
          : s
      ))
      setEdits({})
      setMeta(m => ({
        ...m,
        revision:      res.data.revision,
        review_status: res.data.review_status,
        edited_count:  res.data.edited_sections?.length ?? m?.edited_count,
      }))
      showToast?.(`Saved — revision ${res.data.revision}`)
    } catch (err) {
      showToast?.(
        err?.response?.data?.detail ?? 'Save failed — is the backend running?',
        'error'
      )
    } finally {
      setSaving(false)
    }
  }

  // ── Finalise — approve and rebuild the PDF ──────────
  const handleFinalize = async () => {
    setFinalizing(true)
    try {
      // Send any unsaved edits along so nothing is lost
      const res = await finalizeDraft(
        iepId,
        hasUnsaved ? edits : null,
        { reviewedBy, reviewNotes }
      )
      setSections(prev => prev.map(s =>
        s.key in edits
          ? { ...s, content: edits[s.key],
              human_edited: edits[s.key].trim() !== s.original.trim() }
          : s
      ))
      setEdits({})
      setMeta(m => ({
        ...m,
        revision:      res.data.revision,
        review_status: res.data.review_status,
        edited_count:  res.data.edited_sections?.length ?? m?.edited_count,
      }))
      showToast?.('IEP finalised — PDF rebuilt from your reviewed content')
    } catch (err) {
      showToast?.(
        err?.response?.data?.detail ?? 'Finalise failed — is the backend running?',
        'error'
      )
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

  // ── Render ──────────────────────────────────────────
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

  const editedCount = sections.filter(s => s.human_edited).length

  return (
    <>
      {/* ── Header ───────────────────────────────────── */}
      <header className="page-header">
        <div>
          <h2>Human Review</h2>
          <p>
            Review and edit each section before finalising.
            Editing makes no AI calls — your changes are used exactly as written.
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
            <div className="stat-value" style={{ fontSize: 20 }}>
              {meta?.student_name || '—'}
            </div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon teal"><PencilSimple size={28} /></div>
          <div className="stat-info">
            <h3>Sections Edited</h3>
            <div className="stat-value">{editedCount} / {sections.length}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon lavender"><CheckCircle size={28} /></div>
          <div className="stat-info">
            <h3>Status</h3>
            <div className="stat-value" style={{ fontSize: 20, textTransform: 'capitalize' }}>
              {meta?.review_status || 'pending'}
              {meta?.revision ? ` · r${meta.revision}` : ''}
            </div>
          </div>
        </div>
      </section>

      {/* ── Reviewer identity + notes ────────────────── */}
      <section className="card" style={{ marginBottom: 16 }}>
        <div className="card-header"><h3>Reviewer</h3></div>
        <div className="modern-form">
          <div className="form-row">
            <div className="form-group">
              <label>Reviewed by</label>
              <input
                type="text"
                placeholder="e.g. Ms. Priya Nair, Special Educator"
                value={reviewedBy}
                onChange={e => setReviewedBy(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label>Review notes (optional)</label>
              <input
                type="text"
                placeholder="e.g. Corrected reading goal wording"
                value={reviewNotes}
                onChange={e => setReviewNotes(e.target.value)}
              />
            </div>
          </div>
        </div>
      </section>

      {/* ── Section editors ──────────────────────────── */}
      <section className="card">
        <div className="card-header flex-between">
          <div>
            <h3>IEP Sections</h3>
            <span className="subtitle">
              {hasUnsaved
                ? `${dirtyKeys.length} unsaved change${dirtyKeys.length > 1 ? 's' : ''}`
                : 'All changes saved'}
            </span>
          </div>
          <div className="draft-actions" style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-secondary"
              onClick={handleSave}
              disabled={saving || !hasUnsaved}
            >
              {saving
                ? <><SpinnerGap size={16} className="spin" /> Saving…</>
                : <><FloppyDisk size={16} /> Save Draft</>}
            </button>
            <button
              className="btn btn-primary"
              onClick={handleFinalize}
              disabled={finalizing}
            >
              {finalizing
                ? <><SpinnerGap size={16} className="spin" /> Rebuilding PDF…</>
                : <><CheckCircle size={16} weight="fill" /> Approve &amp; Rebuild PDF</>}
            </button>
          </div>
        </div>

        <div style={{ padding: '8px 0' }}>
          {sections.map((s) => {
            const isOpen  = !!expanded[s.key]
            const isDirty = s.key in edits
            const text    = currentText(s)
            const changed = text.trim() !== s.original.trim()

            return (
              <div
                key={s.key}
                style={{
                  borderBottom: '1px solid var(--border, rgba(255,255,255,0.08))',
                  padding: '10px 16px',
                }}
              >
                {/* Section header row */}
                <div
                  onClick={() => toggle(s.key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    cursor: 'pointer', userSelect: 'none',
                  }}
                >
                  {isOpen ? <CaretDown size={16} /> : <CaretRight size={16} />}
                  <h4 style={{ margin: 0, flex: 1, fontSize: 14 }}>{s.label}</h4>

                  {isDirty && (
                    <span style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 999,
                      background: 'rgba(234,179,8,0.15)', color: '#eab308',
                    }}>
                      Unsaved
                    </span>
                  )}

                  <span
                    title={changed ? 'Edited by a human' : 'Original AI output'}
                    style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 999,
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      background: changed
                        ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.15)',
                      color: changed ? '#22c55e' : 'var(--text-muted, #94a3b8)',
                    }}
                  >
                    {changed ? <User size={12} /> : <Robot size={12} />}
                    {changed ? 'Human' : 'AI'}
                  </span>
                </div>

                {/* Editor */}
                {isOpen && (
                  <div style={{ marginTop: 10 }}>
                    <textarea
                      value={text}
                      onChange={e => setText(s.key, e.target.value)}
                      rows={Math.min(24, Math.max(6, text.split('\n').length + 2))}
                      style={{
                        width: '100%', fontSize: 13, lineHeight: 1.6,
                        fontFamily: 'inherit', resize: 'vertical',
                      }}
                    />
                    <div style={{
                      display: 'flex', alignItems: 'center',
                      justifyContent: 'space-between', marginTop: 6,
                    }}>
                      <button
                        className="btn btn-secondary"
                        style={{ fontSize: 12, padding: '4px 10px' }}
                        onClick={() => revertToOriginal(s.key)}
                        disabled={!changed}
                      >
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