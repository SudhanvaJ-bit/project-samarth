import { useState, useEffect, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import {
  Plus, MagnifyingGlass, ArrowClockwise, SpinnerGap, Users, X, Copy,
  MagicWand, PencilSimple, Archive, ArrowCounterClockwise, Trash, FloppyDisk,
} from '@phosphor-icons/react'
import {
  listStudents, createStudent, updateStudent, deleteStudent, listStudentIEPs, errorText,
} from '../api/samarth'

/**
 * Students — the signed-in educator's own register of students.
 *
 * Each student gets a unique ID (e.g. STU-7K3M9Q) from the server when they
 * are registered. Only the educator who registered a student can see them.
 * From here a teacher can edit a student, archive them, see their IEPs, or
 * start a new IEP with the form already filled in.
 */

const DISABILITIES = [
  'Dyslexia', 'Dysgraphia', 'Dyscalculia', 'Autism Spectrum Disorder', 'ADHD',
  'Visual Impairment', 'Hearing Impairment', 'Intellectual Disability',
  'Cerebral Palsy', 'Speech and Language Disability', 'Multiple Disabilities', 'Other',
]

const EMPTY = {
  full_name: '', date_of_birth: '', grade: '', school_name: '',
  disability_category: '', disability_severity: 'moderate', dominant_language: '',
  guardian_name: '', guardian_contact: '',
  notes: '', academic_history: '', teacher_observations: '', parent_concerns: '',
}
const FIELDS = Object.keys(EMPTY)
const MORE_FIELDS = ['dominant_language', 'academic_history', 'teacher_observations', 'parent_concerns']

const REVIEW_LABEL = { pending: 'Awaiting review', edited: 'In review', approved: 'Approved' }

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

const avatar = (name) =>
  `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=1c1c24&color=f8f8f9`

function ErrorBox({ children }) {
  if (!children) return null
  return (
    <div role="alert" style={{
      background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
      borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#ef4444',
    }}>
      {children}
    </div>
  )
}

// ── The add / edit form ─────────────────────────────────────────────────

function StudentForm({ student, onSaved, onClose, onGenerate, openReview, showToast, prefs }) {
  const isNew = !student
  const [form, setForm]       = useState(() =>
    isNew
      ? { ...EMPTY,                                   // saved defaults from Settings
          school_name:         prefs?.default_school_name || '',
          grade:               prefs?.default_grade || '',
          disability_severity: prefs?.default_severity || 'moderate',
          dominant_language:   prefs?.default_language || '' }
      : Object.fromEntries(FIELDS.map(k => [k, student[k] ?? ''])))
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState(null)
  const [more, setMore]       = useState(!isNew && MORE_FIELDS.some(k => student[k]))
  const [ieps, setIeps]       = useState([])
  const [confirmDelete, setConfirmDelete] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    if (isNew) return
    listStudentIEPs(student.student_code)
      .then(({ data }) => setIeps(data?.ieps ?? []))
      .catch(() => { /* list is informational */ })
  }, [isNew, student])

  const missing = ['full_name', 'date_of_birth', 'grade', 'school_name', 'disability_category']
    .filter(k => !String(form[k]).trim())

  const save = async () => {
    if (missing.length) {
      setError(`Please fill in: ${missing.map(k => k.replace(/_/g, ' ')).join(', ')}.`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const { data } = isNew
        ? await createStudent(form)
        : await updateStudent(student.student_code, form)
      showToast(isNew ? `Registered ${data.full_name} — ID ${data.student_code}` : 'Student updated')
      onSaved(data, isNew)
    } catch (err) {
      setError(errorText(err, 'Could not save the student.'))
    } finally {
      setSaving(false)
    }
  }

  const setArchived = async (archived) => {
    setSaving(true)
    try {
      const { data } = await updateStudent(student.student_code, { is_archived: archived })
      showToast(archived ? 'Student archived' : 'Student restored')
      onSaved(data, false)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return }
    setSaving(true)
    try {
      await deleteStudent(student.student_code)
      showToast('Student deleted')
      onSaved(null, false)
    } catch (err) {
      setError(errorText(err))
      setConfirmDelete(false)
    } finally {
      setSaving(false)
    }
  }

  const copyCode = () => {
    navigator.clipboard?.writeText(student.student_code)
      .then(() => showToast('Student ID copied'))
      .catch(() => {})
  }

  const today = new Date().toISOString().slice(0, 10)

  // Rendered into <body> (a portal) so the panel sits above the sidebar —
  // the main content area has its own stacking layer it can't escape.
  return createPortal(
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000,
      display: 'flex', justifyContent: 'flex-end',
    }}>
      <div className="card student-drawer" onClick={e => e.stopPropagation()} style={{
        width: '100%', maxWidth: 560, height: '100%', borderRadius: 0, overflowY: 'auto',
        // Solid, so the page behind doesn't show through the panel
        background: 'var(--bg-dark)', boxShadow: '-12px 0 40px rgba(0,0,0,0.5)',
      }}>
        <div className="card-header flex-between">
          <div>
            <h3>{isNew ? 'Add student' : student.full_name}</h3>
            {!isNew && (
              <button type="button" onClick={copyCode} title="Copy student ID" style={{
                background: 'none', border: 'none', padding: 0, marginTop: 6, cursor: 'pointer',
                color: 'var(--teal)', fontFamily: 'monospace', fontSize: 13,
                display: 'inline-flex', alignItems: 'center', gap: 6,
              }}>
                {student.student_code} <Copy size={13} />
              </button>
            )}
          </div>
          <button className="btn-icon" onClick={onClose} title="Close"
            style={{ border: 'none', boxShadow: 'none', padding: 8 }}>
            <X size={20} />
          </button>
        </div>

        <div className="modern-form" style={{ padding: 24 }}>
          {!isNew && student.is_archived && (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              This student is archived — hidden from your list until restored.
            </div>
          )}

          <div className="form-group">
            <label htmlFor="st-name">Full name *</label>
            <input id="st-name" type="text" value={form.full_name}
              placeholder="e.g. Arjun Sharma" onChange={e => set('full_name', e.target.value)} />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="st-dob">Date of birth *</label>
              <input id="st-dob" type="date" max={today} value={form.date_of_birth}
                onChange={e => set('date_of_birth', e.target.value)} />
            </div>
            <div className="form-group">
              <label htmlFor="st-grade">Grade *</label>
              <input id="st-grade" type="text" value={form.grade}
                placeholder="e.g. Grade 4" onChange={e => set('grade', e.target.value)} />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="st-school">School *</label>
            <input id="st-school" type="text" value={form.school_name}
              placeholder="e.g. DPS Bengaluru" onChange={e => set('school_name', e.target.value)} />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="st-cat">Disability category *</label>
              <select id="st-cat" value={form.disability_category}
                onChange={e => set('disability_category', e.target.value)}>
                <option value="">Select category…</option>
                {DISABILITIES.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="st-sev">Severity</label>
              <select id="st-sev" value={form.disability_severity}
                onChange={e => set('disability_severity', e.target.value)}>
                <option value="mild">Mild</option>
                <option value="moderate">Moderate</option>
                <option value="severe">Severe</option>
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="st-guardian">Parent / guardian</label>
              <input id="st-guardian" type="text" value={form.guardian_name}
                onChange={e => set('guardian_name', e.target.value)} />
            </div>
            <div className="form-group">
              <label htmlFor="st-contact">Guardian contact</label>
              <input id="st-contact" type="text" value={form.guardian_contact}
                placeholder="Phone or email" onChange={e => set('guardian_contact', e.target.value)} />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="st-notes">Teacher notes</label>
            <textarea id="st-notes" rows="4" value={form.notes}
              placeholder="Strengths, challenges, observations… (used as the IEP's teacher notes)"
              onChange={e => set('notes', e.target.value)} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {form.notes.length} chars · an IEP needs at least 50
            </span>
          </div>

          <button type="button" className="btn btn-secondary" style={{ alignSelf: 'flex-start' }}
            onClick={() => setMore(m => !m)}>
            {more ? 'Hide' : 'Show'} more background
          </button>

          {more && (
            <>
              <div className="form-group">
                <label htmlFor="st-lang">Dominant language</label>
                <input id="st-lang" type="text" value={form.dominant_language}
                  placeholder="e.g. Kannada" onChange={e => set('dominant_language', e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="st-acad">Academic history</label>
                <textarea id="st-acad" rows="2" value={form.academic_history}
                  onChange={e => set('academic_history', e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="st-obs">Classroom observations</label>
                <textarea id="st-obs" rows="2" value={form.teacher_observations}
                  onChange={e => set('teacher_observations', e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="st-parent">Parent concerns</label>
                <textarea id="st-parent" rows="2" value={form.parent_concerns}
                  onChange={e => set('parent_concerns', e.target.value)} />
              </div>
            </>
          )}

          <ErrorBox>{error}</ErrorBox>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? <SpinnerGap size={16} className="spin" /> : <FloppyDisk size={16} />}
              {isNew ? ' Register student' : ' Save changes'}
            </button>
            {!isNew && !student.is_archived && (
              <button className="btn btn-secondary" onClick={() => onGenerate(student)} disabled={saving}>
                <MagicWand size={16} /> Generate IEP
              </button>
            )}
          </div>

          {!isNew && (
            <>
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 16 }}>
                <h4 style={{ margin: '0 0 10px' }}>IEPs ({ieps.length})</h4>
                {ieps.length === 0 ? (
                  <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
                    No IEPs yet for this student.
                  </p>
                ) : ieps.map(i => (
                  <div key={i.iep_id} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.04)', fontSize: 13,
                  }}>
                    <span>
                      {fmtDate(i.created_at)} ·{' '}
                      <span className={`status-badge ${i.review_status === 'approved' ? 'status-active' : 'status-draft'}`}>
                        {REVIEW_LABEL[i.review_status] ?? i.review_status}
                      </span>
                    </span>
                    <button className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: 12 }}
                      onClick={() => openReview?.(i.iep_id)}>
                      <PencilSimple size={14} /> Review
                    </button>
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 16 }}>
                {student.is_archived ? (
                  <button className="btn btn-secondary" onClick={() => setArchived(false)} disabled={saving}>
                    <ArrowCounterClockwise size={16} /> Restore
                  </button>
                ) : (
                  <button className="btn btn-secondary" onClick={() => setArchived(true)} disabled={saving}>
                    <Archive size={16} /> Archive
                  </button>
                )}
                {ieps.length === 0 && (
                  <button className="btn btn-secondary" onClick={remove} disabled={saving}
                    style={{ color: '#ef4444', borderColor: 'rgba(239,68,68,0.4)' }}>
                    <Trash size={16} /> {confirmDelete ? 'Click again to delete' : 'Delete'}
                  </button>
                )}
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
                Students with IEPs can be archived but not deleted, so their records are kept.
              </p>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}

// ── The page ────────────────────────────────────────────────────────────

export default function StudentsPage({ showToast, onGenerate, openReview, active = true, prefs = null }) {
  const [students, setStudents]     = useState([])
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [query, setQuery]           = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing]       = useState(null)     // null | 'new' | student

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await listStudents(showArchived)
      setStudents(data ?? [])
    } catch (err) {
      if (err?.response?.status !== 401) setError(errorText(err, 'Could not load your students.'))
    } finally {
      setLoading(false)
    }
  }, [showArchived])

  // Reload whenever the page is opened (new IEPs change the counts)
  useEffect(() => { if (active) load() }, [active, load])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return students
    return students.filter(s =>
      [s.full_name, s.student_code, s.grade, s.disability_category, s.school_name]
        .some(v => String(v || '').toLowerCase().includes(q)))
  }, [students, query])

  const handleSaved = (saved, isNew) => {
    load()
    setEditing(isNew && saved ? saved : null)   // after registering, show their ID
  }

  const generateFor = (student) => {
    setEditing(null)
    onGenerate?.(student)
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Students</h2>
          <p>Your registered students. Each has a unique ID, and only you can see them.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing('new')}>
          <Plus size={16} /> Add Student
        </button>
      </header>

      {error && <div style={{ marginBottom: 16 }}><ErrorBox>{error}</ErrorBox></div>}

      <div className="card table-container">
        <div className="table-toolbar">
          <div className="search-box form-group">
            <MagnifyingGlass size={18} />
            <input type="text" placeholder="Search name, ID, grade…" value={query}
              onChange={e => setQuery(e.target.value)} />
          </div>
          <div className="filter-actions" style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={showArchived}
                onChange={e => setShowArchived(e.target.checked)} />
              Show archived
            </label>
            <button className="btn btn-secondary" onClick={load} disabled={loading}>
              {loading ? <SpinnerGap size={16} className="spin" /> : <ArrowClockwise size={16} />} Refresh
            </button>
          </div>
        </div>

        {loading && students.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center' }}><SpinnerGap size={28} className="spin" /></div>
        ) : students.length === 0 ? (
          <div className="placeholder-card" style={{ margin: 24 }}>
            <Users size={56} />
            <h3>No students yet</h3>
            <p>Add a student to give them an ID and keep their details for future IEPs.</p>
            <button className="btn btn-primary" onClick={() => setEditing('new')}>
              <Plus size={16} /> Add your first student
            </button>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="premium-table">
              <thead>
                <tr><th>Student</th><th>Age · Grade</th><th>Disability</th><th>IEPs</th><th>Updated</th><th></th></tr>
              </thead>
              <tbody>
                {shown.map(s => (
                  <tr key={s.student_code} onClick={() => setEditing(s)} style={{ cursor: 'pointer',
                    opacity: s.is_archived ? 0.55 : 1 }}>
                    <td>
                      <div className="user-cell">
                        <img src={avatar(s.full_name)} alt="" />
                        <div>
                          <span className="name">{s.full_name}{s.is_archived ? ' (archived)' : ''}</span>
                          <span className="id" style={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{s.student_code}</span>
                        </div>
                      </div>
                    </td>
                    <td>{s.age} yrs · {s.grade}</td>
                    <td>{s.disability_category} <span style={{ color: 'var(--text-muted)' }}>({s.disability_severity})</span></td>
                    <td>
                      {s.iep_count === 0 ? <span style={{ color: 'var(--text-muted)' }}>None</span> : (
                        <span className={`status-badge ${s.latest_iep?.review_status === 'approved' ? 'status-active' : 'status-draft'}`}>
                          {s.iep_count} · {REVIEW_LABEL[s.latest_iep?.review_status] ?? 'IEP'}
                        </span>
                      )}
                    </td>
                    <td>{fmtDate(s.updated_at)}</td>
                    <td className="action-cell" style={{ textAlign: 'right' }}>
                      {!s.is_archived && (
                        <button className="btn btn-secondary" style={{ padding: '8px 14px', fontSize: 13 }}
                          onClick={e => { e.stopPropagation(); generateFor(s) }}>
                          <MagicWand size={15} /> Generate IEP
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {shown.length === 0 && (
              <p style={{ padding: 24, color: 'var(--text-muted)', margin: 0 }}>No students match “{query}”.</p>
            )}
          </div>
        )}

        {students.length > 0 && (
          <div className="table-footer">
            <span>
              {shown.length === students.length
                ? `${students.length} student${students.length !== 1 ? 's' : ''}`
                : `Showing ${shown.length} of ${students.length}`}
            </span>
          </div>
        )}
      </div>

      {editing && (
        <StudentForm
          key={editing === 'new' ? 'new' : editing.student_code + editing.updated_at}
          student={editing === 'new' ? null : editing}
          onSaved={handleSaved}
          onClose={() => setEditing(null)}
          onGenerate={generateFor}
          openReview={(id) => { setEditing(null); openReview?.(id) }}
          showToast={showToast}
          prefs={prefs}
        />
      )}
    </>
  )
}
