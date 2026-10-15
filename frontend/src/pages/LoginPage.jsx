import { useEffect, useState } from 'react'
import { Brain, SignIn, SpinnerGap, WarningCircle } from '@phosphor-icons/react'
import { login, getDemoInfo, API_BASE_URL } from '../api/samarth'

/**
 * Login screen. There is no sign-up link on purpose: accounts are created
 * by an administrator, because IEPs contain children's disability records.
 */
export default function LoginPage({ onLogin, notice }) {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy]         = useState(false)
  const [error, setError]       = useState(null)
  const [demo, setDemo]         = useState(null)   // set only on the online demo

  useEffect(() => {
    getDemoInfo()
      .then(({ data }) => { if (data?.enabled) setDemo(data) })
      .catch(() => { /* not the demo, or server unreachable — login still works */ })
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError('Enter your email and password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const user = await login(email.trim(), password)
      onLogin(user)
    } catch (err) {
      setError(
        err?.response?.status === 401
          ? 'Incorrect email or password.'
          : (err?.response?.data?.detail ?? `Could not reach the server at ${API_BASE_URL}.`)
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', width: '100%',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }}>
      <div className="card" style={{ width: '100%', maxWidth: 420, padding: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <div className="logo-icon"><Brain size={22} weight="fill" /></div>
          <div className="logo-text">
            <h1 style={{ margin: 0 }}>SAMARTH</h1>
            <span>IEP Generator</span>
          </div>
        </div>

        <h2 style={{ margin: '0 0 6px' }}>Sign in</h2>
        <p style={{ marginTop: 0, color: 'var(--text-muted)', fontSize: 14 }}>
          Use the account your administrator created for you.
        </p>

        {demo && (
          <div style={{
            background: 'rgba(20,184,166,0.08)', border: '1px solid rgba(20,184,166,0.35)',
            borderRadius: 10, padding: '12px 14px', fontSize: 13, marginBottom: 12,
          }}>
            <strong>Online demo.</strong> Sign in with the shared demo account:
            <div style={{ fontFamily: 'monospace', margin: '6px 0' }}>
              {demo.login.email} / {demo.login.password}
            </div>
            <button type="button" className="btn btn-secondary"
              style={{ padding: '6px 12px', fontSize: 13 }}
              onClick={() => { setEmail(demo.login.email); setPassword(demo.login.password) }}>
              Use demo account
            </button>
            <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: 12 }}>
              All students in the demo are synthetic. Records reset when the server restarts.
            </div>
          </div>
        )}

        {notice && (
          <div style={{
            background: 'rgba(234,179,8,0.1)', border: '1px solid rgba(234,179,8,0.3)',
            borderRadius: 10, padding: '10px 14px', fontSize: 13, color: '#eab308', marginBottom: 12,
          }}>
            {notice}
          </div>
        )}

        <form className="modern-form" onSubmit={submit} noValidate>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="username" autoFocus
              placeholder="you@school.in" value={email}
              onChange={e => setEmail(e.target.value)} />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="current-password"
              value={password} onChange={e => setPassword(e.target.value)} />
          </div>

          {error && (
            <div role="alert" style={{
              background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 10, padding: '10px 14px', fontSize: 13, color: '#ef4444',
            }}>
              <WarningCircle size={15} style={{ verticalAlign: -3, marginRight: 6 }} />
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={busy}
            style={{ width: '100%', justifyContent: 'center' }}>
            {busy
              ? <><SpinnerGap size={16} className="spin" /> Signing in…</>
              : <><SignIn size={16} /> Sign in</>}
          </button>
        </form>

        <p style={{ marginTop: 20, marginBottom: 0, fontSize: 12, color: 'var(--text-muted)' }}>
          No account? Ask your school's SAMARTH administrator.
        </p>
      </div>
    </div>
  )
}