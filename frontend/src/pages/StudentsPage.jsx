import { Plus, MagnifyingGlass, Funnel, ArrowSquareOut, DotsThree } from '@phosphor-icons/react'

const STUDENTS = [
  { name: 'Alex Johnson',     id: '#84920', grade: '7th Grade',  cat: 'SLD',              status: 'status-draft',  statusLabel: 'Drafting',      date: 'Today, 09:41 AM' },
  { name: 'Mia Chen',         id: '#84921', grade: '4th Grade',  cat: 'Autism Spectrum',  status: 'status-active', statusLabel: 'Active',         date: 'Oct 12, 2025' },
  { name: 'Marcus Rodriguez', id: '#84922', grade: '10th Grade', cat: 'ADHD',             status: 'status-review', statusLabel: 'Needs Review',   date: 'Sep 05, 2025' },
  { name: 'Sarah Miller',     id: '#84923', grade: '2nd Grade',  cat: 'Speech Impairment',status: 'status-active', statusLabel: 'Active',         date: 'Aug 22, 2025' },
]

export default function StudentsPage() {
  return (
    <>
      <header className="page-header">
        <div><h2>Students Directory</h2><p>Manage student profiles and associated educational data.</p></div>
        <button className="btn btn-primary"><Plus size={16} /> Add Student</button>
      </header>
      <div className="card table-container">
        <div className="table-toolbar">
          <div className="search-box form-group">
            <MagnifyingGlass size={18} />
            <input type="text" placeholder="Search students…" />
          </div>
          <div className="filter-actions">
            <button className="btn btn-secondary"><Funnel size={16} /> Filter</button>
            <button className="btn btn-secondary"><ArrowSquareOut size={16} /> Export</button>
          </div>
        </div>
        <div className="table-wrapper">
          <table className="premium-table">
            <thead>
              <tr><th>Student Name</th><th>Grade</th><th>Disability Category</th><th>IEP Status</th><th>Last Updated</th><th></th></tr>
            </thead>
            <tbody>
              {STUDENTS.map(s => (
                <tr key={s.id}>
                  <td>
                    <div className="user-cell">
                      <img src={`https://ui-avatars.com/api/?name=${encodeURIComponent(s.name)}&background=1c1c24&color=f8f8f9`} alt={s.name} />
                      <div><span className="name">{s.name}</span><span className="id">ID: {s.id}</span></div>
                    </div>
                  </td>
                  <td>{s.grade}</td>
                  <td>{s.cat}</td>
                  <td><span className={`status-badge ${s.status}`}>{s.statusLabel}</span></td>
                  <td>{s.date}</td>
                  <td className="action-cell">
                    <button className="btn btn-icon" style={{ borderRadius: 8, padding: '6px 10px' }}>
                      <DotsThree size={18} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>Showing 1–4 of 342 students</span>
          <div className="pagination">
            <button className="btn btn-icon disabled" style={{ borderRadius: 8, padding: '6px 10px' }}>◂</button>
            <button className="btn btn-icon"           style={{ borderRadius: 8, padding: '6px 10px' }}>▸</button>
          </div>
        </div>
      </div>
    </>
  )
}