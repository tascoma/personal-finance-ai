import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { loginUser } from '../api/auth'
import { ApiError } from '../api/client'
import SvgIcon from '../components/SvgIcon'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const { access_token } = await loginUser(email, password)
      login(access_token)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-form-side">
        <div className="login-form-wrap">
          <div className="row gap-3 mb-6">
            <span className="brand-mark">F</span>
            <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: '-0.015em' }}>Finance AI</span>
          </div>

          <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-0.025em', marginBottom: 8 }}>
            Sign in to your ledger
          </div>
          <div className="muted mb-6" style={{ fontSize: 13.5 }}>
            Your double-entry personal finance tracker.
          </div>

          <form onSubmit={handleSubmit} className="stack gap-3">
            <div>
              <label className="field-label" htmlFor="email">Email</label>
              <input
                id="email"
                className="inp"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{ width: '100%' }}
                required
                autoFocus
              />
            </div>
            <div>
              <label className="field-label" htmlFor="password">Password</label>
              <input
                id="password"
                className="inp"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ width: '100%' }}
                required
              />
            </div>
            {error && (
              <div className="banner banner--red">
                <SvgIcon name="alert" size={14} />
                <span>{error}</span>
              </div>
            )}
            <button className="btn btn-primary btn-lg mt-3" type="submit" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
              {!loading && <SvgIcon name="arrow" size={16} />}
            </button>
            <div className="muted text-center mt-3" style={{ fontSize: 12.5 }}>
              Single-operator deployment · Registration closed
            </div>
          </form>
        </div>
      </div>

      <div className="login-art-side">
        <div className="login-art-mark">
          <span className="brand-mark">F</span>
          <span>Finance AI</span>
        </div>
        <div>
          <div className="login-art-quote">
            Your double-entry ledger,<br />powered by AI extractors.
          </div>
          <div className="login-art-foot mt-6">
            Statements · paystubs · mortgage docs — parsed, classified, and reconciled.
          </div>
        </div>
        <div className="login-art-foot">Personal Finance AI</div>
      </div>
    </div>
  )
}
