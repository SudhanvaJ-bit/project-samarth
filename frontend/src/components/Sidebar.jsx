import {
  Brain, FilePlus, Files, Users, ChartLineUp, Gear, Sun, Moon, List
} from '@phosphor-icons/react'

const NAV = [
  { id: 'generate',  label: 'Generate IEP', Icon: FilePlus },
  { id: 'my-ieps',   label: 'My IEPs',       Icon: Files },
  { id: 'students',  label: 'Students',       Icon: Users },
  { id: 'analytics', label: 'Analytics',      Icon: ChartLineUp },
  { id: 'settings',  label: 'Settings',       Icon: Gear },
]

export default function Sidebar({ view, setView, collapsed, setCollapsed, theme, toggleTheme }) {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="logo-container">
          <div className="logo-icon"><Brain size={22} weight="fill" /></div>
          {!collapsed && (
            <div className="logo-text">
              <h1>SAMARTH</h1>
              <span>IEP Generator</span>
            </div>
          )}
        </div>
        <button className="btn-icon" onClick={() => setCollapsed(c => !c)}
          style={{ border: 'none', boxShadow: 'none', padding: 8 }}>
          <List size={20} />
        </button>
      </div>

      <nav className="sidebar-menu">
        {NAV.map(({ id, label, Icon }) => (
          <button key={id}
            className={`menu-item ${view === id ? 'active' : ''}`}
            onClick={() => setView(id)}>
            <Icon size={20} weight={view === id ? 'fill' : 'regular'} />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button className="menu-item profile-item"
          onClick={() => setView('profile')}
          style={{ padding: 0, border: 'none', background: 'none', boxShadow: 'none' }}>
          <div className="profile-avatar">
            <img src="https://ui-avatars.com/api/?name=Dr.+Smith&background=f8f8f9&color=050508" alt="Dr. Smith" />
          </div>
          {!collapsed && <span>Dr. Smith</span>}
        </button>
        <button className="btn-icon" onClick={toggleTheme}
          style={{ borderRadius: '50%', padding: 8, border: 'none', flexShrink: 0 }}>
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
    </aside>
  )
}