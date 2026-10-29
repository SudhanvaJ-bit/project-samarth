import { useState, useEffect } from 'react'
import { FloppyDisk, Key, SpinnerGap } from '@phosphor-icons/react'
import { updateMe, changePassword, getAnalytics, errorText } from '../api/samarth'

/**
 * Profile — the signed-in account: real name, email, role and counts, with
 * a name you can change and a working password change.
 * The email is the login and is managed by an administrator.
 */

const initials = (name = '') =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?'

const ROLE_LABEL = { educator: 'Educator', admin: 'Administrator' }

function Message({ kind, children }) {
  if (!children) return null
  const ok = kind === 'ok'
  return (
    <p role={ok ? 'status' : 'alert'}
      style={{ fontSize: 13, margin: 0, color: ok ? 'var(--sage-green)' : '#ef4444' }}>
      {children}
    </p>
  )
}

export default function ProfilePage({ user, onUserUpdated, showToast, active = true }) {
  const [name, setName]         = useState(user?.full_name ?? '')
  const [savingName, setSavingName] = useState(false)
  const [nameMsg, setNameMsg]   = useState(null)

  const [pw, setPw]             = useState({ current: '', next: '', confirm: '' })
  const [savingPw, setSavingPw] = useState(false)
  const [pwMsg, setPwMsg]       = useState(null)

  const [stats, setStats]       = useState(null)

  useEffect(() => {
    if (!active) return
    getAnalytics().then(({ data }) => setStats(data.totals)).catch(() => {})
  }, [active])

  const saveName = async () => {
    setSavingName(true)
    setNameMsg(null)
    try {
      const { data } = await updateMe(name)
      onUserUpdated?.(data)
      setName(data.full_name)
      setNameMsg({ kind: 'ok', text: 'Name updated. New reviews are signed with it.' })
    } catch (err) {
      setNameMsg({ kind: 'err', text: errorText(err, 'Could not update your name.') })
    } finally {
      setSavingName(false)
    }
  }

  const savePassword = async () => {
    setPwMsg(null)
    if (!pw.current || !pw.next) {
      setPwMsg({ kind: 'err', text: 'Enter your current and new password.' })
      return
    }
    if (pw.next !== pw.confirm) {
      setPwMsg({ kind: 'err', text: "The new passwords don't match." })
      return
    }
    setSavingPw(true)
    try {
      await changePassword(pw.current, pw.next)
      setPw({ current: '', next: '', confirm: '' })
      setPwMsg({ kind: 'ok', text: 'Password changed. Use it next time you sign in.' })
      showToast?.('Password changed')
    } catch (err) {
      setPwMsg({ kind: 'err', text: errorText(err, 'Could not change your password.') })
    } finally {
      setSavingPw(false)
    }
  }

  return (
    <>
      <header className="page-header">
        <div><h2>Profile</h2><p>Your account details and password.</p></div>
      </header>

      <div className="profile-layout">
        <div className="card">
          <div className="profile-header-main">
            <img className="profile-huge-avatar" alt=""
              src={`https://ui-avatars.com/api/?name=${encodeURIComponent(initials(user?.full_name))}&background=f8f8f9&color=050508&size=120`} />
            <h3>{user?.full_name}</h3>
            <p className="role-badge">{ROLE_LABEL[user?.role] ?? user?.role}</p>
            <p className="profile-email">{user?.email}</p>
          </div>
          <div className="profile-stats">
            <div className="p-stat"><h4>{stats ? stats.ieps : '—'}</h4><span>IEPs generated</span></div>
            <div className="p-stat"><h4>{stats ? stats.approved : '—'}</h4><span>Approved</span></div>
            <div className="p-stat"><h4>{stats ? stats.students : '—'}</h4><span>Students</span></div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>Personal information</h3></div>
          <div className="modern-form">
            <div className="form-group">
              <label htmlFor="pf-name">Full name</label>
              <input id="pf-name" type="text" value={name} onChange={e => setName(e.target.value)} />
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Shown as the reviewer on IEPs you edit or approve.
              </span>
            </div>
            <div className="form-group">
              <label htmlFor="pf-email">Email (sign-in)</label>
              <input id="pf-email" type="email" value={user?.email ?? ''} disabled />
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Your administrator manages sign-in emails.
              </span>
            </div>
            <Message kind={nameMsg?.kind}>{nameMsg?.text}</Message>
            <div className="form-actions">
              <button className="btn btn-primary" style={{ flex: '0 0 auto' }}
                onClick={saveName} disabled={savingName || name.trim() === user?.full_name}>
                {savingName ? <SpinnerGap size={16} className="spin" /> : <FloppyDisk size={16} />} Save name
              </button>
            </div>
          </div>

          <div className="card-header" style={{ borderTop: '1px solid rgba(255,255,255,0.04)', marginTop: 20 }}>
            <h3>Change password</h3>
          </div>
          <div className="modern-form">
            <div className="form-group">
              <label htmlFor="pf-current">Current password</label>
              <input id="pf-current" type="password" autoComplete="current-password" value={pw.current}
                onChange={e => setPw(p => ({ ...p, current: e.target.value }))} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="pf-new">New password</label>
                <input id="pf-new" type="password" autoComplete="new-password" value={pw.next}
                  onChange={e => setPw(p => ({ ...p, next: e.target.value }))} />
              </div>
              <div className="form-group">
                <label htmlFor="pf-confirm">Confirm new password</label>
                <input id="pf-confirm" type="password" autoComplete="new-password" value={pw.confirm}
                  onChange={e => setPw(p => ({ ...p, confirm: e.target.value }))} />
              </div>
            </div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>At least 8 characters.</span>
            <Message kind={pwMsg?.kind}>{pwMsg?.text}</Message>
            <div className="form-actions">
              <button className="btn btn-secondary" style={{ flex: '0 0 auto' }}
                onClick={savePassword} disabled={savingPw}>
                {savingPw ? <SpinnerGap size={16} className="spin" /> : <Key size={16} />} Change password
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
