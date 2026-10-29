import { useState, useEffect, useCallback } from 'react'
import {
  FileText, TrendUp, Users, CheckCircle, PencilSimple, Timer,
  ArrowClockwise, SpinnerGap,
} from '@phosphor-icons/react'
import { getAnalytics, errorText } from '../api/samarth'

/**
 * Analytics — figures computed by the server from the signed-in educator's
 * OWN IEPs and students (GET /analytics). Nothing here is sample data.
 */

const COLORS = ['var(--sage-green)', 'var(--teal)', 'var(--lavender)', '#f59e0b', '#6b7280']

function fmtWhen(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

function fmtSeconds(s) {
  if (s == null) return '—'
  return s < 90 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

function Stat({ icon, tone = '', title, value, note }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}>{icon}</div>
      <div className="stat-info">
        <h3>{title}</h3>
        <div className="stat-value">{value}</div>
        {note && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{note}</span>}
      </div>
    </div>
  )
}

const empty = (text) => (
  <p style={{ color: 'var(--text-muted)', fontSize: 14, padding: '16px 32px', margin: 0 }}>{text}</p>
)

export default function AnalyticsPage({ active = true, openReview }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await getAnalytics()
      setData(data)
    } catch (err) {
      if (err?.response?.status !== 401) setError(errorText(err, 'Could not load analytics.'))
    } finally {
      setLoading(false)
    }
  }, [])

  // Refresh each time the page is opened, so new IEPs show up
  useEffect(() => { if (active) load() }, [active, load])

  if (!data) {
    return (
      <>
        <header className="page-header">
          <div><h2>Analytics</h2><p>Your IEPs and students at a glance.</p></div>
        </header>
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          {error
            ? <p style={{ color: '#ef4444', margin: 0 }}>{error}</p>
            : <SpinnerGap size={28} className="spin" />}
        </div>
      </>
    )
  }

  const t        = data.totals
  const maxMonth = Math.max(...data.monthly.map(m => m.count), 1)
  const approvedPct = t.ieps ? Math.round((100 * t.approved) / t.ieps) : 0

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Analytics</h2>
          <p>Your IEPs and students at a glance. Only your own records are counted.</p>
        </div>
        <button className="btn btn-secondary" onClick={load} disabled={loading}>
          {loading ? <SpinnerGap size={16} className="spin" /> : <ArrowClockwise size={16} />} Refresh
        </button>
      </header>

      {error && <p style={{ color: '#ef4444', margin: 0 }}>{error}</p>}

      <section className="stats-row">
        <Stat icon={<FileText size={28} />} title="IEPs generated" value={t.ieps}
          note={`${t.this_month} this month`} />
        <Stat icon={<CheckCircle size={28} />} tone="teal" title="Approved" value={t.approved}
          note={t.ieps ? `${approvedPct}% of IEPs · ${t.awaiting_review + t.in_review} still in review` : 'None yet'} />
        <Stat icon={<Users size={28} />} tone="lavender" title="Students registered" value={t.students}
          note={`${t.linked_to_student} IEP${t.linked_to_student !== 1 ? 's' : ''} filed under a student`
            + (t.students_archived ? ` · ${t.students_archived} archived` : '')} />
      </section>

      <section className="stats-row">
        <Stat icon={<TrendUp size={28} />} title="Awaiting review" value={t.awaiting_review}
          note="Generated, not yet opened for review" />
        <Stat icon={<PencilSimple size={28} />} tone="teal" title="Edited by you"
          value={data.human_edit_rate == null ? '—' : `${data.human_edit_rate}%`}
          note="IEPs where you corrected the AI's draft" />
        <Stat icon={<Timer size={28} />} tone="lavender" title="Avg. generation time"
          value={fmtSeconds(data.avg_generation_seconds)}
          note={data.timed_ieps ? `Across ${data.timed_ieps} timed IEP${data.timed_ieps !== 1 ? 's' : ''}`
            : 'Recorded for IEPs generated from now on'} />
      </section>

      <section className="analytics-grid">
        <div className="card">
          <div className="card-header flex-between">
            <h3>IEPs generated — last 6 months</h3>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {data.monthly[0].label} – {data.monthly[data.monthly.length - 1].label}
            </span>
          </div>
          <div className="bar-chart-wrap">
            <div className="bar-chart">
              {data.monthly.map((m, i) => {
                const current = i === data.monthly.length - 1
                return (
                  <div key={m.month} className="bar-group">
                    <div className="bar-col">
                      <div className="bar-fill" title={`${m.count} IEP${m.count !== 1 ? 's' : ''}`}
                        style={{
                          height: m.count ? `${Math.max((m.count / maxMonth) * 100, 8)}%` : '0%',
                          background: current
                            ? 'linear-gradient(to top,var(--lavender),var(--teal))'
                            : 'linear-gradient(to top,var(--teal),var(--sage-green))',
                        }} />
                    </div>
                    <span className="bar-label" style={current ? { color: 'var(--teal)', fontWeight: 700 } : {}}>
                      {m.label}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{m.count}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>By disability category</h3></div>
          <div className="breakdown-list">
            {data.by_disability.length ? data.by_disability.map((b, i) => (
              <div key={b.label} className="breakdown-item">
                <div className="breakdown-label">
                  <span className="breakdown-dot" style={{ background: COLORS[i % COLORS.length] }} />
                  <span>{b.label} · {b.count}</span>
                </div>
                <div className="breakdown-bar-wrap">
                  <div className="breakdown-bar">
                    <div className="breakdown-fill" style={{ width: `${b.pct}%`, background: COLORS[i % COLORS.length] }} />
                  </div>
                  <span className="breakdown-pct">{b.pct}%</span>
                </div>
              </div>
            )) : <p style={{ color: 'var(--text-muted)', fontSize: 14, margin: 0 }}>No IEPs yet.</p>}
          </div>
        </div>
      </section>

      <section className="analytics-bottom-grid">
        <div className="card">
          <div className="card-header"><h3>By grade</h3></div>
          <div className="grade-grid">
            {data.by_grade.length ? data.by_grade.map((g, i) => (
              <div key={g.label} className="grade-tile">
                <span className="grade-name">{g.label}</span>
                <div className="grade-value" style={{ color: COLORS[i % COLORS.length] }}>{g.count}</div>
                <div className="grade-bar">
                  <div style={{ width: `${g.pct}%`, background: COLORS[i % COLORS.length] }} />
                </div>
              </div>
            )) : empty('No IEPs yet.')}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>Recent activity</h3></div>
          <div className="activity-feed">
            {data.recent.length ? data.recent.map((e, i) => (
              <div key={`${e.iep_id}-${e.type}-${i}`} className="activity-item"
                onClick={() => openReview?.(e.iep_id)} style={{ cursor: 'pointer' }}
                title="Open in Review">
                <div className="activity-dot"
                  style={{ background: e.type === 'approved' ? 'var(--teal)' : 'var(--sage-green)' }} />
                <div className="activity-content">
                  <p>
                    {e.type === 'approved' ? 'IEP approved for ' : 'IEP generated for '}
                    <strong>{e.student_name}</strong>
                  </p>
                  <span>{fmtWhen(e.at)}</span>
                </div>
              </div>
            )) : empty('Nothing yet. Generate your first IEP to see activity here.')}
          </div>
        </div>
      </section>
    </>
  )
}
