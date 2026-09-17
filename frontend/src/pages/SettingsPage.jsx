export default function SettingsPage() {
  return (
    <>
      <header className="page-header">
        <div><h2>Settings</h2><p>Manage your SAMARTH workspace preferences.</p></div>
        <button className="btn btn-primary">Save Changes</button>
      </header>
      <div className="settings-grid">
        <div className="card">
          <div className="card-header"><h3>General Preferences</h3></div>
          <div className="modern-form">
            <div className="form-group">
              <label>Default Grade Level</label>
              <select defaultValue="middle"><option value="elementary">Elementary (K–5)</option><option value="middle">Middle School (6–8)</option><option value="high">High School (9–12)</option></select>
            </div>
            <div className="form-group">
              <label>Legal Framework</label>
              <select defaultValue="rpwd"><option value="rpwd">RPwD Act 2016</option><option value="ncte">NCTE / NCERT Guidelines</option></select>
            </div>
            <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <label style={{ color: 'var(--text-main)', textTransform: 'none', letterSpacing: 0, fontSize: 14 }}>Auto-Save IEP Drafts</label>
                <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Automatically save progress while generating.</span>
              </div>
              <label className="toggle-switch"><input type="checkbox" defaultChecked /><span className="slider" /></label>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h3>AI Configuration</h3></div>
          <div className="modern-form">
            <div className="form-group">
              <label>Tone & Formatting</label>
              <select><option>Professional & Academic</option><option>Empathetic & Supportive</option><option>Direct & Action-Oriented</option></select>
            </div>
            <div className="form-group">
              <label>LLM Model</label>
              <select defaultValue="flash"><option value="flash">gemini-2.5-flash (default)</option></select>
            </div>
            <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <label style={{ color: 'var(--text-main)', textTransform: 'none', letterSpacing: 0, fontSize: 14 }}>Parent-Friendly Summaries</label>
                <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Generate a simplified summary for parents.</span>
              </div>
              <label className="toggle-switch"><input type="checkbox" defaultChecked /><span className="slider" /></label>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}