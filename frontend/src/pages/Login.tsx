import { useState } from 'react'
import { useLogin } from '../hooks/useAuth'
import { apiErrorMessage } from '../utils/api'
import { useTheme } from '../styles/theme'
import { Input, Btn, ErrorAlert } from '../components/ui'

export default function Login() {
  const t = useTheme()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin1234')
  const login = useLogin()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    login.mutate({ username, password })
  }

  return (
    <div style={{ minHeight: '100vh', background: t.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 32 }}>
      {/* Logo mark */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 52, height: 52, borderRadius: 14, background: t.accentDim, border: `1px solid ${t.accent}44`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth={2} strokeLinecap="round">
            <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/>
            <line x1="3" y1="6" x2="21" y2="6"/>
            <path d="M16 10a4 4 0 01-8 0"/>
          </svg>
        </div>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, color: t.text, textAlign: 'center', letterSpacing: '-0.02em' }}>ThriftOS</div>
          <div style={{ fontSize: 13, color: t.textMuted, textAlign: 'center', marginTop: 2 }}>Thrift Store Management System</div>
        </div>
      </div>

      <div style={{ width: '100%', maxWidth: 360, background: t.surface, border: `1px solid ${t.border}`, borderRadius: 16, padding: 28, boxShadow: t.shadowLg }}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input label="Username" value={username} onChange={setUsername} placeholder="admin" />
          <Input label="Password" value={password} onChange={setPassword} placeholder="password" type="password" />

          {login.isError && <ErrorAlert message={apiErrorMessage(login.error)} />}

          <Btn variant="primary" full size="lg" disabled={login.isPending} type="submit">
            {login.isPending ? 'Signing in…' : 'Sign In'}
          </Btn>
        </form>
      </div>
    </div>
  )
}
