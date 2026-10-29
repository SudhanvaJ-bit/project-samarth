import { useState, useEffect } from 'react'
import { FloppyDisk, SpinnerGap, Sun, Moon } from '@phosphor-icons/react'
import { getPreferences, savePreferences, getSystemInfo, errorText } from '../api/samarth'

/**
 * Settings
 *  - IEP defaults: saved per educator on the server; they pre-fill the
 *    Generate IEP and Add Student forms.
 *  - Appearance: light/dark theme (this browser).
 *  - Workspace: how this server is set up. Read-only on purpose — models,
 *    mode and limits are chosen by whoever runs the server, because they
 *    affect cost and every user.
 */

const ROLE_LABEL = {
  scraper:    'Profile analysis',
  compliance: 'Legal compliance (RAG)',
  drafting:   'IEP drafting',
  extraction: 'PDF report reading',
}

const MODE_LABEL = {
  live:   'Live — Gemini generates every IEP',
  replay: 'Replay — reuses recorded answers where available',
  demo:   'Demo — replays recorded sample students only',
}

function Row({ label, children }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '10px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.04)', fontSize: 14 }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ textAlign: 'right' }}>{children}</span>
    </div>
  )
}

export default function SettingsPage({ showToast, theme, toggleTheme, prefs, onPrefsSaved }) {
  const [form, setForm]     = useState(() => ({
    default_school_name: '', default_grade: '', default_severity: 'moderate', default_language: '',
    ...(prefs || {}),
  }))
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)
  const [system, setSystem] = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    // Fresh copy from the server in case they were changed in another browser
    getPreferences().then(({ data }) => setForm(f => ({ ...f, ...data }))).catch(() => {})
    getSystemInfo().then(({ data }) => setSystem(data)).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const { data } = await savePreferences(form)
      setForm(data)
      onPrefsSaved?.(data)
      showToast?.('Settings saved')
    } catch (err) {
      setError(errorText(err, 'Could not save settings.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h2>Settings</h2><p>Your defaults and how this SAMARTH workspace is set up.</p></div>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? <SpinnerGap size={16} className="spin" /> : <FloppyDisk size={16} />} Save changes
        </button>
      </header>

      <div className="settings-grid">
        <div className="card">
          <div className="card-header"><h3>IEP defaults</h3></div>
          <div className="modern-form">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
              Pre-filled on Generate IEP and Add Student, so you don't retype them each time.
            </p>
            <div className="form-group">
              <label htmlFor="pref-school">School / agency</label>
              <input id="pref-school" type="text" value={form.default_school_name}
                placeholder="e.g. Kendriya Vidyalaya, Mysuru"
                onChange={e => set('default_school_name', e.target.value)} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="pref-grade">Grade</label>
                <input id="pref-grade" type="text" value={form.default_grade}
                  placeholder="e.g. Grade 4" onChange={e => set('default_grade', e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="pref-sev">Severity</label>
                <select id="pref-sev" value={form.default_severity}
                  onChange={e => set('default_severity', e.target.value)}>
                  <option value="mild">Mild</option>
                  <option value="moderate">Moderate</option>
                  <option value="severe">Severe</option>
                </select>
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="pref-lang">Students' dominant language</label>
              <input id="pref-lang" type="text" value={form.default_language}
                placeholder="e.g. Kannada" onChange={e => set('default_language', e.target.value)} />
            </div>
            {error && <p role="alert" style={{ color: '#ef4444', fontSize: 13, margin: 0 }}>{error}</p>}
          </div>

          <div className="card-header" style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
            <h3>Appearance</h3>
          </div>
          <div className="modern-form">
            <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <label style={{ color: 'var(--text-main)', textTransform: 'none', letterSpacing: 0, fontSize: 14 }}>
                  Theme
                </label>
                <span style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                  Currently {theme === 'dark' ? 'dark' : 'light'}. Saved in this browser.
                </span>
              </div>
              <button type="button" className="btn btn-secondary" onClick={toggleTheme}>
                {theme === 'dark' ? <><Sun size={16} /> Light</> : <><Moon size={16} /> Dark</>}
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>Workspace</h3></div>
          <div className="modern-form">
            <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
              Set by whoever runs this server. Shown so you know what produces your drafts.
            </p>
            {!system ? <SpinnerGap size={20} className="spin" /> : (
              <div>
                <Row label="AI mode">{MODE_LABEL[system.llm_mode] ?? system.llm_mode}</Row>
                {Object.entries(system.models).map(([role, model]) => (
                  <Row key={role} label={ROLE_LABEL[role] ?? role}>
                    <code>{model}</code>
                    {system.fallback_models?.[role]?.length
                      ? <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                          {' '}+{system.fallback_models[role].length} fallback
                        </span>
                      : null}
                  </Row>
                ))}
                <Row label="When Gemini is busy">
                  Tries every model, up to {system.fallback_rounds} round{system.fallback_rounds !== 1 ? 's' : ''}
                </Row>
                <Row label="Daily limit">
                  {system.daily_limit
                    ? `${system.used_last_24h ?? 0} of ${system.daily_limit} IEPs used (last 24 h)`
                    : 'No limit'}
                </Row>
                <Row label="Legal sources">
                  {system.legal_corpus.documents.join(', ')}
                  {system.legal_corpus.chunks ? ` · ${system.legal_corpus.chunks} passages indexed` : ''}
                </Row>
                <Row label="Copies of prompts kept on server">
                  {system.saves_recordings ? 'Yes (for replay)' : 'No'}
                </Row>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
