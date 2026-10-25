import { useState, useEffect, useCallback } from 'react'
import {
  Files, DownloadSimple, PencilSimple, ArrowClockwise, SpinnerGap,
} from '@phosphor-icons/react'
import { downloadIEP, listDrafts } from '../api/samarth'

/**
 * My IEPs — the signed-in educator's IEPs, loaded from the server.
 *
 * This used to read a history list from the browser's localStorage. That
 * list was shared by everyone using the same browser, so after login it
 * would have shown one teacher another teacher's students. The server now
 * decides what each account may see.
 */

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

const STATUS_LABEL = { pending: 'Awaiting review', edited: 'In review', approved: 'Approved' }

function statusClass(status) {
  if (status === 'approved') return 'status-badge status-active'
  return 'status-badge status-pending'
}

export default function MyIEPsPage({ showToast, openReview, active = true }) {
  const [drafts, setDrafts]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await listDrafts(200)
      setDrafts(data?.drafts ?? [])
    } catch (err) {
      if (err?.response?.status !== 401) {
        setError(err?.response?.data?.detail ?? 'Could not load your IEPs. Is the backend running?')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  // Reload every time the page is opened, so a newly generated IEP appears
  useEffect(() => { if (active) load() }, [active, load])

  const handleDownload = async (iepId, name) => {
    try {
      const res = await downloadIEP(iepId)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a   = document.createElement('a')
      a.href     = url
      a.download = `IEP_${name}_${iepId.slice(0, 8)}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
      showToast('PDF downloaded')
    } catch {
      showToast('Download failed — is the backend running?', 'error')
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h2>My IEPs</h2>
          <p>IEPs you have generated. Only you can see these.</p>
        </div>
        <button className="btn btn-secondary" onClick={load} disabled={loading}>
          {loading ? <SpinnerGap size={16} className="spin" /> : <ArrowClockwise size={16} />} Refresh
        </button>
      </header>

      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#ef4444', marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {loading && drafts.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <SpinnerGap size={28} className="spin" />
        </div>
      ) : drafts.length === 0 ? (
        <div className="placeholder-card">
          <Files size={56} style={{
            background: 'linear-gradient(135deg,#fff,#888)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }} />
          <h3>No IEPs yet</h3>
          <p>Generate your first IEP to see it listed here.</p>
        </div>
      ) : (
        <div className="card table-container">
          <table className="premium-table">
            <thead>
              <tr>
                <th>Student</th><th>Disability</th><th>Review</th><th>Last updated</th><th></th>
              </tr>
            </thead>
            <tbody>
              {drafts.map(item => (
                <tr key={item.iep_id}>
                  <td>
                    <div className="user-cell">
                      <img
                        src={`https://ui-avatars.com/api/?name=${encodeURIComponent(item.student_name)}&background=1c1c24&color=f8f8f9`}
                        alt={item.student_name} />
                      <div>
                        <span className="name">{item.student_name}</span>
                        <span className="id" style={item.student_code ? { fontFamily: 'monospace' } : undefined}>
                          {item.student_code || `${item.iep_id.slice(0, 12)}…`}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td>{item.disability_category || '—'}</td>
                  <td>
                    <span className={statusClass(item.review_status)}>
                      {STATUS_LABEL[item.review_status] ?? item.review_status}
                      {item.revision ? ` · r${item.revision}` : ''}
                    </span>
                  </td>
                  <td>{fmtDate(item.updated_at || item.created_at)}</td>
                  <td className="action-cell" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                    <button className="btn btn-secondary" style={{ padding: '8px 14px', fontSize: 13 }}
                      onClick={() => openReview?.(item.iep_id)}>
                      <PencilSimple size={15} /> Review
                    </button>
                    <button className="btn btn-secondary" style={{ padding: '8px 14px', fontSize: 13 }}
                      onClick={() => handleDownload(item.iep_id, item.student_name)}>
                      <DownloadSimple size={15} /> PDF
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="table-footer">
            <span>
              {drafts.length} IEP{drafts.length !== 1 ? 's' : ''} ·{' '}
              {drafts.filter(d => d.review_status === 'approved').length} approved
            </span>
          </div>
        </div>
      )}
    </>
  )
}