import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import Toast from './components/Toast'
import GeneratePage from './pages/GeneratePage'
import MyIEPsPage from './pages/MyIEPsPage'
import StudentsPage from './pages/StudentsPage'
import AnalyticsPage from './pages/AnalyticsPage'
import SettingsPage from './pages/SettingsPage'
import ProfilePage from './pages/ProfilePage'

export default function App() {
  const [view, setView] = useState('generate')
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')
  const [collapsed, setCollapsed] = useState(false)
  const [toast, setToast] = useState(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type, id: Date.now() })
    setTimeout(() => setToast(null), 3500)
  }

  const pages = {
    generate:  <GeneratePage showToast={showToast} />,
    'my-ieps': <MyIEPsPage showToast={showToast} />,
    students:  <StudentsPage />,
    analytics: <AnalyticsPage />,
    settings:  <SettingsPage />,
    profile:   <ProfilePage />,
  }

  return (
    <div className="app-container">
      <Sidebar
        view={view} setView={setView}
        collapsed={collapsed} setCollapsed={setCollapsed}
        theme={theme} toggleTheme={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
      />
      <main className="main-content">
        {Object.entries(pages).map(([key, page]) => (
          <div key={key} className={`view-section ${view === key ? 'active' : ''}`}
            style={{ display: view === key ? 'flex' : 'none' }}>
            {page}
          </div>
        ))}
      </main>
      {toast && <Toast key={toast.id} msg={toast.msg} type={toast.type} />}
    </div>
  )
}