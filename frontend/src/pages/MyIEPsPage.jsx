import { Files, DownloadSimple, Trash } from '@phosphor-icons/react'
import { downloadIEP } from '../api/samarth'

export default function MyIEPsPage({ showToast }) {
  const raw = localStorage.getItem('samarth_iep_history')
  const history = raw ? JSON.parse(raw) : []

  const handleDownload = async (iep_id, name) => {
    try {
      const res = await downloadIEP(iep_id)
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url; a.download = `IEP_${name}_${iep_id.slice(0,8)}.pdf`; a.click()
      window.URL.revokeObjectURL(url)
      showToast('PDF downloaded')
    } catch { showToast('Download failed — is the backend running?', 'error') }
  }

  const clearHistory = () => {
    if (window.confirm('Clear all IEP history?')) {
      localStorage.removeItem('samarth_iep_history')
      window.location.reload()
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h2>My IEPs</h2><p>View and manage all your generated Individualized Education Programs.</p></div>
        {history.length > 0 && (
          <button className="btn btn-danger" onClick={clearHistory}><Trash size={16} /> Clear All</button>
        )}
      </header>
      {history.length === 0 ? (
        <div className="placeholder-card">
          <Files size={56} style={{ background: 'linear-gradient(135deg,#fff,#888)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }} />
          <h3>No recent IEPs found</h3>
          <p>Generate your first IEP to see it listed here.</p>
        </div>
      ) : (
        <div className="card table-container">
          <table className="premium-table">
            <thead>
              <tr>
                <th>Student</th><th>Disability</th><th>Status</th><th>Date</th><th></th>
              </tr>
            </thead>
            <tbody>
              {history.map(item => (
                <tr key={item.iep_id}>
                  <td>
                    <div className="user-cell">
                      <img src={`https://ui-avatars.com/api/?name=${encodeURIComponent(item.student_name)}&background=1c1c24&color=f8f8f9`} alt={item.student_name} />
                      <div>
                        <span className="name">{item.student_name}</span>
                        <span className="id">{item.iep_id.slice(0, 12)}…</span>
                      </div>
                    </div>
                  </td>
                  <td>{item.disability_category || '—'}</td>
                  <td><span className="status-badge status-active">{item.workflow_status || 'Completed'}</span></td>
                  <td>{item.date}</td>
                  <td className="action-cell">
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
            <span>Showing {history.length} IEP{history.length !== 1 ? 's' : ''}</span>
          </div>
        </div>
      )}
    </>
  )
}