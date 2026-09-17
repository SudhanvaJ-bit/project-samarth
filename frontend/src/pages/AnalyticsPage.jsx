import { FileText, TrendUp, ClockCountdown } from '@phosphor-icons/react'

function readHistory() {
  try {
    return JSON.parse(localStorage.getItem('samarth_iep_history') || '[]')
  } catch {
    return []
  }
}

const CATEGORY_COLORS = [
  'var(--sage-green)',
  'var(--teal)',
  'var(--lavender)',
  '#f59e0b',
  '#6b7280',
]

export default function AnalyticsPage() {
  const history = readHistory()
  const now     = new Date()

  // ── This-month count ─────────────────────────────────────────
  const thisMonthCount = history.filter(item => {
    const d = new Date(item.created_at || item.date)
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
  }).length

  // ── Last 6 months bar chart ───────────────────────────────────
  const monthLabels  = []
  const monthlyCounts = []

  for (let i = 5; i >= 0; i--) {
    const d     = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const label = d.toLocaleString('en-US', { month: 'short' })
    const count = history.filter(item => {
      const id = new Date(item.created_at || item.date)
      return id.getMonth() === d.getMonth() && id.getFullYear() === d.getFullYear()
    }).length
    monthLabels.push(label)
    monthlyCounts.push(count)
  }

  const maxCount = Math.max(...monthlyCounts, 1)

  const bars = monthLabels.map((label, i) => ({
    label,
    count: monthlyCounts[i],
    // Min height of 5% so empty bars are visible; proportional otherwise
    h:      monthlyCounts[i] > 0 ? Math.max((monthlyCounts[i] / maxCount) * 100, 15) : 5,
    active: i === monthLabels.length - 1,
  }))

  // ── Disability category breakdown ────────────────────────────
  const categoryCounts = history.reduce((acc, item) => {
    const cat = item.disability_category?.trim() || 'Other'
    acc[cat] = (acc[cat] || 0) + 1
    return acc
  }, {})

  const breakdown = Object.entries(categoryCounts)
    .sort((a, b) => b[1] - a[1])   // most common first
    .map(([label, count], i) => ({
      label,
      count,
      pct:   history.length ? Math.round((count / history.length) * 100) : 0,
      color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
    }))

  // ── Grade distribution ────────────────────────────────────────
  // Note: grade is only present for IEPs generated after the history-save fix.
  // Old entries without grade are excluded from this chart.
  const gradeCounts = history.reduce((acc, item) => {
    const grade = item.grade?.trim()
    if (!grade) return acc          // skip entries without grade data
    acc[grade] = (acc[grade] || 0) + 1
    return acc
  }, {})

  const grades = Object.entries(gradeCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([label, val], i) => ({
      label,
      val,
      pct:   history.length ? Math.round((val / history.length) * 100) : 0,
      color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
    }))

  // ── Recent activity feed ─────────────────────────────────────
  const activity = history.slice(0, 5).map(item => ({
    dot:  'var(--sage-green)',
    msg:  <>IEP generated for <strong>{item.student_name || 'Unknown Student'}</strong></>,
    time: item.created_at
      ? new Date(item.created_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
      : 'Recently',
  }))

  // ── Shared empty-state style ─────────────────────────────────
  const emptyMsg = (
    <p style={{ color: 'var(--text-muted)', fontSize: 14, padding: '16px 0' }}>
      No data available yet. Generate your first IEP to see analytics.
    </p>
  )

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Platform Analytics</h2>
          <p>Insights into IEP generation, student demographics, and usage.</p>
        </div>
      </header>

      {/* ── Stats row ── */}
      <section className="stats-row">
        <div className="stat-card">
          <div className="stat-icon"><FileText size={28} /></div>
          <div className="stat-info">
            <h3>Total IEPs Generated</h3>
            <div className="stat-value">{history.length}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon teal"><TrendUp size={28} /></div>
          <div className="stat-info">
            <h3>This Month</h3>
            <div className="stat-value">+{thisMonthCount}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon lavender"><ClockCountdown size={28} /></div>
          <div className="stat-info">
            <h3>Avg. Generation Time</h3>
            <div className="stat-value">~90s</div>
          </div>
        </div>
      </section>

      {/* ── Charts row ── */}
      <section className="analytics-grid">

        {/* Bar chart — last 6 months */}
        <div className="card">
          <div className="card-header flex-between">
            <h3>IEPs Generated — Last 6 Months</h3>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {monthLabels[0]} – {monthLabels[monthLabels.length - 1]}
            </span>
          </div>
          <div className="bar-chart-wrap">
            <div className="bar-chart">
              {bars.map(b => (
                <div key={b.label} className="bar-group">
                  <div className="bar-col">
                    <div className="bar-fill"
                      title={`${b.count} IEP${b.count !== 1 ? 's' : ''}`}
                      style={{
                        height: `${b.h}%`,
                        background: b.active
                          ? 'linear-gradient(to top,var(--lavender),var(--teal))'
                          : 'linear-gradient(to top,var(--teal),var(--sage-green))',
                      }} />
                  </div>
                  <span className="bar-label"
                    style={b.active ? { color: 'var(--teal)', fontWeight: 700 } : {}}>
                    {b.label}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{b.count}</span>
                </div>
              ))}
            </div>
            <div className="bar-chart-y">
              <span>{maxCount}</span>
              <span>{Math.ceil(maxCount * 0.75)}</span>
              <span>{Math.ceil(maxCount * 0.5)}</span>
              <span>{Math.ceil(maxCount * 0.25)}</span>
              <span>0</span>
            </div>
          </div>
        </div>

        {/* Disability breakdown */}
        <div className="card">
          <div className="card-header"><h3>Disability Category Breakdown</h3></div>
          <div className="breakdown-list">
            {breakdown.length ? breakdown.map(b => (
              <div key={b.label} className="breakdown-item">
                <div className="breakdown-label">
                  <span className="breakdown-dot" style={{ background: b.color }} />
                  <span>{b.label}</span>
                </div>
                <div className="breakdown-bar-wrap">
                  <div className="breakdown-bar">
                    <div className="breakdown-fill"
                      style={{ width: `${b.pct}%`, background: b.color }} />
                  </div>
                  <span className="breakdown-pct">{b.pct}%</span>
                </div>
              </div>
            )) : emptyMsg}
          </div>
        </div>
      </section>

      {/* ── Bottom row ── */}
      <section className="analytics-bottom-grid">

        {/* Grade distribution */}
        <div className="card">
          <div className="card-header"><h3>IEPs by Grade Level</h3></div>
          <div className="grade-grid">
            {grades.length ? grades.map(g => (
              <div key={g.label} className="grade-tile">
                <span className="grade-name">{g.label}</span>
                <div className="grade-value" style={{ color: g.color }}>{g.val}</div>
                <div className="grade-bar">
                  <div style={{ width: `${g.pct}%`, background: g.color }} />
                </div>
              </div>
            )) : (
              <p style={{ color: 'var(--text-muted)', fontSize: 14, padding: '16px 32px' }}>
                No grade data yet — grade is saved from the next IEP you generate.
              </p>
            )}
          </div>
        </div>

        {/* Recent activity */}
        <div className="card">
          <div className="card-header"><h3>Recent Activity</h3></div>
          <div className="activity-feed">
            {activity.length ? activity.map((a, i) => (
              <div key={i} className="activity-item">
                <div className="activity-dot" style={{ background: a.dot }} />
                <div className="activity-content">
                  <p>{a.msg}</p>
                  <span>{a.time}</span>
                </div>
              </div>
            )) : emptyMsg}
          </div>
        </div>
      </section>
    </>
  )
}