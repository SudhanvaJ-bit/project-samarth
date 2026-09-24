import {
  Brain, FilePlus, Files, Users, ChartLineUp, Gear, Sun, Moon, List,
  PencilSimple, SignOut,
} from '@phosphor-icons/react'

const NAV = [
  { id: 'generate',  label: 'Generate IEP', Icon: FilePlus },
  { id: 'my-ieps',   label: 'My IEPs',       Icon: Files },
  // Human Review — opens the section editor for the selected IEP.
  // With nothing selected, App.jsx shows a "No IEP selected" placeholder.
  { id: 'review',    label: 'Review',        Icon: PencilSimple },
  { id: 'students',  label: 'Students',       Icon: Users },
  { id: 'analytics', label: 'Analytics',      Icon: ChartLineUp },
  { id: 'settings',  label: 'Settings',       Icon: Gear },
]

const initials = (name = '') =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?'

export default function Sidebar({ view, setView, collapsed, setCollapsed, theme, toggleTheme, user, onLogout }) {
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
          title={user?.email}
          style={{ padding: 0, border: 'none', background: 'none', boxShadow: 'none', minWidth: 0 }}>
          <div className="profile-avatar">
            <img
              src={`https://ui-avatars.com/api/?name=${encodeURIComponent(initials(user?.full_name))}&background=f8f8f9&color=050508`}
              alt={user?.full_name || 'User'} />
          </div>
          {!collapsed && (
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.full_name || 'Signed in'}
            </span>
          )}
        </button>
        <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
          <button className="btn-icon" onClick={toggleTheme} title="Toggle theme"
            style={{ borderRadius: '50%', padding: 8, border: 'none' }}>
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button className="btn-icon" onClick={onLogout} title="Sign out"
            style={{ borderRadius: '50%', padding: 8, border: 'none' }}>
            <SignOut size={18} />
          </button>
        </div>
      </div>
    </aside>
  )
}