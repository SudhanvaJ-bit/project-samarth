import { useState, useEffect } from 'react'
import { ShieldCheck, SignOut, SpinnerGap } from '@phosphor-icons/react'
import Sidebar from './components/Sidebar'
import Toast from './components/Toast'
import LoginPage from './pages/LoginPage'
import GeneratePage from './pages/GeneratePage'
import MyIEPsPage from './pages/MyIEPsPage'
import StudentsPage from './pages/StudentsPage'
import AnalyticsPage from './pages/AnalyticsPage'
import SettingsPage from './pages/SettingsPage'
import ProfilePage from './pages/ProfilePage'
import ReviewPage from './pages/ReviewPage'
import {
  getToken, getStoredUser, fetchMe, clearSession, setUnauthorizedHandler,
} from './api/samarth'

export default function App() {
  const [theme, setTheme]         = useState(() => localStorage.getItem('theme') || 'dark')
  const [collapsed, setCollapsed] = useState(false)
  const [toast, setToast]         = useState(null)

  // ── Auth state ──────────────────────────────────────
  // authChecked stays false until we've confirmed the stored token is still
  // valid, so the app never flashes pages the user may not be allowed to see.
  const [user, setUser]               = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [loginNotice, setLoginNotice] = useState(null)

  const [view, setView]               = useState('generate')
  const [reviewIepId, setReviewIepId] = useState(null)
  // "Generate IEP" on the Students page: which student, and a fresh key so
  // the Generate page restarts with that student's details filled in
  const [generateFor, setGenerateFor] = useState({ student: null, key: 0 })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type, id: Date.now() })
    setTimeout(() => setToast(null), 3500)
  }

  const resetNavigation = () => {
    setView('generate')
    setReviewIepId(null)
    setGenerateFor(g => ({ student: null, key: g.key + 1 }))
  }

  const generateForStudent = (student) => {
    setGenerateFor(g => ({ student, key: g.key + 1 }))
    setView('generate')
  }

  // Any 401 from the API (expired or deactivated account) lands here
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      resetNavigation()
      setLoginNotice('Your session has ended. Please sign in again.')
    })
  }, [])

  // On load: verify the stored token with the server rather than trusting it
  useEffect(() => {
    if (!getToken()) { setAuthChecked(true); return }
    const cached = getStoredUser()
    fetchMe()
      .then(res => setUser(res.data))
      .catch(() => { clearSession(); if (cached) setLoginNotice('Please sign in again.') })
      .finally(() => setAuthChecked(true))
  }, [])

  const handleLogin = (u) => {
    setLoginNotice(null)
    resetNavigation()
    setUser(u)
    showToast(`Welcome, ${u.full_name}`)
  }

  const handleLogout = () => {
    clearSession()
    setUser(null)
    resetNavigation()
    setLoginNotice(null)
  }

  const openReview = (iepId) => {
    if (!iepId) { showToast('No IEP selected to review', 'error'); return }
    setReviewIepId(iepId)
    setView('review')
  }

  // ── Render: auth gates ──────────────────────────────
  if (!authChecked) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <SpinnerGap size={28} className="spin" />
      </div>
    )
  }

  if (!user) {
    return (
      <>
        <LoginPage onLogin={handleLogin} notice={loginNotice} />
        {toast && <Toast key={toast.id} msg={toast.msg} type={toast.type} />}
      </>
    )
  }

  // Admins manage accounts; they deliberately have no access to IEP records.
  if (user.role === 'admin') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        <div className="card" style={{ maxWidth: 520, padding: 32 }}>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 0 }}>
            <ShieldCheck size={24} /> Administrator account
          </h2>
          <p>
            Signed in as <strong>{user.full_name}</strong> ({user.email}).
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 14, lineHeight: 1.6 }}>
            Administrator accounts manage educator logins. They do not have access
            to students' IEPs — only the educator who created an IEP can open it.
            Manage accounts from the API docs at <code>/docs</code> or with
            <code> python -m app.cli</code>.
          </p>
          <button className="btn btn-secondary" onClick={handleLogout}>
            <SignOut size={16} /> Sign out
          </button>
        </div>
      </div>
    )
  }

  const pages = {
    generate:  <GeneratePage key={`generate-${generateFor.key}`} showToast={showToast}
                 openReview={openReview} initialStudent={generateFor.student}
                 active={view === 'generate'} />,
    'my-ieps': <MyIEPsPage   showToast={showToast} openReview={openReview} active={view === 'my-ieps'} />,
    students:  <StudentsPage showToast={showToast} openReview={openReview}
                 onGenerate={generateForStudent} active={view === 'students'} />,
    analytics: <AnalyticsPage />,
    settings:  <SettingsPage />,
    profile:   <ProfilePage />,
  }

  // key={user.id} remounts every page when a different person signs in, so
  // nothing from the previous user's session (form data, results, lists)
  // survives into the next one.
  return (
    <div className="app-container" key={user.id}>
      <Sidebar
        view={view} setView={setView}
        collapsed={collapsed} setCollapsed={setCollapsed}
        theme={theme} toggleTheme={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
        user={user} onLogout={handleLogout}
      />
      <main className="main-content">
        {Object.entries(pages).map(([key, page]) => (
          <div key={key} className={`view-section ${view === key ? 'active' : ''}`}
            style={{ display: view === key ? 'flex' : 'none' }}>
            {page}
          </div>
        ))}

        {view === 'review' && reviewIepId && (
          <div className="view-section active" style={{ display: 'flex' }}>
            <ReviewPage key={reviewIepId} iepId={reviewIepId} user={user}
              showToast={showToast} onBack={() => setView('my-ieps')} />
          </div>
        )}

        {view === 'review' && !reviewIepId && (
          <div className="view-section active" style={{ display: 'flex' }}>
            <div className="card" style={{ padding: 32 }}>
              <h3>No IEP selected</h3>
              <p style={{ color: 'var(--text-muted)', marginTop: 8 }}>
                Generate an IEP, or open one from My IEPs, then choose
                “Review &amp; Edit” to open it here.
              </p>
              <button className="btn btn-secondary" style={{ marginTop: 16 }}
                onClick={() => setView('my-ieps')}>
                Go to My IEPs
              </button>
            </div>
          </div>
        )}
      </main>
      {toast && <Toast key={toast.id} msg={toast.msg} type={toast.type} />}
    </div>
  )
}